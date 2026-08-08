"""Domain-neutral Single Source of Accepted Truth storage."""

from onlydsl_contracts.ssot import (
    CandidateRevision,
    PromotionApproval,
    SsotConflict,
    SsotError,
    SsotManifest,
    SsotValidationError,
    ValidationReport,
)

from .reader import SsotReader
from .validation import TreeValidation, TreeValidator, basic_validate_tree
from .writer import SsotStore

__all__ = [
    "CandidateRevision", "PromotionApproval", "SsotConflict", "SsotError",
    "SsotManifest", "SsotReader", "SsotStore", "SsotValidationError",
    "TreeValidation", "TreeValidator", "ValidationReport",
    "basic_validate_tree",
]
