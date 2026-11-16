"""Format versions and migrations of the assistant's own state files.

Every state file in ``AI_Bot_State`` that this program owns carries a
``format_version``. Reading a file migrates it step by step to the current
version; the program itself only ever sees the current shape (without the
version field). Writing stamps the current version. A file written before
versions existed counts as version 0.

Two layouts:

- object files (settings, rule profile, rule job, coverage report): the
  version is one more key of the object;
- record files keyed by folder or model (material selections, model tests):
  ``{"format_version": n, "records": {...}}``, so the version can never be
  mistaken for a folder or a model.

A file from a newer program version, or with an invalid version, raises
``StateFormatError`` (a ``ValueError``). Callers treat it like an unreadable
file, as they already do for corrupt JSON.

Session files (``state.json``), the document index and the caches keep their
own existing version fields and are not handled here.

To change a format: raise its ``version`` and add the migration from the
previous version to ``migrations``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

FORMAT_KEY = "format_version"
RECORDS_KEY = "records"


class StateFormatError(ValueError):
    """The file's format version is invalid or newer than this program."""


@dataclass(frozen=True)
class StateFormat:
    name: str
    version: int
    records: bool = False
    # migrations[n] turns a payload of version n into version n + 1.
    migrations: dict[int, Callable[[dict], dict]] = field(default_factory=dict)


def _unversioned(payload: dict) -> dict:
    """0 -> 1: files from before format versions have the same content."""
    return payload


SETTINGS = StateFormat("workbench_settings", 1, migrations={0: _unversioned})
CODEBOOK_PROFILE = StateFormat("codebook_profile", 1, migrations={0: _unversioned})
CODEBOOK_JOB = StateFormat("codebook_task", 1, migrations={0: _unversioned})
COVERAGE = StateFormat("analysis_coverage", 1, migrations={0: _unversioned})
MATERIAL_SELECTIONS = StateFormat("material_selections", 1, records=True, migrations={0: _unversioned})
MODEL_TESTS = StateFormat("model_tests", 1, records=True, migrations={0: _unversioned})

FORMATS = (SETTINGS, CODEBOOK_PROFILE, CODEBOOK_JOB, COVERAGE, MATERIAL_SELECTIONS, MODEL_TESTS)


def _split(fmt: StateFormat, raw: Any) -> tuple[int, Any]:
    if fmt.records:
        if isinstance(raw, dict) and FORMAT_KEY in raw and set(raw) <= {FORMAT_KEY, RECORDS_KEY}:
            return raw[FORMAT_KEY], raw.get(RECORDS_KEY)
        return 0, raw  # before versions: the records themselves
    if not isinstance(raw, dict):
        raise StateFormatError(f"{fmt.name}: not a JSON object")
    payload = {key: value for key, value in raw.items() if key != FORMAT_KEY}
    return raw.get(FORMAT_KEY, 0), payload


def decode(fmt: StateFormat, raw: Any) -> dict:
    """Return the payload of a parsed file in the current format."""
    version, payload = _split(fmt, raw)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise StateFormatError(f"{fmt.name}: invalid format version {version!r}")
    if version > fmt.version:
        raise StateFormatError(f"{fmt.name}: format version {version} is newer than {fmt.version}")
    if not isinstance(payload, dict):
        raise StateFormatError(f"{fmt.name}: unexpected content")
    while version < fmt.version:
        payload = fmt.migrations[version](payload)
        version += 1
    return payload


def encode(fmt: StateFormat, payload: dict) -> dict:
    """Return the JSON document to write for a payload in the current format."""
    if fmt.records:
        return {FORMAT_KEY: fmt.version, RECORDS_KEY: payload}
    return {FORMAT_KEY: fmt.version, **{key: value for key, value in payload.items() if key != FORMAT_KEY}}
