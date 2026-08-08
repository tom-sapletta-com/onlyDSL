from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from aql import AqlContract
from governance import canonical_hash
from onlydsl.dsl.repair_plan import RepairPlan, RepairTask, render_repair_plan
from onlydsl.governance.authority_projection import AuthorityProjection, project_authority, render_authority_projection
from onlydsl.runtime.integrity import ProjectIntegrity, parse_project_integrity


@dataclass(frozen=True, slots=True)
class RepairCycle:
    integrity: ProjectIntegrity
    plan: RepairPlan
    authority: AuthorityProjection

    def to_dict(self) -> dict:
        return {
            "schema": "onlydsl.project-integrity-repair-cycle/v2",
            "status": "authorized",
            "integrity": asdict(self.integrity),
            "repair_plan_markdown": render_repair_plan(self.plan),
            "authority_projection_markdown": render_authority_projection(self.authority),
        }


def load_repair_registry(root: str | Path) -> dict:
    path = Path(root) / "config/process-packs/project-integrity-closure/registry.v2.json"
    return json.loads(path.read_text(encoding="utf-8"))


def plan_integrity_repairs(
    integrity_markdown: str, *, twin_revision: int, contract: AqlContract,
    registry: dict, principal: str = "bot:evolution-agent",
) -> RepairCycle:
    integrity = parse_project_integrity(integrity_markdown)
    mappings = registry.get("findings", {})
    tasks: list[RepairTask] = []
    operations: list[tuple[str, str]] = []
    integrity_uri = "urn:subactor:project-integrity:" + integrity.source_hash
    for finding in integrity.findings:
        mapping = mappings.get(finding.code)
        if not mapping:
            continue
        if finding.repair_uri != mapping["repair_uri"]:
            raise ValueError(f"finding {finding.code} proposes a repair URI that differs from the system registry")
        task_id = f"repair-{len(tasks)+1}-{finding.code.lower().replace('_', '-')}"
        target = finding.subjects[0] if finding.subjects and "://" in finding.subjects[0] else f"twin://{integrity.project_id}/component/{finding.subjects[0] if finding.subjects else 'project'}"
        evidence = tuple(dict.fromkeys((*finding.evidence, integrity_uri)))
        tasks.append(RepairTask(
            task_id, finding.code, target, evidence, mapping["oql"], mapping["uri_process"],
            mapping["expected_result"], mapping["acceptance"], mapping["rollback"], (), mapping["authority_class"],
        ))
        operations.append((mapping["oql"], mapping["uri_process"]))
    plan_id = "closure-" + integrity.source_hash.split(":")[-1][:16]
    plan = RepairPlan(plan_id, integrity.project_id, twin_revision, integrity.source_hash, "authorized" if tasks else "no-action", tuple(tasks))
    authority = project_authority(contract, twin_id=integrity.project_id, from_revision=twin_revision, operations=operations, principal=principal)
    return RepairCycle(integrity, plan, authority)


def execute_repair_cycle(
    cycle: RepairCycle, *, executor: Callable[[RepairTask], dict],
    testql: Callable[[], bool], eql: Callable[[], bool], next_integrity_markdown: Callable[[], str],
) -> dict:
    receipts = []
    for task in cycle.plan.tasks:
        result = executor(task)
        receipts.append({"task": task.id, "uri_process": task.uri_process, "result": result})
        if not result.get("ok"):
            return _receipt(cycle, "rolled_back", receipts, False, False, [])
    testql_ok, eql_ok = testql(), eql()
    after = parse_project_integrity(next_integrity_markdown())
    before_codes = {finding.code for finding in cycle.integrity.findings}
    after_codes = {finding.code for finding in after.findings}
    closed = sorted(before_codes - after_codes)
    state = "verified" if testql_ok and eql_ok and before_codes <= set(closed) else "rejected"
    return _receipt(cycle, state, receipts, testql_ok, eql_ok, closed)


def _receipt(cycle: RepairCycle, state: str, operations: list[dict], testql: bool, eql: bool, closed: list[str]) -> dict:
    core = {
        "schema": "onlydsl.project-integrity-closure-receipt/v2", "state": state,
        "plan_id": cycle.plan.id, "from_revision": cycle.plan.from_revision,
        "operations": operations, "testql": testql, "eql": eql, "closed_findings": closed,
    }
    return {**core, "receipt_hash": canonical_hash(core)}
