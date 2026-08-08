from __future__ import annotations

import asyncio
import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from boundary import (
    build_context_analysis_bundle,
    build_twin_bootstrap_bundle,
    build_twin_update_bundle,
    source_text_dsl,
)
from contextdsl import compiler_from_payload, extract_contextdsl, parse_context_dsl, validate_context_markdown
from digital_twin import (
    buildplandsl_schema,
    extract_twindsl,
    intent_fingerprint,
    parse_twindsl,
    twin_to_mermaid,
    twindsl_schema,
    validate_buildplan_markdown,
    validate_twin_markdown,
)
from intentdsl import codegen, extract_intentdsl, parse_dsl, run_program, validate_markdown
from evolution import EvolutionStore
from aql import AqlContract
from source_ingest import build_source_index, validate_sourceindex_markdown
from twin_store import TwinStore
from ifuri_core.dsl_document import make_dsl_document
from ifuri_core.dsl_pb2 import DslDocument
from ifuri_core.envelope import EnvelopeCodec
from ifuri_core.llm_gateway import (
    build_llm_build_plan_handler,
    build_llm_reasoner_handler,
    build_llm_semantic_handler,
    build_llm_twin_bootstrap_handler,
    build_llm_twin_update_handler,
    gateway_provider_status,
)
from ifuri_core.manifest import CapabilityRegistry
from ifuri_core.runtime import IfuriRuntime
from ifuri_core.transport import InProcessTransport

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SOURCES = Path(os.getenv("SOURCES_DIR", str(ROOT / "sources")))
STORE = TwinStore(os.getenv("TWIN_STATE_DIR", str(ROOT / "state")))
EVOLUTION = EvolutionStore(os.getenv("EVOLUTION_STATE_DIR", str(ROOT / "runtime" / "evolution")))


def evolution_authority_status():
    path = os.getenv("EVOLUTION_AQL_CONTRACT", str(ROOT / "config/contracts/evolution-agent.contract.aql"))
    try:
        return AqlContract.from_file(path).public_status()
    except Exception as exc:
        return {"configured": False, "error": str(exc)}

REGISTRY = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")
INPROC = InProcessTransport()
BACKEND = os.getenv("LLM_BACKEND", "demo")
INPROC.register("llm.reasoner.analyze", build_llm_reasoner_handler(BACKEND))
INPROC.register("llm.semantic.compile", build_llm_semantic_handler(BACKEND))
INPROC.register("llm.twin.bootstrap", build_llm_twin_bootstrap_handler(BACKEND))
INPROC.register("llm.twin.update", build_llm_twin_update_handler(BACKEND))
INPROC.register("llm.builder.plan", build_llm_build_plan_handler(BACKEND))
RUNTIME = IfuriRuntime(REGISTRY, {"inproc": INPROC})


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _context_registries(context_markdown: str) -> tuple[set[str], set[str], dict[str, Any]]:
    doc = parse_context_dsl(extract_contextdsl(context_markdown))
    state_values = {name: spec["value"] for name, spec in doc.states.items()}
    return doc.action_capabilities, doc.event_capabilities, state_values


def _unpack_dsl(reply) -> DslDocument:
    output = DslDocument()
    EnvelopeCodec.unpack(reply, output)
    return output


def _ifuri_analyze_context(body: dict[str, Any]) -> dict[str, Any]:
    context_markdown = compiler_from_payload(body.get("context", body)).to_markdown()
    context_validation = validate_context_markdown(context_markdown)
    if not context_validation["valid"]:
        raise ValueError("invalid ContextDSL: " + "; ".join(context_validation["errors"]))
    dsl_doc = make_dsl_document("contextdsl", context_markdown)
    reply, route = asyncio.run(RUNTIME.call("ifuri://llm/reasoner/default/commands/analyze", dsl_doc))
    output = _unpack_dsl(reply)
    actions, events, state_values = _context_registries(context_markdown)
    intent_validation = validate_markdown(output.markdown, action_registry=actions, event_registry=events)
    runtime_result = None
    if intent_validation["valid"]:
        program = parse_dsl(extract_intentdsl(output.markdown))
        runtime_inputs = {name: state_values[name] for name in program.inputs if name in state_values}
        if len(runtime_inputs) == len(program.inputs):
            runtime_result = run_program(program, runtime_inputs, action_registry=actions, event_registry=events)
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
    reply, route = asyncio.run(RUNTIME.call("ifuri://llm/semantic/default/commands/compile", source_doc))
    output = _unpack_dsl(reply)
    return {"markdown": output.markdown, "validation": validate_markdown(output.markdown), "route": route.to_dict()}


def _twin_payload(markdown: str) -> dict[str, Any]:
    doc = parse_twindsl(extract_twindsl(markdown))
    return {
        "markdown": markdown,
        "validation": validate_twin_markdown(markdown),
        "mermaid": twin_to_mermaid(doc),
        "revision": doc.revision,
        "intent_fingerprint": doc.intent_fingerprint,
        "sources": [{"id": x.id, "path": x.path, "digest": x.digest} for x in doc.sources.values()],
        "open_questions": list(doc.open_questions),
    }


def _bootstrap_twin(body: dict[str, Any]) -> dict[str, Any]:
    intent = str(body.get("intent", "")).strip()
    if not intent:
        raise ValueError("intent is required")
    if STORE.exists() and not bool(body.get("reset", False)):
        raise ValueError("digital twin already exists; use reset=true to bootstrap a new intent")
    if bool(body.get("reset", False)):
        STORE.reset_current()

    fp = intent_fingerprint(intent)
    source_md = source_text_dsl(intent, str(body.get("language", "en")), fingerprint=fp)
    source_doc = make_dsl_document("sourcedsl", source_md)
    reply, route = asyncio.run(
        RUNTIME.call(
            "ifuri://llm/twin/default/commands/bootstrap",
            source_doc,
            source_uri="ifuri://twin/session/default/commands/bootstrap",
        )
    )
    output = _unpack_dsl(reply)
    STORE.save(output.markdown)
    result = _twin_payload(output.markdown)
    result.update({
        "route": route.to_dict(),
        "llm_request_markdown": build_twin_bootstrap_bundle(intent, fp, twindsl_schema(), str(body.get("language", "en"))).markdown,
        "provider": gateway_provider_status(),
    })
    return result


def _scan_sources() -> dict[str, Any]:
    index = build_source_index(SOURCES)
    markdown = index.to_markdown()
    return {
        "markdown": markdown,
        "validation": validate_sourceindex_markdown(markdown),
        "documents": index.source_refs(),
    }


def _update_twin(body: dict[str, Any]) -> dict[str, Any]:
    current = STORE.load_markdown()
    source = _scan_sources()
    if not source["documents"] and not bool(body.get("allow_empty", False)):
        raise ValueError("sources/ contains no Markdown documents")
    bundle_md = current + "\n" + source["markdown"]
    input_doc = make_dsl_document("dslbundle", bundle_md)
    reply, route = asyncio.run(
        RUNTIME.call(
            "ifuri://llm/twin/default/commands/update",
            input_doc,
            source_uri="ifuri://twin/session/default/commands/update",
        )
    )
    output = _unpack_dsl(reply)
    STORE.save(output.markdown)
    result = _twin_payload(output.markdown)
    result.update({
        "route": route.to_dict(),
        "source_index": source,
        "llm_request_markdown": build_twin_update_bundle(current, source["markdown"], twindsl_schema()).markdown,
        "provider": gateway_provider_status(),
    })
    return result


def _plan_twin() -> dict[str, Any]:
    current = STORE.load_markdown()
    input_doc = make_dsl_document("twindsl", current)
    reply, route = asyncio.run(
        RUNTIME.call(
            "ifuri://llm/builder/default/commands/plan",
            input_doc,
            source_uri="ifuri://builder/session/default/commands/plan",
        )
    )
    output = _unpack_dsl(reply)
    return {
        "markdown": output.markdown,
        "validation": validate_buildplan_markdown(output.markdown),
        "route": route.to_dict(),
        "provider": gateway_provider_status(),
        "schema": buildplandsl_schema(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "IfuriDigitalTwinLab/0.4"

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path != "/api/health" and os.getenv("QUIET", "0") != "1":
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
        data = payload if isinstance(payload, bytes) else _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        if self.path != "/api/health":
            try:
                EVOLUTION.add_event("http_response", {
                    "method": self.command,
                    "path": urlparse(self.path).path,
                    "status": status,
                    "bytes": len(data),
                })
            except Exception:
                pass

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
                "version": "0.4.0",
                "boundary": "dsl-only",
                "addressing": "ifuri",
                "wire_contract": "protobuf",
                "cqrs_es": True,
                "digital_twin": True,
                "provider": gateway_provider_status(),
            })
            return
        if path == "/api/llm/status":
            self._send(200, gateway_provider_status())
            return
        if path == "/api/evolution/status":
            status = EVOLUTION.status()
            status["authority"] = evolution_authority_status()
            status["execution_boundary"] = {
                "model_commands": "forbidden",
                "uri_owner": "system_process_pack",
                "secret_values_visible_to_model": False,
            }
            self._send(200, status)
            return
        if path == "/api/evolution/diagnostics":
            limit_raw = (parse_qs(parsed.query).get("limit") or ["20"])[0]
            try:
                limit = min(100, max(1, int(limit_raw)))
            except ValueError:
                raise ValueError("diagnostics limit must be an integer")
            self._send(200, {
                "schema": "subactor.diagnostic-log-view/v1",
                "diagnostics": EVOLUTION.latest_diagnostics(limit),
            })
            return
        if path == "/api/ifuri/route":
            uri = (parse_qs(parsed.query).get("uri") or [""])[0]
            self._send(200, REGISTRY.explain(uri))
            return
        if path == "/api/ifuri/capabilities":
            self._send(200, {"capabilities": REGISTRY.dump()})
            return
        if path == "/api/twin":
            if not STORE.exists():
                self._send(200, {"exists": False})
            else:
                self._send(200, {"exists": True, **_twin_payload(STORE.load_markdown())})
            return
        if path == "/api/twin/sources":
            self._send(200, _scan_sources())
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
            if path == "/api/twin/bootstrap":
                self._send(200, _bootstrap_twin(body))
                return
            if path == "/api/twin/update":
                self._send(200, _update_twin(body))
                return
            if path == "/api/twin/plan":
                self._send(200, _plan_twin())
                return
            if path == "/api/evolution/guidance":
                result = EVOLUTION.add_guidance(
                    str(body.get("directive", "")),
                    source=str(body.get("source", "api")),
                    priority=str(body.get("priority", "normal")),
                )
                self._send(201, result)
                return
            if path == "/api/evolution/report":
                result = EVOLUTION.add_incident(
                    str(body.get("kind", "reported_bug")),
                    str(body.get("message", "")),
                    source=str(body.get("source", "api")),
                    severity=str(body.get("severity", "error")),
                    route=str(body.get("route", "")),
                    trace=str(body.get("trace", "")),
                    fields=dict(body.get("fields", {}) or {}),
                )
                self._send(202, result)
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
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": type(exc).__name__, "message": str(exc)})
        except RuntimeError as exc:
            EVOLUTION.add_event("llm_provider_failure", {
                "path": urlparse(self.path).path,
                "error_type": type(exc).__name__,
                "message": str(exc)[:4000],
            })
            self._send(502, {"error": type(exc).__name__, "message": str(exc)})
        except Exception as exc:
            incident = EVOLUTION.add_incident(
                "unhandled_exception",
                str(exc),
                source="http_server",
                severity="error",
                route=urlparse(self.path).path,
                trace=traceback.format_exc(),
                fields={"method": self.command, "error_type": type(exc).__name__},
            )
            self._send(500, {
                "error": type(exc).__name__,
                "message": str(exc),
                "incident_id": incident["id"],
            })


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    print(f"IFURI Digital Twin Lab 0.4.0 listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
