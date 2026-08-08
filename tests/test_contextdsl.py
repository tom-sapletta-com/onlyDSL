import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boundary import LlmBoundaryError, assert_dsl_only, build_context_analysis_bundle  # noqa: E402
from contextdsl import (  # noqa: E402
    ContextCompiler,
    DslContextEvent,
    compiler_from_payload,
    extract_contextdsl,
    parse_context_dsl,
    validate_context_markdown,
)
from intentdsl import validate_markdown  # noqa: E402
from llm_client import analyze_context, convert_english  # noqa: E402


class ContextDslTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "name": "auth_failure_context",
            "origin": "api_gateway",
            "purpose": "failure_analysis",
            "trace_id": "req_7f21",
            "state": {"api_status": 401, "refresh_status": 401},
            "metrics": {"request_latency_ms": 83.4},
            "capabilities": {"actions": ["refresh_token"], "events": ["auth_error"]},
            "events": [
                {"source": "auth_service", "code": "request_unauthorized", "severity": "error", "fields": {"status": 401}},
                {"source": "auth_service", "code": "token_refresh_failed", "severity": "error", "fields": {"status": 401}},
            ],
        }

    def test_runtime_payload_compiles_to_contextdsl(self):
        md = compiler_from_payload(self.sample_payload()).to_markdown()
        result = validate_context_markdown(md)
        self.assertTrue(result["valid"], result["errors"])
        self.assertIn("CAPABILITY action refresh_token", md)
        self.assertIn("RECORD event auth_service request_unauthorized", md)

    def test_preferred_semantic_event_is_dsl_native(self):
        compiler = ContextCompiler(trace_id="t1")
        compiler.event(DslContextEvent("billing", "payment_declined", "error", {"status": 402, "attempt": 2}))
        doc = parse_context_dsl(extract_contextdsl(compiler.to_markdown()))
        self.assertEqual(doc.records[0].code, "payment_declined")
        self.assertEqual(doc.records[0].fields["status"], 402)

    def test_legacy_log_adapter_is_lossy_and_hides_raw_line(self):
        raw = "2026-08-08T12:00:00 ERROR auth_service refresh token failed status=401 secret=abc123"
        md = ContextCompiler(trace_id="t2").legacy_log(raw).to_markdown()
        self.assertNotIn(raw, md)
        self.assertIn("legacy = true", md)
        self.assertIn("lossy = true", md)
        self.assertIn("raw_digest", md)

    def test_boundary_rejects_raw_prose(self):
        with self.assertRaises(LlmBoundaryError):
            assert_dsl_only("raw log here\n```contextdsl\nCONTEXT x\n```", {"contextdsl"})

    def test_context_analysis_bundle_contains_only_dsl_blocks(self):
        context_md = compiler_from_payload(self.sample_payload()).to_markdown()
        bundle = build_context_analysis_bundle(context_md)
        assert_dsl_only(bundle.markdown, {"contractdsl", "taskdsl", "contextdsl"})
        self.assertNotIn("Analyze the following", bundle.markdown)

    def test_demo_analysis_uses_contextdsl_and_returns_valid_intent(self):
        context_md = compiler_from_payload(self.sample_payload()).to_markdown()
        result = analyze_context(context_md, "demo")
        doc = parse_context_dsl(extract_contextdsl(context_md))
        validation = validate_markdown(
            result["markdown"],
            action_registry=doc.action_capabilities,
            event_registry=doc.event_capabilities,
        )
        self.assertTrue(validation["valid"], validation["errors"])
        self.assertIn("DO refresh_token", result["markdown"])
        self.assertIn("EMIT auth_error", result["markdown"])

    def test_capability_validation_rejects_invented_action(self):
        md = """```intentdsl
INTENT bad
STATE ok boolean = true
RULE run
  WHEN ok == true
  DO delete_database
END
OUTPUT result
```"""
        result = validate_markdown(md, action_registry={"refresh_token"}, event_registry={"auth_error"})
        self.assertFalse(result["valid"])
        self.assertTrue(any("not declared by runtime capabilities" in x for x in result["errors"]))

    def test_source_text_is_wrapped_before_llm_boundary(self):
        result = convert_english("When API returns 401, refresh token once.", "demo")
        req = result["request_markdown"]
        assert_dsl_only(req, {"contractdsl", "taskdsl", "sourcedsl"})
        self.assertIn("```sourcedsl", req)
        self.assertIn("PAYLOAD", req)


if __name__ == "__main__":
    unittest.main()
