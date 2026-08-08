from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


def _q(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class DiagnosticRule:
    code: str
    patterns: tuple[str, ...]
    category: str
    action: str
    confidence: str
    cause: str
    objective: str
    required_oql: str
    required_uri: str
    checks: tuple[str, ...]
    solution_steps: tuple[str, ...]


# This catalog is system-owned diagnostic policy, not model output. Entries may
# suggest an already registered OQL/URI pair, but never grant authority.
RULES = (
    DiagnosticRule(
        "GEOMETRY_REFERENCE_EXTENT_DRIFT", (r"GEOMETRY_REFERENCE_EXTENT_DRIFT", r"geometry-reference-extent-drift"),
        "physical_evidence_conflict", "manual", "high",
        "The compiled source geometry and its registered reference asset disagree beyond the exact extent tolerance.",
        "Reconcile which source revision is authoritative; do not widen tolerance or alter dimensions merely to pass validation.",
        "geometry.reconcile", "process://twin/geometry/reconcile-source-evidence",
        ("both_source_hashes_preserved", "unit_contract_verified", "authoritative_extent_selected", "geometry_receipt_passes"),
        ("compare_axis_extent_and_units", "trace_both_artifacts_to_source_revisions", "obtain_or_apply_system_owned_evidence_decision", "replay_exact_build_contract"),
    ),
    DiagnosticRule(
        "GEOMETRY_OPENSCAD_BACKEND_REQUIRED", (r"GEOMETRY_OPENSCAD_BACKEND_REQUIRED", r"geometry-openscad-backend-required"),
        "runtime_capability", "manual", "high",
        "A system-owned CAD process was selected but its declared OpenSCAD backend is unavailable.",
        "Provision or select the registered CAD backend outside the model boundary, then replay the unchanged build contract.",
        "none", "subactor://process/repair/geometry/install-openscad-backend",
        ("openscad_version_recorded", "geometry_contract_unchanged", "geometry_receipt_valid"),
        ("preserve_failed_geometry_receipt", "resolve_system_owned_backend", "replay_exact_geometry_contract"),
    ),
    DiagnosticRule(
        "GEOMETRY_VALIDATION_INCOMPLETE", (r"GEOMETRY_VALIDATION_INCOMPLETE", r"geometry checks.*incomplete"),
        "physical_evidence", "manual", "high",
        "One or more checks required by SpatialClassDSL lack grounded physical evidence.",
        "Collect the missing measurement/CAD/IFC evidence; never synthesize a passing pose or constraint.",
        "physical-evidence.complete", "process://twin/physical-evidence/complete",
        ("required_checks_accounted", "source_reference_present", "testql_geometry_passes"),
        ("read_requirement_denominators", "identify_missing_subject_evidence", "intake_grounded_evidence"),
    ),
    DiagnosticRule(
        "CONCEPTUAL_GEOMETRY_ASSUMPTION", (r"CONCEPTUAL_GEOMETRY_ASSUMPTION", r"conceptual primitive geometry"),
        "ungrounded_assumption", "patch", "high",
        "A physical or hybrid component is rendered with provisional primitive geometry.",
        "Compile existing grounded CAD or register the assumption until physical evidence arrives.",
        "geometry.compile", "cad://openscad/scad/geometry/compile",
        ("asset_grounded", "scene_identity_stable", "assumption_superseded"),
        ("resolve_component_source_evidence", "compile_via_registered_cad_process", "verify_next_integrity_iteration"),
    ),
    DiagnosticRule(
        "OBSERVATION_UNIT_MIXED_FORBIDDEN", (r"OBSERVATION_UNIT_MIXED_FORBIDDEN", r"UNIT mixed"),
        "parameter_contract", "patch", "high",
        "One row assigns a heterogeneous unit label to multiple domain parameters.",
        "Replace the aggregate unit with an exact per-metric unit map and validate it against ParameterContractDSL.",
        "data.change", "repo://workspace/data/command/patch",
        ("no_mixed_unit", "parameter_contracts_pass", "observations_parse"),
        ("enumerate_row_metrics", "bind_exact_unit_per_metric", "replay_observation_intake"),
    ),
    DiagnosticRule(
        "SPATIAL_CLASS_INVALID", (r"SPATIAL_CLASS_(?:MISSING|INVALID)", r"invalid spatialClass", r"has no spatial type contract"),
        "ontology", "patch", "high",
        "A Twin component lacks a valid physical/cyber/logical/hybrid classification or type contract.",
        "Correct SpatialClassDSL and recalculate completeness without changing stable component identity.",
        "data.change", "repo://workspace/data/command/patch",
        ("spatial_class_valid", "requirements_non_contradictory", "component_ids_stable"),
        ("classify_component_ontology", "declare_type_requirements", "rerun_integrity"),
    ),
    DiagnosticRule(
        "SEMANTIC_MATH_AUTHORITY_FIELD_FORBIDDEN", (r"SEMANTIC_MATH_AUTHORITY_FIELD_FORBIDDEN", r"semantic_math_authority_field_forbidden"),
        "llm_boundary", "defer", "high",
        "The semantic model response attempted to emit a system-owned authority field.",
        "Keep the deterministic semantic fallback and do not merge or execute the rejected field.",
        "none", "none",
        ("model_authority_absent", "authority_projection_system_owned", "fallback_audited"),
        ("preserve_rejected_generation_audit", "use_semantic_fallback", "review_provider_schema_if_repeated"),
    ),
    DiagnosticRule(
        "AUTONOMY_RATE_LIMIT_EXCEEDED", (r"AutonomyRateLimitExceeded", r"autonomy rate limit"),
        "policy_budget", "defer", "high",
        "The runtime exhausted its configured autonomy budget.",
        "Wait for or explicitly reset the policy window, then replay the same evidence.",
        "runtime.change", "repo://workspace/runtime/command/patch",
        ("policy_budget_available", "iteration_allowed", "scene_publish_allowed"),
        ("preserve_failed_evidence", "read_policy_window", "retry_after_budget_reset"),
    ),
    DiagnosticRule(
        "AQL_AUTHORITY_DENIED", (r"AQL denied", r"uri_process_not_granted", r"oql_not_granted", r"principal_mismatch", r"contract_expired"),
        "authority", "manual", "high",
        "The requested operation is outside the active AQL grant or the grant is invalid.",
        "Request a system-owned authority decision; do not patch or weaken governance.",
        "none", "none",
        ("authority_contract_reviewed", "principal_matches", "contract_not_expired"),
        ("preserve_denial_receipt", "identify_missing_grant", "request_authority_review"),
    ),
    DiagnosticRule(
        "ITERATION_POLICY_DENIED", (r"IterationAllowed=false", r"ScenePublishAllowed=false", r"ITERATION_BLOCKED_VALIDATION_OR_POLICY"),
        "policy_gate", "manual", "high",
        "A runtime policy gate rejected iteration or scene publication.",
        "Inspect the policy receipt and satisfy the rejected precondition without bypassing it.",
        "none", "none",
        ("iteration_allowed", "scene_publish_allowed", "policy_receipt_present"),
        ("read_policy_failures", "map_failure_to_precondition", "request_policy_compliant_replay"),
    ),
    DiagnosticRule(
        "PYTHON_IMPORT_ERROR", (r"ImportError", r"cannot import name"),
        "python_import", "patch", "high",
        "A Python module is present but a required symbol cannot be imported.",
        "Restore or correct the smallest module/export boundary and rerun import plus tests.",
        "code.change", "repo://workspace/source/command/patch",
        ("python_import_succeeds", "unit_tests_pass", "health_green"),
        ("inspect_import_chain", "verify_symbol_definition", "apply_minimal_source_patch"),
    ),
    DiagnosticRule(
        "PYTHON_MODULE_NOT_FOUND", (r"ModuleNotFoundError", r"No module named"),
        "python_dependency", "patch", "high",
        "A module path or declared dependency cannot be resolved in the active runtime.",
        "Correct the import/package metadata and verify inside the same runtime image.",
        "dependency.change", "repo://workspace/dependency/command/patch",
        ("module_resolves", "unit_tests_pass", "container_health_green"),
        ("inspect_runtime_sys_path", "compare_dependency_manifest", "apply_minimal_dependency_or_import_patch"),
    ),
    DiagnosticRule(
        "TESTQL_ASSERTION_FAILED", (r"testql.*failed", r"verification.*failed", r"expected .+ got", r"ASSERTION_FAILED"),
        "verification", "patch", "high",
        "A typed TestQL expectation differs from the observed runtime result.",
        "Repair the producing code or contract, never rewrite the assertion merely to make it green.",
        "code.change", "repo://workspace/source/command/patch",
        ("original_testql_expectation_passes", "unit_tests_pass", "health_green"),
        ("read_testqldsl_evidence", "locate_producer_of_actual_value", "patch_producer_not_expectation"),
    ),
    DiagnosticRule(
        "JSON_DECODE_ERROR", (r"JSONDecodeError", r"invalid json", r"unexpected token.*json"),
        "serialization", "patch", "high",
        "A producer emitted malformed or incorrectly framed JSON.",
        "Correct serialization or response framing and retain schema validation.",
        "code.change", "repo://workspace/source/command/patch",
        ("json_parses", "schema_valid", "unit_tests_pass"),
        ("capture_bounded_payload", "locate_serializer", "patch_framing_or_encoding"),
    ),
    DiagnosticRule(
        "HTTP_NOT_FOUND", (r"HTTP(?:Error)?\s*404", r"status[^\n]*404", r"not_found"),
        "http_route", "patch", "medium",
        "The requested HTTP route or resource is not registered at the observed address.",
        "Reconcile the caller route with the public API without adding an ungoverned proxy.",
        "code.change", "repo://workspace/source/command/patch",
        ("route_returns_expected_status", "public_api_compatible", "unit_tests_pass"),
        ("compare_requested_and_registered_route", "verify_method", "patch_smallest_route_boundary"),
    ),
    DiagnosticRule(
        "HTTP_SERVER_ERROR", (r"HTTP(?:Error)?\s*5\d\d", r"status[^\n]*5\d\d", r"unhandled_exception"),
        "http_runtime", "patch", "medium",
        "An HTTP handler raised or returned an internal server failure.",
        "Repair the traced handler and verify the exact route plus global health.",
        "code.change", "repo://workspace/source/command/patch",
        ("route_not_5xx", "unit_tests_pass", "health_green"),
        ("read_bounded_trace", "locate_handler", "apply_minimal_handler_patch"),
    ),
    DiagnosticRule(
        "CONNECTION_REFUSED", (r"ConnectionRefused", r"connection refused", r"ECONNREFUSED"),
        "availability", "defer", "high",
        "The target process was not accepting connections at the configured address.",
        "Verify process readiness and retry without changing application semantics.",
        "none", "none",
        ("target_process_running", "readiness_green", "original_probe_passes"),
        ("preserve_probe_evidence", "check_readiness", "retry_with_bounded_backoff"),
    ),
    DiagnosticRule(
        "OPERATION_TIMEOUT", (r"TimeoutError", r"timed out", r"ETIMEDOUT"),
        "timeout", "defer", "medium",
        "A bounded operation did not complete before its deadline.",
        "Measure the slow stage, retry within policy, and patch only with repeatable evidence.",
        "none", "none",
        ("stage_duration_recorded", "bounded_retry_completed"),
        ("record_stage_timing", "retry_with_bounded_backoff", "escalate_if_repeatable"),
    ),
    DiagnosticRule(
        "PATCH_BASE_STALE", (r"base hash mismatch", r"git apply check failed", r"patch does not apply"),
        "stale_proposal", "defer", "high",
        "The workspace changed after the proposal was bound to its base hash.",
        "Discard the stale proposal, reread current code, and request a newly bound patch.",
        "none", "none",
        ("current_hash_reread", "new_proposal_hash_bound"),
        ("reject_stale_envelope", "reread_current_source", "regenerate_patch"),
    ),
)


FALLBACK_RULE = DiagnosticRule(
    "UNCLASSIFIED_RUNTIME_ERROR", (), "unknown", "manual", "low",
    "No deterministic catalog rule matched the supplied evidence.",
    "Collect a concrete error code or reproduction before any source mutation is proposed.",
    "none", "none",
    ("concrete_error_code_present", "reproduction_present"),
    ("preserve_original_evidence", "request_concrete_error_code", "classify_before_patch"),
)


def _candidate_paths(text: str) -> list[str]:
    found: list[str] = []
    pattern = r"(?:/app/|/workspace/)?([A-Za-z0-9_./-]+\.(?:py|html|css|js|mjs|ts|json|ya?ml|toml))"
    for raw in re.findall(pattern, text):
        path = raw.lstrip("/")
        if path.startswith(("app/", "workspace/")):
            path = path.split("/", 1)[1]
        if path not in found:
            found.append(path)
    return found[:8]


def diagnose_incident(incident_markdown: str, incident_id: str = "unknown") -> dict[str, Any]:
    text = str(incident_markdown)
    rule = next((item for item in RULES if any(re.search(pattern, text, re.I) for pattern in item.patterns)), FALLBACK_RULE)
    diagnostic_id = "diag-" + hashlib.sha256((incident_id + "\0" + text).encode("utf-8")).hexdigest()[:20]
    paths = _candidate_paths(text)
    rows = [
        "```diagnosticdsl",
        f"DIAGNOSTIC {diagnostic_id}",
        f"INCIDENT {_q(incident_id)}",
        f"ERROR_CODE {rule.code}",
        f"CATEGORY {rule.category}",
        f"CONFIDENCE {rule.confidence}",
        f"ACTION {rule.action}",
        f"CAUSE {_q(rule.cause)}",
        f"OBJECTIVE {_q(rule.objective)}",
        f"REQUIRED_OQL {rule.required_oql}",
        f"REQUIRED_URI_PROCESS {rule.required_uri}",
        "NOTE suggestion_is_not_authority",
        "FORBID execute_model_supplied_commands",
        "FORBID weaken_aql_or_validation",
    ]
    rows.extend(f"CANDIDATE_PATH {_q(path)}" for path in paths)
    rows.extend(f"SOLUTION_STEP {index} {step}" for index, step in enumerate(rule.solution_steps, 1))
    rows.extend(f"VERIFY {check}" for check in rule.checks)
    rows.extend(["END_DIAGNOSTIC", "```"])
    return {
        "id": diagnostic_id,
        "code": rule.code,
        "category": rule.category,
        "action": rule.action,
        "confidence": rule.confidence,
        "candidate_paths": paths,
        "markdown": "\n".join(rows),
    }


__all__ = ["DiagnosticRule", "RULES", "diagnose_incident"]
