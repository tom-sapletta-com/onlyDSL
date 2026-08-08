from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evolution import EvolutionStore  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def wait_for(url: str, timeout: float) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True, f"HTTP {response.status}"
                last = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(1)
    return False, last


def render_testqldsl(run_id: str, target: str, result: dict[str, Any]) -> str:
    rows = [
        "```testqldsl",
        f"TESTQL_RESULT {run_id}",
        "PROFILE testql.verification-result.v1",
        f"OCCURRED_AT {json.dumps(now())}",
        f"TARGET {json.dumps(target)}",
        f"OK {str(bool(result.get('ok'))).lower()}",
        f"REQUEST_HASH {result.get('request_hash', '')}",
        f"RESULT_HASH {result.get('result_hash', '')}",
        f"FILES {int(result.get('files', 0))}",
        f"PASSED_FILES {int(result.get('passed_files', 0))}",
        f"FAILED_FILES {int(result.get('failed_files', 0))}",
    ]
    for run in result.get("runs", []):
        rows.append("RUN " + json.dumps(run, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    rows.extend(["END_TESTQL_RESULT", "```"])
    return "\n".join(rows)


def synthetic_failure(scenario: Path, message: str) -> dict[str, Any]:
    import hashlib

    request_hash = hashlib.sha256(f"{scenario}:{message}".encode()).hexdigest()
    base = {
        "schema": "testql.verification-result.v1",
        "ok": False,
        "files": 1,
        "passed_files": 0,
        "failed_files": 1,
        "runs": [{
            "file": str(scenario), "source": scenario.name, "ok": False,
            "passed": 0, "failed": 1, "steps": 0, "skipped": 0,
            "validated": 0, "executed": 0, "profile": "startup",
            "duration_ms": 0.0, "errors": [message], "warnings": [],
            "failures": [{"name": "startup", "status": "error", "message": message}],
        }],
        "dry_run": False,
        "request_hash": request_hash,
    }
    base["result_hash"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return base


def verify(scenario: Path, target: str) -> dict[str, Any]:
    try:
        from testql.verification import VerificationRequest, run_verification

        request = VerificationRequest(
            file_specs=(str(scenario),), project_dir=ROOT, url=target,
            dry_run=False, quiet=True, timeout=30_000,
        )
        return run_verification(request).to_dict()
    except Exception as exc:
        return synthetic_failure(scenario, f"{type(exc).__name__}: {exc}")


def failure_summary(result: dict[str, Any]) -> str:
    failures = []
    for run in result.get("runs", []):
        failures.extend(item.get("message", "") for item in run.get("failures", []))
        failures.extend(run.get("errors", []))
    return "; ".join(str(item) for item in failures if item)[:6000] or "TestQL verification failed"


def write_twin_observation(path: Path, target: str, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    received_at = now()
    record = {
        "observedAt": received_at,
        "receivedAt": received_at,
        "subjectUri": "subactor://project/nanobionic-laboratory-md/digital-twin",
        "status": "ready" if result.get("ok") else "testql_failed",
        "severity": "info" if result.get("ok") else "error",
        "metric": "testql.startup.verification",
        "value": bool(result.get("ok")),
        "target": target,
        "resultHash": result.get("result_hash"),
        "failures": [] if result.get("ok") else [failure_summary(result)],
        "labels": ["testql", "startup", "digital-twin"],
    }
    path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    store = EvolutionStore(os.getenv("EVOLUTION_STATE_DIR", ROOT / "runtime/evolution"))
    output = store.root / "testql"
    output.mkdir(parents=True, exist_ok=True)
    targets = [
        ("onlydsl", ROOT / "testql/onlydsl-startup.testql.toon.yaml", os.getenv("TESTQL_ONLYDSL_URL", "http://127.0.0.1:18787")),
        ("digital-twin", ROOT / "testql/digital-twin-startup.testql.toon.yaml", os.getenv("TESTQL_TWIN_URL", "http://127.0.0.1:7444")),
    ]
    overall = True
    wait_seconds = float(os.getenv("TESTQL_STARTUP_WAIT_SECONDS", "45"))
    for name, scenario, target in targets:
        run_id = f"{name}-{uuid.uuid4().hex}"
        ready, detail = wait_for(target + ("/api/health" if name == "onlydsl" else "/api/state"), wait_seconds)
        result = verify(scenario, target) if ready else synthetic_failure(scenario, f"target unavailable: {detail}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        (output / f"{stamp}-{name}.result.json").write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        dsl_path = output / f"{stamp}-{name}.testqldsl"
        dsl_path.write_text(render_testqldsl(run_id, target, result), encoding="utf-8")
        store.add_event("testql_verification", {
            "target": name, "ok": bool(result.get("ok")),
            "result_hash": result.get("result_hash", ""), "dsl": dsl_path.name,
        })
        if name == "onlydsl" and not result.get("ok"):
            store.add_incident(
                "testql_verification_failed", failure_summary(result), source="testql",
                severity="error", route=target,
                trace=f"server.py scripts/startup_testql.py {scenario.relative_to(ROOT)}",
                fields={"result_hash": result.get("result_hash", ""), "testqldsl": dsl_path.name},
            )
        if name == "digital-twin":
            observation = Path(os.getenv("TESTQL_TWIN_OBSERVATION_LOG", "/twin-project/logs/testql-verification.jsonl"))
            twin_dsl = Path(os.getenv("TESTQL_TWIN_DSL_LOG", "/twin-project/logs/testql-latest.testqldsl"))
            try:
                write_twin_observation(observation, target, result)
                twin_dsl.write_text(dsl_path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError as exc:
                result["ok"] = False
                store.add_event("testql_observation_write_failed", {"message": str(exc), "path": str(observation)})
        overall = overall and bool(result.get("ok"))
        print(json.dumps({"target": name, "ready": ready, "ok": result.get("ok"), "result_hash": result.get("result_hash")}, sort_keys=True), flush=True)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
