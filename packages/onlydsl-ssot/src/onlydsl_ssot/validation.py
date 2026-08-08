from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeAlias

from .manifest import collect_file_hashes

TreeValidation: TypeAlias = tuple[dict[str, str], tuple[str, ...], str | None, str | None]


class TreeValidator(Protocol):
    """Application-injected validation boundary for candidate trees."""

    def __call__(self, tree: Path) -> TreeValidation: ...


PROTECTED_PARTS = {"authority", "grants", "process-packs", "locks", "queue", "secrets", ".onlydsl"}
ALLOWED_SUFFIXES = {".dsl", ".projectdsl", ".json", ".jsonl", ".md"}
TEXT_SUFFIXES = {".dsl", ".projectdsl", ".md"}


def basic_validate_tree(tree: Path) -> TreeValidation:
    """Validate SSOT safety and encoding without knowing application DSLs."""
    issues: list[str] = []
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
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            issues.append(f"SSOT_FILE_TYPE_FORBIDDEN:{relative}")
            continue
        if suffix in TEXT_SUFFIXES:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(f"SSOT_TEXT_INVALID_UTF8:{relative}")
                continue
            if "PROFILE aql:contract" in content or "ALLOW URI_PROCESS" in content:
                issues.append(f"AUTHORITY_CONTENT_FORBIDDEN:{relative}")
            elif suffix == ".dsl" and not content.strip():
                issues.append(f"DSL_INVALID:{relative}:ValueError:empty DSL document")
    return hashes, tuple(issues), None, None


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
