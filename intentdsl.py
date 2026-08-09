from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from intent_codegen import generate_code, php_array

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


def _parse_rule_statement(raw: str, lineno: int, rule: Rule) -> None:
    if raw.startswith("WHEN "):
        rule.when = raw[5:].strip()
    elif raw.startswith("DO "):
        name, args = _parse_call(raw[3:])
        rule.operations.append(Operation("do", name, args))
    elif raw.startswith("EMIT "):
        name, args = _parse_call(raw[5:])
        rule.operations.append(Operation("emit", name, args))
    elif raw.startswith("SET "):
        match = re.fullmatch(rf"SET ({IDENT_RE})\s*=\s*(.+)", raw)
        if not match:
            raise IntentDslError(f"Line {lineno}: invalid SET")
        rule.operations.append(Operation("set", match.group(2).strip(), {"target": match.group(1)}))
    elif raw.startswith("ASSERT "):
        rule.operations.append(Operation("assert", raw[7:].strip()))
    elif raw == "STOP":
        rule.operations.append(Operation("stop"))
    else:
        raise IntentDslError(f"Line {lineno}: unknown rule statement: {raw}")


def _parse_program_declaration(stripped: str, lineno: int, program: Program | None) -> tuple[Program | None, Rule | None]:
    if stripped.startswith("INTENT "):
        name = stripped[7:].strip()
        if not re.fullmatch(IDENT_RE, name):
            raise IntentDslError(f"Line {lineno}: invalid intent identifier")
        if program is not None:
            raise IntentDslError(f"Line {lineno}: INTENT already declared")
        return Program(intent=name), None
    if program is None:
        raise IntentDslError(f"Line {lineno}: INTENT must be the first declaration")
    if stripped.startswith("INPUT "):
        match = re.fullmatch(rf"INPUT ({IDENT_RE}) ({'|'.join(TYPE_NAMES)})", stripped)
        if not match:
            raise IntentDslError(f"Line {lineno}: invalid INPUT")
        program.inputs[match.group(1)] = match.group(2)
    elif stripped.startswith("STATE "):
        match = re.fullmatch(rf"STATE ({IDENT_RE}) ({'|'.join(TYPE_NAMES)})\s*=\s*(.+)", stripped)
        if not match:
            raise IntentDslError(f"Line {lineno}: invalid STATE")
        program.states[match.group(1)] = {"type": match.group(2), "initial": _parse_literal(match.group(3))}
    elif stripped.startswith("RULE "):
        name = stripped[5:].strip()
        if not re.fullmatch(IDENT_RE, name):
            raise IntentDslError(f"Line {lineno}: invalid RULE identifier")
        return program, Rule(name=name)
    elif stripped.startswith("FORBID "):
        program.forbids.append(stripped[7:].strip())
    elif stripped.startswith("OUTPUT "):
        name = stripped[7:].strip()
        if not re.fullmatch(IDENT_RE, name):
            raise IntentDslError(f"Line {lineno}: invalid OUTPUT identifier")
        program.outputs.append(name)
    else:
        raise IntentDslError(f"Line {lineno}: unknown declaration: {stripped}")
    return program, None


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
                if program is None:
                    raise IntentDslError(f"Line {lineno}: rule block cannot appear before INTENT")
                program.rules.append(current_rule)
                current_rule = None
                continue
            if not raw.startswith("  "):
                raise IntentDslError(f"Line {lineno}: rule statements require two-space indentation")
            _parse_rule_statement(stripped, lineno, current_rule)
            continue

        program, current_rule = _parse_program_declaration(stripped, lineno, program)

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


def _validate_rule_expressions(rule: Rule, declared: set[str], errors: list[str]) -> None:
    for expr in [rule.when, *[op.value for op in rule.operations if op.kind in {"assert", "set"}]]:
        try:
            unknown = expr_names(expr) - declared
            if unknown:
                errors.append(f"Rule {rule.name}: unknown symbols in {expr!r}: {', '.join(sorted(unknown))}")
        except IntentDslError as exc:
            errors.append(f"Rule {rule.name}: {exc}")


def _validate_rule_runtime_capabilities(
    rule: Rule,
    program: Program,
    allowed_actions: set[str] | None,
    allowed_events: set[str] | None,
    errors: list[str],
) -> None:
    for op in rule.operations:
        if op.kind == "set":
            target = op.args["target"]
            if target not in program.states:
                errors.append(f"SET target {target!r} is not a STATE")
        elif op.kind == "do" and allowed_actions is not None and op.value not in allowed_actions:
            errors.append(f"Rule {rule.name}: DO action {op.value!r} is not declared by runtime capabilities")
        elif op.kind == "emit" and allowed_events is not None and op.value not in allowed_events:
            errors.append(f"Rule {rule.name}: EMIT event {op.value!r} is not declared by runtime capabilities")


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
        _validate_rule_runtime_capabilities(rule, program, allowed_actions, allowed_events, errors)
        _validate_rule_expressions(rule, declared, errors)

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

    def apply_operation(rule_name: str, op: Operation) -> bool:
        nonlocal halted
        if op.kind == "set":
            value = eval_expr(op.value, env)
            target = op.args["target"]
            expected = program.states[target]["type"]
            if not _type_ok(expected, value):
                errors.append(f"SET {target}: expected {expected}, got {type(value).__name__}")
                halted = True
                return False
            state[target] = value
            env[target] = value
            trace.append({"kind": "set", "target": target, "value": value})
        elif op.kind == "assert":
            ok = bool(eval_expr(op.value, env))
            trace.append({"kind": "assert", "expr": op.value, "ok": ok})
            if not ok:
                errors.append(f"ASSERT failed: {op.value}")
                halted = True
                return False
        elif op.kind == "do":
            trace.append({"kind": "action", "name": op.value, "args": op.args})
        elif op.kind == "emit":
            event = {"name": op.value, "args": op.args}
            events.append(event)
            trace.append({"kind": "emit", **event})
        elif op.kind == "stop":
            trace.append({"kind": "stop"})
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
            if not apply_operation(rule.name, op):
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
    lines.extend(_auth_recovery_lines() if intent == "auth_recovery" else _generic_demo_lines(text))
    return "```intentdsl\n" + "\n".join(lines) + "\n```"


def _auth_recovery_lines() -> list[str]:
    return [
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


def _generic_demo_lines(text: str) -> list[str]:
    # Generic, safe representation: preserve content as an event payload and force explicit follow-up refinement.
    label = "_".join(_slug_words(text)[:5]) or "unclassified"
    safe_text = json.dumps(text.strip()[:500], ensure_ascii=False)
    return [
        "STATE accepted boolean = false",
        "RULE capture",
        "  WHEN true",
        f"  EMIT source_intent(label=\"{label}\",text={safe_text})",
        "  SET accepted = true",
        "END",
        "OUTPUT captured_intent",
    ]


def codegen(program: Program, target: str) -> str:
    target = target.lower()
    if target not in {"python", "typescript", "javascript", "php"}:
        raise IntentDslError(f"Unsupported codegen target: {target}")
    return generate_code(program, target)
