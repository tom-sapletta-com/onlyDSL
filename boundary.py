from __future__ import annotations

import json
import re
from dataclasses import dataclass

DSL_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z][A-Za-z0-9_.-]*)\s*\n(?P<body>.*?)```", re.S)
INPUT_DSL_LANGS = {"contractdsl", "taskdsl", "contextdsl", "sourcedsl", "schemadsl", "capabilitydsl"}
OUTPUT_DSL_LANGS = {"intentdsl", "decisiondsl", "patchdsl"}


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
FORBID raw_context
FORBID prose_outside_dsl
FORBID undeclared_action
FORBID undeclared_event
```"""


def task_dsl(task: str, source: str, target: str = "intentdsl.v1") -> str:
    return f"""```taskdsl
TASK {task}
SOURCE {source}
TARGET {target}
MODE semantic_compile
RETURN single_fenced_block
```"""


def source_text_dsl(text: str, language: str = "en") -> str:
    # Natural language is source data, but it crosses the LLM boundary only as a typed DSL value.
    return "```sourcedsl\n" + "\n".join([
        "SOURCE user_text",
        f"LANG {language}",
        "MEDIA text",
        "PAYLOAD " + json.dumps(text, ensure_ascii=False),
        "END_SOURCE",
    ]) + "\n```"


def build_source_compile_bundle(text: str, language: str = "en") -> DslBundle:
    md = "\n".join([contract_dsl(), task_dsl("compile_intent", "sourcedsl"), source_text_dsl(text, language)])
    return DslBundle(md).validate_for_llm()


def build_context_analysis_bundle(context_markdown: str) -> DslBundle:
    # Context must already be compiled by runtime/application. This function never accepts raw logs/state/tool payloads.
    assert_dsl_only(context_markdown, {"contextdsl"})
    md = "\n".join([contract_dsl(), task_dsl("analyze_runtime_context", "contextdsl"), context_markdown])
    return DslBundle(md).validate_for_llm()
