import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intentdsl import (  # noqa: E402
    codegen,
    demo_english_to_dsl,
    extract_intentdsl,
    parse_dsl,
    run_program,
    validate_markdown,
)


class IntentDslTests(unittest.TestCase):
    def setUp(self):
        self.sample = (ROOT / "examples" / "auth_recovery.md").read_text(encoding="utf-8")

    def test_parse_and_validate(self):
        result = validate_markdown(self.sample)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["ast"]["intent"], "auth_recovery")

    def test_runtime_is_proactive(self):
        program = parse_dsl(extract_intentdsl(self.sample))
        result = run_program(program, {"api_status": 401, "refresh_status": 401})
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["state"]["retry_count"], 1)
        self.assertEqual(result["events"][0]["name"], "auth_error")
        action_names = [x.get("name") for x in result["trace"] if x["kind"] == "action"]
        self.assertIn("refresh_token", action_names)

    def test_unknown_symbol_rejected(self):
        broken = self.sample.replace("api_status == 401", "missing_status == 401")
        result = validate_markdown(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown symbols" in x for x in result["errors"]))

    def test_demo_converter_outputs_valid_dsl(self):
        md = demo_english_to_dsl("When API returns 401, refresh token once. Never retry more than twice.")
        self.assertTrue(validate_markdown(md)["valid"])

    def test_codegen_all_targets(self):
        program = parse_dsl(extract_intentdsl(self.sample))
        for target in ("python", "typescript", "javascript", "php"):
            generated = codegen(program, target)
            self.assertGreater(len(generated), 80)


if __name__ == "__main__":
    unittest.main()
