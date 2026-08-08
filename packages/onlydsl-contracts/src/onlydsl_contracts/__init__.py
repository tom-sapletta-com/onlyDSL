"""Public, execution-free onlyDSL contracts."""

from importlib.metadata import PackageNotFoundError, version

from .ifuri import IfUri, IfUriError, canonicalize
from .ssot import (
    CandidateRevision,
    PromotionApproval,
    SsotConflict,
    SsotError,
    SsotManifest,
    SsotValidationError,
    ValidationReport,
)

try:
    __version__ = version("onlydsl-contracts")
except PackageNotFoundError:
    __version__ = "0.0.8"

__all__ = [
    "CandidateRevision", "IfUri", "IfUriError", "PromotionApproval",
    "SsotConflict", "SsotError", "SsotManifest", "SsotValidationError",
    "ValidationReport", "canonicalize",
]
