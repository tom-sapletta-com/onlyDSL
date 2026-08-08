from __future__ import annotations

from pathlib import Path

from digital_twin import validate_twin_markdown
from source_ingest import validate_sourceindex_markdown

from onlydsl_contracts.dsl.assumption import parse_assumptions
from onlydsl_contracts.dsl.claim import parse_claims
from onlydsl_contracts.dsl.development_evidence import parse_development_evidence
from onlydsl_contracts.dsl.evidence_set import parse_evidence_set
from onlydsl_contracts.dsl.parameter_contract import parse_parameter_contracts
from onlydsl_contracts.dsl.repair_plan import parse_repair_plan
from onlydsl_contracts.dsl.spatial_class import parse_spatial_class
from onlydsl_contracts.dsl.trust import parse_trust_policy
from onlydsl.runtime.integrity import parse_project_integrity
from onlydsl_ssot.validation import (
    PROTECTED_PARTS,
    basic_validate_tree,
    render_validation,
)


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
    elif name == "development-evidence.dsl":
        parse_development_evidence(content)
    elif name == "source-index.dsl":
        result = validate_sourceindex_markdown(content)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
    elif name == "twin.dsl":
        result = validate_twin_markdown(content)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
    return None, None


def validate_tree(tree: Path) -> tuple[dict[str, str], tuple[str, ...], str | None, str | None]:
    hashes, base_issues, _, _ = basic_validate_tree(tree)
    issues = list(base_issues)
    integrity: str | None = None
    completeness: str | None = None
    if any(issue.startswith("TREE_INVALID:") for issue in issues):
        return hashes, tuple(issues), integrity, completeness
    for relative in hashes:
        parts = {part.lower() for part in Path(relative).parts}
        if parts & PROTECTED_PARTS or relative.lower().endswith(".aql"):
            continue
        path = tree / relative
        if path.suffix.lower() in {".dsl", ".projectdsl", ".md"}:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "PROFILE aql:contract" in content or "ALLOW URI_PROCESS" in content:
                continue
            if path.suffix.lower() == ".dsl" and not content.strip():
                continue
            try:
                parsed_integrity, parsed_completeness = _validate_known_dsl(relative, content)
                integrity = parsed_integrity or integrity
                completeness = parsed_completeness or completeness
            except Exception as exc:
                issues.append(f"DSL_INVALID:{relative}:{type(exc).__name__}:{exc}")
    return hashes, tuple(dict.fromkeys(issues)), integrity, completeness
