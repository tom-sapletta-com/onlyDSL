from __future__ import annotations

from boundary import assert_dsl_only
from contextdsl import validate_context_markdown
from llm_client import analyze_context

from .dsl_document import make_dsl_document, validate_dsl_document
from .dsl_pb2 import DslDocument
from .envelope import EnvelopeCodec, MessageKind


class LlmGatewayError(ValueError):
    pass


def build_llm_reasoner_handler(backend: str = "demo"):
    """Create an IFURI capability handler with a hard DSL-only LLM boundary.

    Domain/runtime code cannot pass raw logs/prose through this handler: the protobuf
    payload must be a DslDocument of type `contextdsl` and the fenced content is
    validated before the LLM client is reached.
    """

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
        outgoing = make_dsl_document("intentdsl", result["markdown"])
        return EnvelopeCodec.create(
            target_uri=envelope.source_uri,
            source_uri=envelope.target_uri,
            kind=MessageKind.REPLY,
            payload=outgoing,
            correlation_id=envelope.correlation_id or envelope.id,
            causation_id=envelope.id,
            metadata={
                "backend": str(result.get("backend", backend)),
                "constrained": str(bool(result.get("constrained", False))).lower(),
            },
        )

    return handler


def _extract_source_payload(markdown: str) -> str:
    import json
    import re

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
        outgoing = make_dsl_document("intentdsl", result["markdown"])
        return EnvelopeCodec.create(
            target_uri=envelope.source_uri,
            source_uri=envelope.target_uri,
            kind=MessageKind.REPLY,
            payload=outgoing,
            correlation_id=envelope.correlation_id or envelope.id,
            causation_id=envelope.id,
            metadata={
                "backend": str(result.get("backend", backend)),
                "constrained": str(bool(result.get("constrained", False))).lower(),
            },
        )

    return handler
