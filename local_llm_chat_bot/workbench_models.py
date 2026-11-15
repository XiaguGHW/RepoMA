"""Request bodies of the Bosch Assembly Assistant HTTP API (pydantic models).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


REQUEST_ID = r"^(?:[a-f0-9]{32})?$"


class Setup(BaseModel):
    workspace: str = ""
    state_dir: str = ""
    model: str = "gpt-5.5"
    session: str = "default"
    env_file: str = ""
    language: str = "de"


class PathRequest(BaseModel):
    path: str


class ModelTestRequest(BaseModel):
    model: str


class ModelSwitchRequest(BaseModel):
    model: str


class LanguageRequest(BaseModel):
    language: str


class SessionRenameRequest(BaseModel):
    name: str
    source: str = ""


class SessionDeleteRequest(BaseModel):
    confirmed: bool = False
    name: str = ""


class SessionOpenRequest(BaseModel):
    name: str


class SessionPinRequest(BaseModel):
    name: str
    pinned: bool


class BGRequest(BaseModel):
    codebook: str
    folder: str


class TargetRequest(BaseModel):
    target: str
    codebook: str = ""
    selected_paths: list[str] = []


class CodebookPrepareRequest(BaseModel):
    path: str
    model: str = ""
    request_id: str = Field(default="", pattern=REQUEST_ID)
    # The browser starts a background job and follows /api/codebook/task.
    # API callers that omit it keep the original blocking response.
    background: bool = False


class ChatRequest(BaseModel):
    request_id: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    question: str = Field(max_length=50000)
    # None = decide from the question (the UI no longer offers a mode switch).
    require_classification: bool | None = None
    # Optional single active material this turn is restricted to.
    focus_source_id: str = Field(default="", max_length=200)


class CompareRequest(BaseModel):
    question: str = Field(max_length=50000)
    models: list[str]
    request_id: str = Field(default="", pattern=REQUEST_ID)


class CoverageRequest(BaseModel):
    full: bool = False
    request_id: str = Field(default="", pattern=REQUEST_ID)


class CacheFileRequest(BaseModel):
    document_id: str
    confirmed: bool = False


class CacheConfirmRequest(BaseModel):
    confirmed: bool = False
    request_id: str = Field(default="", pattern=REQUEST_ID)


class OperationCancelRequest(BaseModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class CodebookEditRequest(BaseModel):
    draft: dict
    confirmed: bool = False
    profile_version: str | None = None


class ChatCancelRequest(BaseModel):
    request_id: str


class ApplyRequest(BaseModel):
    confirmed: bool = False
    plan_id: str = ""
