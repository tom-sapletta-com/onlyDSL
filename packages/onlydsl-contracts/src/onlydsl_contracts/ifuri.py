"""Location-independent IFURI value object."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class IfUriError(ValueError):
    pass


_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_KINDS = {"commands", "queries", "events", "artifacts", "streams"}
_KIND_SUBJECT_PREFIX = {
    "commands": "cmd",
    "queries": "qry",
    "events": "evt",
    "artifacts": "art",
    "streams": "str",
}


@dataclass(frozen=True, slots=True)
class IfUri:
    """Location-independent capability URI.

    Canonical shape:
      ifuri://<bounded-context>/<entity>/<identity>/<kind>/<operation>

    No port/userinfo/query/fragment is allowed. Transport placement is deliberately
    absent from the logical address.
    """

    bounded_context: str
    entity: str
    identity: str
    kind: str
    operation: str

    @classmethod
    def parse(cls, raw: str) -> "IfUri":
        if not isinstance(raw, str) or not raw:
            raise IfUriError("URI must be a non-empty string")
        parsed = urlsplit(raw)
        _validate_uri_parts(parsed)
        bounded_context = parsed.hostname
        entity, identity, kind, operation = _path_segments(parsed.path)
        _validate_segments(bounded_context, entity, identity, operation)
        if kind not in _KINDS:
            raise IfUriError(f"invalid kind {kind!r}; expected one of {sorted(_KINDS)}")
        return cls(bounded_context, entity, identity, kind, operation)

    def __str__(self) -> str:
        return f"ifuri://{self.bounded_context}/{self.entity}/{self.identity}/{self.kind}/{self.operation}"

    def to_subject(self, prefix: str = "ifuri") -> str:
        """Map the logical URI deterministically to a NATS subject."""
        return ".".join([prefix, _KIND_SUBJECT_PREFIX[self.kind], self.bounded_context, self.entity, self.identity, self.operation])

    @property
    def is_request_reply(self) -> bool:
        return self.kind in {"commands", "queries"}

    @property
    def is_event(self) -> bool:
        return self.kind == "events"


def _validate_uri_parts(parsed: object) -> None:
    # urlsplit returns SplitResult, but keeping this helper structural avoids exposing it publicly.
    if parsed.scheme != "ifuri":
        raise IfUriError("URI scheme must be 'ifuri'")
    if parsed.username or parsed.password or parsed.port:
        raise IfUriError("userinfo and port are forbidden in logical IFURI addresses")
    if parsed.query or parsed.fragment:
        raise IfUriError("query and fragment are forbidden in canonical IFURI addresses")
    if not parsed.hostname:
        raise IfUriError("bounded context is required")


def _path_segments(path: str) -> tuple[str, str, str, str]:
    segments = [seg for seg in path.split("/") if seg]
    if len(segments) != 4:
        raise IfUriError("IFURI must have exactly 4 path segments: <entity>/<identity>/<kind>/<operation>")
    return tuple(segments)  # type: ignore[return-value]


def _validate_segments(bounded_context: str, entity: str, identity: str, operation: str) -> None:
    for label, value in (("bounded_context", bounded_context), ("entity", entity), ("identity", identity), ("operation", operation)):
        if not _SEGMENT_RE.fullmatch(value):
            raise IfUriError(f"invalid {label}: {value!r}")


def canonicalize(raw: str) -> str:
    return str(IfUri.parse(raw))
