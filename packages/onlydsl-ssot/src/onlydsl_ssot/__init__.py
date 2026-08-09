"""Domain-neutral Single Source of Accepted Truth storage."""

from importlib.metadata import PackageNotFoundError, version

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

try:
    __version__ = version("onlydsl-ssot")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "CandidateRevision", "PromotionApproval", "SsotConflict", "SsotError",
    "SsotManifest", "SsotReader", "SsotStore", "SsotValidationError",
    "TreeValidation", "TreeValidator", "ValidationReport",
    "__version__", "basic_validate_tree",
]
