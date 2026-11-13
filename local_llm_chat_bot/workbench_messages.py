"""Interface messages: localized message objects, request errors that carry a
message key, and redaction of secrets in values shown or logged.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from release_safety import redact_secrets, safe_error
from workbench_i18n import UIMessage, localize_message
from workbench_startup import StartupError


def ui_message(data, key, **params):
    language = data.get('language', 'zh') if isinstance(data, dict) else data
    return UIMessage(key, language, **params)


def message_payload(value):
    return value.payload() if isinstance(value, UIMessage) else {'text': str(value)}


class UIRequestError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)
        self.ui_message = message


class UIValidationError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.ui_message = message


def error_copy(error, data):
    value = error.detail if isinstance(error, HTTPException) else getattr(error, 'ui_message', str(error))
    if isinstance(error, StartupError):
        value = ui_message(data, error.code, **error.params)
    def redact(item):
        if isinstance(item, UIMessage):
            return UIMessage(item.message_key, item.language, **{key: redact(part) for key, part in item.params.items()})
        return safe_error(item) if isinstance(item, str) else item
    return localize_message(redact(value), data.get('language', 'zh'))


def redact_value(value: Any, key: Any = None) -> Any:
    """Recursively redact the active Farm key from model input/output structures."""
    if isinstance(value, UIMessage):
        return value  # Structured, application-generated UI copy.
    if isinstance(value, str):
        return redact_secrets(value, key)
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    if isinstance(value, dict):
        return {name: redact_value(item, key) for name, item in value.items()}
    return value
