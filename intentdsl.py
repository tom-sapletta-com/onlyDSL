from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

FENCE_RE = re.compile(r"```intentdsl\s*\n(?P<body>.*?)```", re.I | re.S)
IDENT_RE = r"[A-Za-z_][A-Za-z0-9_]*"
TYPE_NAMES = {"string", "number", "integer", "boolean"}


class IntentDslError(ValueError):
    pass


@dataclass
class Operation:
    kind: str
    value: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    name: str
    when: str = "true"
    operations: list[Operation] = field(default_factory=list)


@dataclass
class Program:
    intent: str
    inputs: dict[str, str] = field(default_factory=dict)
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    forbids: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_intentdsl(markdown: str) -> str:
    match = FENCE_RE.search(markdown)
    if match:
        return match.group("body").strip() + "\n"
    # API callers may send raw DSL. This is intentional: Markdown is transport, not parser semantics.
    if markdown.lstrip().startswith("INTENT "):
        return markdown.strip() + "\n"
    raise IntentDslError("No ```intentdsl fenced block found")


def _parse_literal(raw: str) -> Any:
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    if raw.startswith('"') and raw.endswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntentDslError(f"Invalid string literal: {raw}") from exc
    raise IntentDslError(f"Invalid literal: {raw}")


def _parse_call(raw: str) -> tuple[str, dict[str, Any]]:
    raw = raw.strip()
    plain = re.fullmatch(IDENT_RE, raw)
    if plain:
        return raw, {}
    match = re.fullmatch(rf"({IDENT_RE})\((.*)\)", raw)
    if not match:
        raise IntentDslError(f"Invalid action/event call: {raw}")
    name, arg_src = match.groups()
    arg_src = arg_src.strip()
    if not arg_src:
        return name, {}
    try:
        node = ast.parse(f"f({arg_src})", mode="eval").body
    except SyntaxError as exc:
        raise IntentDslError(f"Invalid call arguments: {raw}") from exc
    if not isinstance(node, ast.Call) or node.args:
        raise IntentDslError("Only named literal arguments are allowed")
    args: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is None or not isinstance(kw.value, ast.Constant):
            raise IntentDslError("Only named literal arguments are allowed")
        args[kw.arg] = kw.value.value
    return name, args


def parse_dsl(dsl: str) -> Program:
    lines = dsl.splitlines()
    program: Program | None = None
    current_rule: Rule | None = None

    for lineno, raw in enumerate(lines, start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()

        if current_rule is not None:
            if stripped == "END":
                program.rules.append(current_rule)  # type: ignore[union-attr]
                current_rule = None
                continue
            if not raw.startswith("  "):
                raise IntentDslError(f"Line {lineno}: rule statements require two-space indentation")
            if stripped.startswith("WHEN "):
                current_rule.when = stripped[5:].strip()
            elif stripped.startswith("DO "):
                name, args = _parse_call(stripped[3:])
                current_rule.operations.append(Operation("do", name, args))
            elif stripped.startswith("EMIT "):
                name, args = _parse_call(stripped[5:])
                current_rule.operations.append(Operation("emit", name, args))
            elif stripped.startswith("SET "):
                m = re.fullmatch(rf"SET ({IDENT_RE})\s*=\s*(.+)", stripped)
                if not m:
                    raise IntentDslError(f"Line {lineno}: invalid SET")
                current_rule.operations.append(Operation("set", m.group(2).strip(), {"target": m.group(1)}))
            elif stripped.startswith("ASSERT "):
                current_rule.operations.append(Operation("assert", stripped[7:].strip()))
            elif stripped == "STOP":
                current_rule.operations.append(Operation("stop"))
            else:
                raise IntentDslError(f"Line {lineno}: unknown rule statement: {stripped}")
            continue

        if stripped.startswith("INTENT "):
            name = stripped[7:].strip()
            if not re.fullmatch(IDENT_RE, name):
                raise IntentDslError(f"Line {lineno}: invalid intent identifier")
            if program is not None:
                raise IntentDslError(f"Line {lineno}: INTENT already declared")
            program = Program(intent=name)
            continue

        if program is None:
            raise IntentDslError(f"Line {lineno}: INTENT must be the first declaration")

        if stripped.startswith("INPUT "):
            m = re.fullmatch(rf"INPUT ({IDENT_RE}) ({'|'.join(TYPE_NAMES)})", stripped)
            if not m:
                raise IntentDslError(f"Line {lineno}: invalid INPUT")
            program.inputs[m.group(1)] = m.group(2)
        elif stripped.startswith("STATE "):
            m = re.fullmatch(rf"STATE ({IDENT_RE}) ({'|'.join(TYPE_NAMES)})\s*=\s*(.+)", stripped)
            if not m:
                raise IntentDslError(f"Line {lineno}: invalid STATE")
            program.states[m.group(1)] = {"type": m.group(2), "initial": _parse_literal(m.group(3))}
        elif stripped.startswith("RULE "):
            name = stripped[5:].strip()
            if not re.fullmatch(IDENT_RE, name):
                raise IntentDslError(f"Line {lineno}: invalid RULE identifier")
            current_rule = Rule(name=name)
        elif stripped.startswith("FORBID "):
            program.forbids.append(stripped[7:].strip())
        elif stripped.startswith("OUTPUT "):
            name = stripped[7:].strip()
            if not re.fullmatch(IDENT_RE, name):
                raise IntentDslError(f"Line {lineno}: invalid OUTPUT identifier")
            program.outputs.append(name)
        else:
            raise IntentDslError(f"Line {lineno}: unknown declaration: {stripped}")

    if current_rule is not None:
        raise IntentDslError(f"Rule {current_rule.name!r} is missing END")
    if program is None:
        raise IntentDslError("Missing INTENT declaration")
    return program


_ALLOWED_EXPR_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.Mod, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def _normalize_expr(expr: str) -> str:
    return re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", expr, flags=re.I), flags=re.I)


def _expr_tree(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(_normalize_expr(expr), mode="eval")
    except SyntaxError as exc:
        raise IntentDslError(f"Invalid expression {expr!r}: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_EXPR_NODES):
            raise IntentDslError(f"Forbidden expression construct {type(node).__name__} in {expr!r}")
    return tree


def expr_names(expr: str) -> set[str]:
    tree = _expr_tree(expr)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in {"True", "False"}}


def eval_expr(expr: str, env: dict[str, Any]) -> Any:
    tree = _expr_tree(expr)
    code = compile(tree, "<intentdsl>", "eval")
    return eval(code, {"__builtins__": {}}, env)  # noqa: S307 - AST whitelist removes calls/attrs/subscripts.


def _type_ok(type_name: str, value: Any) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def validate_program(
    program: Program,
    action_registry: Iterable[str] | None = None,
    event_registry: Iterable[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    declared = set(program.inputs) | set(program.states)
    allowed_actions = set(action_registry) if action_registry is not None else None
    allowed_events = set(event_registry) if event_registry is not None else None

    overlap = set(program.inputs) & set(program.states)
    if overlap:
        errors.append(f"Symbols declared as both INPUT and STATE: {', '.join(sorted(overlap))}")

    for name, spec in program.states.items():
        if not _type_ok(spec["type"], spec["initial"]):
            errors.append(f"STATE {name!r} initial value does not match {spec['type']}")

    seen_rules: set[str] = set()
    for rule in program.rules:
        if rule.name in seen_rules:
            errors.append(f"Duplicate rule: {rule.name}")
        seen_rules.add(rule.name)
        if not rule.operations:
            warnings.append(f"Rule {rule.name} has no operations")
        expressions = [rule.when]
        for op in rule.operations:
            if op.kind in {"assert", "set"}:
                expressions.append(op.value)
            if op.kind == "set":
                target = op.args["target"]
                if target not in program.states:
                    errors.append(f"SET target {target!r} is not a STATE")
            elif op.kind == "do" and allowed_actions is not None and op.value not in allowed_actions:
                errors.append(f"Rule {rule.name}: DO action {op.value!r} is not declared by runtime capabilities")
            elif op.kind == "emit" and allowed_events is not None and op.value not in allowed_events:
                errors.append(f"Rule {rule.name}: EMIT event {op.value!r} is not declared by runtime capabilities")
        for expr in expressions:
            try:
                unknown = expr_names(expr) - declared
                if unknown:
                    errors.append(f"Rule {rule.name}: unknown symbols in {expr!r}: {', '.join(sorted(unknown))}")
            except IntentDslError as exc:
                errors.append(f"Rule {rule.name}: {exc}")

    for expr in program.forbids:
        try:
            unknown = expr_names(expr) - declared
            if unknown:
                errors.append(f"FORBID {expr!r}: unknown symbols: {', '.join(sorted(unknown))}")
        except IntentDslError as exc:
            errors.append(str(exc))

    if not program.rules:
        warnings.append("Program has no RULE blocks")
    if not program.outputs:
        warnings.append("Program has no OUTPUT declaration")

    return {"valid": not errors, "errors": errors, "warnings": warnings, "ast": program.to_dict()}


def validate_markdown(
    markdown: str,
    action_registry: Iterable[str] | None = None,
    event_registry: Iterable[str] | None = None,
) -> dict[str, Any]:
    try:
        dsl = extract_intentdsl(markdown)
        program = parse_dsl(dsl)
        result = validate_program(program, action_registry=action_registry, event_registry=event_registry)
        result["dsl"] = dsl
        return result
    except IntentDslError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": [], "ast": None, "dsl": ""}


def run_program(
    program: Program,
    inputs: dict[str, Any],
    action_registry: Iterable[str] | None = None,
    event_registry: Iterable[str] | None = None,
) -> dict[str, Any]:
    validation = validate_program(program, action_registry=action_registry, event_registry=event_registry)
    if not validation["valid"]:
        return {"ok": False, "errors": validation["errors"], "trace": [], "events": [], "state": {}}

    errors: list[str] = []
    for name, type_name in program.inputs.items():
        if name not in inputs:
            errors.append(f"Missing input: {name}")
        elif not _type_ok(type_name, inputs[name]):
            errors.append(f"Input {name!r} must be {type_name}, got {type(inputs[name]).__name__}")
    if errors:
        return {"ok": False, "errors": errors, "trace": [], "events": [], "state": {}}

    state = {name: spec["initial"] for name, spec in program.states.items()}
    env = {**inputs, **state}
    trace: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    halted = False

    def check_forbids(stage: str) -> bool:
        nonlocal halted
        for expr in program.forbids:
            if bool(eval_expr(expr, env)):
                errors.append(f"FORBID violated at {stage}: {expr}")
                trace.append({"kind": "forbid", "expr": expr, "stage": stage, "ok": False})
                halted = True
                return False
        return True

    if not check_forbids("start"):
        return {"ok": False, "errors": errors, "trace": trace, "events": events, "state": state}

    for rule in program.rules:
        cond = bool(eval_expr(rule.when, env))
        trace.append({"kind": "rule", "rule": rule.name, "when": rule.when, "matched": cond})
        if not cond:
            continue
        for op in rule.operations:
            if op.kind == "set":
                value = eval_expr(op.value, env)
                target = op.args["target"]
                expected = program.states[target]["type"]
                if not _type_ok(expected, value):
                    errors.append(f"SET {target}: expected {expected}, got {type(value).__name__}")
                    halted = True
                    break
                state[target] = value
                env[target] = value
                trace.append({"kind": "set", "target": target, "value": value})
            elif op.kind == "assert":
                ok = bool(eval_expr(op.value, env))
                trace.append({"kind": "assert", "expr": op.value, "ok": ok})
                if not ok:
                    errors.append(f"ASSERT failed: {op.value}")
                    halted = True
                    break
            elif op.kind == "do":
                trace.append({"kind": "action", "name": op.value, "args": op.args})
            elif op.kind == "emit":
                event = {"name": op.value, "args": op.args}
                events.append(event)
                trace.append({"kind": "emit", **event})
            elif op.kind == "stop":
                trace.append({"kind": "stop"})
                halted = True
                break
            if not check_forbids(f"rule:{rule.name}"):
                break
        if halted:
            break

    return {"ok": not errors, "errors": errors, "trace": trace, "events": events, "state": state, "halted": halted}


def _slug_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in {"the", "a", "an", "to", "and", "of", "then", "it", "still", "if", "when"}]


def demo_english_to_dsl(text: str) -> str:
    """Deterministic baseline for the included demo. Arbitrary English should use grammar-constrained LLM mode."""
    lower = text.lower()
    intent = "runtime_policy"
    if "token" in lower and ("401" in lower or "unauthor" in lower):
        intent = "auth_recovery"
    elif "refund" in lower:
        intent = "refund_policy"

    lines = [f"INTENT {intent}"]

    if intent == "auth_recovery":
        lines += [
            "INPUT api_status integer",
            "INPUT refresh_status integer",
            "STATE retry_count integer = 0",
            "RULE unauthorized",
            "  WHEN api_status == 401",
            "  DO refresh_token",
            "  SET retry_count = retry_count + 1",
            "  ASSERT retry_count <= 2",
            "END",
            "RULE refresh_failed",
            "  WHEN refresh_status == 401 and retry_count >= 1",
            "  EMIT auth_error(reason=\"refresh_failed\")",
            "  STOP",
            "END",
            "FORBID retry_count > 2",
            "OUTPUT auth_recovery_result",
        ]
    else:
        # Generic, safe representation: preserve content as an event payload and force explicit follow-up refinement.
        label = "_".join(_slug_words(text)[:5]) or "unclassified"
        safe_text = json.dumps(text.strip()[:500], ensure_ascii=False)
        lines += [
            "STATE accepted boolean = false",
            "RULE capture",
            "  WHEN true",
            f"  EMIT source_intent(label=\"{label}\",text={safe_text})",
            "  SET accepted = true",
            "END",
            "ASSERTION_PLACEHOLDER" if False else "OUTPUT captured_intent",
        ]
    return "```intentdsl\n" + "\n".join(lines) + "\n```"


def _js_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def codegen(program: Program, target: str) -> str:
    target = target.lower()
    if target not in {"python", "typescript", "javascript", "php"}:
        raise IntentDslError(f"Unsupported codegen target: {target}")

    if target == "python":
        lines = ["def run(ctx):", "    actions = []", "    events = []"]
        for name in program.inputs:
            lines.append(f"    {name} = ctx[{name!r}]")
        for name, spec in program.states.items():
            lines.append(f"    {name} = {spec['initial']!r}")
        for rule in program.rules:
            expr = _normalize_expr(rule.when)
            lines.append(f"    if {expr}:")
            if not rule.operations:
                lines.append("        pass")
            for op in rule.operations:
                if op.kind == "do":
                    lines.append(f"        actions.append(({op.value!r}, {op.args!r}))")
                elif op.kind == "emit":
                    lines.append(f"        events.append({{'name': {op.value!r}, 'args': {op.args!r}}})")
                elif op.kind == "set":
                    lines.append(f"        {op.args['target']} = {_normalize_expr(op.value)}")
                elif op.kind == "assert":
                    lines.append(f"        assert {_normalize_expr(op.value)}")
                elif op.kind == "stop":
                    lines.append("        return {'actions': actions, 'events': events}")
        lines.append("    return {'actions': actions, 'events': events}")
        return "\n".join(lines)

    if target in {"typescript", "javascript"}:
        sig = "export function run(ctx: Record<string, unknown>)" if target == "typescript" else "export function run(ctx)"
        lines = [f"{sig} {{", "  const actions = [];", "  const events = [];"]
        for name, spec in program.states.items():
            decl = f"let {name}" + (f": { {'string':'string','number':'number','integer':'number','boolean':'boolean'}[spec['type']] }" if target == "typescript" else "")
            lines.append(f"  {decl} = {_js_literal(spec['initial'])};")
        for inp in program.inputs:
            typecast = " as any" if target == "typescript" else ""
            lines.append(f"  const {inp} = ctx[{_js_literal(inp)}]{typecast};")
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
                    expr2 = op.value.replace(" and ", " && ").replace(" or ", " || ")
                    lines.append(f"    if (!({expr2})) throw new Error({_js_literal('ASSERT failed: ' + op.value)});")
                elif op.kind == "stop":
                    lines.append("    return {actions, events};")
            lines.append("  }")
        lines.append("  return {actions, events};")
        lines.append("}")
        return "\n".join(lines)

    # PHP
    lines = ["<?php", "function runIntent(array $ctx): array {", "    $actions = [];", "    $events = [];"]
    for name, spec in program.states.items():
        val = json.dumps(spec["initial"], ensure_ascii=False)
        val = {"true": "true", "false": "false"}.get(val, val)
        lines.append(f"    ${name} = {val};")
    for inp in program.inputs:
        lines.append(f"    ${inp} = $ctx[{json.dumps(inp)}];")
    for rule in program.rules:
        expr = rule.when.replace(" and ", " && ").replace(" or ", " || ")
        expr = re.sub(rf"\b({'|'.join(map(re.escape, program.inputs.keys() | program.states.keys()))})\b", r"$\1", expr) if (program.inputs or program.states) else expr
        expr = expr.replace("true", "true").replace("false", "false")
        lines.append(f"    if ({expr}) {{")
        for op in rule.operations:
            if op.kind == "do":
                lines.append(f"        $actions[] = ['name' => {json.dumps(op.value)}, 'args' => {php_array(op.args)}];")
            elif op.kind == "emit":
                lines.append(f"        $events[] = ['name' => {json.dumps(op.value)}, 'args' => {php_array(op.args)}];")
            elif op.kind == "set":
                value = op.value.replace(" and ", " && ").replace(" or ", " || ")
                value = re.sub(rf"\b({'|'.join(map(re.escape, program.inputs.keys() | program.states.keys()))})\b", r"$\1", value)
                lines.append(f"        ${op.args['target']} = {value};")
            elif op.kind == "assert":
                value = re.sub(rf"\b({'|'.join(map(re.escape, program.inputs.keys() | program.states.keys()))})\b", r"$\1", op.value)
                lines.append(f"        if (!({value})) throw new RuntimeException({json.dumps('ASSERT failed: ' + op.value)});")
            elif op.kind == "stop":
                lines.append("        return ['actions' => $actions, 'events' => $events];")
        lines.append("    }")
    lines.append("    return ['actions' => $actions, 'events' => $events];")
    lines.append("}")
    return "\n".join(lines)


def php_array(values: dict[str, Any]) -> str:
    if not values:
        return "[]"
    parts = []
    for key, value in values.items():
        lit = json.dumps(value, ensure_ascii=False)
        lit = {"true": "true", "false": "false", "null": "null"}.get(lit, lit)
        parts.append(f"{json.dumps(key)} => {lit}")
    return "[" + ", ".join(parts) + "]"
