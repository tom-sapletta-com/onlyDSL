from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ifuri_core.uri import IfUri, IfUriError

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


@dataclass(slots=True)
class TwinNode:
    id: str
    kind: str
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


def parse_twindsl(text: str) -> TwinDocument:
    lines = [(idx + 1, raw.strip()) for idx, raw in enumerate(text.splitlines()) if raw.strip()]
    if not lines:
        raise TwinDslError("empty TwinDSL")
    if not lines[0][1].startswith("TWIN "):
        raise TwinDslError("TwinDSL must start with TWIN <name>")

    name = lines[0][1][len("TWIN "):].strip()
    if not _ID_RE.fullmatch(name):
        raise TwinDslError(f"invalid twin name {name!r}")

    version = revision = None
    fp = summary = None
    goals: list[str] = []
    nodes: dict[str, TwinNode] = {}
    caps: dict[str, TwinCapability] = {}
    edges: list[TwinEdge] = []
    invariants: dict[str, TwinInvariant] = {}
    evo_allow: list[str] = []
    evo_require: list[str] = []
    evo_forbid: list[str] = []
    sources: dict[str, TwinSourceRef] = {}
    questions: list[str] = []

    i = 1
    saw_end = False
    while i < len(lines):
        lineno, line = lines[i]
        if line == "END_TWIN":
            if i != len(lines) - 1:
                raise TwinDslError(f"line {lineno}: END_TWIN must be last")
            saw_end = True
            break
        if line.startswith("VERSION "):
            version = int(line.split(None, 1)[1])
        elif line.startswith("REVISION "):
            revision = int(line.split(None, 1)[1])
        elif line.startswith("INTENT_FINGERPRINT "):
            fp = line.split(None, 1)[1].strip()
        elif line.startswith("INTENT_SUMMARY "):
            summary = _json_string(line[len("INTENT_SUMMARY "):], label="INTENT_SUMMARY")
        elif line.startswith("GOAL "):
            goals.append(_json_string(line[len("GOAL "):], label="GOAL"))
        elif line.startswith("OPEN_QUESTION "):
            questions.append(_json_string(line[len("OPEN_QUESTION "):], label="OPEN_QUESTION"))
        elif line.startswith("NODE "):
            m = re.fullmatch(r"NODE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+KIND\s+([A-Za-z][A-Za-z0-9_.-]{0,95})", line)
            if not m:
                raise TwinDslError(f"line {lineno}: invalid NODE header")
            node = TwinNode(m.group(1), m.group(2))
            i += 1
            while i < len(lines) and lines[i][1] != "END":
                subline_no, sub = lines[i]
                if sub.startswith("RESPONSIBILITY "):
                    node.responsibility = _json_string(sub[len("RESPONSIBILITY "):], label="RESPONSIBILITY")
                elif sub.startswith("EVIDENCE "):
                    ev = sub.split(None, 1)[1].strip()
                    if not _ID_RE.fullmatch(ev):
                        raise TwinDslError(f"line {subline_no}: invalid EVIDENCE id")
                    node.evidence.append(ev)
                else:
                    raise TwinDslError(f"line {subline_no}: unknown NODE directive {sub!r}")
                i += 1
            if i >= len(lines) or lines[i][1] != "END":
                raise TwinDslError(f"line {lineno}: NODE missing END")
            if node.id in nodes:
                raise TwinDslError(f"duplicate node {node.id}")
            nodes[node.id] = node
        elif line.startswith("CAPABILITY "):
            cap_id = line.split(None, 1)[1].strip()
            if not _ID_RE.fullmatch(cap_id):
                raise TwinDslError(f"line {lineno}: invalid capability id")
            cap = TwinCapability(cap_id)
            i += 1
            while i < len(lines) and lines[i][1] != "END":
                subline_no, sub = lines[i]
                if sub.startswith("URI "):
                    cap.uri = sub.split(None, 1)[1].strip()
                elif sub.startswith("OWNER "):
                    cap.owner = sub.split(None, 1)[1].strip()
                elif sub.startswith("INPUT "):
                    cap.input_type = sub.split(None, 1)[1].strip()
                elif sub.startswith("OUTPUT "):
                    cap.output_type = sub.split(None, 1)[1].strip()
                elif sub.startswith("RESPONSIBILITY "):
                    cap.responsibility = _json_string(sub[len("RESPONSIBILITY "):], label="RESPONSIBILITY")
                elif sub.startswith("EVIDENCE "):
                    ev = sub.split(None, 1)[1].strip()
                    if not _ID_RE.fullmatch(ev):
                        raise TwinDslError(f"line {subline_no}: invalid EVIDENCE id")
                    cap.evidence.append(ev)
                else:
                    raise TwinDslError(f"line {subline_no}: unknown CAPABILITY directive {sub!r}")
                i += 1
            if i >= len(lines) or lines[i][1] != "END":
                raise TwinDslError(f"line {lineno}: CAPABILITY missing END")
            if cap.id in caps:
                raise TwinDslError(f"duplicate capability {cap.id}")
            caps[cap.id] = cap
        elif line.startswith("EDGE "):
            m = re.fullmatch(r"EDGE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+->\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+REL\s+([A-Za-z][A-Za-z0-9_.-]{0,95})", line)
            if not m:
                raise TwinDslError(f"line {lineno}: invalid EDGE")
            edges.append(TwinEdge(m.group(1), m.group(2), m.group(3)))
        elif line.startswith("INVARIANT "):
            inv_id = line.split(None, 1)[1].strip()
            if not _ID_RE.fullmatch(inv_id):
                raise TwinDslError(f"line {lineno}: invalid invariant id")
            inv = TwinInvariant(inv_id)
            i += 1
            while i < len(lines) and lines[i][1] != "END":
                subline_no, sub = lines[i]
                if sub.startswith("ASSERT "):
                    inv.assertions.append(_json_string(sub[len("ASSERT "):], label="ASSERT"))
                elif sub.startswith("EVIDENCE "):
                    ev = sub.split(None, 1)[1].strip()
                    if not _ID_RE.fullmatch(ev):
                        raise TwinDslError(f"line {subline_no}: invalid EVIDENCE id")
                    inv.evidence.append(ev)
                else:
                    raise TwinDslError(f"line {subline_no}: unknown INVARIANT directive {sub!r}")
                i += 1
            if i >= len(lines) or lines[i][1] != "END":
                raise TwinDslError(f"line {lineno}: INVARIANT missing END")
            invariants[inv.id] = inv
        elif line == "EVOLUTION":
            i += 1
            while i < len(lines) and lines[i][1] != "END":
                subline_no, sub = lines[i]
                if sub.startswith("ALLOW "):
                    evo_allow.append(_json_string(sub[len("ALLOW "):], label="ALLOW"))
                elif sub.startswith("REQUIRE "):
                    evo_require.append(_json_string(sub[len("REQUIRE "):], label="REQUIRE"))
                elif sub.startswith("FORBID "):
                    evo_forbid.append(_json_string(sub[len("FORBID "):], label="FORBID"))
                else:
                    raise TwinDslError(f"line {subline_no}: unknown EVOLUTION directive {sub!r}")
                i += 1
            if i >= len(lines) or lines[i][1] != "END":
                raise TwinDslError(f"line {lineno}: EVOLUTION missing END")
        elif line.startswith("SOURCE "):
            m = re.fullmatch(r"SOURCE\s+([A-Za-z][A-Za-z0-9_.-]{0,95})\s+HASH\s+(sha256:[0-9a-f]{64})(?:\s+PATH\s+(.+))?", line)
            if not m:
                raise TwinDslError(f"line {lineno}: invalid SOURCE")
            path = ""
            if m.group(3):
                path = _json_string(m.group(3), label="SOURCE PATH")
            sources[m.group(1)] = TwinSourceRef(m.group(1), m.group(2), path)
        else:
            raise TwinDslError(f"line {lineno}: unknown TwinDSL directive {line!r}")
        i += 1

    if not saw_end:
        raise TwinDslError("TwinDSL missing END_TWIN")
    if version is None or revision is None or fp is None or summary is None:
        raise TwinDslError("TwinDSL requires VERSION, REVISION, INTENT_FINGERPRINT and INTENT_SUMMARY")

    doc = TwinDocument(
        name=name,
        version=version,
        revision=revision,
        intent_fingerprint=fp,
        intent_summary=summary,
        goals=goals,
        nodes=nodes,
        capabilities=caps,
        edges=edges,
        invariants=invariants,
        evolution_allow=evo_allow,
        evolution_require=evo_require,
        evolution_forbid=evo_forbid,
        sources=sources,
        open_questions=questions,
    )
    errors = validate_twin(doc)
    if errors:
        raise TwinDslError("; ".join(errors))
    return doc


def validate_twin(doc: TwinDocument) -> list[str]:
    errors: list[str] = []
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

    symbols = set(doc.nodes) | set(doc.capabilities)
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
    for edge in doc.edges:
        if edge.source not in symbols:
            errors.append(f"EDGE source {edge.source!r} is undeclared")
        if edge.target not in symbols:
            errors.append(f"EDGE target {edge.target!r} is undeclared")
    for inv in doc.invariants.values():
        if not inv.assertions:
            errors.append(f"invariant {inv.id} requires ASSERT")
    for source in doc.sources.values():
        if not _HASH_RE.fullmatch(source.digest):
            errors.append(f"source {source.id} has invalid hash")
    known_sources = set(doc.sources)
    for node in doc.nodes.values():
        for ev in node.evidence:
            if ev not in known_sources:
                errors.append(f"node {node.id} references unknown evidence {ev}")
    for cap in doc.capabilities.values():
        for ev in cap.evidence:
            if ev not in known_sources:
                errors.append(f"capability {cap.id} references unknown evidence {ev}")
    return errors


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
    for node in doc.nodes.values():
        label = f"{node.id}\\n[{node.kind}]"
        lines.append(f'  {node.id}["{label}"]')
    for cap in doc.capabilities.values():
        cap_node = "cap_" + re.sub(r"[^A-Za-z0-9_]", "_", cap.id)
        lines.append(f'  {cap_node}(("{cap.id}"))')
        if cap.owner in doc.nodes:
            lines.append(f"  {cap.owner} -->|owns| {cap_node}")
    def ref(symbol: str) -> str:
        if symbol in doc.nodes:
            return symbol
        if symbol in doc.capabilities:
            return "cap_" + re.sub(r"[^A-Za-z0-9_]", "_", symbol)
        return symbol
    for edge in doc.edges:
        lines.append(f"  {ref(edge.source)} -->|{edge.relation}| {ref(edge.target)}")
    return "\n".join(lines)


def demo_bootstrap_twin(user_text: str) -> str:
    normalized = normalize_intent(user_text)
    fp = intent_fingerprint(user_text)
    user_hash = "sha256:" + hashlib.sha256(user_text.encode("utf-8")).hexdigest()
    summary = normalized[:420] or "Build an application from user intent and validated external sources."
    return "```twindsl\n" + "\n".join([
        "TWIN application",
        "VERSION 1",
        "REVISION 1",
        f"INTENT_FINGERPRINT {fp}",
        f"INTENT_SUMMARY {_quoted(summary)}",
        f"GOAL {_quoted('Build a correct application whose evolution remains bounded by the user intent and source-backed evidence.')}",
        "NODE user KIND actor",
        f"  RESPONSIBILITY {_quoted('Provides intent, desired outcome, constraints and acceptance direction.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE intent_compiler KIND service",
        f"  RESPONSIBILITY {_quoted('Compiles user natural-language intent into validated DSL before downstream reasoning.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE source_ingest KIND service",
        f"  RESPONSIBILITY {_quoted('Transforms Markdown documents from sources/ into deterministic SourceIndexDSL before LLM analysis.')}",
        "END",
        "NODE digital_twin KIND model",
        f"  RESPONSIBILITY {_quoted('Maintains the current source-backed application model, capabilities, invariants and evolution limits.')}",
        "  EVIDENCE user_intent",
        "END",
        "NODE builder_agent KIND service",
        f"  RESPONSIBILITY {_quoted('Derives implementation plans and code changes from the validated digital twin, never from raw context.')}",
        "  EVIDENCE user_intent",
        "END",
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
        "EDGE user -> compile_user_intent REL invokes",
        "EDGE compile_user_intent -> digital_twin REL creates",
        "EDGE source_ingest -> update_from_sources REL supplies",
        "EDGE update_from_sources -> digital_twin REL revises",
        "EDGE digital_twin -> plan_build REL constrains",
        "INVARIANT preserve_user_intent",
        f"  ASSERT {_quoted('Every revision must keep the original INTENT_FINGERPRINT and must not contradict explicit user intent.')}",
        "  EVIDENCE user_intent",
        "END",
        "INVARIANT evidence_before_evolution",
        f"  ASSERT {_quoted('New requirements or capabilities require evidence from user_intent or a source document; unsupported assumptions remain OPEN_QUESTION.')}",
        "  EVIDENCE user_intent",
        "END",
        "EVOLUTION",
        f"  ALLOW {_quoted('Refine architecture, implementation details, capabilities and acceptance criteria when supported by sources.')}",
        f"  ALLOW {_quoted('Add implementation-specific nodes without changing the original product outcome.')}",
        f"  REQUIRE {_quoted('Preserve user intent and the immutable INTENT_FINGERPRINT across revisions.')}",
        f"  REQUIRE {_quoted('Attach source evidence to source-derived changes.')}",
        f"  FORBID {_quoted('Invent product requirements that are unsupported by user intent or sources.')}",
        f"  FORBID {_quoted('Remove invariants solely to make an implementation easier.')}",
        "END",
        f"SOURCE user_intent HASH {user_hash}",
        f"OPEN_QUESTION {_quoted('Which concrete domain entities, workflows and external integrations should be refined from sources/?')}",
        "END_TWIN",
    ]) + "\n```"


def render_twin(doc: TwinDocument) -> str:
    lines = [
        f"TWIN {doc.name}",
        f"VERSION {doc.version}",
        f"REVISION {doc.revision}",
        f"INTENT_FINGERPRINT {doc.intent_fingerprint}",
        f"INTENT_SUMMARY {_quoted(doc.intent_summary)}",
    ]
    lines.extend(f"GOAL {_quoted(g)}" for g in doc.goals)
    for node in doc.nodes.values():
        lines.append(f"NODE {node.id} KIND {node.kind}")
        if node.responsibility:
            lines.append(f"  RESPONSIBILITY {_quoted(node.responsibility)}")
        lines.extend(f"  EVIDENCE {e}" for e in node.evidence)
        lines.append("END")
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
    for edge in doc.edges:
        lines.append(f"EDGE {edge.source} -> {edge.target} REL {edge.relation}")
    for inv in doc.invariants.values():
        lines.append(f"INVARIANT {inv.id}")
        lines.extend(f"  ASSERT {_quoted(x)}" for x in inv.assertions)
        lines.extend(f"  EVIDENCE {e}" for e in inv.evidence)
        lines.append("END")
    lines.append("EVOLUTION")
    lines.extend(f"  ALLOW {_quoted(x)}" for x in doc.evolution_allow)
    lines.extend(f"  REQUIRE {_quoted(x)}" for x in doc.evolution_require)
    lines.extend(f"  FORBID {_quoted(x)}" for x in doc.evolution_forbid)
    lines.append("END")
    for src in doc.sources.values():
        row = f"SOURCE {src.id} HASH {src.digest}"
        if src.path:
            row += f" PATH {_quoted(src.path)}"
        lines.append(row)
    lines.extend(f"OPEN_QUESTION {_quoted(x)}" for x in doc.open_questions)
    lines.append("END_TWIN")
    return "```twindsl\n" + "\n".join(lines) + "\n```"


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
REPEAT BLOCK PHASE <id>
  REQUIRE PURPOSE <json-string>
  REPEAT BLOCK TASK <id>
    REQUIRE TARGET_URI ifuri://<context>/<entity>/<identity>/<kind>/<operation>
    REQUIRE ACTION <json-string>
    REQUIRE ACCEPTANCE <json-string>
    REPEAT EVIDENCE <source-id>
  END
END
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


def validate_buildplan_markdown(markdown: str) -> dict[str, Any]:
    try:
        text = extract_buildplanddsl(markdown)
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        if not lines or not lines[0].startswith("BUILD_PLAN ") or lines[-1] != "END_BUILD_PLAN":
            raise TwinDslError("invalid BUILD_PLAN envelope")
        if not any(x.startswith("FROM_REVISION ") for x in lines):
            raise TwinDslError("FROM_REVISION is required")
        if not any(x.startswith("PHASE ") for x in lines):
            raise TwinDslError("at least one PHASE is required")
        for line in lines:
            if line.startswith("TARGET_URI "):
                IfUri.parse(line.split(None, 1)[1])
        return {"valid": True, "errors": []}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


def demo_build_plan(doc: TwinDocument) -> str:
    evidence = next(iter(doc.sources), "user_intent")
    return "```buildplanddsl\n" + "\n".join([
        f"BUILD_PLAN {doc.name}",
        f"FROM_REVISION {doc.revision}",
        "PHASE foundation",
        f"  PURPOSE {_quoted('Stabilize contracts, digital twin state and source-backed invariants before implementation expansion.')}",
        "  TASK persist_twin",
        "    TARGET_URI ifuri://twin/state/default/commands/save",
        f"    ACTION {_quoted('Persist validated TwinDSL revisions and provenance atomically.')}",
        f"    ACCEPTANCE {_quoted('Revision can be reloaded byte-for-byte and intent fingerprint remains unchanged.')}",
        f"    EVIDENCE {evidence}",
        "  END",
        "END",
        "PHASE implementation",
        f"  PURPOSE {_quoted('Implement capabilities represented by the twin using IFURI and Protobuf contracts.')}",
        "  TASK implement_capabilities",
        "    TARGET_URI ifuri://builder/code/default/commands/implement",
        f"    ACTION {_quoted('Generate or modify code only for capabilities and constraints present in the current twin.')}",
        f"    ACCEPTANCE {_quoted('Tests pass and no invariant or source-backed constraint is violated.')}",
        f"    EVIDENCE {evidence}",
        "  END",
        "END",
        "END_BUILD_PLAN",
    ]) + "\n```"
