from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evolution import EvolutionStore  # noqa: E402


class LiveSupervisor:
    def __init__(self):
        self.root = ROOT
        self.store = EvolutionStore(os.getenv("EVOLUTION_STATE_DIR", ROOT / "runtime/evolution"))
        self.child: subprocess.Popen[str] | None = None
        self.stop_requested = False
        self.last_lines: deque[str] = deque(maxlen=80)
        self.started_at = 0.0

    def _files(self) -> list[Path]:
        files = list(self.root.glob("*.py"))
        for directory, patterns in (
            (self.root / "ifuri_core", ("*.py",)),
            (self.root / "manifests", ("*.yaml", "*.yml")),
            (self.root / "static", ("*.html", "*.js", "*.css")),
        ):
            for pattern in patterns:
                files.extend(directory.rglob(pattern))
        return sorted(path for path in files if path.is_file())

    def _snapshot(self) -> dict[str, int]:
        snapshot: dict[str, int] = {}
        for path in self._files():
            try:
                snapshot[str(path.relative_to(self.root))] = path.stat().st_mtime_ns
            except FileNotFoundError:
                pass
        return snapshot

    def _capture(self, pipe) -> None:
        for line in iter(pipe.readline, ""):
            clean = line.rstrip("\r\n")
            if clean:
                self.last_lines.append(clean)
                print(clean, flush=True)
                self.store.add_event("application_log", {"stream": "combined", "message": clean[:4000]})

    def _start(self, reason: str) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.child = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=self.root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.started_at = time.monotonic()
        threading.Thread(target=self._capture, args=(self.child.stdout,), daemon=True).start()
        self.store.add_event("application_started", {"pid": self.child.pid, "reason": reason})

    def _stop_child(self) -> None:
        if self.child is None or self.child.poll() is not None:
            return
        self.child.terminate()
        try:
            self.child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait(timeout=5)

    def _restart(self, changed: list[str]) -> None:
        old_pid = self.child.pid if self.child else 0
        self.store.add_event("application_reload_requested", {"pid": old_pid, "changed": changed})
        self._stop_child()
        self._start("source_change")

    def shutdown(self, *_args) -> None:
        self.stop_requested = True
        self._stop_child()

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
        snapshot = self._snapshot()
        self._start("supervisor_start")
        crashes = 0
        while not self.stop_requested:
            time.sleep(0.75)
            current = self._snapshot()
            changed = sorted(key for key in set(snapshot) | set(current) if snapshot.get(key) != current.get(key))
            if changed:
                snapshot = current
                self._restart(changed)
                crashes = 0
                continue
            if self.child is not None and self.child.poll() is not None:
                if self.stop_requested:
                    break
                code = self.child.returncode
                uptime = time.monotonic() - self.started_at
                self.store.add_incident(
                    "process_exit",
                    f"application process exited with code {code}",
                    source="live_supervisor",
                    severity="critical",
                    trace="\n".join(self.last_lines),
                    fields={"exit_code": code, "uptime_seconds": round(uptime, 3)},
                )
                crashes = crashes + 1 if uptime < 15 else 1
                delay = min(30, 2 ** min(crashes, 5))
                self.store.add_event("application_restart_scheduled", {"delay_seconds": delay, "crashes": crashes})
                time.sleep(delay)
                if not self.stop_requested:
                    self._start("crash_recovery")
        self.store.add_event("supervisor_stopped", {})
        return 0


if __name__ == "__main__":
    raise SystemExit(LiveSupervisor().run())
