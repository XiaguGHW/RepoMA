"""Model calls with usage accounting, size limits and readable connector failures.

Shared by rule preparation, material pre-reading and classification.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from release_safety import normalize_usage, redact_secrets
from request_runtime import RequestCancelled, ResponseLimitExceeded
from workbench_i18n import UIMessage, localize_message
from workbench_messages import UIRequestError, redact_value


def connector_failure(raw: Any) -> str | None:
    """Return a connector-level failure message, if a connector returned one.

    The Bosch Farm connector intentionally returns transport failures as text so
    callers can still display them in simple scripts.  A workbench answer must
    not mistake that text for an LLM answer, however.
    """
    text = str(raw or "").strip()
    if not text:
        return UIMessage("model.empty")
    normalized = text.casefold()
    if normalized.startswith(("error:", "http error", "error after ")):
        return text
    if normalized.startswith("(no text content"):
        return UIMessage("model.empty_endpoint", detail=text)
    return None


def require_model_success(raw: Any, context=None) -> str:
    """Return a non-empty model answer or raise a user-visible failure."""
    text = str(raw or "").strip()
    failure = connector_failure(text)
    if failure:
        context = context or UIMessage('model.context_main')
        language = getattr(context, 'language', 'zh')
        raise UIRequestError(UIMessage('model.request_failed', language, context=context,
                                        detail=localize_message(failure, language)))
    return text


def accounted_model_call(data, connector, *args, usage_records=None, **kwargs):
    """Record dispatches before response validation; failed output still costs."""
    check_request(data)
    connector.last_usage = None
    connector.last_response_model = None
    connector.usage_attempts = None
    old_control = getattr(connector, "request_control", None)
    connector.request_control = data.get("request_control")
    # Defense in depth: the Farm key never leaves in a prompt, whatever its source.
    key = connector.api_key
    args = tuple(redact_value(item, key) if index else item for index, item in enumerate(args))
    handler = kwargs.get("event_handler")
    if handler:  # Streamed previews/reasoning are shown live: redact them too.
        kwargs["event_handler"] = lambda kind, text: handler(kind, redact_secrets(text, key))
    try:
        result = redact_secrets(connector.ask_about_files(*args, **kwargs), key)
        check_request(data)
        if data.get("request_control"):
            data["request_control"].limit(len(result))
        return result
    finally:
        connector.request_control = old_control
        attempts = connector.usage_attempts
        if attempts is None:  # Custom/test connector with no transport ledger.
            attempts = [{"usage": connector.get_last_token_usage(),
                         "model": connector.last_response_model or connector.model_name}]
        elif attempts and connector.last_response_model:
            attempts[-1]["model"] = connector.last_response_model
        for attempt in attempts:
            usage = normalize_usage(attempt["usage"])
            estimate = data["state"].note_usage(usage, data["pricing"], attempt["model"])
            usage["cost_usd"] = estimate["cost_usd"] if estimate else None
            if estimate and estimate.get("cost_usd") is None:  # priced only in part
                usage["known_cost_usd"] = estimate["known_cost_usd"]
                usage["unpriced_tokens"] = estimate["unpriced_tokens"]
            if usage_records is not None:
                usage_records.append(usage)


def check_request(data):
    control = data.get("request_control")
    if control:
        control.check()
    elif data.get("cancel_event") and data["cancel_event"].is_set():
        raise RequestCancelled("Request cancelled")


@contextmanager
def commit_answer(data):
    control = data.get("request_control")
    if control:
        with control.commit():
            yield
    else:
        check_request(data)
        yield


def check_answer_size(data, answer):
    control = data.get("request_control")
    if control and len(answer) > control.policy.max_answer_chars:
        raise ResponseLimitExceeded("Answer exceeds the configured size limit")
