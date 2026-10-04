"""REST API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.container import Container
from app.core.db import get_session
from app.models import ConversationMessage, GenerationJob, Lesson, Scene, ValidationRecord
from app.schemas.api import (
    AskRequest,
    AskResponse,
    ChatReply,
    CreateLessonRequest,
    CreateLessonResponse,
    JobOut,
    LessonOut,
    LessonSummary,
    RegenerateRequest,
    RenderRequest,
    SceneOut,
    ValidationOut,
)
from app.schemas.scope import ScopeIR
from app.schemas.validation import LessonStatus
from app.services.pipeline import LessonPipeline, PipelineError

router = APIRouter(prefix="/api")

_BUSY = {
    LessonStatus.PENDING.value,
    LessonStatus.PLANNING.value,
    LessonStatus.GENERATING.value,
    LessonStatus.VALIDATING.value,
    LessonStatus.RENDERING.value,
}


def container(request: Request) -> Container:
    return request.app.state.container


def pipeline(c: Container = Depends(container)) -> LessonPipeline:
    if c.pipeline is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Gemini is not configured: {c.llm_error}")
    return c.pipeline


def _media_url(c: Container, path: str | None) -> str | None:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(c.settings.media_dir.resolve())
    except ValueError:
        return None
    return f"/media/{rel.as_posix()}"


def _lesson_or_404(session: Session, lesson_id: str) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lesson not found")
    return lesson


def _scene_out(c: Container, s: Scene) -> SceneOut:
    return SceneOut(
        scene_id=s.scene_id,
        order=s.order,
        title=s.title,
        kind=s.kind or "main",
        parent_scene_id=s.parent_scene_id,
        question=s.question,
        followup=s.followup,
        status=s.status,
        error=s.error,
        scene_ir=s.scene_ir,
        narration=s.narration,
        voiceover=s.voiceover,
        visual_meta=s.visual_meta,
        animation_plan=s.animation_plan,
        visual_plan=s.visual_plan,
        manim_code=s.manim_code,
        render_status=s.render_status,
        render_attempts=s.render_attempts,
        render_stderr=(s.render_stderr or "")[-4000:] or None,
        video_url=_media_url(c, s.video_path),
        regeneration_count=s.regeneration_count,
    )


@router.get("/health")
def health(c: Container = Depends(container)) -> dict:
    return {
        "status": "ok",
        "gemini_configured": c.pipeline is not None,
        "model": c.settings.gemini_model,
        "prompt_versions": c.prompts.versions(),
    }


@router.post("/lessons", status_code=status.HTTP_202_ACCEPTED, response_model=CreateLessonResponse)
def create_lesson(
    body: CreateLessonRequest,
    session: Session = Depends(get_session),
    c: Container = Depends(container),
    p: LessonPipeline = Depends(pipeline),
) -> CreateLessonResponse:
    lesson = Lesson(problem_text=body.problem.strip(), scope_text=(body.scope or "").strip() or None, render_quality=body.quality)
    session.add(lesson)
    session.commit()
    c.jobs.submit(f"generate:{lesson.id}", p.run_generation, lesson.id)
    return CreateLessonResponse(lesson_id=lesson.id, status=lesson.status)


@router.get("/lessons", response_model=list[LessonSummary])
def list_lessons(session: Session = Depends(get_session)) -> list[LessonSummary]:
    rows = session.scalars(select(Lesson).order_by(Lesson.created_at.desc()).limit(30))
    return [
        LessonSummary(
            id=r.id,
            created_at=r.created_at,
            status=r.status,
            problem_text=r.problem_text,
            title=(r.lesson_ir or {}).get("title"),
        )
        for r in rows
    ]


@router.get("/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson(lesson_id: str, session: Session = Depends(get_session), c: Container = Depends(container)) -> LessonOut:
    lesson = _lesson_or_404(session, lesson_id)
    warning = None
    if lesson.scope_ir:
        w = ScopeIR.model_validate(lesson.scope_ir).warning
        warning = w.model_dump() if w else None
    # latest result per (validator, target)
    latest: dict[tuple[str, str], ValidationRecord] = {}
    for v in session.scalars(select(ValidationRecord).where(ValidationRecord.lesson_id == lesson_id).order_by(ValidationRecord.id)):
        latest[(v.validator, v.target)] = v
    return LessonOut(
        id=lesson.id,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        status=lesson.status,
        current_stage=lesson.current_stage,
        error=lesson.error,
        problem_text=lesson.problem_text,
        scope_text=lesson.scope_text,
        problem_ir=lesson.problem_ir,
        scope_ir=lesson.scope_ir,
        scope_warning=warning,
        solution_ir=lesson.solution_ir,
        lesson_ir=lesson.lesson_ir,
        math_verified=lesson.math_verified,
        verified_value=lesson.verified_value,
        render_quality=lesson.render_quality or c.settings.manim_quality,
        video_url=_media_url(c, lesson.video_path),
        scenes=[_scene_out(c, s) for s in lesson.scenes if s.kind != "followup"],
        followups=[_scene_out(c, s) for s in lesson.scenes if s.kind == "followup"],
        validations=[
            ValidationOut(
                validator=v.validator,
                target=v.target,
                scene_id=v.scene_id,
                passed=v.passed,
                issues=v.issues,
                details=v.details,
                created_at=v.created_at,
            )
            for v in latest.values()
        ],
    )


@router.get("/lessons/{lesson_id}/scenes", response_model=list[SceneOut])
def get_scenes(lesson_id: str, session: Session = Depends(get_session), c: Container = Depends(container)) -> list[SceneOut]:
    lesson = _lesson_or_404(session, lesson_id)
    return [_scene_out(c, s) for s in lesson.scenes]


@router.post("/lessons/{lesson_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render(
    lesson_id: str,
    body: RenderRequest | None = None,
    session: Session = Depends(get_session),
    c: Container = Depends(container),
    p: LessonPipeline = Depends(pipeline),
) -> dict:
    lesson = _lesson_or_404(session, lesson_id)
    if lesson.status in _BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"lesson is busy ({lesson.status})")
    if not lesson.lesson_ir:
        raise HTTPException(status.HTTP_409_CONFLICT, "lesson has not been planned yet")
    lesson.status = LessonStatus.RENDERING.value
    if body and body.quality:
        lesson.render_quality = body.quality
    session.commit()
    c.jobs.submit(f"render:{lesson_id}", p.render_lesson, lesson_id, body.scene_ids if body else None)
    return {"lesson_id": lesson_id, "status": LessonStatus.RENDERING.value}


@router.get("/lessons/{lesson_id}/media")
def media(lesson_id: str, session: Session = Depends(get_session), c: Container = Depends(container)) -> dict:
    lesson = _lesson_or_404(session, lesson_id)
    return {
        "lesson_id": lesson_id,
        "status": lesson.status,
        "lesson_video_url": _media_url(c, lesson.video_path),
        "scenes": [
            {
                "scene_id": s.scene_id,
                "title": s.title,
                "render_status": s.render_status,
                "render_attempts": s.render_attempts,
                "video_url": _media_url(c, s.video_path),
            }
            for s in lesson.scenes
        ],
    }


@router.post("/lessons/{lesson_id}/chat", response_model=ChatReply)
def chat(
    lesson_id: str,
    body: AskRequest,
    session: Session = Depends(get_session),
    p: LessonPipeline = Depends(pipeline),
) -> ChatReply:
    """Answer a question about a scene in chat, with the lesson as context. If the learner needs a deeper
    explanation, they request a video answer with POST /ask (the chat history is part of its context)."""
    _lesson_or_404(session, lesson_id)
    session.close()
    try:
        a = p.answer_in_chat(lesson_id, body.scene_id, body.question)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    except PipelineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except Exception as exc:  # noqa: BLE001 - Gemini down etc.
        text = str(exc)
        if "429" in text or "RESOURCE_EXHAUSTED" in text:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Limit Gemini API jest wyczerpany (429) — podnieś limit wydatków w AI Studio lub zmień klucz, potem spróbuj ponownie.",
            )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Tutor nie mógł odpowiedzieć: {text[:300]}")
    return ChatReply(answer=a.answer, suggest_video=a.suggest_video, video_reason=a.video_reason)


@router.post("/lessons/{lesson_id}/ask", status_code=status.HTTP_202_ACCEPTED, response_model=AskResponse)
def ask(
    lesson_id: str,
    body: AskRequest,
    session: Session = Depends(get_session),
    c: Container = Depends(container),
    p: LessonPipeline = Depends(pipeline),
) -> AskResponse:
    """Answer a question about a scene with a NEW follow-up video (not a chat message)."""
    _lesson_or_404(session, lesson_id)
    session.close()
    try:
        scene_id = p.create_followup(lesson_id, body.scene_id, body.question)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    except PipelineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    c.jobs.submit(f"followup:{lesson_id}:{scene_id}", p.generate_followup, lesson_id, scene_id)
    return AskResponse(scene_id=scene_id, parent_scene_id=body.scene_id, status="PLANNING")


@router.post("/lessons/{lesson_id}/scenes/{scene_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_scene(
    lesson_id: str,
    scene_id: str,
    body: RegenerateRequest,
    session: Session = Depends(get_session),
    c: Container = Depends(container),
    p: LessonPipeline = Depends(pipeline),
) -> dict:
    lesson = _lesson_or_404(session, lesson_id)
    if lesson.status in _BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"lesson is busy ({lesson.status})")
    target = next((s for s in lesson.scenes if s.scene_id == scene_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    if target.kind == "followup":
        target.status = "PLANNING" if body.artifact == "scene" else "GENERATING"
    else:
        lesson.status = LessonStatus.GENERATING.value
    session.commit()
    c.jobs.submit(f"regenerate:{lesson_id}:{scene_id}", p.regenerate, lesson_id, scene_id, body.artifact, body.instruction)
    return {"lesson_id": lesson_id, "scene_id": scene_id, "artifact": body.artifact, "status": "GENERATING"}


@router.post("/lessons/{lesson_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(
    lesson_id: str,
    session: Session = Depends(get_session),
    c: Container = Depends(container),
    p: LessonPipeline = Depends(pipeline),
) -> dict:
    """Resume a failed lesson; completed stages are reused, failed ones re-run."""
    lesson = _lesson_or_404(session, lesson_id)
    if lesson.status in _BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"lesson is busy ({lesson.status})")
    lesson.status = LessonStatus.PENDING.value
    session.commit()
    c.jobs.submit(f"retry:{lesson_id}", p.run_generation, lesson_id)
    return {"lesson_id": lesson_id, "status": LessonStatus.PENDING.value}


@router.get("/lessons/{lesson_id}/jobs", response_model=list[JobOut])
def jobs(lesson_id: str, session: Session = Depends(get_session)) -> list[JobOut]:
    _lesson_or_404(session, lesson_id)
    rows = session.scalars(select(GenerationJob).where(GenerationJob.lesson_id == lesson_id).order_by(GenerationJob.id))
    return [
        JobOut(
            stage=r.stage,
            scene_id=r.scene_id,
            status=r.status,
            model=r.model,
            prompt_name=r.prompt_name,
            prompt_version=r.prompt_version,
            attempts=r.attempts,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_ms=r.duration_ms,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/lessons/{lesson_id}/timings")
def timings(lesson_id: str, session: Session = Depends(get_session)) -> dict:
    """Where the time went: wall-clock phases and per-stage sums (Gemini calls, voice, render)."""
    lesson = _lesson_or_404(session, lesson_id)
    from app.services.pipeline import store as st

    phases = lesson.timings or {}
    return {"lesson_id": lesson_id, "status": lesson.status, "total_s": round(sum(phases.values()), 1),
            "phases": phases, "stages": st.stage_timings(lesson_id)}


@router.get("/lessons/{lesson_id}/messages")
def messages(lesson_id: str, session: Session = Depends(get_session)) -> list[dict]:
    _lesson_or_404(session, lesson_id)
    rows = session.scalars(
        select(ConversationMessage).where(ConversationMessage.lesson_id == lesson_id).order_by(ConversationMessage.id)
    )
    return [
        {"role": r.role, "scene_id": r.scene_id, "content": r.content, "payload": r.payload, "created_at": r.created_at}
        for r in rows
    ]
