from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aql import AqlContract
from boundary import authority_dsl, build_autonomous_repair_bundle
from digital_twin import buildplandsl_schema, extract_twindsl, parse_twindsl, validate_buildplan_markdown
from llm_client import bootstrap_twin, plan_build
from onlydsl.dsl.assumption import parse_assumptions, render_assumptions
from onlydsl.dsl.common import ControlDslError
from onlydsl.dsl.evidence_set import create_evidence_set, parse_evidence_set, render_evidence_set
from onlydsl.dsl.parameter_contract import parse_parameter_contracts
from onlydsl.dsl.repair_plan import parse_repair_plan
from onlydsl.dsl.spatial_class import SpatialClass, parse_spatial_class, render_spatial_class, spatial_class_from_twin
from onlydsl.runtime.integrity import parse_project_integrity
from onlydsl.runtime.repair_controller import execute_repair_cycle, load_repair_registry, plan_integrity_repairs

ROOT = Path(__file__).resolve().parents[1]


def integrity(findings: bool = True, *, complete: bool = False) -> str:
    rows = [
        "```projectintegritydsl", "PROJECT_INTEGRITY laboratory", "METHOD deterministic-cross-layer",
        "COVERAGE LAYERS 8/8 DEPENDENCIES 5/6 PARAMETERS 183/183 ASSUMPTIONS 0/1",
        f"COMPLETENESS {'COMPLETE' if complete else 'INCOMPLETE'}",
    ]
    if findings:
        rows.extend([
            "FINDING CONCEPTUAL_GEOMETRY_ASSUMPTION SEVERITY WARNING CATEGORY ungrounded-assumption LAYER design",
            '  SUBJECTS ["biospec_bioreactor_01"]', "  EVIDENCE []",
            "  REPAIR subactor://process/repair/project-integrity/replace-conceptual-geometry",
            '  MESSAGE "temporary cube requires grounded CAD"', "END_FINDING",
            "FINDING GEOMETRY_VALIDATION_INCOMPLETE SEVERITY WARNING CATEGORY missing-evidence LAYER validation",
            '  SUBJECTS ["dashboard-floor-plan"]', "  EVIDENCE []",
            "  REPAIR subactor://process/repair/project-integrity/complete-geometry-evidence",
            '  MESSAGE "orientation and constraints are missing"', "END_FINDING",
        ])
    rows.extend(["RESULT PASS", "END_PROJECT_INTEGRITY", "```"])
    return "\n".join(rows)


class ProjectIntegrityClosureTests(unittest.TestCase):
    def test_authority_is_not_sent_to_the_model_and_demo_health_is_truthful(self):
        incident = '```incidentdsl\nINCIDENT one\nMESSAGE "bug"\nEND_INCIDENT\n```'
        authority = authority_dsl("sha256:" + "a" * 64, {"server.py": ("code.change", "repo://workspace/source/command/patch")})
        bundle = build_autonomous_repair_bundle(incident, [], {"server.py": "VALUE = 1\n"}, authority_markdown=authority)
        self.assertNotIn("authoritydsl", bundle.markdown)
        self.assertNotIn("CONTRACT_HASH", bundle.markdown)
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('"runtime_profile": RUNTIME_PROFILE', server_source)
        self.assertIn('"cqrs_es": False', server_source)
        self.assertNotIn('"cqrs_es": True', server_source)

    def test_spatial_class_limits_geometry_to_physical_and_hybrid(self):
        markdown = """```spatialclassdsl
SPATIAL_MODEL laboratory
TYPE equipment
  CLASS physical
  REQUIRE position
  REQUIRE size
  REQUIRE orientation
END_TYPE
TYPE software_service
  CLASS cyber
  FORBID position
  FORBID size
  REQUIRE logical-endpoint
  REQUIRE runtime-status
END_TYPE
TYPE governance_layer
  CLASS logical
  FORBID position
  FORBID size
END_TYPE
COMPONENT bioreactor TYPE equipment
COMPONENT sila TYPE software_service
COMPONENT governance TYPE governance_layer
END_SPATIAL_MODEL
```"""
        document = parse_spatial_class(markdown)
        self.assertEqual(document.classify("bioreactor"), SpatialClass.PHYSICAL)
        self.assertEqual(document.geometry_subjects(), {"bioreactor"})
        self.assertEqual(parse_spatial_class(render_spatial_class(document)).geometry_subjects(), {"bioreactor"})
        projected = spatial_class_from_twin({"id": "lab", "components": [
            {"id": "bioreactor", "type": "equipment", "properties": {"spatialClass": "physical", "spatialRequire": "position|size|orientation"}, "children": []},
            {"id": "planner", "type": "service", "properties": {"spatialClass": "cyber", "spatialRequire": "logical-endpoint|runtime-status", "spatialForbid": "position|size|orientation"}, "children": []},
        ]})
        self.assertEqual(projected.geometry_subjects(), {"bioreactor"})

    def test_assumption_has_lifecycle_and_exact_replacement_evidence(self):
        markdown = """```assumptiondsl
ASSUMPTION_SET laboratory
ASSUMPTION geo-build-position-v1
  SUBJECT twin://laboratory/component/build
  CLASS geometry
  STATUS open
  CLAIM "temporary placement"
  REASON "survey not delivered"
  INTRODUCED_BY deterministic-layout
  EVIDENCE []
  REPLACE_WHEN "evidence.level >= measured"
  REPAIR subactor://process/repair/project-integrity/replace-conceptual-geometry
END_ASSUMPTION
END_ASSUMPTION_SET
```"""
        document = parse_assumptions(markdown)
        updated = document.replace_with_evidence("geo-build-position-v1", "urn:survey:sha256:abc", condition_met=True)
        self.assertEqual(updated.status, "superseded")
        self.assertIn("urn:survey:sha256:abc", render_assumptions(document))

    def test_parameter_contract_rejects_mixed_unit_and_domain_range_error(self):
        contracts = parse_parameter_contracts("""```parametercontractdsl
PARAMETER_CONTRACTS laboratory
PARAMETER temperature
  SUBJECT_TYPE laboratory_environment
  TYPE decimal
  UNIT Cel
  RANGE [-20, 80]
  QUALITY observed
END_PARAMETER
PARAMETER availability
  SUBJECT_TYPE software_service
  TYPE boolean
  UNIT none
  QUALITY observed
END_PARAMETER
END_PARAMETER_CONTRACTS
```""")
        self.assertTrue(contracts.validate(name="temperature", subject_type="laboratory_environment", value=22, unit="Cel", quality="observed").ok)
        self.assertEqual(contracts.validate(name="temperature", subject_type="laboratory_environment", value=100, unit="Cel", quality="observed").code, "PARAMETER_ABOVE_MAXIMUM")
        self.assertEqual(contracts.validate(name="availability", subject_type="software_service", value=True, unit="none", quality="observed").code, "PARAMETER_VALID")
        self.assertEqual(contracts.validate(name="temperature", subject_type="laboratory_environment", value=22, unit="mixed", quality="observed").code, "PARAMETER_UNIT_MIXED_FORBIDDEN")
        with self.assertRaises(ControlDslError):
            parse_parameter_contracts("""```parametercontractdsl
PARAMETER_CONTRACTS bad
PARAMETER temperature
  SUBJECT_TYPE laboratory_environment
  TYPE decimal
  UNIT mixed
  QUALITY observed
END_PARAMETER
END_PARAMETER_CONTRACTS
```""")

    def test_evidence_set_replaces_long_uri_list_with_hash_bound_reference(self):
        evidence = create_evidence_set("research-v34", "urn:subactor:query-result:sha256:abc", ["urn:r:2", "urn:r:1", "urn:r:1"])
        self.assertEqual(evidence.members, 2)
        parsed = parse_evidence_set(render_evidence_set(evidence))
        self.assertEqual(parsed.members_hash, evidence.members_hash)
        self.assertTrue(parsed.uri.startswith("urn:subactor:evidence-set:sha256:"))

    def test_build_plan_is_bound_to_exact_twin_revision_hash_and_evidence(self):
        twin_result = bootstrap_twin("Build a governed source-backed application.", "demo")
        twin = parse_twindsl(extract_twindsl(twin_result["markdown"]))
        result = plan_build(twin_result["markdown"], "demo")
        self.assertTrue(validate_buildplan_markdown(result["markdown"], twin)["valid"])
        self.assertIn("FROM_TWIN_HASH sha256:", result["markdown"])
        self.assertIn("EXPECTED_RESULT", result["markdown"])
        self.assertIn("ROLLBACK", result["markdown"])
        schema = buildplandsl_schema()
        self.assertIn('EXAMPLE EVIDENCE ["user_intent"', schema)
        self.assertIn("EXAMPLE DEPENDS_ON []", schema)
        stale = result["markdown"].replace("FROM_REVISION 1", "FROM_REVISION 2")
        self.assertFalse(validate_buildplan_markdown(stale, twin)["valid"])

    def test_project_integrity_has_four_outcomes_and_system_owned_repair_plan(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        cycle = plan_integrity_repairs(integrity(), twin_revision=3, contract=contract, registry=load_repair_registry(ROOT))
        self.assertEqual(cycle.integrity.integrity, "PASS")
        self.assertEqual(cycle.integrity.evidence, "INCOMPLETE")
        self.assertEqual(cycle.integrity.operational_ready, "PARTIAL")
        self.assertEqual(cycle.integrity.autonomy_ready, "PASS")
        plan = parse_repair_plan(cycle.to_dict()["repair_plan_markdown"])
        self.assertEqual(plan.from_revision, 3)
        self.assertEqual({task.uri_process for task in plan.tasks}, {"cad://openscad/scad/geometry/compile", "process://twin/physical-evidence/complete"})
        authority = cycle.to_dict()["authority_projection_markdown"]
        self.assertIn("OWNERSHIP system", authority)
        self.assertIn("model_cannot_create_or_modify_authority", authority)
        self.assertIn("ASSUMPTION conceptual-geometry-assumption-biospec-bioreactor-01-1", cycle.to_dict()["assumption_markdown"])

    def test_repair_plan_identity_is_append_only_across_twin_revisions(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        registry = load_repair_registry(ROOT)
        revision_three = plan_integrity_repairs(integrity(), twin_revision=3, contract=contract, registry=registry)
        revision_four = plan_integrity_repairs(integrity(), twin_revision=4, contract=contract, registry=registry)
        self.assertNotEqual(revision_three.plan.id, revision_four.plan.id)
        self.assertTrue(revision_three.plan.id.startswith("closure-r3-"))
        self.assertTrue(revision_four.plan.id.startswith("closure-r4-"))
        self.assertEqual(revision_three.plan.from_integrity_hash, revision_four.plan.from_integrity_hash)

    def test_e2e_finding_to_authorized_process_testql_eql_and_closed_iteration(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        cycle = plan_integrity_repairs(integrity(), twin_revision=3, contract=contract, registry=load_repair_registry(ROOT))
        called: list[str] = []
        receipt = execute_repair_cycle(
            cycle,
            executor=lambda task: called.append(task.uri_process) or {"ok": True, "artifact": "urn:physical-evidence:sha256:new"},
            testql=lambda: True, eql=lambda: True,
            next_integrity_markdown=lambda: integrity(False, complete=True),
        )
        self.assertEqual(receipt["state"], "verified")
        self.assertEqual(set(receipt["closed_findings"]), {"CONCEPTUAL_GEOMETRY_ASSUMPTION", "GEOMETRY_VALIDATION_INCOMPLETE"})
        self.assertEqual(called, ["cad://openscad/scad/geometry/compile", "process://twin/physical-evidence/complete"])
        self.assertTrue(receipt["receipt_hash"].startswith("sha256:"))

    def test_extent_drift_routes_to_evidence_reconciliation_without_weakening_tolerance(self):
        markdown = """```projectintegritydsl
PROJECT_INTEGRITY laboratory
METHOD deterministic-cross-layer
COVERAGE LAYERS 8/8 DEPENDENCIES 5/6 PARAMETERS 183/183 ASSUMPTIONS 0/1
COMPLETENESS INCOMPLETE
FINDING GEOMETRY_REFERENCE_EXTENT_DRIFT SEVERITY ERROR CATEGORY inconsistency LAYER validation
  SUBJECTS ["biospec_cad_lid_unf", "lid-build"]
  EVIDENCE ["urn:source:scad", "urn:reference:step"]
  REPAIR subactor://process/repair/geometry/reconcile-source-evidence
  MESSAGE "actual height 14 mm differs from reference 18 mm"
END_FINDING
RESULT FAIL
END_PROJECT_INTEGRITY
```"""
        cycle = plan_integrity_repairs(
            markdown, twin_revision=4,
            contract=AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql"),
            registry=load_repair_registry(ROOT),
        )
        task = cycle.plan.tasks[0]
        self.assertEqual(task.operation, "geometry.reconcile")
        self.assertEqual(task.uri_process, "process://twin/geometry/reconcile-source-evidence")
        self.assertIn("without widening tolerance", task.acceptance)
        self.assertEqual(task.authority_class, "physical-evidence-conflict")

    def test_rejected_development_evidence_routes_to_system_owned_repair(self):
        markdown = """```projectintegritydsl
PROJECT_INTEGRITY laboratory
METHOD deterministic-cross-layer
COVERAGE LAYERS 8/8 DEPENDENCIES 4/6 PARAMETERS 183/183 ASSUMPTIONS 0/1
COMPLETENESS INCOMPLETE
FINDING DEVELOPMENT_EVIDENCE_NOT_ACCEPTED SEVERITY ERROR CATEGORY inconsistency LAYER development
  SUBJECTS ["development-evidence"]
  EVIDENCE ["urn:todo2code:diagnostic:PLANNED_NOT_IMPLEMENTED"]
  REPAIR subactor://process/repair/project-integrity/repair-development-evidence
  MESSAGE "a completed claim has no Git or AST implementation proof"
END_FINDING
RESULT FAIL
END_PROJECT_INTEGRITY
```"""
        cycle = plan_integrity_repairs(
            markdown, twin_revision=51,
            contract=AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql"),
            registry=load_repair_registry(ROOT),
        )
        task = cycle.plan.tasks[0]
        self.assertEqual(task.operation, "development-evidence.repair")
        self.assertEqual(task.uri_process, "process://twin/development-evidence/repair")
        self.assertIn("rules pass unchanged", task.acceptance)
        self.assertEqual(task.authority_class, "development-evidence")
        self.assertIn("OWNERSHIP system", cycle.to_dict()["authority_projection_markdown"])

    def test_web_control_plane_exposes_live_integrity_to_repair_plan(self):
        html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.assertIn("ProjectIntegrityDSL → RepairPlanDSL", html)
        self.assertIn("/api/integrity/current", html)
        self.assertIn("/api/integrity/repair-plan", html)
        self.assertIn("cad|subactor|twin|ifuri", html)
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('live_markdown = str(live["project_integrity_markdown"]).strip()', server_source)


if __name__ == "__main__":
    unittest.main()
