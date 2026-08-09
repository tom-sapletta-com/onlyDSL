"""Datowe modele domeny TwinDSL, niezależne od parsera i renderera."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TwinNode:
    id: str
    kind: str
    spatial_class: str = ""
    responsibility: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TwinCapability:
    id: str
    uri: str = ""
    owner: str = ""
    input_type: str = ""
    output_type: str = ""
    responsibility: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TwinInvariant:
    id: str
    assertions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TwinEdge:
    source: str
    target: str
    relation: str


@dataclass(slots=True)
class TwinSourceRef:
    id: str
    digest: str
    path: str = ""


@dataclass(slots=True)
class TwinDocument:
    name: str
    version: int
    revision: int
    intent_fingerprint: str
    intent_summary: str
    goals: list[str] = field(default_factory=list)
    nodes: dict[str, TwinNode] = field(default_factory=dict)
    capabilities: dict[str, TwinCapability] = field(default_factory=dict)
    edges: list[TwinEdge] = field(default_factory=list)
    invariants: dict[str, TwinInvariant] = field(default_factory=dict)
    evolution_allow: list[str] = field(default_factory=list)
    evolution_require: list[str] = field(default_factory=list)
    evolution_forbid: list[str] = field(default_factory=list)
    sources: dict[str, TwinSourceRef] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BuildTask:
    id: str
    target_uri: str
    action: str
    acceptance: str
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BuildPlan:
    twin: str
    revision: int
    phases: list[tuple[str, list[BuildTask]]]
