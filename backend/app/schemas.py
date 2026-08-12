from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    display_name: str = ""
    role: str = "researcher"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    must_change_password: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    title: str
    description: str = ""
    template_key: str = "gartner_panel"
    evidence_mode: bool = True
    max_agent_pct: float = 10.0


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    template_key: str | None = None
    evidence_mode: bool | None = None
    max_agent_pct: float | None = None
    publish_ready: bool | None = None


class ProjectOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    owner_id: int
    agent_contribution_pct: float
    human_contribution_pct: float
    template_key: str = "blank"
    evidence_mode: bool = True
    max_agent_pct: float = 10.0
    publish_ready: bool = False
    archived: bool = False
    storage_path: str = ""
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    section_count: int = 0
    sections_with_content: int = 0
    task_count: int = 0
    tasks_done: int = 0
    artifact_count: int = 0
    progress_pct: float = 0.0

    model_config = {"from_attributes": True}


class SectionCreate(BaseModel):
    title: str
    prompt: str = ""
    content_md: str = ""
    sort_order: int = 0


class SectionUpdate(BaseModel):
    title: str | None = None
    prompt: str | None = None
    content_md: str | None = None
    sort_order: int | None = None
    agent_chars: int | None = None
    human_chars: int | None = None


class SectionOut(BaseModel):
    id: int
    project_id: int
    title: str
    prompt: str
    content_md: str
    sort_order: int
    agent_chars: int
    human_chars: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    assignee_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_id: int | None = None


class TaskOut(BaseModel):
    id: int
    project_id: int
    assignee_id: int | None
    title: str
    description: str
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: int
    project_id: int
    filename: str
    original_name: str
    content_type: str
    size_bytes: int
    notes: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenCreate(BaseModel):
    provider: str
    label: str = "default"
    value: str
    is_active: bool = True


class TokenUpdate(BaseModel):
    provider: str | None = None
    label: str | None = None
    value: str | None = None
    is_active: bool | None = None


class TokenOut(BaseModel):
    id: int
    provider: str
    label: str
    is_active: bool
    masked_value: str
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TokenBulkActionResponse(BaseModel):
    ok: bool
    affected: int
    message: str


class AssistantRequest(BaseModel):
    prompt: str
    section_id: int | None = None
    mode: str = "research"
    rewrite_human: bool = False
    providers: list[str] | None = None
    evidence_mode: bool | None = None
    multi_agent: bool = True


class AssistantResponse(BaseModel):
    content: str
    agent_chars: int
    notes: str = ""
    citations: list[dict[str, str]] = []
    providers_used: list[str] = []
    roles: dict[str, Any] = {}
    used_live: bool = False
    critique: str = ""
    red_team: str = ""


class ApplyAssistantRequest(BaseModel):
    section_id: int
    content: str
    mark_as_agent: bool = True


class AiCheckRequest(BaseModel):
    text: str
    source_label: str = "paste"


class AiCheckOut(BaseModel):
    id: int
    source_label: str
    ai_pct: float
    human_pct: float
    signals: dict[str, Any]
    recommendations: list[str]
    created_at: datetime
    extracted_text: str | None = None
    filename: str | None = None
    char_count: int | None = None
    truncated: bool | None = None


class TextExtractOut(BaseModel):
    filename: str
    extension: str
    char_count: int
    truncated: bool
    text: str
    supported_extensions: list[str]


class JudgeRequest(BaseModel):
    text: str
    project_id: int | None = None
    section_id: int | None = None
    criteria: list[str] = Field(
        default_factory=lambda: [
            "accuracy",
            "relevance",
            "originality",
            "ethics",
            "clarity",
        ]
    )


class JudgeOut(BaseModel):
    id: int
    overall_score: float
    scores: dict[str, float]
    feedback: str
    created_at: datetime


class RewriteRequest(BaseModel):
    text: str
    strength: str = "medium"


class ExportRequest(BaseModel):
    title: str
    content_md: str
    project_id: int | None = None
    force: bool = False


class HealthOut(BaseModel):
    status: str
    checks: dict[str, Any]
    version: str
    app_env: str


class KillSwitchResponse(BaseModel):
    ok: bool
    removed_tokens: int
    message: str


class CitationCreate(BaseModel):
    project_id: int
    style: str = "apa"
    title: str
    url: str = ""
    author: str = ""
    year: str = ""
    notes: str = ""


class CitationOut(BaseModel):
    id: int
    project_id: int
    style: str
    title: str
    url: str
    author: str
    year: str
    formatted: str
    notes: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FrameworkMapCreate(BaseModel):
    project_id: int
    framework: str
    ref_id: str
    name: str = ""
    notes: str = ""
    severity: str = "medium"


class FrameworkMapOut(BaseModel):
    id: int
    project_id: int
    framework: str
    ref_id: str
    name: str
    notes: str
    severity: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PeerReviewCreate(BaseModel):
    project_id: int
    section_id: int | None = None
    comments: str
    overall_score: float = 0.0
    status: str = "open"


class PeerReviewUpdate(BaseModel):
    comments: str | None = None
    overall_score: float | None = None
    status: str | None = None


class PeerReviewOut(BaseModel):
    id: int
    project_id: int
    section_id: int | None
    reviewer: str
    status: str
    comments: str
    overall_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ControlItemCreate(BaseModel):
    project_id: int
    pack_id: str = ""
    control_name: str
    vendor: str = ""
    status: str = "unknown"
    notes: str = ""
    residual_risk: str = "medium"


class ControlItemOut(BaseModel):
    id: int
    project_id: int
    pack_id: str
    control_name: str
    vendor: str
    status: str
    notes: str
    residual_risk: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DiagramRequest(BaseModel):
    kind: str = "attack"
    title: str = "Attack path"
    project_id: int | None = None
    section_id: int | None = None
    text: str = ""


class EvidenceRequest(BaseModel):
    text: str
    project_id: int | None = None
