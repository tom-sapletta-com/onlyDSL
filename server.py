from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from boundary import build_context_analysis_bundle, source_text_dsl
from contextdsl import compiler_from_payload, extract_contextdsl, parse_context_dsl, validate_context_markdown
from intentdsl import codegen, extract_intentdsl, parse_dsl, run_program, validate_markdown
from ifuri_core.dsl_document import make_dsl_document
from ifuri_core.dsl_pb2 import DslDocument
from ifuri_core.envelope import EnvelopeCodec
from ifuri_core.llm_gateway import build_llm_reasoner_handler, build_llm_semantic_handler
from ifuri_core.manifest import CapabilityRegistry
from ifuri_core.runtime import IfuriRuntime
from ifuri_core.transport import InProcessTransport

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

REGISTRY = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")
INPROC = InProcessTransport()
INPROC.register("llm.reasoner.analyze", build_llm_reasoner_handler(os.getenv("LLM_BACKEND", "demo")))
INPROC.register("llm.semantic.compile", build_llm_semantic_handler(os.getenv("LLM_BACKEND", "demo")))
RUNTIME = IfuriRuntime(REGISTRY, {"inproc": INPROC})


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _context_registries(context_markdown: str) -> tuple[set[str], set[str], dict[str, Any]]:
    doc = parse_context_dsl(extract_contextdsl(context_markdown))
    state_values = {name: spec["value"] for name, spec in doc.states.items()}
    return doc.action_capabilities, doc.event_capabilities, state_values


def _ifuri_analyze_context(body: dict[str, Any]) -> dict[str, Any]:
    context_markdown = compiler_from_payload(body.get("context", body)).to_markdown()
    context_validation = validate_context_markdown(context_markdown)
    if not context_validation["valid"]:
        raise ValueError("invalid ContextDSL: " + "; ".join(context_validation["errors"]))
    dsl_doc = make_dsl_document("contextdsl", context_markdown)
    reply, route = asyncio.run(
        RUNTIME.call("ifuri://llm/reasoner/default/commands/analyze", dsl_doc)
    )
    output = DslDocument()
    EnvelopeCodec.unpack(reply, output)
    actions, events, state_values = _context_registries(context_markdown)
    intent_validation = validate_markdown(
        output.markdown, action_registry=actions, event_registry=events
    )
    runtime_result = None
    if intent_validation["valid"]:
        program = parse_dsl(extract_intentdsl(output.markdown))
        runtime_inputs = {name: state_values[name] for name in program.inputs if name in state_values}
        if len(runtime_inputs) == len(program.inputs):
            runtime_result = run_program(
                program,
                runtime_inputs,
                action_registry=actions,
                event_registry=events,
            )
    return {
        "context_markdown": context_markdown,
        "context_validation": context_validation,
        "llm_request_markdown": build_context_analysis_bundle(context_markdown).markdown,
        "intent_markdown": output.markdown,
        "intent_validation": intent_validation,
        "runtime": runtime_result,
        "route": route.to_dict(),
        "llm_boundary": "IfEnvelope + DslDocument only",
    }


def _ifuri_compile_source(text: str) -> dict[str, Any]:
    source_doc = make_dsl_document("sourcedsl", source_text_dsl(text, "en"))
    reply, route = asyncio.run(
        RUNTIME.call("ifuri://llm/semantic/default/commands/compile", source_doc)
    )
    output = DslDocument()
    EnvelopeCodec.unpack(reply, output)
    return {
        "markdown": output.markdown,
        "validation": validate_markdown(output.markdown),
        "route": route.to_dict(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "IfuriIntentDSLLab/0.3"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("QUIET", "0") != "1":
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
        data = payload if isinstance(payload, bytes) else _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._send(200, {
                "ok": True,
                "version": "0.3.0",
                "boundary": "dsl-only",
                "addressing": "ifuri",
                "wire_contract": "protobuf",
                "cqrs_es": True,
            })
            return
        if path == "/api/ifuri/route":
            uri = (parse_qs(parsed.query).get("uri") or [""])[0]
            self._send(200, REGISTRY.explain(uri))
            return
        if path == "/api/ifuri/capabilities":
            self._send(200, {"capabilities": REGISTRY.dump()})
            return
        if path in {"/", "/index.html"}:
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
            path = urlparse(self.path).path
            if path == "/api/compile-context":
                compiler = compiler_from_payload(body)
                markdown = compiler.to_markdown()
                self._send(200, {"markdown": markdown, "validation": validate_context_markdown(markdown)})
                return

            if path in {"/api/analyze-context", "/api/ifuri/analyze-context"}:
                self._send(200, _ifuri_analyze_context(body))
                return

            if path in {"/api/convert", "/api/ifuri/compile-source"}:
                self._send(200, _ifuri_compile_source(str(body.get("text", ""))))
                return

            if path == "/api/validate":
                self._send(200, validate_markdown(str(body.get("markdown", ""))))
                return

            if path == "/api/run":
                markdown = str(body.get("markdown", ""))
                program = parse_dsl(extract_intentdsl(markdown))
                self._send(200, run_program(program, dict(body.get("inputs", {}) or {})))
                return

            if path == "/api/codegen":
                markdown = str(body.get("markdown", ""))
                program = parse_dsl(extract_intentdsl(markdown))
                self._send(200, {"code": codegen(program, str(body.get("target", "python")))})
                return

            self._send(404, {"error": "not_found"})
        except Exception as exc:
            self._send(400, {"error": type(exc).__name__, "message": str(exc)})


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    print(f"IFURI + IntentDSL Lab 0.3.0 listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
