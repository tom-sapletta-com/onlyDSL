from __future__ import annotations

import json
from dataclasses import dataclass

from ifuri_core.uri import IfUri, IfUriError

from .common import ControlDslError, HASH_RE, extract_one, json_string, list_value, parse_json_list, quoted


@dataclass(frozen=True, slots=True)
class RepairTask:
    id: str
    finding_code: str
    target: str
    evidence: tuple[str, ...]
    operation: str
    uri_process: str
    expected_result: str
    acceptance: str
    rollback: str
    depends_on: tuple[str, ...]
    authority_class: str


@dataclass(frozen=True, slots=True)
class RepairPlan:
    id: str
    twin_id: str
    from_revision: int
    from_integrity_hash: str
    status: str
    tasks: tuple[RepairTask, ...]


_REPAIR_TASK_FIELDS = {
    "FINDING", "TARGET", "EVIDENCE", "OPERATION", "URI_PROCESS", "EXPECTED_RESULT",
    "ACCEPTANCE", "ROLLBACK", "DEPENDS_ON", "AUTHORITY_CLASS",
}


def _validate_repair_task(task: RepairTask, task_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not all((task.target, task.evidence, task.operation, task.expected_result, task.acceptance, task.rollback, task.authority_class)):
        errors.append(f"TASK {task.id} has an empty required field")
    if not task.uri_process.startswith(("repo://", "process://", "cad://", "vault://")):
        errors.append(f"TASK {task.id} URI_PROCESS is not system-addressable")
    unknown = set(task.depends_on) - task_ids
    if unknown:
        errors.append(f"TASK {task.id} DEPENDS_ON unknown tasks: {', '.join(sorted(unknown))}")
    return errors


def validate_repair_plan(plan: RepairPlan) -> list[str]:
    errors: list[str] = []
    if plan.from_revision < 1:
        errors.append("FROM_REVISION must be >= 1")
    if not HASH_RE.fullmatch(plan.from_integrity_hash):
        errors.append("FROM_INTEGRITY_HASH must be exact sha256")
    task_ids = {task.id for task in plan.tasks}
    if len(task_ids) != len(plan.tasks):
        errors.append("TASK ids must be unique")
    if not plan.tasks and plan.status != "no-action":
        errors.append("at least one TASK is required")
    if plan.tasks and plan.status == "no-action":
        errors.append("no-action plan cannot contain TASKs")
    for task in plan.tasks:
        errors.extend(_validate_repair_task(task, task_ids))
    return errors


def render_repair_plan(plan: RepairPlan) -> str:
    errors = validate_repair_plan(plan)
    if errors:
        raise ControlDslError("; ".join(errors))
    rows = [
        "```repairplanddsl", f"REPAIR_PLAN {plan.id}", f"TWIN {plan.twin_id}",
        f"FROM_REVISION {plan.from_revision}", f"FROM_INTEGRITY_HASH {plan.from_integrity_hash}",
        f"STATUS {plan.status}",
    ]
    for task in plan.tasks:
        rows.extend([
            f"TASK {task.id}", f"  FINDING {task.finding_code}", f"  TARGET {task.target}",
            f"  EVIDENCE {list_value(task.evidence)}", f"  OPERATION {task.operation}",
            f"  URI_PROCESS {task.uri_process}", f"  EXPECTED_RESULT {quoted(task.expected_result)}",
            f"  ACCEPTANCE {quoted(task.acceptance)}", f"  ROLLBACK {quoted(task.rollback)}",
            f"  DEPENDS_ON {list_value(task.depends_on)}", f"  AUTHORITY_CLASS {task.authority_class}",
            "END_TASK",
        ])
    rows.extend(["END_REPAIR_PLAN", "```"])
    return "\n".join(rows)


def _parse_repair_task(lines: list[str], index: int) -> tuple[RepairTask, int]:
    task_id = lines[index].split(None, 1)[1]
    fields: dict[str, str] = {}
    index += 1
    while index < len(lines) and lines[index] != "END_TASK":
        key, _, value = lines[index].partition(" ")
        if key in fields:
            raise ControlDslError(f"TASK {task_id} repeats {key}")
        fields[key] = value
        index += 1
    if set(fields) != _REPAIR_TASK_FIELDS:
        raise ControlDslError(f"TASK {task_id} fields differ: {sorted(_REPAIR_TASK_FIELDS - fields.keys())}")
    return RepairTask(
        task_id, fields["FINDING"], fields["TARGET"], tuple(parse_json_list(fields["EVIDENCE"], "EVIDENCE")),
        fields["OPERATION"], fields["URI_PROCESS"], json_string(fields["EXPECTED_RESULT"], "EXPECTED_RESULT"),
        json_string(fields["ACCEPTANCE"], "ACCEPTANCE"), json_string(fields["ROLLBACK"], "ROLLBACK"),
        tuple(parse_json_list(fields["DEPENDS_ON"], "DEPENDS_ON")), fields["AUTHORITY_CLASS"],
    ), index


def parse_repair_plan(markdown: str) -> RepairPlan:
    lines = [line.strip() for line in extract_one(markdown, "repairplanddsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("REPAIR_PLAN ") or lines[-1] != "END_REPAIR_PLAN":
        raise ControlDslError("invalid RepairPlanDSL envelope")
    header: dict[str, str] = {}
    tasks: list[RepairTask] = []
    index = 1
    while index < len(lines) - 1:
        if lines[index].startswith("TASK "):
            task, index = _parse_repair_task(lines, index)
            tasks.append(task)
        else:
            key, _, value = lines[index].partition(" ")
            if key in header:
                raise ControlDslError(f"duplicate RepairPlan header {key}")
            header[key] = value
        index += 1
    if set(header) != {"TWIN", "FROM_REVISION", "FROM_INTEGRITY_HASH", "STATUS"}:
        raise ControlDslError("RepairPlanDSL requires exact TWIN/revision/integrity/status headers")
    plan = RepairPlan(lines[0].split(None, 1)[1], header["TWIN"], int(header["FROM_REVISION"]), header["FROM_INTEGRITY_HASH"], header["STATUS"], tuple(tasks))
    errors = validate_repair_plan(plan)
    if errors:
        raise ControlDslError("; ".join(errors))
    return plan
