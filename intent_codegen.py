"""Target-specific renderers for IntentDSL programs.

This module accepts the parser's public Program shape without importing it,
which keeps code generation separate from parsing and runtime evaluation.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _normalize_python_expr(expr: str) -> str:
    return re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", expr, flags=re.I), flags=re.I)


def _js_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def php_array(values: dict[str, Any]) -> str:
    if not values:
        return "[]"
    parts = []
    for key, value in values.items():
        literal = json.dumps(value, ensure_ascii=False)
        literal = {"true": "true", "false": "false", "null": "null"}.get(literal, literal)
        parts.append(f"{json.dumps(key)} => {literal}")
    return "[" + ", ".join(parts) + "]"


def _codegen_python(program: Any) -> str:
    lines = ["def run(ctx):", "    actions = []", "    events = []"]
    for name in program.inputs:
        lines.append(f"    {name} = ctx[{name!r}]")
    for name, spec in program.states.items():
        lines.append(f"    {name} = {spec['initial']!r}")
    for rule in program.rules:
        lines.append(f"    if {_normalize_python_expr(rule.when)}:")
        if not rule.operations:
            lines.append("        pass")
        for op in rule.operations:
            if op.kind == "do":
                lines.append(f"        actions.append(({op.value!r}, {op.args!r}))")
            elif op.kind == "emit":
                lines.append(f"        events.append({{'name': {op.value!r}, 'args': {op.args!r}}})")
            elif op.kind == "set":
                lines.append(f"        {op.args['target']} = {_normalize_python_expr(op.value)}")
            elif op.kind == "assert":
                lines.append(f"        assert {_normalize_python_expr(op.value)}")
            elif op.kind == "stop":
                lines.append("        return {'actions': actions, 'events': events}")
    lines.append("    return {'actions': actions, 'events': events}")
    return "\n".join(lines)


def _codegen_javascript_like(program: Any, target: str) -> str:
    signature = "export function run(ctx: Record<string, unknown>)" if target == "typescript" else "export function run(ctx)"
    lines = [f"{signature} {{", "  const actions = [];", "  const events = [];"]
    for name, spec in program.states.items():
        type_name = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean"}[spec["type"]]
        declaration = f"let {name}" + (f": {type_name}" if target == "typescript" else "")
        lines.append(f"  {declaration} = {_js_literal(spec['initial'])};")
    for input_name in program.inputs:
        typecast = " as any" if target == "typescript" else ""
        lines.append(f"  const {input_name} = ctx[{_js_literal(input_name)}]{typecast};")
    for rule in program.rules:
        expr = rule.when.replace(" and ", " && ").replace(" or ", " || ").replace(" not ", " !")
        expr = re.sub(r"\btrue\b", "true", re.sub(r"\bfalse\b", "false", expr, flags=re.I), flags=re.I)
        lines.append(f"  if ({expr}) {{")
        for op in rule.operations:
            if op.kind == "do":
                lines.append(f"    actions.push({{name: {_js_literal(op.value)}, args: {_js_literal(op.args)}}});")
            elif op.kind == "emit":
                lines.append(f"    events.push({{name: {_js_literal(op.value)}, args: {_js_literal(op.args)}}});")
            elif op.kind == "set":
                value = op.value.replace(" and ", " && ").replace(" or ", " || ")
                lines.append(f"    {op.args['target']} = {value};")
            elif op.kind == "assert":
                value = op.value.replace(" and ", " && ").replace(" or ", " || ")
                lines.append(f"    if (!({value})) throw new Error({_js_literal('ASSERT failed: ' + op.value)});")
            elif op.kind == "stop":
                lines.append("    return {actions, events};")
        lines.append("  }")
    lines.extend(["  return {actions, events};", "}"])
    return "\n".join(lines)


def _codegen_php(program: Any) -> str:
    lines = ["<?php", "function runIntent(array $ctx): array {", "    $actions = [];", "    $events = [];"]
    symbols = program.inputs.keys() | program.states.keys()
    symbol_pattern = rf"\b({'|'.join(map(re.escape, symbols))})\b" if symbols else None
    for name, spec in program.states.items():
        value = json.dumps(spec["initial"], ensure_ascii=False)
        value = {"true": "true", "false": "false"}.get(value, value)
        lines.append(f"    ${name} = {value};")
    for input_name in program.inputs:
        lines.append(f"    ${input_name} = $ctx[{json.dumps(input_name)}];")
    for rule in program.rules:
        expr = rule.when.replace(" and ", " && ").replace(" or ", " || ")
        if symbol_pattern is not None:
            expr = re.sub(symbol_pattern, r"$\1", expr)
        lines.append(f"    if ({expr}) {{")
        for op in rule.operations:
            if op.kind == "do":
                lines.append(f"        $actions[] = ['name' => {json.dumps(op.value)}, 'args' => {php_array(op.args)}];")
            elif op.kind == "emit":
                lines.append(f"        $events[] = ['name' => {json.dumps(op.value)}, 'args' => {php_array(op.args)}];")
            elif op.kind == "set":
                value = op.value.replace(" and ", " && ").replace(" or ", " || ")
                if symbol_pattern is not None:
                    value = re.sub(symbol_pattern, r"$\1", value)
                lines.append(f"        ${op.args['target']} = {value};")
            elif op.kind == "assert":
                value = op.value
                if symbol_pattern is not None:
                    value = re.sub(symbol_pattern, r"$\1", value)
                lines.append(f"        if (!({value})) throw new RuntimeException({json.dumps('ASSERT failed: ' + op.value)});")
            elif op.kind == "stop":
                lines.append("        return ['actions' => $actions, 'events' => $events];")
        lines.append("    }")
    lines.extend(["    return ['actions' => $actions, 'events' => $events];", "}"])
    return "\n".join(lines)


def generate_code(program: Any, target: str) -> str:
    if target == "python":
        return _codegen_python(program)
    if target in {"typescript", "javascript"}:
        return _codegen_javascript_like(program, target)
    return _codegen_php(program)
