from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diagnostics import diagnose_incident


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _qid(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return value[:128] if value and _ID_RE.fullmatch(value[:128]) else uuid.uuid4().hex


def _q(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class EvolutionStore:
    """Filesystem queue whose persisted records are complete, typed DSL documents."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("EVOLUTION_STATE_DIR", "runtime/evolution")).resolve()
        self.inbox = self.root / "inbox"
        self.processing = self.root / "processing"
        self.processed = self.root / "processed"
        self.failed = self.root / "failed"
        self.deferred = self.root / "deferred"
        self.guidance = self.root / "guidance"
        self.diagnostics = self.root / "diagnostics"
        self.events = self.root / "events"
        self.patches = self.root / "patches"
        self.backups = self.root / "backups"
        self.envelopes = self.root / "envelopes"
        self.receipts = self.root / "receipts"
        self.testql = self.root / "testql"
        for directory in (
            self.inbox, self.processing, self.processed, self.failed, self.deferred,
            self.guidance, self.diagnostics, self.events, self.patches, self.backups,
            self.envelopes, self.receipts, self.testql,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _write(self, directory: Path, stem: str, suffix: str, markdown: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = directory / f"{stamp}-{_qid(stem)}.{suffix}"
        tmp = directory / f".{path.name}.{uuid.uuid4().hex}.tmp"
        with self._lock:
            tmp.write_text(markdown, encoding="utf-8")
            tmp.replace(path)
        return path

    def add_guidance(self, text: str, *, source: str = "api", priority: str = "normal") -> dict[str, str]:
        if not str(text).strip():
            raise ValueError("guidance text is required")
        guidance_id = uuid.uuid4().hex
        markdown = "\n".join([
            "```guidancedsl",
            f"GUIDANCE {guidance_id}",
            f"CREATED_AT {_q(_now())}",
            f"SOURCE {_qid(source)}",
            f"PRIORITY {_qid(priority)}",
            f"DIRECTIVE {_q(str(text).strip())}",
            "REQUIRE tests_pass",
            "REQUIRE healthcheck_pass",
            "FORBID reveal_secret_values",
            "FORBID bypass_validation",
            "END_GUIDANCE",
            "```",
        ])
        path = self._write(self.guidance, guidance_id, "guidancedsl", markdown)
        self.add_event("guidance_recorded", {"guidance_id": guidance_id, "path": path.name})
        return {"id": guidance_id, "path": str(path), "markdown": markdown}

    def add_incident(
        self,
        kind: str,
        message: str,
        *,
        source: str = "runtime",
        severity: str = "error",
        route: str = "",
        trace: str = "",
        fields: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        incident_id = uuid.uuid4().hex
        rows = [
            "```incidentdsl",
            f"INCIDENT {incident_id}",
            f"OCCURRED_AT {_q(_now())}",
            f"SOURCE {_qid(source)}",
            f"KIND {_qid(kind)}",
            f"SEVERITY {_qid(severity)}",
            f"MESSAGE {_q(str(message)[:4000])}",
        ]
        if route:
            rows.append(f"ROUTE {_q(str(route)[:1000])}")
        if trace:
            rows.append(f"TRACE {_q(str(trace)[:12000])}")
        for key, value in sorted((fields or {}).items()):
            rows.append(f"FIELD {_qid(str(key))} {_q(value)}")
        rows.extend(["STATUS new", "END_INCIDENT", "```"])
        markdown = "\n".join(rows)
        path = self._write(self.inbox, incident_id, "incidentdsl", markdown)
        self.add_event("incident_recorded", {"incident_id": incident_id, "kind": kind, "path": path.name})
        diagnostic = self.add_diagnostic(incident_id, markdown)
        diagnostic_path = Path(diagnostic["path"])
        return {
            "id": incident_id, "path": str(path), "markdown": markdown,
            "diagnostic_path": str(diagnostic_path), "diagnostic": diagnostic["markdown"],
            "error_code": diagnostic["code"], "repair_action": diagnostic["action"],
        }

    def add_diagnostic(self, incident_id: str, incident_markdown: str) -> dict[str, Any]:
        diagnostic = diagnose_incident(incident_markdown, incident_id)
        path = self._write(
            self.diagnostics, f"{incident_id}-{diagnostic['code']}", "diagnosticdsl", diagnostic["markdown"],
        )
        self.add_event("incident_diagnosed", {
            "incident_id": incident_id,
            "error_code": diagnostic["code"],
            "action": diagnostic["action"],
            "path": path.name,
        })
        return {**diagnostic, "path": str(path)}

    def add_event(self, kind: str, fields: dict[str, Any] | None = None) -> Path:
        event_id = uuid.uuid4().hex
        rows = [
            "```eventdsl",
            f"EVENT {event_id}",
            f"OCCURRED_AT {_q(_now())}",
            f"KIND {_qid(kind)}",
        ]
        for key, value in sorted((fields or {}).items()):
            rows.append(f"FIELD {_qid(str(key))} {_q(value)}")
        rows.extend(["END_EVENT", "```"])
        return self._write(self.events, event_id, "eventdsl", "\n".join(rows))

    def add_json_record(self, kind: str, record_id: str, value: dict[str, Any]) -> Path:
        if kind not in {"envelope", "receipt"}:
            raise ValueError("unsupported governed record kind")
        directory = self.envelopes if kind == "envelope" else self.receipts
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        return self._write(directory, record_id, f"{kind}.json", payload)

    def latest_guidance(self, limit: int = 8) -> list[str]:
        paths = sorted(self.guidance.glob("*.guidancedsl"), reverse=True)[: max(0, limit)]
        return [path.read_text(encoding="utf-8") for path in reversed(paths)]

    def claim_incident(self) -> Path | None:
        for path in sorted(self.inbox.glob("*.incidentdsl")):
            claimed = self.processing / path.name
            try:
                path.replace(claimed)
                return claimed
            except FileNotFoundError:
                continue
        return None

    def finish_incident(self, claimed: Path, *, success: bool) -> Path:
        target = (self.processed if success else self.failed) / claimed.name
        claimed.replace(target)
        return target

    def defer_incident(self, claimed: Path) -> Path:
        target = self.deferred / claimed.name
        claimed.replace(target)
        return target

    def diagnostic_for_incident(self, incident_id: str) -> str:
        paths = sorted(self.diagnostics.glob(f"*-{_qid(incident_id)}-*.diagnosticdsl"), reverse=True)
        return paths[0].read_text(encoding="utf-8") if paths else ""

    def latest_diagnostics(self, limit: int = 20) -> list[dict[str, str]]:
        records = []
        for path in sorted(self.diagnostics.glob("*.diagnosticdsl"), reverse=True)[:max(0, limit)]:
            markdown = path.read_text(encoding="utf-8")
            code = re.search(r"^ERROR_CODE\s+(\S+)", markdown, re.M)
            action = re.search(r"^ACTION\s+(\S+)", markdown, re.M)
            records.append({
                "file": path.name,
                "error_code": code.group(1) if code else "UNKNOWN",
                "action": action.group(1) if action else "unknown",
                "markdown": markdown,
            })
        return records

    def status(self) -> dict[str, Any]:
        def count(directory: Path, pattern: str) -> int:
            return sum(1 for _ in directory.glob(pattern))

        latest_events = sorted(self.events.glob("*.eventdsl"), reverse=True)[:10]
        return {
            "mode": os.getenv("EVOLUTION_MODE", "observe").lower(),
            "enabled": os.getenv("EVOLUTION_ENABLED", "0") == "1",
            "llm_backend": os.getenv("EVOLUTION_LLM_BACKEND", "openrouter"),
            "queue": {
                "inbox": count(self.inbox, "*.incidentdsl"),
                "processing": count(self.processing, "*.incidentdsl"),
                "processed": count(self.processed, "*.incidentdsl"),
                "failed": count(self.failed, "*.incidentdsl"),
                "deferred": count(self.deferred, "*.incidentdsl"),
            },
            "guidance": count(self.guidance, "*.guidancedsl"),
            "diagnostics": {
                "count": count(self.diagnostics, "*.diagnosticdsl"),
                "latest": [path.name for path in sorted(self.diagnostics.glob("*.diagnosticdsl"), reverse=True)[:4]],
            },
            "patches": count(self.patches, "*.patchdsl"),
            "envelopes": count(self.envelopes, "*.envelope.json"),
            "receipts": count(self.receipts, "*.receipt.json"),
            "testql": {
                "results": count(self.testql, "*.result.json"),
                "dsl": count(self.testql, "*.testqldsl"),
                "latest": [path.name for path in sorted(self.testql.glob("*.testqldsl"), reverse=True)[:4]],
            },
            "latest_events": [path.name for path in latest_events],
            "state_dir": str(self.root),
        }
