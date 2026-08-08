"""Compatibility exports; use :mod:`onlydsl_contracts.ssot` in new code."""

from onlydsl_contracts.ssot import (
    CandidateRevision,
    PromotionApproval,
    SsotConflict,
    SsotError,
    SsotManifest,
    SsotValidationError,
    ValidationReport,
)

__all__ = [
    "CandidateRevision", "PromotionApproval", "SsotConflict", "SsotError",
    "SsotManifest", "SsotValidationError", "ValidationReport",
]
