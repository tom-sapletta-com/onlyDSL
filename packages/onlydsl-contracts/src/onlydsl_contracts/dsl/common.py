"""Shared deterministic helpers for public onlyDSL contracts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z][A-Za-z0-9_.-]*)\s*\n(?P<body>.*?)```", re.S)
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,191}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ControlDslError(ValueError):
    pass


def extract_one(markdown: str, language: str) -> str:
    blocks = [m.group("body").strip() for m in FENCE_RE.finditer(markdown) if m.group("lang").lower() == language]
    if len(blocks) != 1:
        raise ControlDslError(f"expected exactly one {language} block, found {len(blocks)}")
    if FENCE_RE.sub("", markdown).strip():
        raise ControlDslError(f"prose outside {language} block is forbidden")
    return blocks[0]


def json_string(raw: str, label: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ControlDslError(f"{label} must be a JSON string") from exc
    if not isinstance(value, str):
        raise ControlDslError(f"{label} must be a string")
    return value


def quoted(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def list_value(values: Iterable[str]) -> str:
    return "[" + ", ".join(json.dumps(value, ensure_ascii=False) for value in values) + "]"


def parse_json_list(raw: str, label: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ControlDslError(f"{label} must be a JSON list") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControlDslError(f"{label} must contain strings")
    return value
