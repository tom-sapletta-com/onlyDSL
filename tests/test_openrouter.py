import os
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from digital_twin import demo_bootstrap_twin  # noqa: E402
from llm_client import bootstrap_twin, convert_english, provider_status  # noqa: E402


class OpenRouterTests(unittest.TestCase):
    def test_env_example_exposes_openrouter_configuration_without_secret(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("OPENROUTER_API_KEY=", text)
        self.assertIn("OPENROUTER_MODEL=~openai/gpt-latest", text)
        self.assertIn("LLM_BACKEND=demo", text)

    def test_openrouter_provider_reads_dedicated_key_and_endpoint(self):
        env = {
            "OPENROUTER_API_KEY": "test-secret-not-real",
            "OPENROUTER_MODEL": "~openai/gpt-latest",
            "OPENROUTER_HTTP_REFERER": "http://localhost:8787",
            "OPENROUTER_APP_TITLE": "IFURI Test",
        }
        with patch.dict(os.environ, env, clear=False):
            status = provider_status("openrouter")
        self.assertTrue(status["configured"])
        self.assertEqual(status["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(status["model"], "~openai/gpt-latest")
        self.assertTrue(status["api_key_present"])
        self.assertIn("HTTP-Referer", status["attribution_headers"])

    def test_openrouter_request_keeps_dsl_only_payload(self):
        captured = {}

        def fake_request(url, payload, api_key="", *, extra_headers=None):
            captured.update(url=url, payload=payload, api_key=api_key, headers=extra_headers or {})
            return {"choices": [{"message": {"content": """```intentdsl
INTENT test
STATE done boolean = false
RULE run
  WHEN true
  SET done = true
END
OUTPUT result
```"""}}], "usage": {"total_tokens": 10}}

        env = {
            "OPENROUTER_API_KEY": "test-secret-not-real",
            "OPENROUTER_MODEL": "~openai/gpt-latest",
            "OPENROUTER_HTTP_REFERER": "http://localhost:8787",
        }
        with patch.dict(os.environ, env, clear=False), patch("llm_client._request_json", side_effect=fake_request):
            result = convert_english("Set done to true.", "openrouter")
        self.assertEqual(captured["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(captured["api_key"], "test-secret-not-real")
        content = captured["payload"]["messages"][0]["content"]
        self.assertTrue(content.startswith("```contractdsl"))
        self.assertNotIn("You are a helpful assistant", content)
        self.assertEqual(result["backend"], "openrouter")
        self.assertEqual(result["model"], "~openai/gpt-latest")


    def test_openrouter_repair_loop_never_feeds_rejected_raw_output_back(self):
        intent = "Build a source-backed digital twin and preserve user intent."
        valid = demo_bootstrap_twin(intent)
        requests = []

        def fake_request(url, payload, api_key="", *, extra_headers=None):
            requests.append(payload["messages"][0]["content"])
            if len(requests) == 1:
                return {"choices": [{"message": {"content": "Here is the twin you requested."}}]}
            return {"choices": [{"message": {"content": valid}}]}

        env = {
            "OPENROUTER_API_KEY": "test-secret-not-real",
            "OPENROUTER_MODEL": "~openai/gpt-latest",
            "LLM_REPAIR_ATTEMPTS": "2",
        }
        with patch.dict(os.environ, env, clear=False), patch("llm_client._request_json", side_effect=fake_request):
            result = bootstrap_twin(intent, "openrouter")
        self.assertEqual(len(requests), 2)
        self.assertEqual(result["repair_attempts"], 1)
        self.assertIn("```validationdsl", requests[1])
        self.assertNotIn("Here is the twin you requested.", requests[1])



if __name__ == "__main__":
    unittest.main()
