"""Background job runner.

A small in-process thread pool is enough for the MVP: job state lives in SQLite
(lesson status, GenerationJob rows), so Redis is not needed. Lessons left in a
non-terminal state by a restart are marked FAILED on startup and can be resumed with
POST /api/lessons/{id}/retry (completed stages are reused).
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from sqlalchemy import select

from app.core.db import session_scope
from app.core.logging import fields, get_logger
from app.models import GenerationJob, Lesson, Scene
from app.schemas.validation import LessonStatus

log = get_logger(__name__)

_ACTIVE = {
    LessonStatus.PENDING.value,
    LessonStatus.PLANNING.value,
    LessonStatus.GENERATING.value,
    LessonStatus.VALIDATING.value,
    LessonStatus.RENDERING.value,
}


class JobRunner:
    def __init__(self, threads: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="job")

    def submit(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        def run() -> Any:
            log.info("job started", extra=fields(job=name))
            try:
                return fn(*args, **kwargs)
            except Exception:
                log.exception("job crashed", extra=fields(job=name))
                raise
            finally:
                log.info("job finished", extra=fields(job=name))

        return self._pool.submit(run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class InlineJobRunner(JobRunner):
    """Runs jobs synchronously (used by tests)."""

    def __init__(self) -> None:  # noqa: D401 - no pool
        pass

    def submit(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(exc)
        return fut

    def shutdown(self) -> None:
        pass


_SCENE_ACTIVE = {"PENDING", "PLANNING", "GENERATING"}
_RENDER_ACTIVE = {"PENDING", "RENDERING"}


def recover_interrupted() -> int:
    with session_scope() as s:
        rows = list(s.scalars(select(Lesson).where(Lesson.status.in_(_ACTIVE))))
        for row in rows:
            row.status = LessonStatus.FAILED.value
            row.error = "interrupted by a server restart; use retry to resume"
        # Question follow-ups run outside the lesson status; without this they would spin forever.
        followups = list(
            s.scalars(
                select(Scene).where(
                    Scene.kind == "followup",
                    (Scene.status.in_(_SCENE_ACTIVE)) | (Scene.render_status.in_(_RENDER_ACTIVE)),
                )
            )
        )
        for job in s.scalars(select(GenerationJob).where(GenerationJob.status == "RUNNING")):
            job.status = "FAILED"
            job.error = "interrupted by a server restart"
        for sc in followups:
            sc.status = "FAILED"
            if sc.render_status in _RENDER_ACTIVE:
                sc.render_status = "FAILED"
            sc.error = "interrupted by a server restart; use Regenerate (Whole scene) to try again"
    return len(rows) + len(followups)
