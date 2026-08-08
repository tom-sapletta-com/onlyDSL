from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from onlydsl.dsl.common import ID_RE

from .diff import calculate_diff, render_diff
from .io import atomic_write_json, atomic_write_text
from .manifest import (
    calculate_revision_hash,
    calculate_section_hashes,
    collect_file_hashes,
    is_immutable_urn,
    normalize_relative_path,
    utc_now,
)
from .model import CandidateRevision, SsotValidationError, ValidationReport
from .validation import render_validation, validate_tree


def _candidate_from_dict(value: dict) -> CandidateRevision:
    return CandidateRevision(
        str(value["candidate_id"]), str(value["project_id"]), str(value["base_revision"]),
        str(value["created_at"]), {str(k): str(v) for k, v in value["file_hashes"].items()},
        tuple(str(item) for item in value.get("evidence_uris", [])), str(value.get("state", "proposed")),
    )


def load_candidate(directory: Path) -> CandidateRevision:
    try:
        return _candidate_from_dict(json.loads((directory / "manifest.json").read_text(encoding="utf-8")))
    except Exception as exc:
        raise SsotValidationError(f"invalid candidate manifest: {directory}") from exc


def save_candidate(directory: Path, value: CandidateRevision) -> None:
    payload = asdict(value)
    payload["evidence_uris"] = list(value.evidence_uris)
    atomic_write_json(directory / "manifest.json", payload)


def create_candidate(
    candidates_root: Path, current_tree: Path, *, project_id: str, base_revision: str,
    updates: dict[str, bytes] | None = None, candidate_id: str | None = None,
    removals: tuple[str, ...] = (), evidence_uris: tuple[str, ...] = (),
) -> CandidateRevision:
    candidate_id = candidate_id or ("candidate-" + utc_now().replace(":", "").replace("-", "").replace(".", "") + "-" + uuid.uuid4().hex[:8])
    if not ID_RE.fullmatch(candidate_id):
        raise SsotValidationError(f"invalid candidate id: {candidate_id}")
    directory = candidates_root / candidate_id
    if directory.exists():
        raise SsotValidationError(f"candidate already exists: {candidate_id}")
    temporary = candidates_root / ("." + candidate_id + ".tmp")
    candidates_root.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    tree = temporary / "tree"
    current_files = collect_file_hashes(current_tree)
    shutil.copytree(current_tree, tree)
    normalized_updates = {
        normalize_relative_path(relative): content for relative, content in (updates or {}).items()
    }
    normalized_removals = tuple(normalize_relative_path(relative) for relative in removals)
    if set(normalized_removals) & set(normalized_updates):
        shutil.rmtree(temporary)
        raise SsotValidationError("candidate cannot update and remove the same path")
    for normalized in normalized_removals:
        target = tree / normalized
        if target.is_symlink() or not target.is_file():
            shutil.rmtree(temporary)
            raise SsotValidationError(f"candidate removal target is not a regular file: {normalized}")
        target.unlink()
    for normalized, content in normalized_updates.items():
        target = tree / normalized
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    file_hashes, issues, _, _ = validate_tree(tree)
    if any(issue.startswith(("AUTHORITY_PATH_FORBIDDEN", "AUTHORITY_CONTENT_FORBIDDEN")) for issue in issues):
        shutil.rmtree(temporary)
        raise SsotValidationError("; ".join(issues))
    immutable_evidence = tuple(dict.fromkeys(evidence_uris))
    if any(not is_immutable_urn(uri) for uri in immutable_evidence):
        shutil.rmtree(temporary)
        raise SsotValidationError("candidate evidence must use immutable urn:*:sha256:<64-hex> identifiers")
    value = CandidateRevision(candidate_id, project_id, base_revision, utc_now(), file_hashes, immutable_evidence)
    save_candidate(temporary, value)
    atomic_write_text(
        temporary / "semantic.diff.dsl",
        render_diff(candidate_id, base_revision, calculate_diff(current_files, file_hashes)),
    )
    temporary.rename(directory)
    return value


def validate_candidate(directory: Path, *, current_revision: str, current_files: dict[str, str]) -> ValidationReport:
    candidate = load_candidate(directory)
    tree = directory / "tree"
    files, tree_issues, integrity, completeness = validate_tree(tree)
    issues = list(tree_issues)
    if candidate.base_revision != current_revision:
        issues.append(f"STALE_BASE_REVISION:{candidate.base_revision}:{current_revision}")
    if files != candidate.file_hashes:
        issues.append("CANDIDATE_MANIFEST_FILE_HASH_MISMATCH")
    sections = calculate_section_hashes(files)
    revision = calculate_revision_hash(candidate.project_id, sections)
    changes = calculate_diff(current_files, files)
    report = ValidationReport(candidate.candidate_id, not issues, candidate.base_revision, revision, tuple(issues), integrity, completeness)
    atomic_write_text(directory / "semantic.diff.dsl", render_diff(candidate.candidate_id, candidate.base_revision, changes))
    atomic_write_text(directory / "validation.dsl", render_validation(
        candidate.candidate_id, base_revision=candidate.base_revision, candidate_revision=revision,
        issues=tuple(issues), integrity=integrity, completeness=completeness,
    ))
    save_candidate(directory, CandidateRevision(
        candidate.candidate_id, candidate.project_id, candidate.base_revision, candidate.created_at,
        candidate.file_hashes, candidate.evidence_uris, "validated" if not issues else "rejected",
    ))
    return report
