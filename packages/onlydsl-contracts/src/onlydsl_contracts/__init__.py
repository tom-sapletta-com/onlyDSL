"""Public, execution-free onlyDSL contracts."""

from importlib.metadata import PackageNotFoundError, version

from .ifuri import IfUri, IfUriError, canonicalize
from .dsl.development_evidence import (
    DevelopmentEvidenceBundle,
    create_development_evidence,
    parse_development_evidence,
    render_development_evidence,
)
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
    __version__ = "0+unknown"

__all__ = [
    "CandidateRevision", "DevelopmentEvidenceBundle", "IfUri", "IfUriError", "PromotionApproval",
    "SsotConflict", "SsotError", "SsotManifest", "SsotValidationError",
    "ValidationReport", "canonicalize", "create_development_evidence",
    "parse_development_evidence", "render_development_evidence",
]
