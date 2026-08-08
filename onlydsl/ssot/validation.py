from __future__ import annotations

from pathlib import Path

from digital_twin import validate_twin_markdown
from source_ingest import validate_sourceindex_markdown

from onlydsl.dsl.assumption import parse_assumptions
from onlydsl.dsl.claim import parse_claims
from onlydsl.dsl.evidence_set import parse_evidence_set
from onlydsl.dsl.parameter_contract import parse_parameter_contracts
from onlydsl.dsl.repair_plan import parse_repair_plan
from onlydsl.dsl.spatial_class import parse_spatial_class
from onlydsl.dsl.trust import parse_trust_policy
from onlydsl.runtime.integrity import parse_project_integrity

from .manifest import collect_file_hashes

PROTECTED_PARTS = {"authority", "grants", "process-packs", "locks", "queue", "secrets", ".onlydsl"}


def _validate_known_dsl(path: str, content: str) -> tuple[str | None, str | None]:
    name = Path(path).name.lower()
    if name in {"assumptions.dsl", "assumption.dsl"}:
        parse_assumptions(content)
    elif name in {"evidence-set.dsl", "evidence-sets.dsl"}:
        parse_evidence_set(content)
    elif name in {"parameter-contract.dsl", "parameter-contracts.dsl"}:
        parse_parameter_contracts(content)
    elif name in {"spatial-class.dsl", "spatial-classes.dsl"}:
        parse_spatial_class(content)
    elif name == "repair-plan.dsl":
        parse_repair_plan(content)
    elif name == "project-integrity.dsl":
        integrity = parse_project_integrity(content)
        return integrity.integrity.lower(), integrity.evidence.lower()
    elif name in {"claims.dsl", "claim.dsl"}:
        parse_claims(content)
    elif name in {"trust.dsl", "trust-policy.dsl"}:
        parse_trust_policy(content)
    elif name == "source-index.dsl":
        result = validate_sourceindex_markdown(content)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
    elif name == "twin.dsl":
        result = validate_twin_markdown(content)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
    elif name.endswith(".dsl") and not content.strip():
        raise ValueError("empty DSL document")
    return None, None


def validate_tree(tree: Path) -> tuple[dict[str, str], tuple[str, ...], str | None, str | None]:
    issues: list[str] = []
    integrity: str | None = None
    completeness: str | None = None
    try:
        hashes = collect_file_hashes(tree)
    except Exception as exc:
        return {}, (f"TREE_INVALID:{type(exc).__name__}:{exc}",), None, None
    if not hashes:
        issues.append("SSOT_CURRENT_EMPTY")
    for relative in hashes:
        parts = {part.lower() for part in Path(relative).parts}
        if parts & PROTECTED_PARTS or relative.lower().endswith(".aql"):
            issues.append(f"AUTHORITY_PATH_FORBIDDEN:{relative}")
            continue
        path = tree / relative
        if path.suffix.lower() not in {".dsl", ".projectdsl", ".json", ".jsonl", ".md"}:
            issues.append(f"SSOT_FILE_TYPE_FORBIDDEN:{relative}")
            continue
        if path.suffix.lower() in {".dsl", ".projectdsl", ".md"}:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(f"SSOT_TEXT_INVALID_UTF8:{relative}")
                continue
            if "PROFILE aql:contract" in content or "ALLOW URI_PROCESS" in content:
                issues.append(f"AUTHORITY_CONTENT_FORBIDDEN:{relative}")
                continue
            try:
                parsed_integrity, parsed_completeness = _validate_known_dsl(relative, content)
                integrity = parsed_integrity or integrity
                completeness = parsed_completeness or completeness
            except Exception as exc:
                issues.append(f"DSL_INVALID:{relative}:{type(exc).__name__}:{exc}")
    return hashes, tuple(issues), integrity, completeness


def render_validation(
    candidate_id: str, *, base_revision: str, candidate_revision: str,
    issues: tuple[str, ...], integrity: str | None, completeness: str | None,
) -> str:
    rows = [
        "SSOT_VALIDATION " + candidate_id,
        "BASE_REVISION " + base_revision,
        "CANDIDATE_REVISION " + candidate_revision,
        "INTEGRITY " + (integrity or "unverified"),
        "COMPLETENESS " + (completeness or "unverified"),
    ]
    rows.extend("ISSUE " + issue for issue in issues)
    rows.extend(["RESULT " + ("PASS" if not issues else "FAIL"), "END_SSOT_VALIDATION"])
    return "\n".join(rows) + "\n"
