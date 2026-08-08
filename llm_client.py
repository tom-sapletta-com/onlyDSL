from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from boundary import DslBundle, assert_dsl_only, build_context_analysis_bundle, build_source_compile_bundle
from contextdsl import extract_contextdsl, parse_context_dsl
from intentdsl import demo_english_to_dsl

ROOT = Path(__file__).resolve().parent
GRAMMAR = (ROOT / "grammar" / "intentdsl.gbnf").read_text(encoding="utf-8")


def _request_json(url: str, payload: dict[str, Any], api_key: str = "") -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM connection failed: {exc}") from exc


def _backend_call(bundle: DslBundle, backend: str) -> dict[str, Any]:
    # The only generic LLM call path. It rejects prose/raw payloads before network I/O.
    bundle.validate_for_llm()
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    if not model:
        raise RuntimeError("LLM_MODEL is required for LLM mode")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": bundle.markdown}],
        "temperature": 0,
        "max_tokens": 1600,
    }
    constrained = False
    if backend == "vllm":
        payload["structured_outputs"] = {"grammar": GRAMMAR}
        constrained = True
    elif backend == "llamacpp":
        payload["grammar"] = GRAMMAR
        constrained = True
    elif backend != "openai_compat":
        raise RuntimeError("LLM_BACKEND must be demo, vllm, llamacpp, or openai_compat")

    result = _request_json(f"{base_url}/chat/completions", payload, api_key)
    try:
        markdown = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {json.dumps(result)[:1000]}") from exc
    assert_dsl_only(markdown, {"intentdsl"})
    return {"backend": backend, "markdown": markdown, "constrained": constrained, "request_markdown": bundle.markdown}


def convert_english(text: str, backend: str | None = None) -> dict[str, Any]:
    """User text may exist, but it reaches the LLM only inside runtime-generated SourceDSL."""
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    bundle = build_source_compile_bundle(text, "en")
    if backend == "demo":
        return {
            "backend": "demo",
            "markdown": demo_english_to_dsl(text),
            "constrained": False,
            "request_markdown": bundle.markdown,
        }
    return _backend_call(bundle, backend)


def _demo_context_analysis(context_markdown: str) -> str:
    doc = parse_context_dsl(extract_contextdsl(context_markdown))
    statuses: list[int] = []
    for state_name, spec in doc.states.items():
        if isinstance(spec.get("value"), int) and "status" in state_name.lower():
            statuses.append(spec["value"])
    for rec in doc.records:
        for key, value in rec.fields.items():
            if "status" in key and isinstance(value, int):
                statuses.append(value)

    if 401 in statuses and "refresh_token" in doc.action_capabilities and "auth_error" in doc.event_capabilities:
        return """```intentdsl
INTENT auth_recovery
INPUT api_status integer
INPUT refresh_status integer
STATE retry_count integer = 0
RULE unauthorized
  WHEN api_status == 401
  DO refresh_token
  SET retry_count = retry_count + 1
  ASSERT retry_count <= 2
END
RULE refresh_failed
  WHEN refresh_status == 401 and retry_count >= 1
  EMIT auth_error(reason="refresh_failed")
  STOP
END
FORBID retry_count > 2
OUTPUT auth_recovery_result
```"""

    return """```intentdsl
INTENT context_assessment
STATE analyzed boolean = false
RULE observe
  WHEN true
  SET analyzed = true
END
OUTPUT context_analysis_result
```"""


def analyze_context(context_markdown: str, backend: str | None = None) -> dict[str, Any]:
    """Strict path: accepts ContextDSL only; raw logs/state/tool output are impossible here."""
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    bundle = build_context_analysis_bundle(context_markdown)
    if backend == "demo":
        return {
            "backend": "demo",
            "markdown": _demo_context_analysis(context_markdown),
            "constrained": False,
            "request_markdown": bundle.markdown,
        }
    return _backend_call(bundle, backend)
