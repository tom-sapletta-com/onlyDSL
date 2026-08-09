from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from onlydsl_contracts.ifuri import IfUri, IfUriError
from twin_models import BuildPlan, BuildTask, TwinCapability, TwinDocument, TwinEdge, TwinInvariant, TwinNode, TwinSourceRef

_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z][A-Za-z0-9_.-]*)\s*\n(?P<body>.*?)```", re.S)
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class TwinDslError(ValueError):
    pass


def normalize_intent(text: str) -> str:
    return " ".join(str(text).strip().split())


def intent_fingerprint(text: str) -> str:
    normalized = normalize_intent(text)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _quoted(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _json_string(raw: str, *, label: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TwinDslError(f"{label} must be a JSON string literal") from exc
    if not isinstance(value, str):
        raise TwinDslError(f"{label} must be a string")
    return value


def extract_twindsl(markdown: str) -> str:
    blocks = [m.group("body").strip() for m in _FENCE_RE.finditer(markdown) if m.group("lang").lower() == "twindsl"]
    if len(blocks) != 1:
        raise TwinDslError(f"expected exactly one twindsl block, found {len(blocks)}")
    outside = _FENCE_RE.sub("", markdown).strip()
    if outside:
        raise TwinDslError("prose outside twindsl block is forbidden")
    return blocks[0]


def _parse_json_text(raw: str, *, label: str) -> str:
    return _json_string(raw, label=label)


def _parse_twin_evidence(raw: str, *, line_no: int) -> str:
    evidence = raw.split(None, 1)[1].strip()
    if not _ID_RE.fullmatch(evidence):
        raise TwinDslError(f"line {line_no}: invalid EVIDENCE id")
    return evidence


def _parse_twin_node_block(lines: list[tuple[int, str]], index: int) -> tuple[int, TwinNode]:
    lineno, line = lines[index]
    match = re.fullmatch(r"NODE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+KIND\s+([A-Za-z][A-Za-z0-9_.-]{0,95})", line)
    if not match:
        raise TwinDslError(f"line {lineno}: invalid NODE header")
    node = TwinNode(match.group(1), match.group(2))
    index += 1
    while index < len(lines) and lines[index][1] != "END":
        subline_no, sub = lines[index]
        if sub.startswith("RESPONSIBILITY "):
            node.responsibility = _parse_json_text(sub[len("RESPONSIBILITY "):], label="RESPONSIBILITY")
        elif sub.startswith("SPATIAL_CLASS "):
            node.spatial_class = sub.split(None, 1)[1]
        elif sub.startswith("EVIDENCE "):
            node.evidence.append(_parse_twin_evidence(sub, line_no=subline_no))
        else:
            raise TwinDslError(f"line {subline_no}: unknown NODE directive {sub!r}")
        index += 1
    if index >= len(lines) or lines[index][1] != "END":
        raise TwinDslError(f"line {lineno}: NODE missing END")
    return index, node


def _parse_twin_capability_block(lines: list[tuple[int, str]], index: int) -> tuple[int, TwinCapability]:
    lineno, line = lines[index]
    cap_id = line.split(None, 1)[1].strip()
    if not _ID_RE.fullmatch(cap_id):
        raise TwinDslError(f"line {lineno}: invalid capability id")
    cap = TwinCapability(cap_id)
    index += 1
    while index < len(lines) and lines[index][1] != "END":
        subline_no, sub = lines[index]
        if sub.startswith("URI "):
            cap.uri = sub.split(None, 1)[1].strip()
        elif sub.startswith("OWNER "):
            cap.owner = sub.split(None, 1)[1].strip()
        elif sub.startswith("INPUT "):
            cap.input_type = sub.split(None, 1)[1].strip()
        elif sub.startswith("OUTPUT "):
            cap.output_type = sub.split(None, 1)[1].strip()
        elif sub.startswith("RESPONSIBILITY "):
            cap.responsibility = _parse_json_text(sub[len("RESPONSIBILITY "):], label="RESPONSIBILITY")
        elif sub.startswith("EVIDENCE "):
            cap.evidence.append(_parse_twin_evidence(sub, line_no=subline_no))
        else:
            raise TwinDslError(f"line {subline_no}: unknown CAPABILITY directive {sub!r}")
        index += 1
    if index >= len(lines) or lines[index][1] != "END":
        raise TwinDslError(f"line {lineno}: CAPABILITY missing END")
    return index, cap


def _parse_twin_invariant_block(lines: list[tuple[int, str]], index: int) -> tuple[int, TwinInvariant]:
    lineno, line = lines[index]
    inv_id = line.split(None, 1)[1].strip()
    if not _ID_RE.fullmatch(inv_id):
        raise TwinDslError(f"line {lineno}: invalid invariant id")
    inv = TwinInvariant(inv_id)
    index += 1
    while index < len(lines) and lines[index][1] != "END":
        subline_no, sub = lines[index]
        if sub.startswith("ASSERT "):
            inv.assertions.append(_parse_json_text(sub[len("ASSERT "):], label="ASSERT"))
        elif sub.startswith("EVIDENCE "):
            inv.evidence.append(_parse_twin_evidence(sub, line_no=subline_no))
        else:
            raise TwinDslError(f"line {subline_no}: unknown INVARIANT directive {sub!r}")
        index += 1
    if index >= len(lines) or lines[index][1] != "END":
        raise TwinDslError(f"line {lineno}: INVARIANT missing END")
    return index, inv


def _parse_twin_evolution_block(lines: list[tuple[int, str]], index: int) -> tuple[int, tuple[list[str], list[str], list[str]]]:
    lineno = lines[index][0]
    allow: list[str] = []
    require: list[str] = []
    forbid: list[str] = []
    index += 1
    while index < len(lines) and lines[index][1] != "END":
        subline_no, sub = lines[index]
        if sub.startswith("ALLOW "):
            allow.append(_parse_json_text(sub[len("ALLOW "):], label="ALLOW"))
        elif sub.startswith("REQUIRE "):
            require.append(_parse_json_text(sub[len("REQUIRE "):], label="REQUIRE"))
        elif sub.startswith("FORBID "):
            forbid.append(_parse_json_text(sub[len("FORBID "):], label="FORBID"))
        else:
            raise TwinDslError(f"line {subline_no}: unknown EVOLUTION directive {sub!r}")
        index += 1
    if index >= len(lines) or lines[index][1] != "END":
        raise TwinDslError(f"line {lineno}: EVOLUTION missing END")
    return index, (allow, require, forbid)


def _parse_twin_source(line: str, lineno: int) -> TwinSourceRef:
    match = re.fullmatch(r"SOURCE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+HASH\s+(sha256:[0-9a-f]{64})(?:\s+PATH\s+(.+))?", line)
    if not match:
        raise TwinDslError(f"line {lineno}: invalid SOURCE")
    path = ""
    if match.group(3):
        path = _parse_json_text(match.group(3), label="SOURCE PATH")
    return TwinSourceRef(match.group(1), match.group(2), path)


@dataclass(slots=True)
class _TwinParseState:
    name: str
    version: int | None = None
    revision: int | None = None
    fingerprint: str | None = None
    summary: str | None = None
    goals: list[str] = field(default_factory=list)
    nodes: dict[str, TwinNode] = field(default_factory=dict)
    capabilities: dict[str, TwinCapability] = field(default_factory=dict)
    edges: list[TwinEdge] = field(default_factory=list)
    invariants: dict[str, TwinInvariant] = field(default_factory=dict)
    evolution_allow: list[str] = field(default_factory=list)
    evolution_require: list[str] = field(default_factory=list)
    evolution_forbid: list[str] = field(default_factory=list)
    sources: dict[str, TwinSourceRef] = field(default_factory=dict)
    questions: list[str] = field(default_factory=list)


def _parse_twin_scalar(state: _TwinParseState, line: str) -> bool:
    if line.startswith("VERSION "):
        state.version = int(line.split(None, 1)[1])
    elif line.startswith("REVISION "):
        state.revision = int(line.split(None, 1)[1])
    elif line.startswith("INTENT_FINGERPRINT "):
        state.fingerprint = line.split(None, 1)[1].strip()
    elif line.startswith("INTENT_SUMMARY "):
        state.summary = _parse_json_text(line[len("INTENT_SUMMARY "):], label="INTENT_SUMMARY")
    elif line.startswith("GOAL "):
        state.goals.append(_parse_json_text(line[len("GOAL "):], label="GOAL"))
    elif line.startswith("OPEN_QUESTION "):
        state.questions.append(_parse_json_text(line[len("OPEN_QUESTION "):], label="OPEN_QUESTION"))
    else:
        return False
    return True


def _parse_twin_declaration(state: _TwinParseState, lines: list[tuple[int, str]], index: int) -> int:
    lineno, line = lines[index]
    if _parse_twin_scalar(state, line):
        return index
    if line.startswith("NODE "):
        index, node = _parse_twin_node_block(lines, index)
        if node.id in state.nodes:
            raise TwinDslError(f"duplicate node {node.id}")
        state.nodes[node.id] = node
    elif line.startswith("CAPABILITY "):
        index, capability = _parse_twin_capability_block(lines, index)
        if capability.id in state.capabilities:
            raise TwinDslError(f"duplicate capability {capability.id}")
        state.capabilities[capability.id] = capability
    elif line.startswith("EDGE "):
        match = re.fullmatch(r"EDGE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+->\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+REL\s+([A-Za-z][A-Za-z0-9_.-]{0,95})", line)
        if not match:
            raise TwinDslError(f"line {lineno}: invalid EDGE")
        state.edges.append(TwinEdge(match.group(1), match.group(2), match.group(3)))
    elif line.startswith("INVARIANT "):
        index, invariant = _parse_twin_invariant_block(lines, index)
        state.invariants[invariant.id] = invariant
    elif line == "EVOLUTION":
        index, (state.evolution_allow, state.evolution_require, state.evolution_forbid) = _parse_twin_evolution_block(lines, index)
    elif line.startswith("SOURCE "):
        source = _parse_twin_source(line, lineno)
        state.sources[source.id] = source
    else:
        raise TwinDslError(f"line {lineno}: unknown TwinDSL directive {line!r}")
    return index


def _build_twin_document(state: _TwinParseState) -> TwinDocument:
    if state.version is None or state.revision is None or state.fingerprint is None or state.summary is None:
        raise TwinDslError("TwinDSL requires VERSION, REVISION, INTENT_FINGERPRINT and INTENT_SUMMARY")
    return TwinDocument(
        name=state.name, version=state.version, revision=state.revision,
        intent_fingerprint=state.fingerprint, intent_summary=state.summary,
        goals=state.goals, nodes=state.nodes, capabilities=state.capabilities,
        edges=state.edges, invariants=state.invariants,
        evolution_allow=state.evolution_allow, evolution_require=state.evolution_require,
        evolution_forbid=state.evolution_forbid, sources=state.sources,
        open_questions=state.questions,
    )


def parse_twindsl(text: str) -> TwinDocument:
    lines = [(idx + 1, raw.strip()) for idx, raw in enumerate(text.splitlines()) if raw.strip()]
    if not lines:
        raise TwinDslError("empty TwinDSL")
    if not lines[0][1].startswith("TWIN "):
        raise TwinDslError("TwinDSL must start with TWIN <name>")

    name = lines[0][1][len("TWIN "):].strip()
    if not _ID_RE.fullmatch(name):
        raise TwinDslError(f"invalid twin name {name!r}")
    state = _TwinParseState(name)
    i = 1
    saw_end = False
    while i < len(lines):
        lineno, line = lines[i]
        if line == "END_TWIN":
            if i != len(lines) - 1:
                raise TwinDslError(f"line {lineno}: END_TWIN must be last")
            saw_end = True
            break
        i = _parse_twin_declaration(state, lines, i)
        i += 1

    if not saw_end:
        raise TwinDslError("TwinDSL missing END_TWIN")
    doc = _build_twin_document(state)
    errors = validate_twin(doc)
    if errors:
        raise TwinDslError("; ".join(errors))
    return doc


def validate_twin(doc: TwinDocument) -> list[str]:
    errors: list[str] = []
    _validate_twin_basics(doc, errors)
    symbols = set(doc.nodes) | set(doc.capabilities)
    known_sources = set(doc.sources)
    _validate_twin_capabilities(doc, errors)
    _validate_twin_edges(doc, symbols, errors)
    _validate_twin_invariants(doc, errors)
    _validate_twin_sources(doc, errors)
    _validate_twin_nodes(doc, known_sources, errors)
    return errors


def _validate_twin_basics(doc: TwinDocument, errors: list[str]) -> None:
    if doc.version != 1:
        errors.append("VERSION must be 1")
    if doc.revision < 1:
        errors.append("REVISION must be >= 1")
    if not _HASH_RE.fullmatch(doc.intent_fingerprint):
        errors.append("INTENT_FINGERPRINT must be sha256:<64 lowercase hex>")
    if not doc.intent_summary.strip():
        errors.append("INTENT_SUMMARY must not be empty")
    if not doc.goals:
        errors.append("at least one GOAL is required")
    if "preserve_user_intent" not in doc.invariants:
        errors.append("INVARIANT preserve_user_intent is required")
    if "user_intent" not in doc.sources:
        errors.append("SOURCE user_intent is required")
    if not doc.evolution_require:
        errors.append("EVOLUTION requires at least one REQUIRE rule")
    if not any("intent" in x.lower() for x in doc.evolution_require):
        errors.append("EVOLUTION REQUIRE must preserve user intent")


def _validate_twin_capabilities(doc: TwinDocument, errors: list[str]) -> None:
    for cap in doc.capabilities.values():
        if cap.owner and cap.owner not in doc.nodes:
            errors.append(f"capability {cap.id} OWNER {cap.owner!r} is not a declared NODE")
        if not cap.uri:
            errors.append(f"capability {cap.id} requires URI")
        else:
            try:
                IfUri.parse(cap.uri)
            except IfUriError as exc:
                errors.append(f"capability {cap.id} URI invalid: {exc}")
        if not cap.responsibility:
            errors.append(f"capability {cap.id} requires RESPONSIBILITY")
        for ev in cap.evidence:
            if ev not in doc.sources:
                errors.append(f"capability {cap.id} references unknown evidence {ev}")


def _validate_twin_edges(doc: TwinDocument, symbols: set[str], errors: list[str]) -> None:
    for edge in doc.edges:
        if edge.source not in symbols:
            errors.append(f"EDGE source {edge.source!r} is undeclared")
        if edge.target not in symbols:
            errors.append(f"EDGE target {edge.target!r} is undeclared")


def _validate_twin_invariants(doc: TwinDocument, errors: list[str]) -> None:
    for inv in doc.invariants.values():
        if not inv.assertions:
            errors.append(f"invariant {inv.id} requires ASSERT")


def _validate_twin_sources(doc: TwinDocument, errors: list[str]) -> None:
    for source in doc.sources.values():
        if not _HASH_RE.fullmatch(source.digest):
            errors.append(f"source {source.id} has invalid hash")


def _validate_twin_nodes(doc: TwinDocument, known_sources: set[str], errors: list[str]) -> None:
    allowed_spatial = {"physical", "cyber", "logical", "hybrid"}
    for node in doc.nodes.values():
        if node.spatial_class not in allowed_spatial:
            errors.append(f"node {node.id} requires SPATIAL_CLASS physical|cyber|logical|hybrid")
        for ev in node.evidence:
            if ev not in known_sources:
                errors.append(f"node {node.id} references unknown evidence {ev}")


def validate_twin_markdown(markdown: str) -> dict[str, Any]:
    try:
        doc = parse_twindsl(extract_twindsl(markdown))
        return {
            "valid": True,
            "errors": [],
            "name": doc.name,
            "revision": doc.revision,
            "intent_fingerprint": doc.intent_fingerprint,
            "nodes": len(doc.nodes),
            "capabilities": len(doc.capabilities),
            "sources": len(doc.sources),
        }
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


def validate_twin_update(previous: TwinDocument, updated: TwinDocument) -> list[str]:
    errors: list[str] = []
    if updated.name != previous.name:
        errors.append("twin identity cannot change during update")
    if updated.revision != previous.revision + 1:
        errors.append(f"updated REVISION must be {previous.revision + 1}")
    if updated.intent_fingerprint != previous.intent_fingerprint:
        errors.append("INTENT_FINGERPRINT is immutable")
    for invariant in previous.invariants:
        if invariant not in updated.invariants:
            errors.append(f"existing invariant {invariant!r} cannot be removed")
    if "user_intent" not in updated.sources:
        errors.append("user_intent source cannot be removed")
    return errors + validate_twin(updated)


def twin_to_mermaid(doc: TwinDocument) -> str:
    lines = ["flowchart LR"]
    lines.extend(_render_twin_nodes(doc))
    lines.extend(_render_twin_capabilities(doc))
    lines.extend(_render_twin_edges(doc))
    return "\n".join(lines)


def _render_twin_nodes(doc: TwinDocument) -> list[str]:
    return [f'  {node.id}["{node.id}\\n[{node.kind}]"]' for node in doc.nodes.values()]


def _render_twin_capabilities(doc: TwinDocument) -> list[str]:
    lines: list[str] = []
    for cap in doc.capabilities.values():
        cap_node = "cap_" + re.sub(r"[^A-Za-z0-9_]", "_", cap.id)
        lines.append(f'  {cap_node}(("{cap.id}"))')
        if cap.owner in doc.nodes:
            lines.append(f"  {cap.owner} -->|owns| {cap_node}")
    return lines


def _render_twin_edges(doc: TwinDocument) -> list[str]:
    def ref(symbol: str) -> str:
        if symbol in doc.nodes:
            return symbol
        if symbol in doc.capabilities:
            return "cap_" + re.sub(r"[^A-Za-z0-9_]", "_", symbol)
        return symbol

    return [f"  {ref(edge.source)} -->|{edge.relation}| {ref(edge.target)}" for edge in doc.edges]


def demo_bootstrap_twin(user_text: str) -> str:
    normalized = normalize_intent(user_text)
    fp = intent_fingerprint(user_text)
    user_hash = "sha256:" + hashlib.sha256(user_text.encode("utf-8")).hexdigest()
    summary = normalized[:420] or "Build an application from user intent and validated external sources."
    lines = [
        "TWIN application",
        "VERSION 1",
        "REVISION 1",
        f"INTENT_FINGERPRINT {fp}",
        f"INTENT_SUMMARY {_quoted(summary)}",
        f"GOAL {_quoted('Build a correct application whose evolution remains bounded by the user intent and source-backed evidence.')}",
    ]
    lines.extend(_bootstrap_node_lines())
    lines.extend(_bootstrap_capability_lines())
    lines.extend(_bootstrap_edges_lines())
    lines.extend(_bootstrap_invariant_lines())
    lines.extend(_bootstrap_evolution_lines())
    lines.extend([
        f"SOURCE user_intent HASH {user_hash}",
        f"OPEN_QUESTION {_quoted('Which concrete domain entities, workflows and external integrations should be refined from sources/?')}",
        "END_TWIN",
    ])
    return "```twindsl\n" + "\n".join(lines) + "\n```"


def _bootstrap_node_lines() -> list[str]:
    return [
        "NODE user KIND actor",
        "  SPATIAL_CLASS logical",
        f"  RESPONSIBILITY {_quoted('Provides intent, desired outcome, constraints and acceptance direction.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE intent_compiler KIND service",
        "  SPATIAL_CLASS cyber",
        f"  RESPONSIBILITY {_quoted('Compiles user natural-language intent into validated DSL before downstream reasoning.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE source_ingest KIND service",
        "  SPATIAL_CLASS cyber",
        f"  RESPONSIBILITY {_quoted('Transforms Markdown documents from sources/ into deterministic SourceIndexDSL before LLM analysis.')}",
        "END",
        "NODE digital_twin KIND model",
        "  SPATIAL_CLASS cyber",
        f"  RESPONSIBILITY {_quoted('Maintains the current source-backed application model, capabilities, invariants and evolution limits.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE builder_agent KIND service",
        "  SPATIAL_CLASS cyber",
        f"  RESPONSIBILITY {_quoted('Derives implementation plans and code changes from the validated digital twin, never from raw context.')}",
        "  EVIDENCE user_intent",
        "END",
    ]


def _bootstrap_capability_lines() -> list[str]:
    return [
        "CAPABILITY compile_user_intent",
        "  URI ifuri://llm/twin/default/commands/bootstrap",
        "  OWNER intent_compiler",
        "  INPUT ifuri.v1.DslDocument",
        "  OUTPUT ifuri.v1.DslDocument",
        f"  RESPONSIBILITY {_quoted('Create revision 1 of the DigitalTwinDSL from runtime-generated SourceDSL.')}",
        "  EVIDENCE user_intent",
        "END",
        "CAPABILITY update_from_sources",
        "  URI ifuri://llm/twin/default/commands/update",
        "  OWNER digital_twin",
        "  INPUT ifuri.v1.DslDocument",
        "  OUTPUT ifuri.v1.DslDocument",
        f"  RESPONSIBILITY {_quoted('Refine the twin only with evidence present in SourceIndexDSL while preserving the immutable intent fingerprint.')}",
        "END",
        "CAPABILITY plan_build",
        "  URI ifuri://llm/builder/default/commands/plan",
        "  OWNER builder_agent",
        "  INPUT ifuri.v1.DslDocument",
        "  OUTPUT ifuri.v1.DslDocument",
        f"  RESPONSIBILITY {_quoted('Generate a source-backed build plan from the current twin revision.')}",
        "  EVIDENCE user_intent",
        "END",
    ]


def _bootstrap_edges_lines() -> list[str]:
    return [
        "EDGE user -> compile_user_intent REL invokes",
        "EDGE compile_user_intent -> digital_twin REL creates",
        "EDGE source_ingest -> update_from_sources REL supplies",
        "EDGE update_from_sources -> digital_twin REL revises",
        "EDGE digital_twin -> plan_build REL constrains",
    ]


def _bootstrap_invariant_lines() -> list[str]:
    return [
        "INVARIANT preserve_user_intent",
        f"  ASSERT {_quoted('Every revision must keep the original INTENT_FINGERPRINT and must not contradict explicit user intent.')}",
        "  EVIDENCE user_intent",
        "END",
        "INVARIANT evidence_before_evolution",
        f"  ASSERT {_quoted('New requirements or capabilities require evidence from user_intent or a source document; unsupported assumptions remain OPEN_QUESTION.')}",
        "  EVIDENCE user_intent",
        "END",
    ]


def _bootstrap_evolution_lines() -> list[str]:
    return [
        "EVOLUTION",
        f"  ALLOW {_quoted('Refine architecture, implementation details, capabilities and acceptance criteria when supported by sources.')}",
        f"  ALLOW {_quoted('Add implementation-specific nodes without changing the original product outcome.')}",
        f"  REQUIRE {_quoted('Preserve user intent and the immutable INTENT_FINGERPRINT across revisions.')}",
        f"  REQUIRE {_quoted('Attach source evidence to source-derived changes.')}",
        f"  FORBID {_quoted('Invent product requirements that are unsupported by user intent or sources.')}",
        f"  FORBID {_quoted('Remove invariants solely to make an implementation easier.')}",
        "END",
    ]


def render_twin(doc: TwinDocument) -> str:
    lines = _render_twin_header(doc)
    lines.extend(_render_twin_goals(doc))
    lines.extend(_render_twin_nodes_block(doc))
    lines.extend(_render_twin_capabilities_block(doc))
    lines.extend(_render_twin_edges_block(doc))
    lines.extend(_render_twin_invariants_block(doc))
    lines.extend(_render_twin_evolution_block(doc))
    lines.extend(_render_twin_sources_block(doc))
    lines.extend(_render_twin_questions_block(doc))
    lines.append("END_TWIN")
    return "```twindsl\n" + "\n".join(lines) + "\n```"


def _render_twin_header(doc: TwinDocument) -> list[str]:
    return [
        f"TWIN {doc.name}",
        f"VERSION {doc.version}",
        f"REVISION {doc.revision}",
        f"INTENT_FINGERPRINT {doc.intent_fingerprint}",
        f"INTENT_SUMMARY {_quoted(doc.intent_summary)}",
    ]


def _render_twin_goals(doc: TwinDocument) -> list[str]:
    return [f"GOAL {_quoted(g)}" for g in doc.goals]


def _render_twin_nodes_block(doc: TwinDocument) -> list[str]:
    lines: list[str] = []
    for node in doc.nodes.values():
        lines.append(f"NODE {node.id} KIND {node.kind}")
        lines.append(f"  SPATIAL_CLASS {node.spatial_class}")
        if node.responsibility:
            lines.append(f"  RESPONSIBILITY {_quoted(node.responsibility)}")
        lines.extend(f"  EVIDENCE {e}" for e in node.evidence)
        lines.append("END")
    return lines


def _render_twin_capabilities_block(doc: TwinDocument) -> list[str]:
    lines: list[str] = []
    for cap in doc.capabilities.values():
        lines.append(f"CAPABILITY {cap.id}")
        if cap.uri:
            lines.append(f"  URI {cap.uri}")
        if cap.owner:
            lines.append(f"  OWNER {cap.owner}")
        if cap.input_type:
            lines.append(f"  INPUT {cap.input_type}")
        if cap.output_type:
            lines.append(f"  OUTPUT {cap.output_type}")
        if cap.responsibility:
            lines.append(f"  RESPONSIBILITY {_quoted(cap.responsibility)}")
        lines.extend(f"  EVIDENCE {e}" for e in cap.evidence)
        lines.append("END")
    return lines


def _render_twin_edges_block(doc: TwinDocument) -> list[str]:
    return [f"EDGE {edge.source} -> {edge.target} REL {edge.relation}" for edge in doc.edges]


def _render_twin_invariants_block(doc: TwinDocument) -> list[str]:
    lines: list[str] = []
    for inv in doc.invariants.values():
        lines.append(f"INVARIANT {inv.id}")
        lines.extend(f"  ASSERT {_quoted(x)}" for x in inv.assertions)
        lines.extend(f"  EVIDENCE {e}" for e in inv.evidence)
        lines.append("END")
    return lines


def _render_twin_evolution_block(doc: TwinDocument) -> list[str]:
    lines = ["EVOLUTION"]
    lines.extend(f"  ALLOW {_quoted(x)}" for x in doc.evolution_allow)
    lines.extend(f"  REQUIRE {_quoted(x)}" for x in doc.evolution_require)
    lines.extend(f"  FORBID {_quoted(x)}" for x in doc.evolution_forbid)
    lines.append("END")
    return lines


def _render_twin_sources_block(doc: TwinDocument) -> list[str]:
    lines: list[str] = []
    for src in doc.sources.values():
        row = f"SOURCE {src.id} HASH {src.digest}"
        if src.path:
            row += f" PATH {_quoted(src.path)}"
        lines.append(row)
    return lines


def _render_twin_questions_block(doc: TwinDocument) -> list[str]:
    return [f"OPEN_QUESTION {_quoted(x)}" for x in doc.open_questions]


def twindsl_schema() -> str:
    # Schema itself is a DSL block; no natural-language prompt is needed at the model boundary.
    return """```schemadsl
SCHEMA twindsl.v1
ROOT TWIN <id>
REQUIRE VERSION 1
REQUIRE REVISION <integer>=1
REQUIRE INTENT_FINGERPRINT sha256:<64hex>
REQUIRE INTENT_SUMMARY <json-string>
REPEAT GOAL <json-string>
BLOCK NODE <id> KIND <id>
  REQUIRE SPATIAL_CLASS physical|cyber|logical|hybrid
  OPTIONAL RESPONSIBILITY <json-string>
  REPEAT EVIDENCE <source-id>
END
BLOCK CAPABILITY <id>
  REQUIRE URI ifuri://<context>/<entity>/<identity>/<kind>/<operation>
  REQUIRE OWNER <node-id>
  OPTIONAL INPUT <protobuf-type>
  OPTIONAL OUTPUT <protobuf-type>
  REQUIRE RESPONSIBILITY <json-string>
  REPEAT EVIDENCE <source-id>
END
REPEAT EDGE <symbol-id> -> <symbol-id> REL <id>
BLOCK INVARIANT <id>
  REPEAT ASSERT <json-string>
  REPEAT EVIDENCE <source-id>
END
BLOCK EVOLUTION
  REPEAT ALLOW <json-string>
  REPEAT REQUIRE <json-string>
  REPEAT FORBID <json-string>
END
REPEAT SOURCE <source-id> HASH sha256:<64hex> [PATH <json-string>]
REPEAT OPEN_QUESTION <json-string>
REQUIRE INVARIANT preserve_user_intent
REQUIRE SOURCE user_intent
END_TWIN
```"""


def buildplandsl_schema() -> str:
    return """```schemadsl
SCHEMA buildplanddsl.v1
ROOT BUILD_PLAN <twin-id>
REQUIRE FROM_REVISION <integer>
REQUIRE FROM_TWIN_HASH sha256:<64hex>
NOTE FROM_REVISION_and_FROM_TWIN_HASH_are_rebound_by_runtime_to_the_current_Twin
REPEAT BLOCK PHASE <id>
  REQUIRE PURPOSE <json-string>
  REPEAT BLOCK TASK <id>
    REQUIRE TARGET_URI ifuri://<context>/<entity>/<identity>/<kind>/<operation>
    REQUIRE EVIDENCE <json-array-of-quoted-source-id-or-evidence-set-uri-strings>
    EXAMPLE EVIDENCE ["user_intent", "urn:subactor:evidence-set:sha256:0123456789abcdef"]
    REQUIRE OPERATION <oql-operation-matching-target-operation>
    REQUIRE EXPECTED_RESULT <json-string>
    REQUIRE ACCEPTANCE <json-string>
    REQUIRE ROLLBACK <json-string>
    REQUIRE DEPENDS_ON <json-array-of-quoted-task-id-strings-or-empty-array>
    EXAMPLE DEPENDS_ON []
    REQUIRE AUTHORITY_CLASS <id>
  END_TASK
END_PHASE
END_BUILD_PLAN
```"""


def extract_buildplanddsl(markdown: str) -> str:
    blocks = [m.group("body").strip() for m in _FENCE_RE.finditer(markdown) if m.group("lang").lower() == "buildplanddsl"]
    if len(blocks) != 1:
        raise TwinDslError(f"expected exactly one buildplanddsl block, found {len(blocks)}")
    outside = _FENCE_RE.sub("", markdown).strip()
    if outside:
        raise TwinDslError("prose outside buildplanddsl block is forbidden")
    return blocks[0]


def validate_buildplan_markdown(markdown: str, twin: TwinDocument | None = None) -> dict[str, Any]:
    from onlydsl_contracts.dsl.build_plan import validate_bound_build_plan
    return validate_bound_build_plan(markdown, twin, render_twin(twin) if twin is not None else "")


def demo_build_plan(doc: TwinDocument) -> str:
    from onlydsl_contracts.dsl.build_plan import semantic_twin_hash
    evidence = next(iter(doc.sources), "user_intent")
    return "```buildplanddsl\n" + "\n".join([
        f"BUILD_PLAN {doc.name}",
        f"FROM_REVISION {doc.revision}",
        f"FROM_TWIN_HASH {semantic_twin_hash(render_twin(doc))}",
        "PHASE foundation",
        f"  PURPOSE {_quoted('Stabilize contracts, digital twin state and source-backed invariants before implementation expansion.')}",
        "  TASK persist_twin",
        "    TARGET_URI ifuri://twin/state/default/commands/save",
        f"    EVIDENCE [{_quoted(evidence)}]",
        "    OPERATION twin.save",
        f"    EXPECTED_RESULT {_quoted('Validated TwinDSL revision and provenance are persisted atomically.')}",
        f"    ACCEPTANCE {_quoted('Revision can be reloaded byte-for-byte and intent fingerprint remains unchanged.')}",
        f"    ROLLBACK {_quoted('Keep the previous exact Twin revision as current.')}",
        "    DEPENDS_ON []",
        "    AUTHORITY_CLASS reversible-state",
        "  END_TASK",
        "END_PHASE",
        "PHASE implementation",
        f"  PURPOSE {_quoted('Implement capabilities represented by the twin using IFURI and Protobuf contracts.')}",
        "  TASK implement_capabilities",
        "    TARGET_URI ifuri://builder/code/default/commands/implement",
        f"    EVIDENCE [{_quoted(evidence)}]",
        "    OPERATION code.implement",
        f"    EXPECTED_RESULT {_quoted('Capabilities represented by the current Twin are implemented without expanding intent.')}",
        f"    ACCEPTANCE {_quoted('Tests pass and no invariant or source-backed constraint is violated.')}",
        f"    ROLLBACK {_quoted('Restore the last verified code artifact and Twin revision.')}",
        '    DEPENDS_ON ["persist_twin"]',
        "    AUTHORITY_CLASS reversible-code",
        "  END_TASK",
        "END_PHASE",
        "END_BUILD_PLAN",
    ]) + "\n```"
