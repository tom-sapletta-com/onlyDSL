from __future__ import annotations

import time
from pathlib import Path

from .manifest import collect_file_hashes, parse_manifest, validate_manifest
from .model import SsotManifest, SsotValidationError


class SsotReader:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.ssot_root = self.project_root / "SSOT"
        self.current_root = self.ssot_root / "current"
        self.manifest_path = self.ssot_root / "manifest.dsl"

    def manifest(self) -> SsotManifest:
        return parse_manifest(self.manifest_path.read_text(encoding="utf-8"))

    def verified_manifest(self, retries: int = 5) -> SsotManifest:
        last_issue = "SSOT_READ_INCONSISTENT"
        for _ in range(max(1, retries)):
            before = self.manifest_path.read_bytes()
            manifest = parse_manifest(before.decode("utf-8"))
            files = collect_file_hashes(self.current_root)
            after = self.manifest_path.read_bytes()
            if before != after:
                last_issue = "SSOT_MANIFEST_CHANGED_DURING_READ"
                time.sleep(0.01)
                continue
            issues = validate_manifest(manifest)
            if files != manifest.files:
                last_issue = "SSOT_CURRENT_FILE_HASH_MISMATCH"
                time.sleep(0.01)
                continue
            if issues:
                raise SsotValidationError("; ".join(issues))
            return manifest
        raise SsotValidationError(last_issue)

    def status(self) -> dict:
        manifest = self.verified_manifest()
        return {
            "schema": "onlydsl.ssot-status/v1",
            "project_id": manifest.project_id,
            "revision": manifest.revision_hash,
            "parent": manifest.parent_hash,
            "integrity": manifest.integrity,
            "completeness": manifest.completeness,
            "sections": manifest.sections,
            "files": len(manifest.files),
            "receipts": len(manifest.receipts),
            "ssot_uri": "urn:subactor:ssot:" + manifest.revision_hash,
        }

    def history(self) -> tuple[SsotManifest, ...]:
        manifests = []
        for path in sorted((self.ssot_root / "revisions").glob("*.manifest.dsl")):
            manifests.append(parse_manifest(path.read_text(encoding="utf-8")))
        return tuple(sorted(manifests, key=lambda item: (item.created_at, item.revision_hash)))
