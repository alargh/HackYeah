"""SQLAlchemy ORM models. Every important intermediate artifact is persisted."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    problem_text: Mapped[str] = mapped_column(Text)
    scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    problem_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scope_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    solution_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    lesson_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    math_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verified_value: Mapped[str | None] = mapped_column(String(128), nullable=True)

    video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # phase -> wall seconds
    render_quality: Mapped[str | None] = mapped_column(String(4), nullable=True)  # l | m | h (None = default)

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="lesson", order_by="Scene.order", cascade="all, delete-orphan"
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(String(64))
    order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256), default="")

    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "main" scenes form the lesson; "followup" scenes answer a learner question as a video.
    kind: Mapped[str] = mapped_column(String(16), default="main")
    parent_scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # answer summary, concepts
    ledger_extra: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # follow-up symbols

    scene_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    narration: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    voiceover: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    visual_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # retrieval + validity + code source
    animation_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    visual_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    manim_code: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    render_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    render_stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_attempts: Mapped[int] = mapped_column(Integer, default=0)
    video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0)

    lesson: Mapped[Lesson] = relationship(back_populates="scenes")


class GenerationJob(Base):
    """One row per pipeline stage execution (LLM call, validation run, render)."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValidationRecord(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validator: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    passed: Mapped[bool] = mapped_column(Boolean)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16))  # user | tutor
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
