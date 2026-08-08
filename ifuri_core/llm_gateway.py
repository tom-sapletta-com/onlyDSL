from __future__ import annotations

import json
import re

from boundary import assert_dsl_only
from contextdsl import validate_context_markdown
from digital_twin import validate_buildplan_markdown, validate_twin_markdown
from llm_client import analyze_context, bootstrap_twin, plan_build, provider_status, update_twin
from source_ingest import validate_sourceindex_markdown

from .dsl_document import make_dsl_document, validate_dsl_document
from .dsl_pb2 import DslDocument
from .envelope import EnvelopeCodec, MessageKind


class LlmGatewayError(ValueError):
    pass


_FENCE = re.compile(r"```(?P<lang>[A-Za-z][A-Za-z0-9_.-]*)\s*\n(?P<body>.*?)```", re.S)


def _reply(envelope, dsl_type: str, markdown: str, result: dict, backend: str):
    outgoing = make_dsl_document(dsl_type, markdown)
    return EnvelopeCodec.create(
        target_uri=envelope.source_uri,
        source_uri=envelope.target_uri,
        kind=MessageKind.REPLY,
        payload=outgoing,
        correlation_id=envelope.correlation_id or envelope.id,
        causation_id=envelope.id,
        metadata={
            "backend": str(result.get("backend", backend)),
            "model": str(result.get("model", "")),
            "constrained": str(bool(result.get("constrained", False))).lower(),
        },
    )


def build_llm_reasoner_handler(backend: str = "demo"):
    def handler(resolved, envelope):
        incoming = DslDocument()
        EnvelopeCodec.unpack(envelope, incoming)
        validate_dsl_document(incoming)
        if incoming.dsl_type != "contextdsl":
            raise LlmGatewayError("LLM analysis capability requires contextdsl input")
        assert_dsl_only(incoming.markdown, {"contextdsl"})
        validation = validate_context_markdown(incoming.markdown)
        if not validation["valid"]:
            raise LlmGatewayError("invalid ContextDSL: " + "; ".join(validation["errors"]))
        result = analyze_context(incoming.markdown, backend)
        assert_dsl_only(result["markdown"], {"intentdsl"})
        return _reply(envelope, "intentdsl", result["markdown"], result, backend)

    return handler


def _extract_source_payload(markdown: str) -> str:
    assert_dsl_only(markdown, {"sourcedsl"})
    match = re.search(r"```sourcedsl\s*\n(.*?)```", markdown, re.S | re.I)
    if not match:
        raise LlmGatewayError("missing sourcedsl block")
    for line in match.group(1).splitlines():
        if line.startswith("PAYLOAD "):
            value = json.loads(line[len("PAYLOAD "):])
            if not isinstance(value, str):
                raise LlmGatewayError("SourceDSL PAYLOAD must be a string")
            return value
    raise LlmGatewayError("SourceDSL PAYLOAD is required")


def build_llm_semantic_handler(backend: str = "demo"):
    from llm_client import convert_english

    def handler(resolved, envelope):
        incoming = DslDocument()
        EnvelopeCodec.unpack(envelope, incoming)
        validate_dsl_document(incoming)
        if incoming.dsl_type != "sourcedsl":
            raise LlmGatewayError("semantic compiler requires sourcedsl input")
        source_text = _extract_source_payload(incoming.markdown)
        result = convert_english(source_text, backend)
        assert_dsl_only(result["markdown"], {"intentdsl"})
        return _reply(envelope, "intentdsl", result["markdown"], result, backend)

    return handler


def build_llm_twin_bootstrap_handler(backend: str = "demo"):
    def handler(resolved, envelope):
        incoming = DslDocument()
        EnvelopeCodec.unpack(envelope, incoming)
        validate_dsl_document(incoming)
        if incoming.dsl_type != "sourcedsl":
            raise LlmGatewayError("twin bootstrap requires sourcedsl input")
        source_text = _extract_source_payload(incoming.markdown)
        result = bootstrap_twin(source_text, backend)
        if not validate_twin_markdown(result["markdown"])["valid"]:
            raise LlmGatewayError("twin bootstrap returned invalid TwinDSL")
        return _reply(envelope, "twindsl", result["markdown"], result, backend)

    return handler


def _extract_bundle_blocks(markdown: str) -> dict[str, str]:
    assert_dsl_only(markdown, {"twindsl", "sourceindexdsl"})
    blocks: dict[str, str] = {}
    for match in _FENCE.finditer(markdown):
        lang = match.group("lang").lower()
        if lang in blocks:
            raise LlmGatewayError(f"duplicate {lang} in dslbundle")
        blocks[lang] = f"```{lang}\n{match.group('body').strip()}\n```"
    return blocks


def build_llm_twin_update_handler(backend: str = "demo"):
    def handler(resolved, envelope):
        incoming = DslDocument()
        EnvelopeCodec.unpack(envelope, incoming)
        validate_dsl_document(incoming)
        if incoming.dsl_type != "dslbundle":
            raise LlmGatewayError("twin update requires dslbundle input")
        blocks = _extract_bundle_blocks(incoming.markdown)
        twin_md = blocks.get("twindsl", "")
        source_md = blocks.get("sourceindexdsl", "")
        if not twin_md or not source_md:
            raise LlmGatewayError("twin update dslbundle requires twindsl + sourceindexdsl")
        if not validate_sourceindex_markdown(source_md)["valid"]:
            raise LlmGatewayError("invalid SourceIndexDSL")
        result = update_twin(twin_md, source_md, backend)
        return _reply(envelope, "twindsl", result["markdown"], result, backend)

    return handler


def build_llm_build_plan_handler(backend: str = "demo"):
    def handler(resolved, envelope):
        incoming = DslDocument()
        EnvelopeCodec.unpack(envelope, incoming)
        validate_dsl_document(incoming)
        if incoming.dsl_type != "twindsl":
            raise LlmGatewayError("build planner requires twindsl input")
        if not validate_twin_markdown(incoming.markdown)["valid"]:
            raise LlmGatewayError("invalid TwinDSL")
        result = plan_build(incoming.markdown, backend)
        if not validate_buildplan_markdown(result["markdown"])["valid"]:
            raise LlmGatewayError("invalid BuildPlanDSL")
        return _reply(envelope, "buildplanddsl", result["markdown"], result, backend)

    return handler


def gateway_provider_status(backend: str | None = None):
    return provider_status(backend)
