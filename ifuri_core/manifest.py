from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .uri import IfUri, IfUriError


class ManifestError(ValueError):
    pass


_PARAM_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_LITERAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_VALID_KINDS = {"commands", "queries", "events", "artifacts", "streams"}


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    preferred: str = "inproc"
    fallbacks: tuple[str, ...] = ()

    def ordered(self) -> tuple[str, ...]:
        return (self.preferred, *self.fallbacks)


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    uri_pattern: str
    input_type: str = ""
    output_type: str = ""
    message_kind: str = "command"
    idempotent: bool = False
    durable: bool = False
    runtime: str = "default"
    transport: TransportPolicy = field(default_factory=TransportPolicy)

    def match(self, uri: IfUri) -> dict[str, str] | None:
        pattern = _parse_pattern(self.uri_pattern)
        values = [
            uri.bounded_context,
            uri.entity,
            uri.identity,
            uri.kind,
            uri.operation,
        ]
        params: dict[str, str] = {}
        for token, value in zip(pattern, values):
            pm = _PARAM_RE.fullmatch(token)
            if pm:
                params[pm.group(1)] = value
            elif token != value:
                return None
        return params

    @property
    def specificity(self) -> int:
        return sum(1 for token in _parse_pattern(self.uri_pattern) if not _PARAM_RE.fullmatch(token))


@dataclass(frozen=True, slots=True)
class ResolvedCapability:
    capability: Capability
    uri: IfUri
    params: dict[str, str]


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability] | None = None):
        self._capabilities: list[Capability] = []
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: Capability) -> None:
        if any(c.id == capability.id for c in self._capabilities):
            raise ManifestError(f"duplicate capability id: {capability.id}")
        _validate_capability(capability)
        self._capabilities.append(capability)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "CapabilityRegistry":
        if int(raw.get("version", 0)) != 1:
            raise ManifestError("capability manifest version must be 1")
        caps: list[Capability] = []
        for row in raw.get("capabilities", []) or []:
            if not isinstance(row, dict):
                raise ManifestError("each capability must be an object")
            semantics = row.get("semantics", {}) or {}
            placement = row.get("placement", {}) or {}
            transports = row.get("transport", {}) or {}
            fallback = transports.get("fallback", transports.get("fallbacks", [])) or []
            if isinstance(fallback, str):
                fallback = [fallback]
            caps.append(
                Capability(
                    id=str(row.get("id", "")),
                    uri_pattern=str(row.get("uri_pattern", row.get("uri", ""))),
                    input_type=str((row.get("contract", {}) or {}).get("input", "")),
                    output_type=str((row.get("contract", {}) or {}).get("output", "")),
                    message_kind=str(semantics.get("kind", "command")),
                    idempotent=bool(semantics.get("idempotent", False)),
                    durable=bool(semantics.get("durable", False)),
                    runtime=str(placement.get("runtime", "default")),
                    transport=TransportPolicy(
                        preferred=str(transports.get("preferred", "inproc")),
                        fallbacks=tuple(str(x) for x in fallback),
                    ),
                )
            )
        return cls(caps)

    @classmethod
    def from_file(cls, path: str | Path) -> "CapabilityRegistry":
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in {".yaml", ".yml"}:
            raw = yaml.safe_load(text)
        else:
            raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ManifestError("manifest root must be an object")
        return cls.from_mapping(raw)

    def resolve(self, uri_raw: str) -> ResolvedCapability:
        uri = IfUri.parse(uri_raw)
        candidates: list[tuple[int, Capability, dict[str, str]]] = []
        for capability in self._capabilities:
            params = capability.match(uri)
            if params is not None:
                candidates.append((capability.specificity, capability, params))
        if not candidates:
            raise ManifestError(f"no capability route for {uri}")
        candidates.sort(key=lambda row: row[0], reverse=True)
        best_specificity = candidates[0][0]
        best = [row for row in candidates if row[0] == best_specificity]
        if len(best) > 1:
            ids = ", ".join(row[1].id for row in best)
            raise ManifestError(f"ambiguous capability route for {uri}: {ids}")
        _, capability, params = best[0]
        return ResolvedCapability(capability, uri, params)

    def explain(self, uri_raw: str) -> dict[str, Any]:
        uri = IfUri.parse(uri_raw)
        rows: list[dict[str, Any]] = []
        for c in self._capabilities:
            params = c.match(uri)
            rows.append(
                {
                    "id": c.id,
                    "pattern": c.uri_pattern,
                    "matched": params is not None,
                    "specificity": c.specificity,
                    "params": params or {},
                    "transports": list(c.transport.ordered()),
                    "runtime": c.runtime,
                }
            )
        selected = None
        error = None
        try:
            resolved = self.resolve(uri_raw)
            selected = resolved.capability.id
        except Exception as exc:
            error = str(exc)
        return {"uri": str(uri), "selected": selected, "error": error, "candidates": rows}

    def dump(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.id,
                "uri_pattern": c.uri_pattern,
                "contract": {"input": c.input_type, "output": c.output_type},
                "semantics": {
                    "kind": c.message_kind,
                    "idempotent": c.idempotent,
                    "durable": c.durable,
                },
                "placement": {"runtime": c.runtime},
                "transport": {
                    "preferred": c.transport.preferred,
                    "fallback": list(c.transport.fallbacks),
                },
            }
            for c in self._capabilities
        ]


def _parse_pattern(raw: str) -> tuple[str, str, str, str, str]:
    parsed = urlsplit(raw)
    if parsed.scheme != "ifuri" or not parsed.netloc:
        raise ManifestError(f"invalid IFURI pattern: {raw!r}")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ManifestError("IFURI patterns cannot contain userinfo/port/query/fragment")
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) != 4:
        raise ManifestError("IFURI pattern requires entity/identity/kind/operation")
    tokens = [parsed.hostname or "", *segments]
    seen_params: set[str] = set()
    for index, token in enumerate(tokens):
        pm = _PARAM_RE.fullmatch(token)
        if pm:
            if index == 3:  # kind position; keep it explicit to avoid cross-kind magic.
                raise ManifestError("kind segment must be literal in capability manifests")
            if pm.group(1) in seen_params:
                raise ManifestError(f"duplicate pattern parameter: {pm.group(1)}")
            seen_params.add(pm.group(1))
            continue
        if not _LITERAL_RE.fullmatch(token):
            raise ManifestError(f"invalid pattern token: {token!r}")
    if tokens[3] not in _VALID_KINDS:
        raise ManifestError(f"invalid kind in pattern: {tokens[3]}")
    return tuple(tokens)  # type: ignore[return-value]


def _validate_capability(capability: Capability) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,127}", capability.id):
        raise ManifestError(f"invalid capability id: {capability.id!r}")
    tokens = _parse_pattern(capability.uri_pattern)
    kind = tokens[3]
    expected = {
        "command": "commands",
        "query": "queries",
        "event": "events",
        "artifact": "artifacts",
        "stream": "streams",
    }.get(capability.message_kind)
    if expected is None:
        raise ManifestError(f"unsupported semantic kind: {capability.message_kind}")
    if kind != expected:
        raise ManifestError(
            f"manifest semantic kind {capability.message_kind!r} conflicts with URI kind {kind!r}"
        )
    transports = capability.transport.ordered()
    if len(set(transports)) != len(transports):
        raise ManifestError(f"duplicate transports for {capability.id}")
    for transport in transports:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", transport):
            raise ManifestError(f"invalid transport name: {transport!r}")
