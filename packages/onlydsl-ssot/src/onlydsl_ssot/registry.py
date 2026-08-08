from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from .io import atomic_write_text
from .reader import SsotReader


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    project_id: str
    ssot_uri: str
    path_uri: str
    revision: str
    integrity: str
    completeness: str


def render_registry(entries: tuple[RegistryEntry, ...]) -> str:
    rows = ["PROJECT_REGISTRY onlydsl"]
    for entry in sorted(entries, key=lambda item: item.project_id):
        rows.extend([
            "PROJECT " + json.dumps(entry.project_id), "  SSOT_URI " + entry.ssot_uri,
            "  PATH " + json.dumps(entry.path_uri), "  REVISION " + entry.revision,
            "  INTEGRITY " + entry.integrity, "  COMPLETENESS " + entry.completeness,
            "END_PROJECT",
        ])
    rows.append("END_PROJECT_REGISTRY")
    return "\n".join(rows) + "\n"


def parse_registry(text: str) -> tuple[RegistryEntry, ...]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "PROJECT_REGISTRY onlydsl" or lines[-1] != "END_PROJECT_REGISTRY":
        raise ValueError("invalid project registry")
    entries: list[RegistryEntry] = []
    index = 1
    while index < len(lines) - 1:
        start = shlex.split(lines[index])
        if len(start) != 2 or start[0] != "PROJECT":
            raise ValueError("invalid registry PROJECT")
        fields: dict[str, str] = {}
        index += 1
        while index < len(lines) and lines[index] != "END_PROJECT":
            key, _, value = lines[index].partition(" ")
            fields[key] = shlex.split(value)[0] if value else ""
            index += 1
        required = {"SSOT_URI", "PATH", "REVISION", "INTEGRITY", "COMPLETENESS"}
        if set(fields) != required:
            raise ValueError("registry entry fields differ")
        entries.append(RegistryEntry(start[1], fields["SSOT_URI"], fields["PATH"], fields["REVISION"], fields["INTEGRITY"], fields["COMPLETENESS"]))
        index += 1
    return tuple(entries)


class ProjectRegistry:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else Path.home() / ".onlydsl/projects/registry.dsl"

    def entries(self) -> tuple[RegistryEntry, ...]:
        return parse_registry(self.path.read_text(encoding="utf-8")) if self.path.exists() else ()

    def register(self, project_root: str | Path) -> RegistryEntry:
        reader = SsotReader(project_root)
        manifest = reader.verified_manifest()
        entry = RegistryEntry(
            manifest.project_id, "urn:subactor:ssot:" + manifest.revision_hash,
            reader.ssot_root.as_uri(), manifest.revision_hash, manifest.integrity, manifest.completeness,
        )
        values = {item.project_id: item for item in self.entries()}
        values[entry.project_id] = entry
        atomic_write_text(self.path, render_registry(tuple(values.values())))
        return entry
