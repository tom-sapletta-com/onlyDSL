"""EvidenceSetDSL contract."""

from __future__ import annotations

from dataclasses import dataclass

from .common import ControlDslError, HASH_RE, canonical_hash, extract_one


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    id: str
    query_uri: str
    members: int
    members_hash: str
    uri: str


def create_evidence_set(set_id: str, query_uri: str, member_uris: list[str]) -> EvidenceSet:
    if not query_uri.startswith("urn:"):
        raise ControlDslError("EvidenceSet QUERY must be an immutable URN")
    members = sorted(set(member_uris))
    digest = canonical_hash(members)
    uri = "urn:subactor:evidence-set:" + digest
    return EvidenceSet(set_id, query_uri, len(members), digest, uri)


def render_evidence_set(value: EvidenceSet) -> str:
    return "\n".join([
        "```evidencesetdsl", f"EVIDENCE_SET {value.id}", f"URI {value.uri}",
        f"QUERY {value.query_uri}", f"MEMBERS {value.members}", f"HASH {value.members_hash}",
        "END_EVIDENCE_SET", "```",
    ])


def parse_evidence_set(markdown: str) -> EvidenceSet:
    lines = [line.strip() for line in extract_one(markdown, "evidencesetdsl").splitlines() if line.strip()]
    if len(lines) != 6 or not lines[0].startswith("EVIDENCE_SET ") or lines[-1] != "END_EVIDENCE_SET":
        raise ControlDslError("invalid EvidenceSetDSL envelope")
    fields = dict(line.split(None, 1) for line in lines[1:-1])
    if set(fields) != {"URI", "QUERY", "MEMBERS", "HASH"}:
        raise ControlDslError("EvidenceSetDSL requires URI, QUERY, MEMBERS and HASH")
    if not fields["URI"].startswith("urn:subactor:evidence-set:sha256:") or not fields["QUERY"].startswith("urn:") or not HASH_RE.fullmatch(fields["HASH"]):
        raise ControlDslError("EvidenceSetDSL contains a non-immutable URI or invalid hash")
    members = int(fields["MEMBERS"])
    if members < 0:
        raise ControlDslError("MEMBERS must be non-negative")
    return EvidenceSet(lines[0].split(None, 1)[1], fields["QUERY"], members, fields["HASH"], fields["URI"])
