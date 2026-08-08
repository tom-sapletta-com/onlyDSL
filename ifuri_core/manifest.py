"""File adapter and compatibility exports for capability manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from onlydsl_core.capabilities import (
    Capability,
    CapabilityRegistry as CoreCapabilityRegistry,
    ManifestError,
    ResolvedCapability,
    TransportPolicy,
)


class CapabilityRegistry(CoreCapabilityRegistry):
    @classmethod
    def from_file(cls, path: str | Path) -> "CapabilityRegistry":
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        raw: Any
        if source.suffix.lower() in {".yaml", ".yml"}:
            raw = yaml.safe_load(text)
        else:
            raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ManifestError("manifest root must be an object")
        return cls.from_mapping(raw)


__all__ = [
    "Capability", "CapabilityRegistry", "ManifestError", "ResolvedCapability",
    "TransportPolicy",
]
