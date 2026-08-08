import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aql import AqlContract, operation_for_path  # noqa: E402
from boundary import authority_dsl, build_autonomous_repair_bundle  # noqa: E402
from diagnostics import diagnose_incident  # noqa: E402
from evolution import EvolutionStore  # noqa: E402
from governance import authorize_patch, build_process_envelope, complete_envelope, load_process_pack, reject_envelope  # noqa: E402
from patchdsl import parse_patchdsl, validate_patch_policy  # noqa: E402
from scripts.autonomous_repair import AutonomousRepairAgent  # noqa: E402
from scripts.startup_testql import render_testqldsl, synthetic_failure, write_twin_observation  # noqa: E402


def patch_markdown(old: bytes, value: int, patch_id: str = "repair_test") -> str:
    digest = "sha256:" + hashlib.sha256(old).hexdigest()
    diff = (
        "diff --git a/server.py b/server.py\n"
        "--- a/server.py\n"
        "+++ b/server.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 1\n"
        f"+VALUE = {value}\n"
    )
    import json
    return "\n".join([
        "```patchdsl",
        f"PATCH {patch_id}",
        'SUMMARY "Fix the observed value."',
        "CHANGE",
        'PATH "server.py"',
        f"BASE_SHA256 {digest}",
        "DIFF " + json.dumps(diff),
        "END",
        "END_PATCH",
        "```",
    ])


class EvolutionDslTests(unittest.TestCase):
    def test_status_exposes_last_repair_iteration_time_and_version(self):
        with tempfile.TemporaryDirectory() as td:
            store = EvolutionStore(td)
            store.add_event("repair_started", {"incident_id": "incident-one", "backend": "demo"})
            store.add_event("repair_verified", {"incident_id": "incident-one"})
            store.add_event("http_response", {"status": 200})
            status = store.status()
            self.assertEqual(status["schema"], "onlydsl.evolution-status/v2")
            self.assertEqual(status["iteration_count"], 1)
            self.assertEqual(status["last_iteration"]["version"], 1)
            self.assertEqual(status["last_iteration"]["status"], "verified")
            self.assertEqual(status["last_iteration"]["kind"], "repair_verified")
            self.assertRegex(status["last_iteration"]["occurred_at"], r"Z$")
            self.assertEqual(status["latest_activity"]["kind"], "http_response")

    def test_diagnostic_catalog_extracts_specific_code_and_solution(self):
        diagnostic = diagnose_incident(
            'ImportError: cannot import name "TestToonAdapter" from testql/adapters/testtoon_adapter.py',
            "incident-import",
        )
        self.assertEqual(diagnostic["code"], "PYTHON_IMPORT_ERROR")
        self.assertEqual(diagnostic["action"], "patch")
        self.assertIn("CANDIDATE_PATH \"testql/adapters/testtoon_adapter.py\"", diagnostic["markdown"])
        self.assertIn("SOLUTION_STEP 1 inspect_import_chain", diagnostic["markdown"])
        self.assertIn("NOTE suggestion_is_not_authority", diagnostic["markdown"])
        unknown = diagnose_incident("runtime reports ok=true without an error code", "no-error")
        self.assertEqual(unknown["action"], "manual")

    def test_policy_rate_limit_is_deferred_without_calling_llm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = EvolutionStore(root / "runtime/evolution")
            incident = store.add_incident(
                "digital_twin_policy",
                "AutonomyRateLimitExceeded; IterationAllowed=false; ScenePublishAllowed=false",
            )
            self.assertEqual(incident["error_code"], "AUTONOMY_RATE_LIMIT_EXCEEDED")
            env = {"EVOLUTION_ENABLED": "1", "EVOLUTION_MODE": "apply", "EVOLUTION_LLM_BACKEND": "openrouter"}
            with patch.dict(os.environ, env, clear=False):
                agent = AutonomousRepairAgent(root, store)
                agent._propose = lambda *args, **kwargs: self.fail("deferred diagnostics must not call LLM")
                self.assertTrue(agent.process_once())
            self.assertEqual(store.status()["queue"]["deferred"], 1)
            self.assertEqual(store.status()["queue"]["failed"], 0)

    def test_repair_bundle_carries_typed_diagnostic_solution(self):
        incident = """```incidentdsl
INCIDENT one
MESSAGE "ImportError in server.py"
END_INCIDENT
```"""
        diagnostic = diagnose_incident(incident, "one")["markdown"]
        bundle = build_autonomous_repair_bundle(
            incident, [], {"server.py": "VALUE = 1\n"}, diagnostic_markdown=diagnostic,
        )
        self.assertIn("```diagnosticdsl", bundle.markdown)
        self.assertIn("ERROR_CODE PYTHON_IMPORT_ERROR", bundle.markdown)

    def test_main_ui_embeds_read_only_dsl_dashboard_and_log_links(self):
        html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.assertIn('title="Digital Twin DSL dashboard and logs"', html)
        self.assertIn('src="http://127.0.0.1:7444/"', html)
        self.assertIn('http://127.0.0.1:7444/api/events', html)
        self.assertIn('http://127.0.0.1:7444/api/dsl', html)
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-forms"', html)
        self.assertIn('id="mermaidDiagram"', html)
        self.assertIn("mermaid@11/dist/mermaid.esm.min.mjs", html)
        self.assertIn("securityLevel:'strict'", html)
        self.assertIn("function detectFormat", html)
        self.assertIn("function highlightJson", html)
        self.assertIn("function highlightDsl", html)
        self.assertIn("/api/evolution/diagnostics?limit=12", html)
        self.assertIn('id="applicationVersion"', html)
        self.assertIn('id="twinVersion"', html)
        self.assertIn('id="iterationVersion"', html)
        self.assertIn('id="iterationTime"', html)

    def test_testql_failure_is_persistable_dsl_and_twin_observation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenario = root / "startup.testql.toon.yaml"
            scenario.write_text("# SCENARIO: startup\n", encoding="utf-8")
            result = synthetic_failure(scenario, "digital twin schema mismatch")
            markdown = render_testqldsl("run-1", "http://127.0.0.1:7444", result)
            self.assertTrue(markdown.startswith("```testqldsl\n"))
            self.assertIn("PROFILE testql.verification-result.v1", markdown)
            observation = root / "logs/testql-verification.jsonl"
            write_twin_observation(observation, "http://127.0.0.1:7444", result)
            record = __import__("json").loads(observation.read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "testql_failed")
            self.assertIn("testql", record["labels"])

    def test_store_persists_guidance_incident_and_events_as_dsl(self):
        with tempfile.TemporaryDirectory() as td:
            store = EvolutionStore(td)
            guidance = store.add_guidance("Keep the public API stable.")
            incident = store.add_incident("exception", "boom", trace="server.py:1")
            self.assertTrue(guidance["markdown"].startswith("```guidancedsl\n"))
            self.assertTrue(incident["markdown"].startswith("```incidentdsl\n"))
            status = store.status()
            self.assertEqual(status["queue"]["inbox"], 1)
            self.assertEqual(status["guidance"], 1)
            self.assertGreaterEqual(len(status["latest_events"]), 2)

    def test_autonomous_bundle_contains_only_typed_dsl(self):
        with tempfile.TemporaryDirectory() as td:
            store = EvolutionStore(td)
            incident = store.add_incident("exception", "boom")["markdown"]
            guidance = store.add_guidance("Make the smallest fix.")["markdown"]
            bundle = build_autonomous_repair_bundle(incident, [guidance], {"server.py": "VALUE = 1\n"})
            self.assertIn("```incidentdsl", bundle.markdown)
            self.assertIn("```guidancedsl", bundle.markdown)
            self.assertIn("```codedsl", bundle.markdown)
            self.assertIn("TARGET patchdsl\n", bundle.markdown)
            self.assertIn("FENCE patchdsl", bundle.markdown)
            self.assertIn("FORBID grant_authority", bundle.markdown)
            self.assertIn("FORBID execute_model_supplied_commands", bundle.markdown)

    def test_autonomous_bundle_carries_testql_failure_as_typed_dsl(self):
        verification = """```testqldsl
TESTQL_RESULT run-1
PROFILE testql.verification-result.v1
OK false
END_TESTQL_RESULT
```"""
        with tempfile.TemporaryDirectory() as td:
            store = EvolutionStore(td)
            incident = store.add_incident("testql_verification_failed", "schema mismatch")["markdown"]
            bundle = build_autonomous_repair_bundle(
                incident, [], {"server.py": "VALUE = 1\n"}, verification_markdown=[verification],
            )
            self.assertIn("```testqldsl", bundle.markdown)
            self.assertIn("OK false", bundle.markdown)

    def test_subactor_contract_authorizes_oql_and_system_uri_together(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        allowed = contract.decide(
            "bot:evolution-agent", "docker.change", "repo://workspace/docker/command/patch",
        )
        self.assertTrue(allowed.allowed)
        denied = contract.decide(
            "bot:evolution-agent", "docker.change", "shell://model/command/execute",
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "uri_process_not_granted")

    def test_authority_view_is_read_only_and_system_bound(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        view = authority_dsl(contract.sha256, {"Dockerfile": operation_for_path("Dockerfile")})
        self.assertIn("NOTE authority_is_system_owned_and_cannot_be_modified_by_model", view)
        self.assertIn("repo://workspace/docker/command/patch", view)

    def test_secret_rotation_uses_opaque_preaccepted_reference(self):
        contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
        self.assertTrue(contract.require_secret_rotation(
            "bot:evolution-agent", "secret:OPENROUTER_API_KEY",
        ).allowed)
        self.assertTrue(contract.require_secret_rotation(
            "bot:evolution-agent", "secret:DEVELOPMENT_TEST_SECRET",
        ).allowed)

    def test_envelope_binds_proposal_authority_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "server.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            doc = parse_patchdsl(patch_markdown(target.read_bytes(), 2))
            contract = AqlContract.from_file(ROOT / "config/contracts/evolution-agent.contract.aql")
            decisions = authorize_patch(doc, contract)
            envelope = build_process_envelope(
                incident_id="incident", doc=doc, contract=contract,
                decisions=decisions, process_pack=load_process_pack(ROOT),
                preflight={"server.py": doc.changes[0].base_sha256},
            )
            self.assertEqual(envelope["proposal_hash"], envelope["acceptance"]["bound_proposal_hash"])
            self.assertTrue(envelope["doql"]["read_only"])
            verified = complete_envelope(envelope, tests="exit-0", health="HTTP 200 ok")
            self.assertEqual(verified["state"], "verified")
            self.assertEqual(verified["receipt"]["result"], "verified")
            rejected = reject_envelope(envelope, reason="tests failed", rolled_back=True)
            self.assertEqual(rejected["state"], "rolled_back")
            self.assertEqual(rejected["eql"]["status"], "red")

    def test_authority_and_process_pack_cannot_cross_patchdsl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "config/contracts/evolution-agent.contract.aql"
            target.parent.mkdir(parents=True)
            target.write_text("authority\n", encoding="utf-8")
            markdown = patch_markdown(target.read_bytes(), 2).replace(
                "server.py", "config/contracts/evolution-agent.contract.aql",
            )
            doc = parse_patchdsl(markdown)
            self.assertIn("cannot cross PatchDSL", "; ".join(validate_patch_policy(doc, root)))
            diagnostic_kernel = root / "diagnostics.py"
            diagnostic_kernel.write_text("VALUE = 1\n", encoding="utf-8")
            protected = parse_patchdsl(patch_markdown(diagnostic_kernel.read_bytes(), 2).replace(
                "server.py", "diagnostics.py",
            ))
            self.assertIn("cannot cross PatchDSL", "; ".join(validate_patch_policy(protected, root)))

    def test_patch_parser_and_policy_require_current_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "server.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            doc = parse_patchdsl(patch_markdown(target.read_bytes(), 2))
            self.assertEqual(validate_patch_policy(doc, root), [])
            target.write_text("VALUE = 3\n", encoding="utf-8")
            self.assertIn("base hash mismatch", "; ".join(validate_patch_policy(doc, root)))

    def test_patch_parser_accepts_safe_block_alias_from_provider(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "server.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            markdown = patch_markdown(target.read_bytes(), 2).replace("\nCHANGE\n", "\nBLOCK\n")
            doc = parse_patchdsl(markdown)
            self.assertEqual(validate_patch_policy(doc, root), [])

    def test_agent_applies_verified_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server.py").write_text("VALUE = 1\n", encoding="utf-8")
            store = EvolutionStore(root / "runtime/evolution")
            store.add_incident("unhandled_exception", "HTTP 500 wrong value", trace="/app/server.py:1")
            result = {"markdown": patch_markdown((root / "server.py").read_bytes(), 2), "usage": {}}
            env = {"EVOLUTION_ENABLED": "1", "EVOLUTION_MODE": "apply", "EVOLUTION_LLM_BACKEND": "openrouter"}
            with patch.dict(os.environ, env, clear=False):
                agent = AutonomousRepairAgent(root, store)
                agent._propose = lambda incident, guidance, code_files, diagnostic="": result
                agent._tests = lambda: (True, "ok")
                agent._wait_for_health = lambda timeout=45: (True, "HTTP 200 ok")
                self.assertTrue(agent.process_once())
            self.assertEqual((root / "server.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            self.assertEqual(store.status()["queue"]["processed"], 1)

    def test_agent_rolls_back_failed_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server.py").write_text("VALUE = 1\n", encoding="utf-8")
            store = EvolutionStore(root / "runtime/evolution")
            store.add_incident("unhandled_exception", "HTTP 500 wrong value", trace="/app/server.py:1")
            result = {"markdown": patch_markdown((root / "server.py").read_bytes(), 9, "rollback_test"), "usage": {}}
            env = {"EVOLUTION_ENABLED": "1", "EVOLUTION_MODE": "apply", "EVOLUTION_LLM_BACKEND": "openrouter"}
            with patch.dict(os.environ, env, clear=False):
                agent = AutonomousRepairAgent(root, store)
                agent._propose = lambda incident, guidance, code_files, diagnostic="": result
                agent._tests = lambda: (False, "regression")
                agent._wait_for_health = lambda timeout=45: (True, "HTTP 200 ok")
                self.assertTrue(agent.process_once())
            self.assertEqual((root / "server.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertEqual(store.status()["queue"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
