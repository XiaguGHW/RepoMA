"""The model slot: at most one model task at a time, each stoppable by its ID.

A model task (answer, comparison, coverage, dossier rebuild, rule
preparation) reserves the slot before it starts and releases it when its
work has returned or raised. While the slot is taken, requests that would
change the task's context (session, model, rules, BG selection) are refused.

The slot is not a lock around the model call: requests that cannot affect
the running task (reading status, switching the UI language, pinning,
renaming or deleting another saved session) keep working while it runs.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from request_runtime import RequestControl


class ModelSlot:
    def __init__(self) -> None:
        # Set while a model task holds the slot.  Exposed as an Event so that
        # waiting code and tests can observe it (chat_workbench keeps the old
        # name MODEL_WORK_IN_PROGRESS for this same object).
        self.busy = threading.Event()
        self._guard = threading.Lock()
        self._operations: dict[str, RequestControl] = {}

    def reserve(self) -> bool:
        """Take the slot if it is free; False if another task holds it."""
        with self._guard:
            if self.busy.is_set():
                return False
            self.busy.set()
            return True

    def release(self) -> None:
        self.busy.clear()

    def register(self, operation_id: str, control: RequestControl) -> None:
        """Make the running task stoppable through its page-side operation ID."""
        if operation_id:
            with self._guard:
                self._operations[operation_id] = control

    def forget(self, operation_id: str) -> None:
        with self._guard:
            self._operations.pop(operation_id or "", None)

    def control(self, operation_id: str) -> RequestControl | None:
        with self._guard:
            return self._operations.get(operation_id)
