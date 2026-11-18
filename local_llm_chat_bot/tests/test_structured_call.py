"""The unified model call layer (workbench_structured): attempt ladder, typed
failures, parsing, one repair and cache - with a scripted connector."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import json  # noqa: E402
import unittest  # noqa: E402

from workbench_structured import (Attempt, CallTask, RepairPolicy, StructuredCallError,  # noqa: E402
                                  call_model_text, structured_call)

TRUNCATED = "Error: response stopped at max_tokens (length)"


class ScriptedConnector:
    """Returns the scripted responses in order and records every request."""

    api_key = "secret-key-123"
    model_name = "test-model"

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.last_usage = self.last_response_model = self.usage_attempts = None
        self.request_control = None

    def ask_about_files(self, files, prompt, system, params, **kwargs):
        self.requests.append({"files": files, "prompt": prompt, "system": system, "params": dict(params),
                              "stream": kwargs.get("stream")})
        return self.responses.pop(0)

    def get_last_token_usage(self):
        return {"input_tokens": 1, "output_tokens": 1}


class State:
    def __init__(self):
        self.usages = []

    def note_usage(self, usage, pricing, model):
        self.usages.append(model)
        return None


def session():
    return {"state": State(), "pricing": {}}


class Ladder(unittest.TestCase):
    def test_first_complete_response_is_returned_with_the_first_ceiling(self):
        connector = ScriptedConnector("done")
        task = CallTask("SYS", "ask", CallTask.ladder(100, 200))
        self.assertEqual(call_model_text(session(), connector, task), "done")
        self.assertEqual([r["params"] for r in connector.requests], [{"maxOutputTokens": 100, "temperature": 0}])
        self.assertEqual((connector.requests[0]["system"], connector.requests[0]["stream"]), ("SYS", True))

    def test_only_an_output_limit_moves_to_the_next_step(self):
        connector = ScriptedConnector(TRUNCATED, "done")
        task = CallTask("SYS", "ask", (Attempt(100), Attempt(200, " shorter")))
        seen = []
        self.assertEqual(call_model_text(session(), connector, task,
                                         before_attempt=lambda attempt, number: seen.append((attempt.output_tokens, number))),
                         "done")
        self.assertEqual(seen, [(100, 1), (200, 2)])
        self.assertEqual([r["prompt"] for r in connector.requests], ["ask", "ask shorter"])
        self.assertEqual([r["params"]["maxOutputTokens"] for r in connector.requests], [100, 200])

    def test_an_exhausted_ladder_is_a_typed_output_limit(self):
        connector = ScriptedConnector(TRUNCATED, TRUNCATED)
        with self.assertRaises(StructuredCallError) as caught:
            call_model_text(session(), connector, CallTask("S", "p", CallTask.ladder(1, 2)))
        self.assertEqual((caught.exception.reason, caught.exception.attempts), ("output_limit", 2))
        self.assertEqual(caught.exception.technical, TRUNCATED)

    def test_other_failures_stop_at_once_with_their_reason(self):
        for text, reason, params in (("HTTP error 503: busy", "http", {"status": "503"}),
                                     ("", "empty", {}),
                                     ("Error: ConnectTimeout", "connect_timeout", {})):
            with self.subTest(reason=reason):
                connector = ScriptedConnector(text, "never")
                with self.assertRaises(StructuredCallError) as caught:
                    call_model_text(session(), connector, CallTask("S", "p", CallTask.ladder(1, 2)))
                self.assertEqual((caught.exception.reason, caught.exception.params), (reason, params))
                self.assertEqual((caught.exception.attempts, len(connector.requests)), (1, 1))

    def test_every_attempt_is_accounted(self):
        data, records = session(), []
        connector = ScriptedConnector(TRUNCATED, "done")
        call_model_text(data, connector, CallTask("S", "p", CallTask.ladder(1, 2)), usage_records=records)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(data["state"].usages), 2)

    def test_a_task_needs_an_attempt(self):
        with self.assertRaises(ValueError):
            call_model_text(session(), ScriptedConnector(), CallTask("S", "p", ()))


class Structured(unittest.TestCase):
    def test_parsed_value_is_returned(self):
        value = structured_call(session(), ScriptedConnector('{"a": 1}'), CallTask("S", "p", CallTask.ladder(9)),
                                json.loads)
        self.assertEqual(value, {"a": 1})

    def test_unparseable_response_without_repair_is_invalid(self):
        with self.assertRaises(StructuredCallError) as caught:
            structured_call(session(), ScriptedConnector("not json"), CallTask("S", "p", CallTask.ladder(9)), json.loads)
        self.assertEqual((caught.exception.reason, caught.exception.raw), ("invalid", "not json"))
        self.assertIsInstance(caught.exception.cause, ValueError)

    def test_one_repair_request_follows_an_accepted_parse_error(self):
        connector = ScriptedConnector("{bad", '{"a": 2}')
        repair = RepairPolicy(task=lambda raw, error: CallTask("FIX", f"repair: {raw}", CallTask.ladder(5)))
        value = structured_call(session(), connector, CallTask("S", "p", CallTask.ladder(9)), json.loads, repair=repair)
        self.assertEqual(value, {"a": 2})
        self.assertEqual([(r["system"], r["prompt"]) for r in connector.requests], [("S", "p"), ("FIX", "repair: {bad")])

    def test_repair_is_skipped_when_the_policy_does_not_apply_and_fails_once(self):
        connector = ScriptedConnector("{bad")
        repair = RepairPolicy(task=lambda raw, error: CallTask("FIX", raw, CallTask.ladder(5)), applies=lambda error: False)
        with self.assertRaises(StructuredCallError) as caught:
            structured_call(session(), connector, CallTask("S", "p", CallTask.ladder(9)), json.loads, repair=repair)
        self.assertEqual((caught.exception.reason, len(connector.requests)), ("invalid", 1))
        connector = ScriptedConnector("{bad", "{still bad", "never")
        repair = RepairPolicy(task=lambda raw, error: CallTask("FIX", raw, CallTask.ladder(5)))
        with self.assertRaises(StructuredCallError) as caught:
            structured_call(session(), connector, CallTask("S", "p", CallTask.ladder(9)), json.loads, repair=repair)
        self.assertEqual((caught.exception.reason, len(connector.requests)), ("invalid_after_repair", 2))

    def test_cache_hit_sends_nothing_and_success_is_stored(self):
        class Cache(dict):
            def put(self, key, value):
                self[key] = value

        cache = Cache()
        connector = ScriptedConnector('{"a": 3}')
        task = CallTask("S", "p", CallTask.ladder(9))
        self.assertEqual(structured_call(session(), connector, task, json.loads, cache=cache, cache_key="k"), {"a": 3})
        self.assertEqual(structured_call(session(), connector, task, json.loads, cache=cache, cache_key="k"), {"a": 3})
        self.assertEqual(len(connector.requests), 1)

    def test_secrets_never_leave_in_a_prompt(self):
        connector = ScriptedConnector("ok")
        call_model_text(session(), connector, CallTask("S", "key=secret-key-123", CallTask.ladder(9)))
        self.assertNotIn("secret-key-123", connector.requests[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
