from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from onlydsl_contracts.dsl.common import HASH_RE, ID_RE
from onlydsl_contracts.ssot import CandidateRevision, PromotionApproval, SsotConflict, SsotManifest, SsotValidationError, ValidationReport

from .candidate import create_candidate, load_candidate, save_candidate, validate_candidate
from .io import atomic_write_json, atomic_write_text, fsync_directory
from .manifest import collect_file_hashes, create_manifest, is_immutable_urn, render_manifest
from .reader import SsotReader
from .validation import TreeValidator, basic_validate_tree


class SsotStore(SsotReader):
    def __init__(self, project_root: str | Path, *, validator: TreeValidator = basic_validate_tree):
        super().__init__(project_root)
        self.validator = validator
        self.candidate_root = self.ssot_root / "candidate"
        self.staging_root = self.ssot_root / ".staging"
        self.revisions_root = self.ssot_root / "revisions"
        self.onlydsl_root = self.project_root / ".onlydsl"
        self.lock_root = self.onlydsl_root / "locks"
        self.lock_path = self.lock_root / "ssot-promotion.lock"

    def initialize(self, project_id: str, *, project_dsl: str | Path | None = None) -> SsotManifest:
        if self.manifest_path.exists():
            return self.verified_manifest()
        if not project_id or any(character.isspace() for character in project_id):
            raise SsotValidationError("project id must be a non-empty token")
        self.current_root.mkdir(parents=True, exist_ok=False)
        for path in (
            self.candidate_root, self.staging_root, self.revisions_root,
            self.ssot_root / "receipts/eql", self.ssot_root / "receipts/testql",
            self.ssot_root / "receipts/geometry", self.ssot_root / "receipts/development",
            self.ssot_root / "receipts/mutation", self.onlydsl_root / "authority/grants",
            self.onlydsl_root / "process-packs", self.onlydsl_root / "cache",
            self.lock_root, self.onlydsl_root / "queue", self.onlydsl_root / "runtime",
        ):
            path.mkdir(parents=True, exist_ok=True)
        source = Path(project_dsl).resolve() if project_dsl else self.project_root / "project.projectdsl"
        target = self.current_root / "project.projectdsl"
        if source.is_file():
            target.write_bytes(source.read_bytes())
        else:
            target.write_text(f"PROJECT {project_id}\nNAME {json.dumps(project_id)}\n", encoding="utf-8")
        atomic_write_text(self.ssot_root / ".gitignore", "candidate/\n.staging/\nreceipts/runtime-heavy/\n")
        atomic_write_text(self.onlydsl_root / ".gitignore", "cache/\nlocks/\nqueue/\nruntime/\n")
        atomic_write_text(self.ssot_root / "README.md", "# SSOT\n\nSingle Source of Accepted Truth. `current/` is promoted state; `candidate/` is not authoritative.\n")
        manifest = create_manifest(project_id, collect_file_hashes(self.current_root))
        text = render_manifest(manifest)
        atomic_write_text(self.manifest_path, text)
        atomic_write_text(self._history_path(manifest.revision_hash), text)
        return manifest

    def create_candidate(
        self, *, updates: dict[str, bytes] | None = None, candidate_id: str | None = None,
        removals: tuple[str, ...] = (), evidence_uris: tuple[str, ...] = (),
    ) -> CandidateRevision:
        current = self.verified_manifest()
        return create_candidate(
            self.candidate_root, self.current_root, project_id=current.project_id,
            base_revision=current.revision_hash, updates=updates, candidate_id=candidate_id,
            removals=removals, evidence_uris=evidence_uris, validator=self.validator,
        )

    def validate_candidate(self, candidate_id: str) -> ValidationReport:
        current = self.verified_manifest()
        return validate_candidate(
            self._candidate_directory(candidate_id), current_revision=current.revision_hash,
            current_files=current.files, validator=self.validator,
        )

    def candidate_diff(self, candidate_id: str) -> str:
        directory = self._candidate_directory(candidate_id)
        self.validate_candidate(candidate_id)
        return (directory / "semantic.diff.dsl").read_text(encoding="utf-8")

    def promote(self, candidate_id: str, approval: PromotionApproval) -> SsotManifest:
        self._validate_approval(approval)
        with self._promotion_lock():
            current, candidate, directory, report, integrity, completeness = self._prepare_promotion(candidate_id, approval)
            stage, manifest = self._stage_promotion(candidate_id, current, directory, report, approval, integrity, completeness)
            self._commit_promotion(stage, manifest, current, candidate_id, approval)
            save_candidate(directory, CandidateRevision(candidate.candidate_id, candidate.project_id, candidate.base_revision, candidate.created_at, candidate.file_hashes, candidate.evidence_uris, "promoted"))
            return self.verified_manifest()

    def _prepare_promotion(self, candidate_id: str, approval: PromotionApproval):
        current = self.verified_manifest()
        directory = self._candidate_directory(candidate_id)
        candidate = load_candidate(directory)
        if candidate.base_revision != current.revision_hash:
            raise SsotConflict(f"STALE_BASE_REVISION:{candidate.base_revision}:{current.revision_hash}")
        report = validate_candidate(directory, current_revision=current.revision_hash, current_files=current.files, validator=self.validator)
        if not report.ok:
            raise SsotValidationError("; ".join(report.issues))
        if report.candidate_revision == current.revision_hash:
            raise SsotConflict("NO_SEMANTIC_CHANGE")
        integrity = (report.integrity or approval.integrity).lower()
        completeness = (report.completeness or approval.completeness).lower()
        if integrity != "pass":
            raise SsotValidationError("SSOT_PROMOTION_REQUIRES_INTEGRITY_PASS")
        if completeness != "complete" and not approval.allow_incomplete:
            raise SsotValidationError("SSOT_INCOMPLETE_REQUIRES_EXPLICIT_GRANT")
        return current, candidate, directory, report, integrity, completeness

    def _stage_promotion(self, candidate_id, current, directory, report, approval, integrity, completeness):
        stage = self.staging_root / (candidate_id + "-" + uuid.uuid4().hex[:8])
        shutil.copytree(directory / "tree", stage)
        receipts = tuple(dict.fromkeys((*approval.testql_receipts, *approval.eql_receipts, "urn:subactor:ssot-promotion:" + report.candidate_revision)))
        manifest = create_manifest(current.project_id, collect_file_hashes(stage), parent_hash=current.revision_hash, receipts=receipts, integrity=integrity, completeness=completeness)
        if manifest.revision_hash != report.candidate_revision:
            shutil.rmtree(stage)
            raise SsotConflict("CANDIDATE_CHANGED_AFTER_VALIDATION")
        return stage, manifest

    def _commit_promotion(self, stage, manifest, current, candidate_id, approval) -> None:
        manifest_text = render_manifest(manifest)
        old_manifest_text = self.manifest_path.read_text(encoding="utf-8")
        backup = self.staging_root / ("previous-" + uuid.uuid4().hex[:8])
        swapped = False
        try:
            os.replace(self.current_root, backup); os.replace(stage, self.current_root); swapped = True
            fsync_directory(self.ssot_root); atomic_write_text(self.manifest_path, manifest_text)
            self._write_append_only(self._history_path(manifest.revision_hash), manifest_text)
            self._write_json_append_only(self.ssot_root / "receipts/mutation" / (manifest.revision_hash.split(":", 1)[1] + ".json"), self._promotion_receipt(candidate_id, manifest, current, approval))
        except Exception:
            if swapped:
                failed = self.staging_root / ("failed-" + uuid.uuid4().hex[:8])
                if self.current_root.exists(): os.replace(self.current_root, failed)
                if backup.exists(): os.replace(backup, self.current_root)
                atomic_write_text(self.manifest_path, old_manifest_text)
            raise
        finally:
            if stage.exists(): shutil.rmtree(stage)
        if backup.exists(): shutil.rmtree(backup)

    def _promotion_receipt(self, candidate_id, manifest, current, approval) -> dict:
        return {"schema": "onlydsl.ssot-promotion-receipt/v1", "state": "accepted", "candidate_id": candidate_id, "project_id": manifest.project_id, "from_revision": current.revision_hash, "revision": manifest.revision_hash, "authority_contract_hash": approval.authority_contract_hash, "testql_receipts": list(approval.testql_receipts), "eql_receipts": list(approval.eql_receipts), "integrity": manifest.integrity, "completeness": manifest.completeness, "ssot_uri": "urn:subactor:ssot:" + manifest.revision_hash}

    def _candidate_directory(self, candidate_id: str) -> Path:
        if not ID_RE.fullmatch(candidate_id):
            raise SsotValidationError(f"invalid candidate id: {candidate_id}")
        directory = self.candidate_root / candidate_id
        if directory.is_symlink() or not directory.is_dir() or directory.parent != self.candidate_root:
            raise SsotValidationError(f"candidate not found: {candidate_id}")
        return directory

    def _history_path(self, revision_hash: str) -> Path:
        return self.revisions_root / (revision_hash.split(":", 1)[1] + ".manifest.dsl")

    def _write_append_only(self, path: Path, content: str) -> None:
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise SsotConflict(f"APPEND_ONLY_CONFLICT:{path}")
            return
        atomic_write_text(path, content)

    def _write_json_append_only(self, path: Path, value: dict) -> None:
        expected = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != expected:
                raise SsotConflict(f"APPEND_ONLY_CONFLICT:{path}")
            return
        atomic_write_json(path, value)

    def _validate_approval(self, approval: PromotionApproval) -> None:
        if not HASH_RE.fullmatch(approval.authority_contract_hash):
            raise SsotValidationError("AUTHORITY_CONTRACT_HASH_REQUIRED")
        if not approval.testql_receipts or any(not is_immutable_urn(uri) or "testql" not in uri.lower() for uri in approval.testql_receipts):
            raise SsotValidationError("IMMUTABLE_TESTQL_RECEIPT_REQUIRED")
        if not approval.eql_receipts or any(not is_immutable_urn(uri) or "eql" not in uri.lower() for uri in approval.eql_receipts):
            raise SsotValidationError("IMMUTABLE_EQL_RECEIPT_REQUIRED")

    @contextmanager
    def _promotion_lock(self):
        self.lock_root.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_path.mkdir()
        except FileExistsError as exc:
            if not self._recover_stale_lock():
                raise SsotConflict("SSOT_PROMOTION_WRITER_ALREADY_ACTIVE") from exc
            self.lock_path.mkdir()
        atomic_write_json(self.lock_path / "owner.json", {
            "pid": os.getpid(), "project": str(self.project_root), "created_at": time.time(),
        })
        try:
            yield
        finally:
            shutil.rmtree(self.lock_path, ignore_errors=True)

    def _recover_stale_lock(self) -> bool:
        try:
            owner = json.loads((self.lock_path / "owner.json").read_text(encoding="utf-8"))
            pid = int(owner["pid"])
            created_at = float(owner.get("created_at", self.lock_path.stat().st_mtime))
        except Exception:
            return False
        stale_after = float(os.getenv("SSOT_LOCK_STALE_SECONDS", "300"))
        if time.time() - created_at <= stale_after:
            return False
        try:
            os.kill(pid, 0)
            return False
        except ProcessLookupError:
            shutil.rmtree(self.lock_path)
            return True
        except PermissionError:
            return False
