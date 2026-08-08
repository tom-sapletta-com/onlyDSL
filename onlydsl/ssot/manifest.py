from __future__ import annotations

import hashlib
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from onlydsl.dsl.common import HASH_RE, canonical_hash

from .model import SsotManifest, SsotValidationError

SCHEMA = "onlydsl.ssot/v1"
INTEGRITY_VALUES = {"pass", "fail", "unverified"}
COMPLETENESS_VALUES = {"complete", "incomplete", "unverified"}
IMMUTABLE_URN_RE = re.compile(r"urn:[A-Za-z0-9][A-Za-z0-9._:-]*:sha256:[0-9a-f]{64}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def is_immutable_urn(value: str) -> bool:
    return bool(IMMUTABLE_URN_RE.fullmatch(value))


def normalize_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise SsotValidationError(f"invalid SSOT relative path: {value!r}")
    return path.as_posix()


def collect_file_hashes(tree: Path) -> dict[str, str]:
    if not tree.is_dir():
        raise SsotValidationError(f"SSOT tree does not exist: {tree}")
    files: dict[str, str] = {}
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            raise SsotValidationError(f"SSOT symlink is forbidden: {path}")
        if path.is_file():
            relative = normalize_relative_path(path.relative_to(tree).as_posix())
            files[relative] = digest_bytes(path.read_bytes())
    return files


def calculate_section_hashes(files: dict[str, str]) -> dict[str, str]:
    grouped: dict[str, dict[str, str]] = {}
    for relative, digest in sorted(files.items()):
        path = PurePosixPath(normalize_relative_path(relative))
        section = path.parts[0] if len(path.parts) > 1 else path.stem
        grouped.setdefault(section, {})[path.as_posix()] = digest
    return {section: canonical_hash(children) for section, children in sorted(grouped.items())}


def calculate_revision_hash(project_id: str, sections: dict[str, str]) -> str:
    return canonical_hash({"schema": SCHEMA, "project_id": project_id, "sections": dict(sorted(sections.items()))})


def create_manifest(
    project_id: str, files: dict[str, str], *, parent_hash: str | None = None,
    receipts: tuple[str, ...] = (), integrity: str = "unverified",
    completeness: str = "unverified", created_at: str | None = None,
) -> SsotManifest:
    sections = calculate_section_hashes(files)
    return SsotManifest(
        project_id=project_id,
        revision_hash=calculate_revision_hash(project_id, sections),
        parent_hash=parent_hash,
        created_at=created_at or utc_now(),
        sections=sections,
        files=dict(sorted(files.items())),
        receipts=tuple(dict.fromkeys(receipts)),
        integrity=integrity.lower(),
        completeness=completeness.lower(),
    )


def validate_manifest(manifest: SsotManifest) -> list[str]:
    issues: list[str] = []
    if not manifest.project_id or any(character.isspace() for character in manifest.project_id):
        issues.append("PROJECT_ID_INVALID")
    if manifest.parent_hash is not None and not HASH_RE.fullmatch(manifest.parent_hash):
        issues.append("PARENT_HASH_INVALID")
    if manifest.integrity not in INTEGRITY_VALUES:
        issues.append("INTEGRITY_INVALID")
    if manifest.completeness not in COMPLETENESS_VALUES:
        issues.append("COMPLETENESS_INVALID")
    for name, digest in (*manifest.sections.items(), *manifest.files.items()):
        if not name or not HASH_RE.fullmatch(digest):
            issues.append(f"ENTRY_INVALID:{name}")
    expected_sections = calculate_section_hashes(manifest.files)
    if manifest.sections != expected_sections:
        issues.append("SECTION_HASH_MISMATCH")
    if manifest.revision_hash != calculate_revision_hash(manifest.project_id, expected_sections):
        issues.append("REVISION_HASH_MISMATCH")
    if any(not is_immutable_urn(receipt) for receipt in manifest.receipts):
        issues.append("RECEIPT_URI_NOT_IMMUTABLE")
    return issues


def render_manifest(manifest: SsotManifest) -> str:
    issues = validate_manifest(manifest)
    if issues:
        raise SsotValidationError("; ".join(issues))
    rows = [
        f"SSOT {manifest.project_id}", f"SCHEMA {SCHEMA}",
        f"REVISION {manifest.revision_hash}", f"PARENT {manifest.parent_hash or 'none'}",
        f"CREATED_AT {json.dumps(manifest.created_at)}",
    ]
    rows.extend(f"SECTION {json.dumps(name, ensure_ascii=False)} {digest}" for name, digest in sorted(manifest.sections.items()))
    rows.extend(f"FILE {json.dumps(name, ensure_ascii=False)} {digest}" for name, digest in sorted(manifest.files.items()))
    rows.extend([
        f"INTEGRITY {manifest.integrity}", f"COMPLETENESS {manifest.completeness}",
    ])
    rows.extend(f"RECEIPT {json.dumps(uri, ensure_ascii=False)}" for uri in manifest.receipts)
    rows.append("END_SSOT")
    return "\n".join(rows) + "\n"


def parse_manifest(text: str) -> SsotManifest:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("SSOT ") or lines[-1] != "END_SSOT":
        raise SsotValidationError("invalid SSOT manifest envelope")
    project_id = lines[0].split(None, 1)[1]
    scalars: dict[str, str] = {}
    sections: dict[str, str] = {}
    files: dict[str, str] = {}
    receipts: list[str] = []
    for line in lines[1:-1]:
        parts = shlex.split(line)
        if not parts:
            continue
        key = parts[0]
        if key in {"SECTION", "FILE"} and len(parts) == 3:
            target = sections if key == "SECTION" else files
            if parts[1] in target:
                raise SsotValidationError(f"duplicate {key} {parts[1]}")
            target[parts[1]] = parts[2]
        elif key == "RECEIPT" and len(parts) == 2:
            receipts.append(parts[1])
        elif len(parts) == 2 and key in {"SCHEMA", "REVISION", "PARENT", "CREATED_AT", "INTEGRITY", "COMPLETENESS"}:
            if key in scalars:
                raise SsotValidationError(f"duplicate manifest field {key}")
            scalars[key] = parts[1]
        else:
            raise SsotValidationError(f"invalid manifest line: {line}")
    required = {"SCHEMA", "REVISION", "PARENT", "CREATED_AT", "INTEGRITY", "COMPLETENESS"}
    if set(scalars) != required or scalars.get("SCHEMA") != SCHEMA:
        raise SsotValidationError("manifest requires exact schema/revision/parent/time/integrity/completeness")
    manifest = SsotManifest(
        project_id, scalars["REVISION"], None if scalars["PARENT"] == "none" else scalars["PARENT"],
        scalars["CREATED_AT"], sections, files, tuple(receipts),
        scalars["INTEGRITY"], scalars["COMPLETENESS"],
    )
    issues = validate_manifest(manifest)
    if issues:
        raise SsotValidationError("; ".join(issues))
    return manifest
