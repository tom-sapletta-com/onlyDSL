from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

IDENT_RE = r"[A-Za-z_][A-Za-z0-9_]*"
IDENT_RX = re.compile(rf"^{IDENT_RE}$")
TYPE_NAMES = {"string", "number", "integer", "boolean"}
FENCE_RE = re.compile(r"```contextdsl\s*\n(?P<body>.*?)```", re.I | re.S)
LEGACY_LOG_RE = re.compile(
    r"^(?:(?P<ts>\d{4}-\d{2}-\d{2}[T ][^ ]+)\s+)?"
    r"(?P<severity>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<source>[A-Za-z0-9_.:/-]+)\s+(?P<message>.*)$",
    re.I,
)
KV_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_.-]*)=([^\s]+)")


class ContextDslError(ValueError):
    pass


@dataclass
class ContextRecord:
    kind: str
    source: str
    code: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextDocument:
    name: str = "runtime_context"
    version: int = 1
    origin: str = "application"
    purpose: str = "analysis"
    trace_id: str = ""
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    action_capabilities: set[str] = field(default_factory=set)
    event_capabilities: set[str] = field(default_factory=set)
    records: list[ContextRecord] = field(default_factory=list)
    policies: dict[str, bool] = field(default_factory=lambda: {
        "dsl_only_llm": True,
        "raw_context_forbidden": True,
    })

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["action_capabilities"] = sorted(self.action_capabilities)
        out["event_capabilities"] = sorted(self.event_capabilities)
        return out


@dataclass(frozen=True)
class DslContextEvent:
    """Preferred application/runtime log event: semantic at the source, before any LLM boundary."""

    source: str
    code: str
    severity: str = "info"
    fields: dict[str, Any] = field(default_factory=dict)


def _ident(value: str, fallback: str = "unknown") -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(value).strip()).strip("_")
    if not value:
        return fallback
    if value[0].isdigit():
        value = "n_" + value
    return value[:96]


def _event_code_from_text(text: str) -> str:
    # Legacy compatibility only. It deliberately does not preserve the raw line.
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    stop = {"the", "a", "an", "is", "was", "to", "for", "of", "and", "or", "with", "at", "on"}
    kept = [w for w in words if w not in stop and not w.isdigit()][:8]
    return _ident("_".join(kept), "legacy_log")


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return json.dumps("none")
    return json.dumps(str(value), ensure_ascii=False)


def _parse_literal(raw: str) -> Any:
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", raw):
        return float(raw)
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContextDslError(f"Invalid literal: {raw}") from exc
    raise ContextDslError(f"Invalid literal: {raw}")


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _parse_legacy_scalar(raw: str) -> Any:
    raw = raw.strip().strip(",;")
    lower = raw.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw.strip('"\'')


class ContextCompiler:
    """Deterministic application-side compiler. No LLM is called here."""

    def __init__(self, name: str = "runtime_context", origin: str = "application", purpose: str = "analysis", trace_id: str = ""):
        self.document = ContextDocument(
            name=_ident(name, "runtime_context"),
            origin=_ident(origin, "application"),
            purpose=_ident(purpose, "analysis"),
            trace_id=trace_id or hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}:{name}".encode()).hexdigest()[:16],
        )

    def policy(self, name: str, enabled: bool = True) -> "ContextCompiler":
        self.document.policies[_ident(name)] = bool(enabled)
        return self

    def capability(self, kind: str, name: str) -> "ContextCompiler":
        name = _ident(name)
        if kind == "action":
            self.document.action_capabilities.add(name)
        elif kind == "event":
            self.document.event_capabilities.add(name)
        else:
            raise ContextDslError(f"Unsupported capability kind: {kind}")
        return self

    def state(self, name: str, value: Any, type_name: str | None = None) -> "ContextCompiler":
        type_name = type_name or _infer_type(value)
        if type_name not in TYPE_NAMES:
            raise ContextDslError(f"Unsupported state type: {type_name}")
        self.document.states[_ident(name)] = {"type": type_name, "value": value}
        return self

    def metric(self, name: str, value: int | float) -> "ContextCompiler":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContextDslError("Metrics must be numeric")
        self.document.metrics[_ident(name)] = value
        return self

    def record(self, kind: str, source: str, code: str, fields: dict[str, Any] | None = None) -> "ContextCompiler":
        kind = _ident(kind).lower()
        if kind not in {"event", "log", "error", "exception", "tool", "retrieval", "trace", "memory", "document", "code", "database"}:
            raise ContextDslError(f"Unsupported record kind: {kind}")
        normalized_fields = {_ident(k): v for k, v in (fields or {}).items()}
        self.document.records.append(ContextRecord(kind, _ident(source), _ident(code), normalized_fields))
        return self

    def event(self, event: DslContextEvent) -> "ContextCompiler":
        fields = {"severity": event.severity.lower(), **event.fields}
        return self.record("event", event.source, event.code, fields)

    def exception(self, exc: BaseException, source: str = "application", code: str = "runtime_exception") -> "ContextCompiler":
        # No traceback/raw message crosses the boundary. Exception class and safe structural fields only.
        fields = {"exception_type": type(exc).__name__}
        for key in ("errno", "status", "status_code", "code"):
            value = getattr(exc, key, None)
            if isinstance(value, (str, int, float, bool)):
                fields[key] = value
        fields["message_digest"] = hashlib.sha256(str(exc).encode("utf-8", errors="replace")).hexdigest()[:16]
        return self.record("exception", source, code, fields)

    def tool_result(self, tool: str, ok: bool, data: dict[str, Any] | None = None) -> "ContextCompiler":
        fields: dict[str, Any] = {"ok": ok}
        for key, value in (data or {}).items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                fields[_ident(key)] = value
            else:
                fields[_ident(key) + "_digest"] = hashlib.sha256(
                    json.dumps(value, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:16]
        return self.record("tool", tool, "success" if ok else "failure", fields)


    def retrieval(self, source: str, code: str, fields: dict[str, Any] | None = None) -> "ContextCompiler":
        return self.record("retrieval", source, code, fields)

    def memory(self, scope: str, code: str, fields: dict[str, Any] | None = None) -> "ContextCompiler":
        return self.record("memory", scope, code, fields)

    def code_fact(self, module: str, code: str, fields: dict[str, Any] | None = None) -> "ContextCompiler":
        return self.record("code", module, code, fields)

    def database_fact(self, entity: str, code: str, fields: dict[str, Any] | None = None) -> "ContextCompiler":
        return self.record("database", entity, code, fields)

    def legacy_log(self, line: str) -> "ContextCompiler":
        """Lossy adapter for old text logs. Prefer `event()` at log emission time."""
        raw = line.strip()
        match = LEGACY_LOG_RE.match(raw)
        if match:
            groups = match.groupdict()
            message = groups["message"] or ""
            kvs = {k: _parse_legacy_scalar(v) for k, v in KV_RE.findall(message)}
            message_without_kv = KV_RE.sub(" ", message)
            code = _event_code_from_text(message_without_kv)
            fields: dict[str, Any] = {
                "severity": (groups["severity"] or "info").lower().replace("warning", "warn"),
                "legacy": True,
                "lossy": True,
                "raw_digest": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16],
                **kvs,
            }
            if groups.get("ts"):
                fields["timestamp"] = groups["ts"]
            return self.record("log", groups.get("source") or "legacy", code, fields)
        return self.record("log", "legacy", _event_code_from_text(raw), {
            "legacy": True,
            "lossy": True,
            "raw_digest": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16],
        })

    def to_markdown(self) -> str:
        return render_context_markdown(self.document)


def render_context_dsl(doc: ContextDocument) -> str:
    lines = [
        f"CONTEXT {_ident(doc.name)}",
        f"VERSION {doc.version}",
        f"ORIGIN {_ident(doc.origin)}",
        f"PURPOSE {_ident(doc.purpose)}",
        f"TRACE {_literal(doc.trace_id)}",
    ]
    for name, enabled in sorted(doc.policies.items()):
        lines.append(f"POLICY {_ident(name)} {'true' if enabled else 'false'}")
    for name in sorted(doc.action_capabilities):
        lines.append(f"CAPABILITY action {_ident(name)}")
    for name in sorted(doc.event_capabilities):
        lines.append(f"CAPABILITY event {_ident(name)}")
    for name, spec in sorted(doc.states.items()):
        lines.append(f"STATE {_ident(name)} {spec['type']} = {_literal(spec['value'])}")
    for name, value in sorted(doc.metrics.items()):
        lines.append(f"METRIC {_ident(name)} = {_literal(value)}")
    for record in doc.records:
        lines.append(f"RECORD {record.kind} {_ident(record.source)} {_ident(record.code)}")
        for key, value in sorted(record.fields.items()):
            lines.append(f"  FIELD {_ident(key)} = {_literal(value)}")
        lines.append("END")
    lines.append("END_CONTEXT")
    return "\n".join(lines) + "\n"


def render_context_markdown(doc: ContextDocument) -> str:
    return "```contextdsl\n" + render_context_dsl(doc) + "```"


def extract_contextdsl(markdown: str) -> str:
    match = FENCE_RE.search(markdown)
    if not match:
        raise ContextDslError("No ```contextdsl fenced block found")
    return match.group("body").strip() + "\n"


def parse_context_dsl(dsl: str) -> ContextDocument:
    lines = dsl.splitlines()
    doc: ContextDocument | None = None
    current: ContextRecord | None = None
    ended = False
    for lineno, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if current is not None:
            if stripped == "END":
                doc.records.append(current)  # type: ignore[union-attr]
                current = None
                continue
            m = re.fullmatch(rf"FIELD ({IDENT_RE})\s*=\s*(.+)", stripped)
            if not m or not raw.startswith("  "):
                raise ContextDslError(f"Line {lineno}: expected indented FIELD or END")
            current.fields[m.group(1)] = _parse_literal(m.group(2))
            continue

        if stripped.startswith("CONTEXT "):
            if doc is not None:
                raise ContextDslError(f"Line {lineno}: duplicate CONTEXT")
            doc = ContextDocument(name=_ident(stripped[8:].strip()))
            continue
        if doc is None:
            raise ContextDslError(f"Line {lineno}: CONTEXT must be first")
        if stripped == "END_CONTEXT":
            ended = True
            continue
        if ended:
            raise ContextDslError(f"Line {lineno}: content after END_CONTEXT")
        if stripped.startswith("VERSION "):
            doc.version = int(stripped[8:].strip())
        elif stripped.startswith("ORIGIN "):
            doc.origin = _ident(stripped[7:].strip())
        elif stripped.startswith("PURPOSE "):
            doc.purpose = _ident(stripped[8:].strip())
        elif stripped.startswith("TRACE "):
            doc.trace_id = str(_parse_literal(stripped[6:]))
        elif stripped.startswith("POLICY "):
            m = re.fullmatch(rf"POLICY ({IDENT_RE}) (true|false)", stripped)
            if not m:
                raise ContextDslError(f"Line {lineno}: invalid POLICY")
            doc.policies[m.group(1)] = m.group(2) == "true"
        elif stripped.startswith("CAPABILITY "):
            m = re.fullmatch(rf"CAPABILITY (action|event) ({IDENT_RE})", stripped)
            if not m:
                raise ContextDslError(f"Line {lineno}: invalid CAPABILITY")
            if m.group(1) == "action":
                doc.action_capabilities.add(m.group(2))
            else:
                doc.event_capabilities.add(m.group(2))
        elif stripped.startswith("STATE "):
            m = re.fullmatch(rf"STATE ({IDENT_RE}) ({'|'.join(TYPE_NAMES)})\s*=\s*(.+)", stripped)
            if not m:
                raise ContextDslError(f"Line {lineno}: invalid STATE")
            doc.states[m.group(1)] = {"type": m.group(2), "value": _parse_literal(m.group(3))}
        elif stripped.startswith("METRIC "):
            m = re.fullmatch(rf"METRIC ({IDENT_RE})\s*=\s*(.+)", stripped)
            if not m:
                raise ContextDslError(f"Line {lineno}: invalid METRIC")
            value = _parse_literal(m.group(2))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContextDslError(f"Line {lineno}: METRIC must be numeric")
            doc.metrics[m.group(1)] = value
        elif stripped.startswith("RECORD "):
            m = re.fullmatch(rf"RECORD (event|log|error|exception|tool|retrieval|trace|memory|document|code|database) ({IDENT_RE}) ({IDENT_RE})", stripped)
            if not m:
                raise ContextDslError(f"Line {lineno}: invalid RECORD")
            current = ContextRecord(m.group(1), m.group(2), m.group(3))
        else:
            raise ContextDslError(f"Line {lineno}: unknown declaration: {stripped}")
    if current is not None:
        raise ContextDslError("Unclosed RECORD block")
    if doc is None:
        raise ContextDslError("Missing CONTEXT")
    if not ended:
        raise ContextDslError("Missing END_CONTEXT")
    return doc


def validate_context_markdown(markdown: str) -> dict[str, Any]:
    try:
        doc = parse_context_dsl(extract_contextdsl(markdown))
    except (ContextDslError, ValueError) as exc:
        return {"valid": False, "errors": [str(exc)], "ast": None}
    errors: list[str] = []
    if doc.version != 1:
        errors.append(f"Unsupported ContextDSL version: {doc.version}")
    if not doc.policies.get("dsl_only_llm", False):
        errors.append("Required policy dsl_only_llm=true is missing")
    if not doc.policies.get("raw_context_forbidden", False):
        errors.append("Required policy raw_context_forbidden=true is missing")
    return {"valid": not errors, "errors": errors, "ast": doc.to_dict()}


def compiler_from_payload(payload: dict[str, Any]) -> ContextCompiler:
    compiler = ContextCompiler(
        name=str(payload.get("name", "runtime_context")),
        origin=str(payload.get("origin", "application")),
        purpose=str(payload.get("purpose", "analysis")),
        trace_id=str(payload.get("trace_id", "")),
    )
    capabilities = payload.get("capabilities", {}) or {}
    for action in capabilities.get("actions", []) or []:
        compiler.capability("action", str(action))
    for event in capabilities.get("events", []) or []:
        compiler.capability("event", str(event))
    for name, value in (payload.get("state", {}) or {}).items():
        compiler.state(str(name), value)
    for name, value in (payload.get("metrics", {}) or {}).items():
        compiler.metric(str(name), value)
    for row in payload.get("events", []) or []:
        if isinstance(row, dict):
            compiler.event(DslContextEvent(
                source=str(row.get("source", "application")),
                code=str(row.get("code", "event")),
                severity=str(row.get("severity", "info")),
                fields=dict(row.get("fields", {}) or {}),
            ))
    logs = payload.get("logs", []) or []
    if isinstance(logs, str):
        logs = logs.splitlines()
    for line in logs:
        if str(line).strip():
            compiler.legacy_log(str(line))
    for row in payload.get("tool_results", []) or []:
        if isinstance(row, dict):
            compiler.tool_result(str(row.get("tool", "tool")), bool(row.get("ok", False)), dict(row.get("data", {}) or {}))
    return compiler
