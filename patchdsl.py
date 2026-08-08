from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_FENCE_RE = re.compile(r"^```patchdsl\s*\n(?P<body>.*)\n```\s*$", re.S | re.I)
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class PatchDslError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PatchChange:
    path: str
    base_sha256: str
    diff: str


@dataclass(frozen=True, slots=True)
class PatchDocument:
    patch_id: str
    summary: str
    changes: tuple[PatchChange, ...]


def _json_string(raw: str, label: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatchDslError(f"{label} must be a JSON string") from exc
    if not isinstance(value, str):
        raise PatchDslError(f"{label} must be a JSON string")
    return value


def parse_patchdsl(markdown: str) -> PatchDocument:
    match = _FENCE_RE.fullmatch(markdown.strip())
    if not match:
        raise PatchDslError("expected exactly one patchdsl block and no outside prose")
    lines = [line.strip() for line in match.group("body").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("PATCH ") or lines[-1] != "END_PATCH":
        raise PatchDslError("invalid PATCH envelope")
    patch_id = lines[0].split(None, 1)[1]
    if not _ID_RE.fullmatch(patch_id):
        raise PatchDslError("invalid patch id")
    if len(lines) < 4 or not lines[1].startswith("SUMMARY "):
        raise PatchDslError("PATCH requires SUMMARY")
    summary = _json_string(lines[1][len("SUMMARY "):], "SUMMARY")
    changes: list[PatchChange] = []
    i = 2
    while i < len(lines) - 1:
        if lines[i] not in {"CHANGE", "BLOCK", "BLOCK CHANGE"}:
            raise PatchDslError(f"unexpected directive {lines[i]!r}")
        if i + 4 >= len(lines):
            raise PatchDslError("truncated CHANGE block")
        path_line, hash_line, diff_line, end_line = lines[i + 1:i + 5]
        if not path_line.startswith("PATH "):
            raise PatchDslError("CHANGE requires PATH")
        if not hash_line.startswith("BASE_SHA256 "):
            raise PatchDslError("CHANGE requires BASE_SHA256")
        if not diff_line.startswith("DIFF "):
            raise PatchDslError("CHANGE requires DIFF")
        if end_line not in {"END", "END_CHANGE"}:
            raise PatchDslError("CHANGE requires END")
        path = _json_string(path_line[len("PATH "):], "PATH")
        base_hash = hash_line[len("BASE_SHA256 "):].strip()
        diff = _json_string(diff_line[len("DIFF "):], "DIFF")
        if not _HASH_RE.fullmatch(base_hash):
            raise PatchDslError("invalid BASE_SHA256")
        if not diff.endswith("\n") or not diff.startswith("diff --git a/"):
            raise PatchDslError("DIFF must be a complete git-style unified diff ending with newline")
        changes.append(PatchChange(path, base_hash, diff))
        i += 5
    if not changes:
        raise PatchDslError("PATCH requires at least one CHANGE")
    if len(changes) > 3:
        raise PatchDslError("PATCH may change at most 3 files")
    if len({change.path for change in changes}) != len(changes):
        raise PatchDslError("duplicate PATH in PATCH")
    return PatchDocument(patch_id, summary, tuple(changes))


def validate_patch_policy(doc: PatchDocument, workspace: str | Path) -> list[str]:
    root = Path(workspace).resolve()
    errors: list[str] = []
    # This function validates structure and integrity only. AQL is the sole
    # authority source and is evaluated separately against OQL + URI Process.
    allowed_suffixes = {
        ".py", ".html", ".css", ".js", ".mjs", ".ts", ".yaml", ".yml",
        ".json", ".toml", ".txt", ".md", ".sh",
    }
    total_added = total_removed = 0
    for change in doc.changes:
        posix = PurePosixPath(change.path)
        if posix.is_absolute() or ".." in posix.parts or str(posix) != change.path:
            errors.append(f"unsafe path {change.path!r}")
            continue
        if change.path == ".env" or change.path.startswith((
            ".git/", "secrets/", "state/", "runtime/evolution/",
            "config/contracts/", "config/process-packs/",
        )) or change.path in {
            "aql.py", "diagnostics.py", "governance.py", "patchdsl.py", "scripts/autonomous_repair.py",
        }:
            errors.append(f"path {change.path!r} cannot cross PatchDSL")
            continue
        if posix.name != "Dockerfile" and posix.suffix.lower() not in allowed_suffixes:
            errors.append(f"path {change.path!r} has a forbidden file type")
        target = (root / change.path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"path {change.path!r} escapes workspace")
            continue
        if not target.is_file():
            errors.append(f"target {change.path!r} does not exist")
            continue
        digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != change.base_sha256:
            errors.append(f"base hash mismatch for {change.path}")
        expected_old = f"--- a/{change.path}\n"
        expected_new = f"+++ b/{change.path}\n"
        if expected_old not in change.diff or expected_new not in change.diff:
            errors.append(f"diff headers do not match PATH {change.path}")
        for line in change.diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                total_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_removed += 1
    if total_added > 200 or total_removed > 200:
        errors.append("patch exceeds the 200 added/removed line limit")
    return errors


def validate_patch_markdown(markdown: str, workspace: str | Path | None = None) -> list[str]:
    try:
        doc = parse_patchdsl(markdown)
        return validate_patch_policy(doc, workspace) if workspace is not None else []
    except Exception as exc:
        return [str(exc)]
