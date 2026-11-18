"""One way to call a model for a structured result.

Every model request of the assistant follows the same pattern:

1. an attempt ladder: try with an output ceiling; only after an output-limit
   stop, try the next step (a larger ceiling, or a prompt suffix such as
   "be shorter"); every attempt is counted against the caller's call limit;
2. connector failures (HTTP, timeout, proxy, empty, output limit) become one
   typed error, ``StructuredCallError``, instead of text that looks like an
   answer;
3. the complete response is parsed/validated by the caller's ``parse``;
   optionally one repair request follows a parse failure;
4. an optional cache returns an earlier result for the same request.

What a caller does after an output limit at the last step - split its input
(rule pages, material groups) or give up - stays with the caller: that is
task knowledge, not call mechanics.  ``call_model_text`` runs only the ladder;
``structured_call`` adds parsing, repair and cache.

Every call still goes through accounted_model_call (usage ledger, cancel,
size limit, key redaction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Protocol, Sequence, TypeVar

from workbench_model_calls import accounted_model_call, connector_failure
from workbench_rules import classify_model_failure
from workbench_session import Session

T = TypeVar("T")


@dataclass(frozen=True)
class Attempt:
    """One step of the ladder."""
    output_tokens: int
    prompt_suffix: str = ""


@dataclass(frozen=True)
class CallTask:
    """One logical model request."""
    system: str
    prompt: str
    attempts: tuple[Attempt, ...]
    files: Sequence[Any] = ()
    temperature: float = 0
    stream: bool = True
    event_handler: Callable[[str, str], None] | None = None

    @staticmethod
    def ladder(*tokens: int) -> tuple[Attempt, ...]:
        return tuple(Attempt(value) for value in tokens)


class StructuredCallError(Exception):
    """A model request that produced no usable result.

    reason: "output_limit" (every step stopped at its ceiling), a connector
    reason from classify_model_failure ("empty", "http", "timeout",
    "connect_timeout", "proxy", "network", "model_error"), "invalid" (the
    response could not be parsed and no repair was allowed) or
    "invalid_after_repair".
    """

    def __init__(self, reason: str, *, params: dict[str, Any] | None = None, technical: str = "",
                 attempts: int = 0, raw: str = "", failure: Any = None, cause: Exception | None = None):
        super().__init__(f"{reason}: {technical}" if technical else reason)
        self.reason = reason
        self.params = params or {}
        self.technical = technical
        self.attempts = attempts
        self.raw = raw
        self.failure = failure  # the connector's failure text or message, when there was one
        self.cause = cause      # the parse error, for "invalid" reasons


class CallCache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def put(self, key: str, value: Any) -> None: ...


@dataclass
class RepairPolicy(Generic[T]):
    """One repair request after a parse failure the policy accepts."""
    task: Callable[[str, Exception], CallTask]          # (raw response, parse error) -> repair request
    applies: Callable[[Exception], bool] = field(default=lambda _error: True)
    parse: Callable[[str], T] | None = None              # default: the call's own parse


def call_model_text(data: Session, connector: Any, task: CallTask, *, usage_records: list | None = None,
                    before_attempt: Callable[[Attempt, int], None] | None = None) -> str:
    """Run the attempt ladder; return the first complete response text.

    Raises StructuredCallError: the connector reason of a non-output-limit
    failure at once, or "output_limit" when the last step also stopped there.
    """
    if not task.attempts:
        raise ValueError("a CallTask needs at least one attempt")
    for number, attempt in enumerate(task.attempts, start=1):
        if before_attempt:
            before_attempt(attempt, number)
        kwargs: dict[str, Any] = {"stream": task.stream, "usage_records": usage_records}
        if task.event_handler is not None:
            kwargs["event_handler"] = task.event_handler
        raw = accounted_model_call(data, connector, list(task.files), task.prompt + attempt.prompt_suffix, task.system,
                                   {"maxOutputTokens": attempt.output_tokens, "temperature": task.temperature},
                                   **kwargs)
        failure = connector_failure(raw)
        if not failure:
            return str(raw)
        reason, params = classify_model_failure(failure)
        if reason == "output_limit" and number < len(task.attempts):
            continue
        raise StructuredCallError(reason, params=params, technical=str(failure), attempts=number,
                                  raw=str(raw or ""), failure=failure)
    raise AssertionError("unreachable")  # the loop returns or raises


def structured_call(data: Session, connector: Any, task: CallTask, parse: Callable[[str], T], *,
                    usage_records: list | None = None,
                    before_attempt: Callable[[Attempt, int], None] | None = None,
                    repair: RepairPolicy[T] | None = None,
                    cache: CallCache | None = None, cache_key: str | None = None) -> T:
    """call_model_text + parse (+ one repair) (+ cache)."""
    if cache is not None and cache_key is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    raw = call_model_text(data, connector, task, usage_records=usage_records, before_attempt=before_attempt)
    try:
        value = parse(raw)
    except (ValueError, TypeError) as error:
        if repair is None or not repair.applies(error):
            raise StructuredCallError("invalid", technical=str(error), raw=raw, cause=error) from error
        repaired = call_model_text(data, connector, repair.task(raw, error), usage_records=usage_records,
                                   before_attempt=before_attempt)
        try:
            value = (repair.parse or parse)(repaired)
        except (ValueError, TypeError) as repair_error:
            raise StructuredCallError("invalid_after_repair", technical=str(repair_error), raw=repaired,
                                      cause=repair_error) from error
    if cache is not None and cache_key is not None:
        cache.put(cache_key, value)
    return value
