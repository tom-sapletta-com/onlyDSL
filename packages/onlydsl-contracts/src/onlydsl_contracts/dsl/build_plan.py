"""BuildPlanDSL contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from onlydsl_contracts.ifuri import IfUri

from .common import ControlDslError, HASH_RE, extract_one, json_string, parse_json_list


@dataclass(frozen=True, slots=True)
class BoundBuildTask:
    id: str
    target_uri: str
    evidence: tuple[str, ...]
    operation: str
    expected_result: str
    acceptance: str
    rollback: str
    depends_on: tuple[str, ...]
    authority_class: str


@dataclass(frozen=True, slots=True)
class BoundBuildPlan:
    twin_id: str
    from_revision: int
    from_twin_hash: str
    tasks: tuple[BoundBuildTask, ...]


def semantic_twin_hash(rendered_twin_markdown: str) -> str:
    return "sha256:" + hashlib.sha256(rendered_twin_markdown.encode("utf-8")).hexdigest()


_TASK_FIELDS = {
    "TARGET_URI", "EVIDENCE", "OPERATION", "EXPECTED_RESULT", "ACCEPTANCE", "ROLLBACK", "DEPENDS_ON", "AUTHORITY_CLASS",
}


def _parse_task(lines: list[str], index: int) -> tuple[BoundBuildTask, int]:
    task_id = lines[index].split(None, 1)[1]
    fields: dict[str, str] = {}
    index += 1
    while index < len(lines) and lines[index] != "END_TASK":
        key, _, value = lines[index].partition(" ")
        if key in fields:
            raise ControlDslError(f"TASK {task_id} repeats {key}")
        fields[key] = value
        index += 1
    if set(fields) != _TASK_FIELDS:
        raise ControlDslError(
            f"TASK {task_id} requires exact fields; missing {sorted(_TASK_FIELDS - fields.keys())}, "
            f"extra {sorted(fields.keys() - _TASK_FIELDS)}"
        )
    target = IfUri.parse(fields["TARGET_URI"])
    operation = fields["OPERATION"]
    if operation.split(".")[-1].replace("-", "_") != target.operation.replace("-", "_"):
        raise ControlDslError(f"TASK {task_id} OPERATION does not match TARGET_URI operation")
    task = BoundBuildTask(
        task_id, str(target), tuple(parse_json_list(fields["EVIDENCE"], "EVIDENCE")), operation,
        json_string(fields["EXPECTED_RESULT"], "EXPECTED_RESULT"), json_string(fields["ACCEPTANCE"], "ACCEPTANCE"),
        json_string(fields["ROLLBACK"], "ROLLBACK"), tuple(parse_json_list(fields["DEPENDS_ON"], "DEPENDS_ON")),
        fields["AUTHORITY_CLASS"],
    )
    return task, index


def _validate_tasks(tasks: list[BoundBuildTask]) -> None:
    if not tasks:
        raise ControlDslError("BuildPlanDSL requires at least one TASK")
    ids = {task.id for task in tasks}
    if len(ids) != len(tasks):
        raise ControlDslError("duplicate TASK id")
    for task in tasks:
        if not task.evidence:
            raise ControlDslError(f"TASK {task.id} requires exact EVIDENCE")
        if set(task.depends_on) - ids:
            raise ControlDslError(f"TASK {task.id} has unknown DEPENDS_ON")


def parse_bound_build_plan(markdown: str) -> BoundBuildPlan:
    lines = [line.strip() for line in extract_one(markdown, "buildplanddsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("BUILD_PLAN ") or lines[-1] != "END_BUILD_PLAN":
        raise ControlDslError("invalid BuildPlanDSL envelope")
    twin_id = lines[0].split(None, 1)[1]
    revision = None
    twin_hash = None
    tasks: list[BoundBuildTask] = []
    index = 1
    phase_depth = 0
    while index < len(lines) - 1:
        line = lines[index]
        if line.startswith("FROM_REVISION "):
            if revision is not None:
                raise ControlDslError("duplicate FROM_REVISION")
            revision = int(line.split(None, 1)[1])
        elif line.startswith("FROM_TWIN_HASH "):
            if twin_hash is not None:
                raise ControlDslError("duplicate FROM_TWIN_HASH")
            twin_hash = line.split(None, 1)[1]
        elif line.startswith("PHASE "):
            phase_depth += 1
        elif line.startswith("PURPOSE "):
            json_string(line.split(None, 1)[1], "PURPOSE")
        elif line.startswith("TASK "):
            if not phase_depth:
                raise ControlDslError("TASK must be inside PHASE")
            task, index = _parse_task(lines, index)
            tasks.append(task)
        elif line == "END_PHASE":
            if not phase_depth:
                raise ControlDslError("END_PHASE without PHASE")
            phase_depth -= 1
        else:
            raise ControlDslError(f"unknown BuildPlanDSL directive {line!r}")
        index += 1
    if phase_depth:
        raise ControlDslError("PHASE missing END_PHASE")
    if revision is None or twin_hash is None or not HASH_RE.fullmatch(twin_hash):
        raise ControlDslError("BuildPlanDSL requires exact FROM_REVISION and FROM_TWIN_HASH")
    _validate_tasks(tasks)
    return BoundBuildPlan(twin_id, revision, twin_hash, tuple(tasks))


def validate_bound_build_plan(markdown: str, twin: Any | None = None, rendered_twin_markdown: str = "") -> dict[str, Any]:
    try:
        plan = parse_bound_build_plan(markdown)
        if twin is not None:
            if plan.twin_id != twin.name:
                raise ControlDslError("BUILD_PLAN twin id differs from current Twin")
            if plan.from_revision != twin.revision:
                raise ControlDslError(f"FROM_REVISION must equal current revision {twin.revision}")
            expected_hash = semantic_twin_hash(rendered_twin_markdown)
            if plan.from_twin_hash != expected_hash:
                raise ControlDslError("FROM_TWIN_HASH differs from the current canonical Twin")
            allowed_evidence = set(twin.sources)
            for task in plan.tasks:
                for evidence in task.evidence:
                    if evidence not in allowed_evidence and not evidence.startswith("urn:subactor:evidence-set:sha256:"):
                        raise ControlDslError(f"TASK {task.id} references evidence outside the current Twin: {evidence}")
        return {"valid": True, "errors": [], "tasks": len(plan.tasks), "from_revision": plan.from_revision, "from_twin_hash": plan.from_twin_hash}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}
