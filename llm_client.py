from __future__ import annotations

import copy
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from boundary import (
    DslBundle,
    LlmBoundaryError,
    assert_dsl_only,
    build_repair_bundle,
    build_build_plan_bundle,
    build_context_analysis_bundle,
    build_source_compile_bundle,
    build_twin_bootstrap_bundle,
    build_twin_update_bundle,
)
from contextdsl import extract_contextdsl, parse_context_dsl
from digital_twin import (
    demo_bootstrap_twin,
    demo_build_plan,
    extract_twindsl,
    intent_fingerprint,
    parse_twindsl,
    render_twin,
    twindsl_schema,
    buildplandsl_schema,
    validate_buildplan_markdown,
    validate_twin_markdown,
    validate_twin_update,
)
from intentdsl import demo_english_to_dsl
from source_ingest import extract_source_refs, validate_sourceindex_markdown

ROOT = Path(__file__).resolve().parent
GRAMMAR = (ROOT / "grammar" / "intentdsl.gbnf").read_text(encoding="utf-8")


class LlmProviderError(RuntimeError):
    pass


def _request_json(
    url: str,
    payload: dict[str, Any],
    api_key: str = "",
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LlmProviderError(f"LLM HTTP {exc.code}: {body[:1800]}") from exc
    except urllib.error.URLError as exc:
        raise LlmProviderError(f"LLM connection failed: {exc}") from exc


def _provider_config(backend: str) -> tuple[str, str, str, dict[str, str]]:
    backend = backend.lower()
    if backend == "openrouter":
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        model = os.getenv("OPENROUTER_MODEL") or os.getenv("LLM_MODEL") or "~openai/gpt-latest"
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY", "")
        if not api_key:
            raise LlmProviderError(
                "OPENROUTER_API_KEY is required when LLM_BACKEND=openrouter; "
                "put it in .env and never commit the real key"
            )
        headers: dict[str, str] = {}
        referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
        title = os.getenv("OPENROUTER_APP_TITLE", "IFURI Digital Twin Lab").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-OpenRouter-Title"] = title
        return base_url, model, api_key, headers

    base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    if not model:
        raise LlmProviderError("LLM_MODEL is required for this LLM backend")
    return base_url, model, api_key, {}


def _backend_call(
    bundle: DslBundle,
    backend: str,
    *,
    output_lang: str,
    max_tokens: int = 3200,
) -> dict[str, Any]:
    """The only generic network LLM call path.

    Input is fail-closed DSL-only. Output is also fail-closed: prose or a wrong DSL
    fence is rejected before it can reach domain/runtime code.
    """
    bundle.validate_for_llm()
    backend = backend.lower()
    base_url, model, api_key, headers = _provider_config(backend)

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": bundle.markdown}],
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", str(max_tokens))),
    }
    constrained = False
    if backend == "vllm":
        if output_lang == "intentdsl":
            payload["structured_outputs"] = {"grammar": GRAMMAR}
            constrained = True
    elif backend == "llamacpp":
        if output_lang == "intentdsl":
            payload["grammar"] = GRAMMAR
            constrained = True
    elif backend in {"openai_compat", "openrouter"}:
        # OpenRouter/OpenAI-compatible providers do not expose arbitrary CFG in this
        # adapter. Correctness is enforced by the DSL contract + fail-closed parser.
        pass
    else:
        raise LlmProviderError(
            "LLM_BACKEND must be demo, openrouter, vllm, llamacpp, or openai_compat"
        )

    result = _request_json(f"{base_url}/chat/completions", payload, api_key, extra_headers=headers)
    try:
        markdown = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmProviderError(f"Unexpected LLM response: {json.dumps(result)[:1200]}") from exc
    assert_dsl_only(markdown, {output_lang})
    return {
        "backend": backend,
        "model": model,
        "markdown": markdown,
        "constrained": constrained,
        "request_markdown": bundle.markdown,
        "usage": result.get("usage") or {},
    }


def provider_status(backend: str | None = None) -> dict[str, Any]:
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    if backend == "demo":
        return {"backend": "demo", "configured": True, "network": False, "model": "deterministic-demo"}
    try:
        base_url, model, api_key, headers = _provider_config(backend)
        return {
            "backend": backend,
            "configured": bool(api_key or backend in {"vllm", "llamacpp", "openai_compat"}),
            "network": True,
            "base_url": base_url,
            "model": model,
            "api_key_present": bool(api_key),
            "attribution_headers": sorted(headers),
        }
    except Exception as exc:
        return {"backend": backend, "configured": False, "error": str(exc)}



def _call_dsl_validated(
    bundle: DslBundle,
    backend: str,
    *,
    output_lang: str,
    max_tokens: int,
    validator: Callable[[str], list[str]],
) -> dict[str, Any]:
    attempts = max(0, int(os.getenv("LLM_REPAIR_ATTEMPTS", "2")))
    current = bundle
    last_errors: list[str] = []
    for attempt in range(attempts + 1):
        try:
            result = _backend_call(current, backend, output_lang=output_lang, max_tokens=max_tokens)
            last_errors = validator(result["markdown"])
            if not last_errors:
                result["repair_attempts"] = attempt
                return result
        except LlmBoundaryError as exc:
            last_errors = [str(exc)]
        if attempt < attempts:
            # Re-send only the original trusted DSL + typed validation errors. The
            # rejected raw model response is deliberately not fed back to the LLM.
            current = build_repair_bundle(bundle, f"{output_lang}.v1", last_errors)
    raise LlmProviderError(
        f"LLM failed {output_lang} validation after {attempts + 1} attempt(s): "
        + "; ".join(last_errors)
    )

def convert_english(text: str, backend: str | None = None) -> dict[str, Any]:
    """User text reaches the LLM only inside runtime-generated SourceDSL."""
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    bundle = build_source_compile_bundle(text, "en")
    if backend == "demo":
        return {
            "backend": "demo",
            "model": "deterministic-demo",
            "markdown": demo_english_to_dsl(text),
            "constrained": False,
            "request_markdown": bundle.markdown,
            "usage": {},
        }
    return _backend_call(bundle, backend, output_lang="intentdsl", max_tokens=1800)


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
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    bundle = build_context_analysis_bundle(context_markdown)
    if backend == "demo":
        return {
            "backend": "demo",
            "model": "deterministic-demo",
            "markdown": _demo_context_analysis(context_markdown),
            "constrained": False,
            "request_markdown": bundle.markdown,
            "usage": {},
        }
    return _backend_call(bundle, backend, output_lang="intentdsl", max_tokens=1800)


def bootstrap_twin(user_text: str, backend: str | None = None) -> dict[str, Any]:
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    fp = intent_fingerprint(user_text)
    bundle = build_twin_bootstrap_bundle(user_text, fp, twindsl_schema(), "en")
    if backend == "demo":
        result = {
            "backend": "demo",
            "model": "deterministic-demo",
            "markdown": demo_bootstrap_twin(user_text),
            "constrained": False,
            "request_markdown": bundle.markdown,
            "usage": {},
        }
    else:
        expected_source_hash = "sha256:" + hashlib.sha256(user_text.encode("utf-8")).hexdigest()

        def validate_bootstrap(markdown: str) -> list[str]:
            validation = validate_twin_markdown(markdown)
            errors = list(validation["errors"])
            if errors:
                return errors
            doc = parse_twindsl(extract_twindsl(markdown))
            if doc.intent_fingerprint != fp:
                errors.append("copy INTENT_FINGERPRINT exactly from SourceDSL")
            if doc.sources.get("user_intent") is None or doc.sources["user_intent"].digest != expected_source_hash:
                errors.append("SOURCE user_intent HASH must equal SourceDSL CONTENT_HASH")
            return errors

        result = _call_dsl_validated(
            bundle, backend, output_lang="twindsl", max_tokens=5200, validator=validate_bootstrap
        )

    validation = validate_twin_markdown(result["markdown"])
    if not validation["valid"]:
        raise LlmProviderError("LLM returned invalid TwinDSL: " + "; ".join(validation["errors"]))
    doc = parse_twindsl(extract_twindsl(result["markdown"]))
    if doc.intent_fingerprint != fp:
        raise LlmProviderError("LLM changed the runtime-computed INTENT_FINGERPRINT")
    expected_source_hash = "sha256:" + hashlib.sha256(user_text.encode("utf-8")).hexdigest()
    if doc.sources.get("user_intent") is None or doc.sources["user_intent"].digest != expected_source_hash:
        raise LlmProviderError("TwinDSL must copy the runtime-computed user_intent source hash")
    result["validation"] = validation
    return result


def _demo_update_twin(previous_markdown: str, source_index_markdown: str) -> str:
    previous = parse_twindsl(extract_twindsl(previous_markdown))
    updated = copy.deepcopy(previous)
    updated.revision += 1
    refs = extract_source_refs(source_index_markdown)
    for source_id, row in refs.items():
        from digital_twin import TwinSourceRef

        updated.sources[source_id] = TwinSourceRef(source_id, row["digest"], row["path"])
    if refs:
        evidence_ids = list(refs)
        if "source_ingest" in updated.nodes:
            for source_id in evidence_ids:
                if source_id not in updated.nodes["source_ingest"].evidence:
                    updated.nodes["source_ingest"].evidence.append(source_id)
        if "evidence_before_evolution" in updated.invariants:
            for source_id in evidence_ids:
                if source_id not in updated.invariants["evidence_before_evolution"].evidence:
                    updated.invariants["evidence_before_evolution"].evidence.append(source_id)
        updated.open_questions = [
            q for q in updated.open_questions if "sources/" not in q
        ]
        updated.open_questions.append(
            "Which source-backed capabilities should be promoted from evidence into implementation tasks first?"
        )
    return render_twin(updated)


def update_twin(
    previous_markdown: str,
    source_index_markdown: str,
    backend: str | None = None,
) -> dict[str, Any]:
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    source_validation = validate_sourceindex_markdown(source_index_markdown)
    if not source_validation["valid"]:
        raise LlmProviderError("invalid SourceIndexDSL: " + "; ".join(source_validation["errors"]))
    previous = parse_twindsl(extract_twindsl(previous_markdown))
    bundle = build_twin_update_bundle(previous_markdown, source_index_markdown, twindsl_schema())
    if backend == "demo":
        result = {
            "backend": "demo",
            "model": "deterministic-demo",
            "markdown": _demo_update_twin(previous_markdown, source_index_markdown),
            "constrained": False,
            "request_markdown": bundle.markdown,
            "usage": {},
        }
    else:
        allowed_refs = {"user_intent": previous.sources["user_intent"].digest}
        allowed_refs.update({k: v["digest"] for k, v in extract_source_refs(source_index_markdown).items()})

        def validate_update(markdown: str) -> list[str]:
            base = validate_twin_markdown(markdown)
            errors = list(base["errors"])
            if errors:
                return errors
            updated = parse_twindsl(extract_twindsl(markdown))
            errors.extend(validate_twin_update(previous, updated))
            for sid, source in updated.sources.items():
                if sid == "user_intent":
                    if source.digest != previous.sources["user_intent"].digest:
                        errors.append("user_intent source digest is immutable")
                elif sid in allowed_refs:
                    if source.digest != allowed_refs[sid]:
                        errors.append(f"SOURCE {sid} digest does not match current SourceIndexDSL")
                elif sid in previous.sources:
                    if source.digest != previous.sources[sid].digest:
                        errors.append(f"SOURCE {sid} changed without current source evidence")
                else:
                    errors.append(f"updated twin invented unknown SOURCE {sid}")
            return errors

        result = _call_dsl_validated(
            bundle, backend, output_lang="twindsl", max_tokens=6200, validator=validate_update
        )

    updated = parse_twindsl(extract_twindsl(result["markdown"]))
    errors = validate_twin_update(previous, updated)
    allowed_refs = {"user_intent": previous.sources["user_intent"].digest}
    allowed_refs.update({k: v["digest"] for k, v in extract_source_refs(source_index_markdown).items()})
    for sid, source in updated.sources.items():
        if sid == "user_intent":
            if source.digest != previous.sources["user_intent"].digest:
                errors.append("user_intent source digest is immutable")
        elif sid in allowed_refs:
            if source.digest != allowed_refs[sid]:
                errors.append(f"SOURCE {sid} digest does not match current SourceIndexDSL")
        elif sid in previous.sources:
            if source.digest != previous.sources[sid].digest:
                errors.append(f"SOURCE {sid} changed without current source evidence")
        else:
            errors.append(f"updated twin invented unknown SOURCE {sid}")
    if errors:
        raise LlmProviderError("LLM returned invalid twin revision: " + "; ".join(errors))
    result["validation"] = validate_twin_markdown(result["markdown"])
    return result


def plan_build(twin_markdown: str, backend: str | None = None) -> dict[str, Any]:
    backend = (backend or os.getenv("LLM_BACKEND", "demo")).lower()
    doc = parse_twindsl(extract_twindsl(twin_markdown))
    bundle = build_build_plan_bundle(twin_markdown, buildplandsl_schema())
    if backend == "demo":
        result = {
            "backend": "demo",
            "model": "deterministic-demo",
            "markdown": demo_build_plan(doc),
            "constrained": False,
            "request_markdown": bundle.markdown,
            "usage": {},
        }
    else:
        def validate_plan(markdown: str) -> list[str]:
            validation = validate_buildplan_markdown(markdown)
            return list(validation["errors"])

        result = _call_dsl_validated(
            bundle, backend, output_lang="buildplanddsl", max_tokens=4200, validator=validate_plan
        )
    validation = validate_buildplan_markdown(result["markdown"])
    if not validation["valid"]:
        raise LlmProviderError("LLM returned invalid BuildPlanDSL: " + "; ".join(validation["errors"]))
    result["validation"] = validation
    return result
