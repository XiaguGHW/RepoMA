"""Bounded cooperative model work and an answer-only incremental JSON preview."""

from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
import re
import threading
import time


class RequestStopped(RuntimeError):
    pass


class RequestCancelled(RequestStopped):
    pass


class RequestTimedOut(RequestStopped):
    pass


class ResponseLimitExceeded(RequestStopped):
    pass


@dataclass(frozen=True)
class RequestPolicy:
    timeout: float = 180
    connect_timeout: float = 5
    read_timeout: float = 20
    attempts: int = 3
    backoff: float = 1
    max_response_chars: int = 262144
    max_answer_chars: int = 131072

    @classmethod
    def from_env(cls):
        def number(name, default, minimum, maximum, integer=False):
            value = float(os.getenv('WORKBENCH_' + name, str(default)))
            if not math.isfinite(value) or not minimum <= value <= maximum or (integer and not value.is_integer()):
                raise ValueError('Invalid WORKBENCH_' + name)
            return int(value) if integer else value
        return cls(
            timeout=number('REQUEST_TIMEOUT_SECONDS', 180, .1, 1800),
            connect_timeout=number('CONNECT_TIMEOUT_SECONDS', 5, .05, 60),
            read_timeout=number('READ_TIMEOUT_SECONDS', 20, .05, 120),
            attempts=number('MAX_ATTEMPTS', 3, 1, 3, True),
            backoff=number('RETRY_BACKOFF_SECONDS', 1, 0, 5),
            max_response_chars=number('MAX_RESPONSE_CHARS', 262144, 1024, 2097152, True),
            max_answer_chars=number('MAX_ANSWER_CHARS', 131072, 256, 1048576, True),
        )


class RequestControl:
    def __init__(self, policy=None):
        self.policy = policy or RequestPolicy.from_env()
        self.deadline = time.monotonic() + self.policy.timeout
        self.cancel_event = threading.Event()
        self.guard = threading.RLock()
        self.reason = ''
        self.committed = False

    def check(self):
        if self.committed:
            return
        if self.cancel_event.is_set():
            if self.reason == 'limit':
                raise ResponseLimitExceeded('Provider response exceeds the configured size limit')
            error = RequestTimedOut if self.reason == 'timeout' else RequestCancelled
            raise error('Request timed out' if self.reason == 'timeout' else 'Request cancelled')
        if time.monotonic() >= self.deadline:
            self.cancel('timeout')
            raise RequestTimedOut('Request timed out')

    def cancel(self, reason='cancelled'):
        with self.guard:
            if self.committed:
                return False
            if not self.cancel_event.is_set():
                self.reason = reason
                self.cancel_event.set()
            return True

    def timeouts(self):
        self.check()
        remaining = max(.001, self.deadline - time.monotonic())
        return min(self.policy.connect_timeout, remaining), min(self.policy.read_timeout, remaining)

    def pause(self, seconds):
        self.check()
        self.cancel_event.wait(min(seconds, max(0, self.deadline - time.monotonic())))
        self.check()

    def limit(self, chars):
        self.check()
        if chars > self.policy.max_response_chars:
            raise ResponseLimitExceeded('Model response exceeds the configured size limit')

    @contextmanager
    def commit(self):
        # Cancellation and final publication have one ordering point. If stop
        # wins, no history/plan/result can commit. A finished commit is final.
        with self.guard:
            self.check()
            yield
            self.committed = True


class AnswerPreview:
    """Linear JSON scanner. Emit only a root object's string-valued answer.

    Other strings (including changes, classification and nested answer keys)
    never reach the preview. The final action still needs the full validator.
    """
    def __init__(self, limit=131072):
        self.limit = limit
        self.count = 0
        self.prefix = ''
        self.started = False
        self.disabled = False
        self.depth = 0
        self.state = 'key'
        self.key = ''
        self.string_role = None
        self.token = ''
        self.escape = False
        self.unicode_digits = None
        self.high_surrogate = None

    def feed(self, chunk):
        output = []
        for char in chunk:
            if self.disabled:
                break
            if not self.started:
                self.prefix += char
                stripped = self.prefix.strip()
                if stripped in ('{', '```json\n{', '```\n{'):
                    self.started = True
                    self.depth = 1
                elif len(self.prefix) > 32 or (stripped and not any(p.startswith(stripped) for p in ('{', '```json\n{', '```\n{'))):
                    self.disabled = True
                continue
            if self.string_role:
                if self.unicode_digits is not None:
                    if char not in '0123456789abcdefABCDEF':
                        self.disabled = True
                        continue
                    self.unicode_digits += char
                    if len(self.unicode_digits) < 4:
                        continue
                    char = chr(int(self.unicode_digits, 16))
                    self.unicode_digits = None
                elif self.escape:
                    self.escape = False
                    if char == 'u':
                        self.unicode_digits = ''
                        continue
                    if char not in '"\\/bfnrt':
                        self.disabled = True
                        continue
                    char = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}.get(char, char)
                elif char == '\\':
                    self.escape = True
                    continue
                elif char == '"':
                    if self.high_surrogate is not None:
                        self.disabled = True
                    if self.string_role == 'key':
                        self.key, self.state = self.token, 'colon'
                    elif self.depth == 1:
                        self.state = 'after'
                    self.string_role = None
                    continue
                elif ord(char) < 32:
                    self.disabled = True
                    continue
                if 0xD800 <= ord(char) <= 0xDBFF:
                    self.high_surrogate = ord(char)
                    continue
                if self.high_surrogate is not None:
                    if not 0xDC00 <= ord(char) <= 0xDFFF:
                        self.disabled = True
                        continue
                    char = chr(0x10000 + ((self.high_surrogate - 0xD800) << 10) + ord(char) - 0xDC00)
                    self.high_surrogate = None
                elif 0xDC00 <= ord(char) <= 0xDFFF:
                    self.disabled = True
                    continue
                if self.string_role == 'key':
                    self.token += char
                    if len(self.token) > 256:
                        self.disabled = True
                elif self.string_role == 'answer':
                    self.count += len(char)
                    if self.count > self.limit:
                        raise ResponseLimitExceeded('Answer preview exceeds the configured size limit')
                    output.append(char)
                continue
            if char == '"':
                self.string_role = ('key' if self.depth == 1 and self.state == 'key' else
                                    'answer' if self.depth == 1 and self.state == 'value' and self.key == 'answer' else 'skip')
                self.token = ''
            elif char in '{[':
                self.depth += 1
            elif char in '}]':
                self.depth -= 1
                if self.depth == 0:
                    self.disabled = True
                elif self.depth == 1:
                    self.state = 'after'
            elif self.depth == 1 and char == ':':
                self.state = 'value'
            elif self.depth == 1 and char == ',':
                self.state, self.key = 'key', ''
            elif self.depth == 1 and self.state == 'value' and not char.isspace():
                self.state = 'after'  # A primitive answer cannot become a later string.
        return ''.join(output)


def looks_like_action(raw):
    text = raw.lstrip()
    return (text.startswith(('{', '[', '```json')) or bool(re.match(r'```\s*[\[{]', text)) or
            bool(re.search(r'\{\s*"(?:answer|changes|classification|read_files)"\s*:', text)))
