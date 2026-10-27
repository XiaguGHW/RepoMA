"""Token savings: cached prompt start, no dossier for one file, unpriced token types."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from code_chat_agent import PricingCatalog, ProjectState  # noqa: E402
from release_safety import PROMPT_CACHE_BREAK, summarize_usage  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402

ANSWER_SYSTEM = "careful local workspace"


class TokenSavings(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm_bg(self, model, files):
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": model, "language": "en"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": files})

    def answer_bodies(self, start):
        return [call["body"] for call in self.f.calls[start:] if ANSWER_SYSTEM in json.dumps(call["body"])]

    def test_claude_answer_caches_identical_rule_block_across_turns(self):
        self.confirm_bg("claude-haiku-5-5", ["facts.txt"])
        before = len(self.f.calls)
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        self.post("/api/chat", {"question": "Explain the motor"})
        first, second = self.answer_bodies(before)[-2:]
        blocks = [body["messages"][0]["content"][0] for body in (first, second)]
        for block in blocks:
            self.assertEqual(block.get("cache_control"), {"type": "ephemeral"})
            self.assertIn("Locked Codebook profile", block["text"])
            self.assertNotIn("WORKBENCH_PROMPT_CACHE_BREAK", json.dumps(first))
        # Only an identical start can be read from the cache in the next turn.
        self.assertEqual(blocks[0]["text"], blocks[1]["text"])
        self.assertIn("Explain the motor", second["messages"][0]["content"][-1]["text"])

    def test_gemini_receives_plain_prompt_with_rules_first(self):
        self.confirm_bg("gemini-2.5-pro", ["facts.txt"])
        before = len(self.f.calls)
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        body = self.answer_bodies(before)[-1]
        text = "\n".join(part.get("text", "") for item in body["contents"] for part in item["parts"])
        self.assertNotIn("WORKBENCH_PROMPT_CACHE_BREAK", text)
        self.assertTrue(text.startswith("BG CLASSIFICATION RULES"))
        self.assertLess(text.index("Locked Codebook profile"), text.index("Recent conversation"))

    def test_single_file_uses_its_summary_without_a_dossier(self):
        self.confirm_bg("gemini-2.5-pro", ["facts.txt"])
        result = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        keys = [item.get("message_key") for item in result["notice_messages"]]
        self.assertNotIn("notice.dossier_created", keys)
        self.assertNotIn("notice.dossier_reused", keys)
        coverage = w.load_coverage(w.ACTIVE["state"])
        self.assertIsNone(w.load_bg_dossier_cache(coverage, w.ACTIVE["model"]))


class UnpricedTokenTypes(unittest.TestCase):
    """Bosch Farm has no cache prices: price the rest, name the cache tokens."""

    def setUp(self):
        self.pricing = PricingCatalog(Path(w.__file__).with_name("model_pricing.json"))

    def test_cache_tokens_are_named_and_the_rest_is_priced(self):
        usage = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 2368,
                 "cache_read_input_tokens": 0}
        self.assertIsNone(self.pricing.estimate("claude-haiku-5-5", None, None, usage=usage))
        partial = self.pricing.partial_estimate("claude-haiku-5-5", usage)
        self.assertEqual(partial["unpriced_tokens"], {"cache_write": 2368})
        price = self.pricing.price_for("claude-haiku-5-5")
        expected = (1000 * price["input_price"] + 500 * price["output_price"]) / 1_000_000
        self.assertAlmostEqual(partial["known_cost_usd"], expected)

    def test_turn_summary_lists_unpriced_types_and_keeps_known_subtotal(self):
        records = [
            {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001},
            {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 300, "cost_usd": None,
             "known_cost_usd": 0.002, "unpriced_tokens": {"cache_write": 300}},
            {"cost_usd": None},
        ]
        summary = summarize_usage(records)
        self.assertIsNone(summary["cost_usd"])
        self.assertAlmostEqual(summary["known_cost_usd"], 0.003)
        self.assertEqual(summary["unpriced_detail"], {"cache_write": 300, "usage_missing_requests": 1})

    def test_session_totals_record_unpriced_detail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "workspace").mkdir()
            state = ProjectState(root / "state", root / "workspace", "pricing-test")
            usage = {"input_tokens": 100, "output_tokens": 10, "cache_creation_input_tokens": 50}
            estimate = state.note_usage(usage, self.pricing, "claude-haiku-5-5")
            self.assertIsNone(estimate["cost_usd"])
            state.note_usage({"input_tokens": 1, "output_tokens": 1}, self.pricing, "not-a-priced-model")
            aggregate = state.data["usage"]
            self.assertEqual(aggregate["unpriced_requests"], 2)
            self.assertEqual(aggregate["unpriced_detail"], {"cache_write": 50, "model_requests": 1})
            self.assertGreater(aggregate["estimated_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
