"""Persistence helpers used by the pipeline (short, thread-safe transactions)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.db import session_scope
from app.models import ConversationMessage, GenerationJob, Lesson, Scene, ValidationRecord
from app.schemas.validation import ValidationResult
from app.services.gemini.client import GenerationMeta


def update_lesson(lesson_id: str, **values: Any) -> None:
    with session_scope() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise KeyError(lesson_id)
        for k, v in values.items():
            setattr(lesson, k, v)


def get_lesson(lesson_id: str) -> Lesson:
    with session_scope() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise KeyError(lesson_id)
        s.expunge(lesson)
        return lesson


def get_scene(lesson_id: str, scene_id: str) -> Scene:
    with session_scope() as s:
        scene = s.scalar(select(Scene).where(Scene.lesson_id == lesson_id, Scene.scene_id == scene_id))
        if scene is None:
            raise KeyError(f"{lesson_id}/{scene_id}")
        s.expunge(scene)
        return scene


def list_scenes(lesson_id: str, kind: str | None = "main") -> list[Scene]:
    """Scenes of a lesson; by default only the main lesson scenes (not question follow-ups)."""
    with session_scope() as s:
        q = select(Scene).where(Scene.lesson_id == lesson_id)
        if kind is not None:
            q = q.where(Scene.kind == kind)
        scenes = list(s.scalars(q.order_by(Scene.order, Scene.id)))
        for sc in scenes:
            s.expunge(sc)
        return scenes


def update_scene(lesson_id: str, scene_id: str, **values: Any) -> None:
    with session_scope() as s:
        scene = s.scalar(select(Scene).where(Scene.lesson_id == lesson_id, Scene.scene_id == scene_id))
        if scene is None:
            raise KeyError(f"{lesson_id}/{scene_id}")
        for k, v in values.items():
            setattr(scene, k, v)


def add_followup_scene(lesson_id: str, parent_scene_id: str, question: str) -> str:
    """Create the row for a question follow-up scene and return its scene_id (e.g. scene_3_q2)."""
    with session_scope() as s:
        n = len(list(s.scalars(select(Scene.id).where(Scene.lesson_id == lesson_id, Scene.kind == "followup")))) + 1
        scene_id = f"{parent_scene_id}_q{n}"
        s.add(
            Scene(
                lesson_id=lesson_id,
                scene_id=scene_id,
                order=1000 + n,
                title=question[:250],
                kind="followup",
                parent_scene_id=parent_scene_id,
                question=question,
                status="PENDING",
            )
        )
        return scene_id


def replace_scenes(lesson_id: str, scenes: list[dict[str, Any]]) -> None:
    with session_scope() as s:
        for old in s.scalars(select(Scene).where(Scene.lesson_id == lesson_id)):
            s.delete(old)
        s.flush()
        for i, sc in enumerate(scenes):
            s.add(Scene(lesson_id=lesson_id, scene_id=sc["scene_id"], order=i, title=sc.get("title", ""), scene_ir=sc))


def record_job(
    lesson_id: str,
    stage: str,
    status: str,
    *,
    scene_id: str | None = None,
    meta: GenerationMeta | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    model: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        s.add(
            GenerationJob(
                lesson_id=lesson_id,
                scene_id=scene_id,
                stage=stage,
                status=status,
                model=meta.model if meta else model,
                prompt_name=meta.prompt_name if meta else None,
                prompt_version=meta.prompt_version if meta else None,
                attempts=meta.attempts if meta else 1,
                started_at=meta.started_at if meta else now,
                finished_at=now,
                duration_ms=meta.duration_ms if meta else duration_ms,
                error=(error or None) and error[:4000],
            )
        )


def start_job(lesson_id: str, stage: str, *, scene_id: str | None = None, model: str | None = None) -> int:
    """A RUNNING row the UI can show live (elapsed time ticking) until finish_job closes it."""
    with session_scope() as s:
        job = GenerationJob(
            lesson_id=lesson_id, scene_id=scene_id, stage=stage, status="RUNNING", model=model,
            attempts=0, started_at=datetime.now(timezone.utc),
        )
        s.add(job)
        s.flush()
        return job.id


def finish_job(
    job_id: int,
    status: str,
    *,
    stage: str | None = None,
    meta: GenerationMeta | None = None,
    error: str | None = None,
    model: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job is None:
            return
        started = job.started_at if job.started_at.tzinfo else job.started_at.replace(tzinfo=timezone.utc)
        job.status = status
        job.stage = stage or (meta.stage if meta else job.stage)
        job.finished_at = now
        job.duration_ms = round((now - started).total_seconds() * 1000)
        job.model = (meta.model if meta else None) or model or job.model
        if meta:
            job.prompt_name, job.prompt_version, job.attempts = meta.prompt_name, meta.prompt_version, meta.attempts
        else:
            job.attempts = max(job.attempts, 1)
        job.error = (error or None) and error[:4000]


def record_phase(lesson_id: str, phase: str, seconds: float) -> None:
    """Wall-clock time of one pipeline phase (parallel work counted once)."""
    with session_scope() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            return
        timings = dict(lesson.timings or {})
        timings[phase] = round(timings.get(phase, 0.0) + seconds, 1)
        lesson.timings = timings


def stage_timings(lesson_id: str) -> list[dict[str, Any]]:
    """Per stage: number of calls, summed and longest duration (from GenerationJob rows)."""
    from sqlalchemy import case, func

    with session_scope() as s:
        rows = s.execute(
            select(
                GenerationJob.stage,
                func.count(GenerationJob.id),
                func.coalesce(func.sum(GenerationJob.duration_ms), 0),
                func.coalesce(func.max(GenerationJob.duration_ms), 0),
                func.sum(case((GenerationJob.status == "FAILED", 1), else_=0)),
            )
            .where(GenerationJob.lesson_id == lesson_id)
            .group_by(GenerationJob.stage)
        ).all()
    out = [
        {"stage": st, "calls": n, "total_s": round(tot / 1000, 1), "max_s": round(mx / 1000, 1), "failed": int(f or 0)}
        for st, n, tot, mx, f in rows
    ]
    return sorted(out, key=lambda r: -r["total_s"])


def record_validation(lesson_id: str, result: ValidationResult, scene_id: str | None = None) -> None:
    with session_scope() as s:
        s.add(
            ValidationRecord(
                lesson_id=lesson_id,
                scene_id=scene_id,
                validator=result.validator,
                target=result.target,
                passed=result.passed,
                issues=[i.model_dump() for i in result.issues],
                details=result.details,
            )
        )


def add_message(lesson_id: str, scene_id: str | None, role: str, content: str, payload: dict | None = None) -> None:
    with session_scope() as s:
        s.add(ConversationMessage(lesson_id=lesson_id, scene_id=scene_id, role=role, content=content, payload=payload))


def history(lesson_id: str, limit: int = 12) -> list[dict[str, str]]:
    with session_scope() as s:
        rows = list(
            s.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.lesson_id == lesson_id)
                .order_by(ConversationMessage.id.desc())
                .limit(limit)
            )
        )
    return [{"role": r.role, "scene_id": r.scene_id or "", "content": r.content} for r in reversed(rows)]
