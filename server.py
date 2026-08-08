from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from contextdsl import compiler_from_payload, extract_contextdsl, parse_context_dsl, validate_context_markdown
from intentdsl import codegen, extract_intentdsl, parse_dsl, run_program, validate_markdown
from llm_client import analyze_context, convert_english

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _context_registries(context_markdown: str) -> tuple[set[str], set[str], dict[str, Any]]:
    doc = parse_context_dsl(extract_contextdsl(context_markdown))
    state_values = {name: spec["value"] for name, spec in doc.states.items()}
    return doc.action_capabilities, doc.event_capabilities, state_values


class Handler(BaseHTTPRequestHandler):
    server_version = "IntentDSLLab/0.2"

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
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send(200, {"ok": True, "version": "0.2.0", "boundary": "dsl-only"})
            return
        if path in {"/", "/index.html"}:
            data = (STATIC / "index.html").read_bytes()
            self._send(200, data, "text/html; charset=utf-8")
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

            if path == "/api/analyze-context":
                # Raw application payload stops here. The LLM client receives only compiled ContextDSL.
                context_markdown = compiler_from_payload(body.get("context", body)).to_markdown()
                context_validation = validate_context_markdown(context_markdown)
                if not context_validation["valid"]:
                    self._send(400, {"error": "invalid_contextdsl", **context_validation})
                    return
                result = analyze_context(context_markdown, str(body.get("backend", "demo")))
                actions, events, state_values = _context_registries(context_markdown)
                validation = validate_markdown(result["markdown"], action_registry=actions, event_registry=events)
                runtime = None
                if validation["valid"]:
                    program = parse_dsl(extract_intentdsl(result["markdown"]))
                    runtime_inputs = {name: state_values[name] for name in program.inputs if name in state_values}
                    missing = [name for name in program.inputs if name not in runtime_inputs]
                    if not missing:
                        runtime = run_program(program, runtime_inputs, action_registry=actions, event_registry=events)
                self._send(200, {
                    "context_markdown": context_markdown,
                    "context_validation": context_validation,
                    "llm_request_markdown": result["request_markdown"],
                    "intent_markdown": result["markdown"],
                    "intent_validation": validation,
                    "runtime": runtime,
                    "backend": result["backend"],
                    "constrained": result["constrained"],
                })
                return

            if path == "/api/convert":
                result = convert_english(str(body.get("text", "")), str(body.get("backend", "demo")))
                validation = validate_markdown(result["markdown"])
                self._send(200, {**result, "validation": validation})
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
        except Exception as exc:  # POC API: return explicit diagnostics.
            self._send(400, {"error": type(exc).__name__, "message": str(exc)})


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    print(f"IntentDSL Lab 0.2.0 listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
