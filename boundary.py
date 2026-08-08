from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

DSL_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z][A-Za-z0-9_.-]*)\s*\n(?P<body>.*?)```", re.S)
INPUT_DSL_LANGS = {
    "contractdsl", "taskdsl", "contextdsl", "sourcedsl", "schemadsl", "capabilitydsl",
    "twindsl", "sourceindexdsl", "validationdsl", "buildplanddsl",
}
OUTPUT_DSL_LANGS = {"intentdsl", "decisiondsl", "patchdsl", "twindsl", "buildplanddsl"}


class LlmBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class DslBundle:
    markdown: str

    def validate_for_llm(self) -> "DslBundle":
        assert_dsl_only(self.markdown, INPUT_DSL_LANGS)
        return self


def assert_dsl_only(markdown: str, allowed_languages: set[str]) -> None:
    if not markdown.strip():
        raise LlmBoundaryError("Empty LLM boundary payload")
    cursor = 0
    found = 0
    for match in DSL_FENCE_RE.finditer(markdown):
        if markdown[cursor:match.start()].strip():
            raise LlmBoundaryError("Natural-language/raw content outside DSL codeblocks is forbidden")
        lang = match.group("lang").lower()
        if lang not in allowed_languages:
            raise LlmBoundaryError(f"DSL language {lang!r} is not allowed at this boundary")
        if not match.group("body").strip():
            raise LlmBoundaryError(f"Empty {lang} block")
        cursor = match.end()
        found += 1
    if markdown[cursor:].strip():
        raise LlmBoundaryError("Natural-language/raw content outside DSL codeblocks is forbidden")
    if not found:
        raise LlmBoundaryError("LLM boundary requires fenced DSL blocks")


def contract_dsl(target: str = "intentdsl.v1") -> str:
    return f"""```contractdsl
PROTOCOL llm_boundary_v1
INPUT dsl_only
TARGET {target}
REQUIRE preserve_semantics
REQUIRE use_declared_symbols
REQUIRE use_declared_capabilities
REQUIRE preserve_source_provenance
FORBID raw_context
FORBID prose_outside_dsl
FORBID undeclared_action
FORBID undeclared_event
FORBID unsupported_requirement
```"""


def task_dsl(task: str, source: str, target: str = "intentdsl.v1", mode: str = "semantic_compile") -> str:
    return f"""```taskdsl
TASK {task}
SOURCE {source}
TARGET {target}
MODE {mode}
RETURN single_fenced_block
```"""


def source_text_dsl(text: str, language: str = "en", *, fingerprint: str = "") -> str:
    # Natural language may be source data, but it crosses the LLM boundary only as a typed DSL value.
    rows = [
        "SOURCE user_text",
        f"LANG {language}",
        "MEDIA text",
        "CONTENT_HASH sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    ]
    if fingerprint:
        rows.append(f"INTENT_FINGERPRINT {fingerprint}")
    rows.extend([
        "PAYLOAD " + json.dumps(text, ensure_ascii=False),
        "END_SOURCE",
    ])
    return "```sourcedsl\n" + "\n".join(rows) + "\n```"


def build_source_compile_bundle(text: str, language: str = "en") -> DslBundle:
    md = "\n".join([contract_dsl(), task_dsl("compile_intent", "sourcedsl"), source_text_dsl(text, language)])
    return DslBundle(md).validate_for_llm()


def build_context_analysis_bundle(context_markdown: str) -> DslBundle:
    assert_dsl_only(context_markdown, {"contextdsl"})
    md = "\n".join([contract_dsl(), task_dsl("analyze_runtime_context", "contextdsl"), context_markdown])
    return DslBundle(md).validate_for_llm()


def build_twin_bootstrap_bundle(user_text: str, fingerprint: str, schema_markdown: str, language: str = "en") -> DslBundle:
    assert_dsl_only(schema_markdown, {"schemadsl"})
    md = "\n".join([
        contract_dsl("twindsl.v1"),
        task_dsl("bootstrap_digital_twin", "sourcedsl", "twindsl.v1", "intent_to_twin"),
        schema_markdown,
        source_text_dsl(user_text, language, fingerprint=fingerprint),
    ])
    return DslBundle(md).validate_for_llm()


def build_twin_update_bundle(twin_markdown: str, source_index_markdown: str, schema_markdown: str) -> DslBundle:
    assert_dsl_only(twin_markdown, {"twindsl"})
    assert_dsl_only(source_index_markdown, {"sourceindexdsl"})
    assert_dsl_only(schema_markdown, {"schemadsl"})
    md = "\n".join([
        contract_dsl("twindsl.v1"),
        task_dsl("update_digital_twin", "twindsl+sourceindexdsl", "twindsl.v1", "evidence_bounded_revision"),
        schema_markdown,
        twin_markdown,
        source_index_markdown,
    ])
    return DslBundle(md).validate_for_llm()


def build_build_plan_bundle(twin_markdown: str, schema_markdown: str) -> DslBundle:
    assert_dsl_only(twin_markdown, {"twindsl"})
    assert_dsl_only(schema_markdown, {"schemadsl"})
    md = "\n".join([
        contract_dsl("buildplanddsl.v1"),
        task_dsl("derive_build_plan", "twindsl", "buildplanddsl.v1", "twin_to_implementation_plan"),
        schema_markdown,
        twin_markdown,
    ])
    return DslBundle(md).validate_for_llm()


def build_repair_bundle(original: DslBundle, target: str, errors: list[str]) -> DslBundle:
    original.validate_for_llm()
    rows = [
        "VALIDATION rejected",
        f"TARGET {target}",
        "ACTION regenerate_complete_output",
    ]
    for error in errors[:12]:
        rows.append("ERROR " + json.dumps(str(error)[:600], ensure_ascii=False))
    validation = "```validationdsl\n" + "\n".join(rows) + "\n```"
    return DslBundle(original.markdown + "\n" + validation).validate_for_llm()
