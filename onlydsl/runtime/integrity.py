from __future__ import annotations

import json
from dataclasses import dataclass

from onlydsl.dsl.common import ControlDslError, canonical_hash, extract_one, parse_json_list


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    code: str
    severity: str
    category: str
    layer: str
    subjects: tuple[str, ...]
    evidence: tuple[str, ...]
    repair_uri: str
    message: str


@dataclass(frozen=True, slots=True)
class ProjectIntegrity:
    project_id: str
    integrity: str
    evidence: str
    operational_ready: str
    autonomy_ready: str
    source_hash: str
    findings: tuple[IntegrityFinding, ...]


def parse_project_integrity(markdown: str) -> ProjectIntegrity:
    body = extract_one(markdown, "projectintegritydsl")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("PROJECT_INTEGRITY ") or lines[-1] != "END_PROJECT_INTEGRITY":
        raise ControlDslError("invalid ProjectIntegrityDSL envelope")
    project_id = lines[0].split(None, 1)[1]
    result = next((line.split(None, 1)[1] for line in lines if line.startswith("RESULT ")), "FAIL")
    completeness = next((line.split(None, 1)[1] for line in lines if line.startswith("COMPLETENESS ")), "INCOMPLETE")
    findings: list[IntegrityFinding] = []
    index = 1
    while index < len(lines) - 1:
        if lines[index].startswith("FINDING "):
            parts = lines[index].split()
            if len(parts) != 8 or parts[2] != "SEVERITY" or parts[4] != "CATEGORY" or parts[6] != "LAYER":
                raise ControlDslError("invalid ProjectIntegrityDSL FINDING header")
            fields: dict[str, str] = {}
            index += 1
            while index < len(lines) and lines[index] != "END_FINDING":
                key, _, value = lines[index].partition(" ")
                fields[key] = value
                index += 1
            if set(fields) != {"SUBJECTS", "EVIDENCE", "REPAIR", "MESSAGE"}:
                raise ControlDslError("FINDING requires subjects, evidence, repair and message")
            findings.append(IntegrityFinding(
                parts[1], parts[3].lower(), parts[5], parts[7], tuple(parse_json_list(fields["SUBJECTS"], "SUBJECTS")),
                tuple(parse_json_list(fields["EVIDENCE"], "EVIDENCE")), fields["REPAIR"], json.loads(fields["MESSAGE"]),
            ))
        index += 1
    operational = "READY" if result == "PASS" and completeness == "COMPLETE" else "PARTIAL" if result == "PASS" else "BLOCKED"
    autonomy = "BLOCKED" if any(f.severity == "error" or f.category in {"broken-dependency", "inconsistency"} for f in findings) else "PASS"
    return ProjectIntegrity(project_id, result, completeness, operational, autonomy, canonical_hash(body), tuple(findings))
