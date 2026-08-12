from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="researcher")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    projects: Mapped[list[Project]] = relationship(back_populates="owner")
    tasks: Mapped[list[ResearchTask]] = relationship(back_populates="assignee")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    agent_contribution_pct: Mapped[float] = mapped_column(Float, default=0.0)
    human_contribution_pct: Mapped[float] = mapped_column(Float, default=100.0)
    template_key: Mapped[str] = mapped_column(String(64), default="blank")
    evidence_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    max_agent_pct: Mapped[float] = mapped_column(Float, default=10.0)
    publish_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_path: Mapped[str] = mapped_column(String(512), default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    sections: Mapped[list[ResearchSection]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[ResearchTask]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    citations: Mapped[list[Citation]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    framework_maps: Mapped[list[FrameworkMapping]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    peer_reviews: Mapped[list[PeerReview]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    control_reviews: Mapped[list[ControlReviewItem]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ResearchSection(Base):
    __tablename__ = "research_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    agent_chars: Mapped[int] = mapped_column(Integer, default=0)
    human_chars: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="sections")


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="todo")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="tasks")
    assignee: Mapped[User | None] = relationship(back_populates="tasks")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="artifacts")


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (UniqueConstraint("provider", "label", name="uq_provider_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(128), default="default")
    encrypted_value: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(128))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiCheckResult(Base):
    __tablename__ = "ai_check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_label: Mapped[str] = mapped_column(String(255), default="paste")
    text_sample: Mapped[str] = mapped_column(Text)
    ai_pct: Mapped[float] = mapped_column(Float)
    human_pct: Mapped[float] = mapped_column(Float)
    signals_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), default="researcher")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JudgeResult(Base):
    __tablename__ = "judge_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("research_sections.id"), nullable=True)
    criteria_json: Mapped[str] = mapped_column(Text, default="{}")
    scores_json: Mapped[str] = mapped_column(Text, default="{}")
    feedback: Mapped[str] = mapped_column(Text, default="")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[str] = mapped_column(String(64), default="researcher")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    style: Mapped[str] = mapped_column(String(16), default="apa")
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[str] = mapped_column(String(32), default="")
    formatted: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="citations")


class FrameworkMapping(Base):
    __tablename__ = "framework_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    framework: Mapped[str] = mapped_column(String(32), default="mitre")  # mitre | stride
    ref_id: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="framework_maps")


class PeerReview(Base):
    __tablename__ = "peer_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    section_id: Mapped[int | None] = mapped_column(ForeignKey("research_sections.id"), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|accepted|rejected
    comments: Mapped[str] = mapped_column(Text, default="")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="peer_reviews")


class ControlReviewItem(Base):
    __tablename__ = "control_review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    pack_id: Mapped[str] = mapped_column(String(64), default="")
    control_name: Mapped[str] = mapped_column(String(255), default="")
    vendor: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="unknown")  # met|partial|gap|unknown
    notes: Mapped[str] = mapped_column(Text, default="")
    residual_risk: Mapped[str] = mapped_column(String(32), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="control_reviews")
