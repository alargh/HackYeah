"""Request/response models of the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RenderQuality = Literal["l", "m", "h"]  # 480p15 · 720p30 · 1080p60


class CreateLessonRequest(BaseModel):
    problem: str = Field(min_length=3, max_length=5000)
    scope: str | None = Field(default=None, max_length=2000)
    quality: RenderQuality | None = None


class CreateLessonResponse(BaseModel):
    lesson_id: str
    status: str


class RenderRequest(BaseModel):
    scene_ids: list[str] | None = None
    quality: RenderQuality | None = None


class RegenerateRequest(BaseModel):
    artifact: Literal["scene", "narration", "visual", "manim"] = "manim"
    instruction: str | None = Field(default=None, max_length=1000)


class AskRequest(BaseModel):
    scene_id: str
    question: str = Field(min_length=1, max_length=1000)


class ChatReply(BaseModel):
    """Chat answer to a question; `suggest_video` means a short video would explain it better."""

    answer: str
    suggest_video: bool = False
    video_reason: str = ""


class AskResponse(BaseModel):
    """A question is answered with a new follow-up video scene, generated in the background."""

    scene_id: str
    parent_scene_id: str
    status: str


class SceneOut(BaseModel):
    scene_id: str
    order: int
    title: str
    kind: str = "main"
    parent_scene_id: str | None = None
    question: str | None = None
    followup: dict[str, Any] | None = None
    status: str
    error: str | None = None
    scene_ir: dict[str, Any] | None = None
    narration: dict[str, Any] | None = None
    voiceover: dict[str, Any] | None = None
    visual_meta: dict[str, Any] | None = None
    animation_plan: dict[str, Any] | None = None
    visual_plan: dict[str, Any] | None = None
    manim_code: dict[str, Any] | None = None
    render_status: str
    render_attempts: int
    render_stderr: str | None = None
    video_url: str | None = None
    regeneration_count: int = 0


class ValidationOut(BaseModel):
    validator: str
    target: str
    scene_id: str | None = None
    passed: bool
    issues: list[dict[str, Any]]
    details: dict[str, Any]
    created_at: datetime


class LessonOut(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str
    current_stage: str | None = None
    error: str | None = None
    problem_text: str
    scope_text: str | None = None
    problem_ir: dict[str, Any] | None = None
    scope_ir: dict[str, Any] | None = None
    scope_warning: dict[str, Any] | None = None
    solution_ir: dict[str, Any] | None = None
    lesson_ir: dict[str, Any] | None = None
    math_verified: bool | None = None
    verified_value: str | None = None
    render_quality: str | None = None
    video_url: str | None = None
    scenes: list[SceneOut] = []
    followups: list[SceneOut] = []
    validations: list[ValidationOut] = []


class LessonSummary(BaseModel):
    id: str
    created_at: datetime
    status: str
    problem_text: str
    title: str | None = None


class JobOut(BaseModel):
    stage: str
    scene_id: str | None
    status: str
    model: str | None
    prompt_name: str | None
    prompt_version: str | None
    attempts: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
