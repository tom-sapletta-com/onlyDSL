from __future__ import annotations

from dataclasses import dataclass


class SsotError(RuntimeError):
    pass


class SsotConflict(SsotError):
    pass


class SsotValidationError(SsotError):
    pass


@dataclass(frozen=True, slots=True)
class SsotManifest:
    project_id: str
    revision_hash: str
    parent_hash: str | None
    created_at: str
    sections: dict[str, str]
    files: dict[str, str]
    receipts: tuple[str, ...]
    integrity: str
    completeness: str


@dataclass(frozen=True, slots=True)
class CandidateRevision:
    candidate_id: str
    project_id: str
    base_revision: str
    created_at: str
    file_hashes: dict[str, str]
    evidence_uris: tuple[str, ...]
    state: str = "proposed"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    candidate_id: str
    ok: bool
    base_revision: str
    candidate_revision: str
    issues: tuple[str, ...]
    integrity: str | None = None
    completeness: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionApproval:
    authority_contract_hash: str
    testql_receipts: tuple[str, ...]
    eql_receipts: tuple[str, ...]
    integrity: str = "pass"
    completeness: str = "complete"
    allow_incomplete: bool = False
