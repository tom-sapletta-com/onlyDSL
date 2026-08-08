"""AssumptionDSL contract."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .common import ControlDslError, extract_one, json_string, list_value, parse_json_list, quoted

STATUSES = {"open", "confirmed", "superseded", "rejected"}
ASSUMPTION_FIELDS = {"SUBJECT", "CLASS", "STATUS", "CLAIM", "REASON", "INTRODUCED_BY", "EVIDENCE", "REPLACE_WHEN", "REPAIR"}


@dataclass(frozen=True, slots=True)
class Assumption:
    id: str
    subject: str
    assumption_class: str
    status: str
    claim: str
    reason: str
    introduced_by: str
    evidence: tuple[str, ...]
    replacement_condition: str
    repair_uri: str


@dataclass(slots=True)
class AssumptionDocument:
    id: str
    assumptions: dict[str, Assumption]

    def replace_with_evidence(self, assumption_id: str, evidence_uri: str, *, condition_met: bool) -> Assumption:
        current = self.assumptions[assumption_id]
        if current.status != "open":
            raise ControlDslError(f"assumption {assumption_id} is not open")
        if not condition_met:
            raise ControlDslError(f"replacement condition is not met for {assumption_id}")
        updated = replace(current, status="superseded", evidence=tuple(dict.fromkeys((*current.evidence, evidence_uri))))
        self.assumptions[assumption_id] = updated
        return updated


def _parse_assumption_fields(lines: list[str], index: int) -> tuple[dict[str, str], int]:
    fields: dict[str, str] = {}
    index += 1
    while index < len(lines) and lines[index] != "END_ASSUMPTION":
        key, _, value = lines[index].partition(" ")
        if key not in ASSUMPTION_FIELDS or key in fields:
            raise ControlDslError(f"invalid or duplicate assumption field {key!r}")
        fields[key] = value
        index += 1
    return fields, index


def _parse_assumption(assumption_id: str, fields: dict[str, str]) -> Assumption:
    missing = ASSUMPTION_FIELDS - fields.keys()
    if missing:
        raise ControlDslError(f"assumption {assumption_id} missing: {', '.join(sorted(missing))}")
    if fields["STATUS"] not in STATUSES:
        raise ControlDslError(f"invalid assumption status {fields['STATUS']!r}")
    if not fields["REPAIR"].startswith("subactor://process/repair/"):
        raise ControlDslError("assumption REPAIR must be a system process URI")
    return Assumption(
        assumption_id, fields["SUBJECT"], fields["CLASS"], fields["STATUS"],
        json_string(fields["CLAIM"], "CLAIM"), json_string(fields["REASON"], "REASON"),
        fields["INTRODUCED_BY"], tuple(parse_json_list(fields["EVIDENCE"], "EVIDENCE")),
        json_string(fields["REPLACE_WHEN"], "REPLACE_WHEN"), fields["REPAIR"],
    )


def parse_assumptions(markdown: str) -> AssumptionDocument:
    lines = [line.strip() for line in extract_one(markdown, "assumptiondsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("ASSUMPTION_SET ") or lines[-1] != "END_ASSUMPTION_SET":
        raise ControlDslError("invalid AssumptionDSL envelope")
    document = AssumptionDocument(lines[0].split(None, 1)[1], {})
    index = 1
    while index < len(lines) - 1:
        if not lines[index].startswith("ASSUMPTION "):
            raise ControlDslError(f"expected ASSUMPTION, got {lines[index]!r}")
        assumption_id = lines[index].split(None, 1)[1]
        fields, index = _parse_assumption_fields(lines, index)
        assumption = _parse_assumption(assumption_id, fields)
        if assumption_id in document.assumptions:
            raise ControlDslError(f"duplicate assumption {assumption_id}")
        document.assumptions[assumption_id] = assumption
        index += 1
    return document


def render_assumptions(document: AssumptionDocument) -> str:
    rows = ["```assumptiondsl", f"ASSUMPTION_SET {document.id}"]
    for item in document.assumptions.values():
        rows.extend([
            f"ASSUMPTION {item.id}", f"  SUBJECT {item.subject}", f"  CLASS {item.assumption_class}",
            f"  STATUS {item.status}", f"  CLAIM {quoted(item.claim)}", f"  REASON {quoted(item.reason)}",
            f"  INTRODUCED_BY {item.introduced_by}", f"  EVIDENCE {list_value(item.evidence)}",
            f"  REPLACE_WHEN {quoted(item.replacement_condition)}", f"  REPAIR {item.repair_uri}",
            "END_ASSUMPTION",
        ])
    rows.extend(["END_ASSUMPTION_SET", "```"])
    return "\n".join(rows)


def assumptions_from_integrity(integrity: object) -> AssumptionDocument:
    """Turn typed ungrounded findings into addressable assumptions; never infer facts."""
    project_id = str(getattr(integrity, "project_id"))
    result = AssumptionDocument(project_id, {})
    for finding in getattr(integrity, "findings"):
        if getattr(finding, "category") != "ungrounded-assumption":
            continue
        subjects = tuple(getattr(finding, "subjects"))
        for index, subject in enumerate(subjects or (project_id,), 1):
            normalized = "".join(character.lower() if character.isalnum() else "-" for character in str(subject)).strip("-")[:80] or "project"
            assumption_id = f"{str(getattr(finding, 'code')).lower().replace('_', '-')}-{normalized}-{index}"
            result.assumptions[assumption_id] = Assumption(
                assumption_id, str(subject), str(getattr(finding, "layer")), "open",
                str(getattr(finding, "message")), f"ProjectIntegrity finding {getattr(finding, 'code')}",
                "onlydsl://runtime/project-integrity", tuple(getattr(finding, "evidence")),
                f"finding {getattr(finding, 'code')} absent from a newer verified ProjectIntegrityDSL",
                str(getattr(finding, "repair_uri")),
            )
    return result
