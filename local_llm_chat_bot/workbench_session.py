"""Type of the active session (``chat_workbench.ACTIVE``).

``ACTIVE`` holds the session opened by ``/api/setup``; it is empty until then.
A model call works on a copy of it that adds the controls of that one call
(``begin_model_work``). It stays a plain dict at runtime; the type lets mypy
check every key and value.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable, TypedDict

if TYPE_CHECKING:
    from code_chat_agent import PricingCatalog, ProjectState
    from llm_connector_with_prompt_caching import LLMConnector
    from local_document_library import LocalDocumentLibrary
    from request_runtime import RequestControl


class Session(TypedDict, total=False):
    """The open session. All keys are set together by /api/setup."""

    state: ProjectState            # session folder, history, usage, context binding
    documents: LocalDocumentLibrary  # document index of the workspace
    model: str                     # canonical model ID of the active model
    language: str                  # UI language: "de", "en" or "zh"
    llm: LLMConnector              # Bosch Farm connection for the active model
    env_file: str                  # .env file the credentials came from
    env_explicit: bool             # True when that .env was given explicitly
    pricing: PricingCatalog        # model prices for usage estimates

    # Only on the copy made for one model call (begin_model_work):
    request_control: RequestControl     # timeout, cancel and size limits of the call
    cancel_event: threading.Event       # set when the user stops the call
    operation_id: str                   # page-side ID used to cancel the call
    answer_events: Callable[[dict[str, Any]], None]  # stream events to the page


SETUP_KEYS = frozenset({"state", "documents", "model", "language", "llm", "env_file", "env_explicit",
                        "pricing"})
MODEL_WORK_KEYS = frozenset({"request_control", "cancel_event", "operation_id", "answer_events"})
