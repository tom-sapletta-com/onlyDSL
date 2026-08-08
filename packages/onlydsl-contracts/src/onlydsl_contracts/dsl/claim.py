"""ClaimDSL contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .common import ControlDslError, HASH_RE, extract_one, json_string, list_value, parse_json_list, quoted

CLAIM_STATUSES = {"proposed", "validated", "accepted", "rejected", "superseded"}
CLAIM_FIELDS = {
    "SUBJECT", "PREDICATE", "VALUE", "UNIT", "SOURCE_URI", "SOURCE_HASH",
    "SOURCE_REVISION", "SOURCE_ANCHOR", "EVIDENCE_KIND", "QUALITY", "TRUST",
    "GENERATED_BY", "VALIDATED_BY", "STATUS", "ACCEPTED_AT", "SUPERSEDES",
}


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    subject: str
    predicate: str
    value: Any
    unit: str
    source_uri: str
    source_hash: str
    source_revision: str
    source_anchor: str
    evidence_kind: str
    quality: Decimal
    trust: str
    generated_by: str
    validated_by: str
    status: str
    accepted_at: str | None
    supersedes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimDocument:
    id: str
    claims: tuple[Claim, ...]


def _parse_claim_fields(lines: list[str], index: int) -> tuple[dict[str, str], int]:
    fields: dict[str, str] = {}
    index += 1
    while index < len(lines) and lines[index] != "END_CLAIM":
        key, _, value = lines[index].partition(" ")
        if key not in CLAIM_FIELDS or key in fields:
            raise ControlDslError(f"invalid or duplicate claim field {key!r}")
        fields[key] = value
        index += 1
    return fields, index


def _parse_claim(claim_id: str, fields: dict[str, str]) -> Claim:
    if set(fields) != CLAIM_FIELDS:
        raise ControlDslError(f"claim {claim_id} fields differ: {sorted(CLAIM_FIELDS - fields.keys())}")
    try:
        value = json.loads(fields["VALUE"])
        quality = Decimal(fields["QUALITY"])
    except (json.JSONDecodeError, InvalidOperation) as exc:
        raise ControlDslError(f"claim {claim_id} has invalid VALUE or QUALITY") from exc
    if not Decimal("0") <= quality <= Decimal("1"):
        raise ControlDslError(f"claim {claim_id} QUALITY must be within 0..1")
    if fields["UNIT"] == "mixed":
        raise ControlDslError("ClaimDSL UNIT mixed is forbidden")
    if not fields["SOURCE_URI"].startswith("urn:") or not HASH_RE.fullmatch(fields["SOURCE_HASH"]):
        raise ControlDslError(f"claim {claim_id} requires immutable source URI and hash")
    status = fields["STATUS"]
    if status not in CLAIM_STATUSES:
        raise ControlDslError(f"claim {claim_id} has invalid STATUS")
    accepted_at = None if fields["ACCEPTED_AT"] == "none" else json_string(fields["ACCEPTED_AT"], "ACCEPTED_AT")
    validated_by = fields["VALIDATED_BY"]
    if status == "accepted" and (not validated_by.startswith(("deterministic:", "testql:", "eql:")) or not accepted_at):
        raise ControlDslError(f"accepted claim {claim_id} requires deterministic validation and ACCEPTED_AT")
    return Claim(
        claim_id, fields["SUBJECT"], fields["PREDICATE"], value, fields["UNIT"],
        fields["SOURCE_URI"], fields["SOURCE_HASH"], json_string(fields["SOURCE_REVISION"], "SOURCE_REVISION"),
        json_string(fields["SOURCE_ANCHOR"], "SOURCE_ANCHOR"), fields["EVIDENCE_KIND"], quality,
        fields["TRUST"], fields["GENERATED_BY"], validated_by, status, accepted_at,
        tuple(parse_json_list(fields["SUPERSEDES"], "SUPERSEDES")),
    )


def parse_claims(markdown: str) -> ClaimDocument:
    lines = [line.strip() for line in extract_one(markdown, "claimdsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("CLAIM_SET ") or lines[-1] != "END_CLAIM_SET":
        raise ControlDslError("invalid ClaimDSL envelope")
    claims: list[Claim] = []
    seen: set[str] = set()
    index = 1
    while index < len(lines) - 1:
        if not lines[index].startswith("CLAIM "):
            raise ControlDslError(f"expected CLAIM, got {lines[index]!r}")
        claim_id = lines[index].split(None, 1)[1]
        fields, index = _parse_claim_fields(lines, index)
        if claim_id in seen:
            raise ControlDslError(f"duplicate claim {claim_id}")
        seen.add(claim_id)
        claims.append(_parse_claim(claim_id, fields))
        index += 1
    return ClaimDocument(lines[0].split(None, 1)[1], tuple(claims))


def render_claims(document: ClaimDocument) -> str:
    rows = ["```claimdsl", f"CLAIM_SET {document.id}"]
    for claim in document.claims:
        rows.extend([
            f"CLAIM {claim.id}", f"  SUBJECT {claim.subject}", f"  PREDICATE {claim.predicate}",
            "  VALUE " + json.dumps(claim.value, ensure_ascii=False, separators=(",", ":")),
            f"  UNIT {claim.unit}", f"  SOURCE_URI {claim.source_uri}", f"  SOURCE_HASH {claim.source_hash}",
            f"  SOURCE_REVISION {quoted(claim.source_revision)}", f"  SOURCE_ANCHOR {quoted(claim.source_anchor)}",
            f"  EVIDENCE_KIND {claim.evidence_kind}", f"  QUALITY {claim.quality}", f"  TRUST {claim.trust}",
            f"  GENERATED_BY {claim.generated_by}", f"  VALIDATED_BY {claim.validated_by}", f"  STATUS {claim.status}",
            f"  ACCEPTED_AT {quoted(claim.accepted_at) if claim.accepted_at else 'none'}",
            f"  SUPERSEDES {list_value(claim.supersedes)}", "END_CLAIM",
        ])
    rows.extend(["END_CLAIM_SET", "```"])
    return "\n".join(rows)
