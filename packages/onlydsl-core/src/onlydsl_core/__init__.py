"""Public transport-neutral onlyDSL runtime primitives."""

from importlib.metadata import PackageNotFoundError, version

from .capabilities import (
    Capability,
    CapabilityRegistry,
    ManifestError,
    ResolvedCapability,
    TransportPolicy,
)
from .dsl_document import DslDocumentError, make_dsl_document, validate_dsl_document
from .envelope import EnvelopeCodec, EnvelopeError, EnvelopeView, MessageKind
from .ports import IfTransport, TransportError
from .runtime import IfuriRuntime, RouteDecision, RuntimeErrorIfuri

try:
    __version__ = version("onlydsl-core")
except PackageNotFoundError:
    __version__ = "0.0.8"

__all__ = [
    "Capability", "CapabilityRegistry", "DslDocumentError", "EnvelopeCodec",
    "EnvelopeError", "EnvelopeView", "IfTransport", "IfuriRuntime",
    "ManifestError", "MessageKind", "ResolvedCapability", "RouteDecision",
    "RuntimeErrorIfuri", "TransportError", "TransportPolicy",
    "make_dsl_document", "validate_dsl_document",
]
