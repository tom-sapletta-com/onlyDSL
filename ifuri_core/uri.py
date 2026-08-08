"""Compatibility exports; use :mod:`onlydsl_contracts.ifuri` in new code."""

from onlydsl_contracts.ifuri import IfUri, IfUriError, canonicalize

__all__ = ["IfUri", "IfUriError", "canonicalize"]
