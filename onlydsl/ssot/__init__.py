"""Single Source of Accepted Truth (SSAT), materialized under a project SSOT/."""

from .model import (
    CandidateRevision,
    PromotionApproval,
    SsotConflict,
    SsotError,
    SsotManifest,
    SsotValidationError,
    ValidationReport,
)
from .reader import SsotReader
from .writer import SsotStore

__all__ = [
    "CandidateRevision", "PromotionApproval", "SsotConflict", "SsotError",
    "SsotManifest", "SsotReader", "SsotStore", "SsotValidationError",
    "ValidationReport",
]
