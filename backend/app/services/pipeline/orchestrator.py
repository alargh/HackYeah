"""The Tutorly pipeline.

problem → ProblemIR → ScopeIR → SolutionIR (validated) → LessonIR (ledger-validated)
        → per scene: NarrationIR (scope-validated) → VisualPlan → ManimCode (AST-validated)
        → render (sandboxed) → lesson video

Every stage output is persisted before the next stage starts, so any stage can be re-run
locally ("local regeneration") without discarding valid earlier work.
"""

from __future__ import annotations

from contextlib import contextmanager

import copy
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import fields, get_logger, log_stage
from app.schemas.generation import (
    AnimationPlan,
    ChatAnswer,
    FollowupPlan,
    ManimCode,
    NarrationIR,
    VisualPlan,
    Voiceover,
    VoiceoverSegment,
)
from app.schemas.lesson import ConceptLedger, LedgerEntry, LessonIR, SceneIR
from app.schemas.problem import ProblemIR
from app.schemas.scope import ScopeIR
from app.schemas.solution import SolutionIR
from app.schemas.validation import LessonStatus, RenderStatus, ValidationResult
from app.services.gemini.client import GeminiClient, Generated, StageError
from app.services.manim.renderer import ManimRenderer, concat_videos
from app.services.pipeline import store
from app.services.tts import SpeechSynthesizer
from app.services.validation import (
    LedgerValidator,
    ManimValidator,
    MathValidator,
    ScopeValidator,
)
from app.services.gemini.transport import TransportError, deadline
from app.services.validation.language import check_texts, spoken
from app.services.validation.visual_validator import ARITY
from app.services.visuals.autofix import autofix, prune
from app.services.validation.visual_validator import VisualPlanValidator
from app.services.visuals.compiler import compile_plan, render_source
from app.services.visuals.retrieval import retrieve

log = get_logger(__name__)
M = TypeVar("M", bound=BaseModel)

Artifact = Literal["scene", "narration", "visual", "manim"]
_CASCADE: dict[str, list[str]] = {
    "scene": ["scene", "narration", "visual", "manim"],
    "narration": ["narration", "visual", "manim"],
    "visual": ["visual", "manim"],
    "manim": ["manim"],
}


class PipelineError(RuntimeError):
    pass


def class_name_for(scene_id: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", scene_id)
    return "Tutorly" + "".join(p[:1].upper() + p[1:] for p in parts if p)


# Teaching-depth problems that must not fail a lesson whose maths is verified (handled by the lesson plan).
_TEACHING_CODES = {"SHORTCUT_NOT_EXPLAINED", "OUT_OF_CURRICULUM", "NAMED_THEOREM_SHORTCUT", "MISSING_REASONING"}

_LLM_STAGES = {
    "analyze_problem": "analyze_problem",
    "compile_scope": "compile_scope",
    "reason_about_problem": "reason",
    "create_lesson_plan": "plan_lesson",
    "regenerate_scene": "regenerate_scene",
    "generate_narration": "narration",
    "generate_visual_plan": "visual_plan",
    "generate_manim_code": "manim_code",
    "plan_followup": "ask_tutor",
}


def _feedback(*results: ValidationResult) -> str:
    return "\n".join(
        f"{r.validator} validator ({r.target}):\n{r.feedback()}"
        for r in results
        if not r.passed
    )


def _ledger_for(lesson: LessonIR, row: Any) -> ConceptLedger:
    """The lesson ledger, extended with symbols a follow-up scene introduced."""
    extra = [LedgerEntry.model_validate(e) for e in (row.ledger_extra or [])]
    return ConceptLedger(entries=[*lesson.concept_ledger.entries, *extra])


class LessonPipeline:
    def __init__(
        self,
        llm: GeminiClient,
        renderer: ManimRenderer,
        settings: Settings,
        tts: SpeechSynthesizer | None = None,
    ):
        self.llm = llm
        self.renderer = renderer
        self.settings = settings
        self.tts = tts
        self.math_validator = MathValidator()
        self.scope_validator = ScopeValidator()
        self.ledger_validator = LedgerValidator()
        self.manim_validator = ManimValidator()
        self.visual_validator = VisualPlanValidator()
        # voice synthesis runs beside visual planning; renders share a bounded number of CPU slots
        self._side = ThreadPoolExecutor(max_workers=16, thread_name_prefix="side")
        self._render_slots = threading.BoundedSemaphore(max(1, settings.render_workers))

    # ------------------------------------------------------------------ helpers

    def _gen(
        self,
        lesson_id: str,
        fn: Callable[..., Generated[M]],
        *args: Any,
        scene_id: str | None = None,
        **kwargs: Any,
    ) -> M:
        """Run one LLM stage; a RUNNING job row is visible while it runs and closed either way."""
        ctx = {"lesson_id": lesson_id, "scene_id": scene_id}
        name = getattr(fn, "__name__", "llm")
        job = store.start_job(
            lesson_id,
            _LLM_STAGES.get(name, name),
            scene_id=scene_id,
            model=getattr(self.llm, "model_name", None),
        )
        try:
            result = fn(*args, ctx=ctx, **kwargs)
        except StageError as exc:
            store.finish_job(
                job, "FAILED", stage=exc.stage, meta=exc.meta, error=exc.message
            )
            raise
        except Exception as exc:
            store.finish_job(job, "FAILED", error=str(exc))
            raise
        store.finish_job(job, "COMPLETED", meta=result.meta)
        return result.value

    @contextmanager
    def _job(
        self,
        lesson_id: str,
        stage: str,
        scene_id: str | None = None,
        model: str | None = None,
    ):
        """Non-LLM stage (voice, compile, render, concat) as a live job row. The body may set
        handle["status"], ["error"], ["model"]; an exception marks the job FAILED and propagates."""
        handle: dict[str, Any] = {"status": "COMPLETED", "error": None, "model": model}
        job = store.start_job(lesson_id, stage, scene_id=scene_id, model=model)
        try:
            yield handle
        except Exception as exc:
            store.finish_job(
                job, "FAILED", error=handle["error"] or str(exc), model=handle["model"]
            )
            raise
        store.finish_job(
            job, handle["status"], error=handle["error"], model=handle["model"]
        )

    def _validated(
        self, lesson_id: str, result: ValidationResult, scene_id: str | None = None
    ) -> ValidationResult:
        store.record_validation(lesson_id, result, scene_id)
        log.info(
            "validation",
            extra=fields(
                lesson_id=lesson_id,
                scene_id=scene_id,
                stage=f"validate_{result.validator}",
                status="PASSED" if result.passed else "FAILED",
                target=result.target,
                issues=len(result.issues),
                errors=[f"{i.code}: {i.message[:160]}" for i in result.issues if i.severity == "error"][:6],
            ),
        )
        return result

    def _status(
        self,
        lesson_id: str,
        status: LessonStatus,
        stage: str | None = None,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status.value, "current_stage": stage}
        if error is not None or status != LessonStatus.FAILED:
            values["error"] = error
        store.update_lesson(lesson_id, **values)
        log.info(
            "lesson status",
            extra=fields(lesson_id=lesson_id, stage=stage, status=status.value),
        )

    def _media_dir(self, lesson_id: str) -> Path:
        d = self.settings.media_dir / "lessons" / lesson_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --------------------------------------------------------------- generation

    def run_generation(self, lesson_id: str) -> None:
        try:
            self._run_generation(lesson_id)
        except Exception as exc:  # noqa: BLE001 - surface every failure on the lesson
            log.exception("generation failed", extra=fields(lesson_id=lesson_id))
            self._status(lesson_id, LessonStatus.FAILED, error=str(exc)[:2000])
            self.log_timings(lesson_id, "FAILED")

    def _phase(self, lesson_id: str, name: str, t0: float) -> float:
        store.record_phase(lesson_id, name, time.perf_counter() - t0)
        return time.perf_counter()

    def log_timings(self, lesson_id: str, outcome: str) -> None:
        """A readable per-lesson timing table in the container log (docker compose logs backend)."""
        try:
            lesson = store.get_lesson(lesson_id)
            phases = lesson.timings or {}
            stages = store.stage_timings(lesson_id)
        except Exception:  # noqa: BLE001 - logging must never break the pipeline
            return
        total = sum(phases.values())
        lines = [
            f"===== Tutorly timings  lesson={lesson_id}  outcome={outcome}  total={total:.1f}s ====="
        ]
        lines.append("  phases (wall clock):")
        for name, sec in phases.items():
            share = f"{100 * sec / total:4.0f}%" if total else ""
            lines.append(
                f"    {name:<26} {sec:7.1f}s  {share}  {'#' * int(30 * sec / total) if total else ''}"
            )
        lines.append("  stages (sum over calls; scenes run in parallel):")
        for r in stages:
            failed = f"  ({r['failed']} failed)" if r["failed"] else ""
            lines.append(
                f"    {r['stage']:<26} {r['calls']:3d}x  total {r['total_s']:7.1f}s  max {r['max_s']:6.1f}s{failed}"
            )
        print("\n".join(lines), flush=True)
        log.info(
            "lesson timings",
            extra=fields(
                lesson_id=lesson_id,
                outcome=outcome,
                total_s=round(total, 1),
                phases=phases,
                stages={r["stage"]: r["total_s"] for r in stages},
            ),
        )

    def _run_generation(self, lesson_id: str) -> None:
        lesson_row = store.get_lesson(lesson_id)
        t = time.perf_counter()
        self._status(lesson_id, LessonStatus.PLANNING, "analyze_problem")

        with log_stage(log, "analyze_problem", lesson_id=lesson_id):
            if lesson_row.problem_ir:
                problem = ProblemIR.model_validate(lesson_row.problem_ir)
            else:
                problem = self._gen(
                    lesson_id, self.llm.analyze_problem, lesson_row.problem_text
                )
                problem.original_text = lesson_row.problem_text
                store.update_lesson(
                    lesson_id, problem_ir=problem.model_dump(mode="json")
                )

        t = self._phase(lesson_id, "analyze_problem", t)
        self._status(lesson_id, LessonStatus.PLANNING, "compile_scope")
        with log_stage(log, "compile_scope", lesson_id=lesson_id):
            if lesson_row.scope_ir:
                scope = ScopeIR.model_validate(lesson_row.scope_ir)
            else:
                scope = self._gen(
                    lesson_id, self.llm.compile_scope, problem, lesson_row.scope_text
                )
                scope.user_scope_text = lesson_row.scope_text
                if not (lesson_row.scope_text or "").strip():
                    scope.mode = "open"
                store.update_lesson(lesson_id, scope_ir=scope.model_dump(mode="json"))

        t = self._phase(lesson_id, "compile_scope", t)
        self._status(lesson_id, LessonStatus.PLANNING, "reason")
        with log_stage(log, "reason", lesson_id=lesson_id):
            if lesson_row.solution_ir and lesson_row.math_verified:
                solution = SolutionIR.model_validate(lesson_row.solution_ir)
            else:
                solution = self.solve(lesson_id, problem, scope)

        t = self._phase(lesson_id, "reason+verify", t)
        self._status(lesson_id, LessonStatus.PLANNING, "plan_lesson")
        with log_stage(log, "plan_lesson", lesson_id=lesson_id):
            if lesson_row.lesson_ir:
                lesson = LessonIR.model_validate(lesson_row.lesson_ir)
            else:
                lesson = self.plan_lesson(lesson_id, problem, scope, solution)

        t = self._phase(lesson_id, "plan_lesson", t)
        self._status(lesson_id, LessonStatus.GENERATING, "scene_artifacts")
        scenes = store.list_scenes(lesson_id)
        pending = [s.scene_id for s in scenes if s.status != "GENERATED"]
        render_now = self.settings.auto_render
        if (
            render_now
        ):  # scenes already generated earlier (retry) render alongside the new ones
            for sc in scenes:
                if (
                    sc.status == "GENERATED"
                    and sc.render_status != RenderStatus.COMPLETED.value
                ):
                    pending.append(sc.scene_id)
        workers = max(1, min(self.settings.scene_workers, len(pending) or 1))
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="scene"
        ) as pool:
            list(
                pool.map(
                    lambda sid: self._scene_pipeline(
                        lesson_id, sid, problem, scope, lesson, render_now
                    ),
                    pending,
                )
            )

        t = self._phase(lesson_id, "scenes(narr+voice+visual+render)", t)
        self._status(lesson_id, LessonStatus.VALIDATING, "final_validation")
        scenes = store.list_scenes(lesson_id)
        ok = [s for s in scenes if s.status == "GENERATED"]
        self._validated(lesson_id, self.ledger_validator.validate_ledger(lesson))
        if not ok:
            raise PipelineError("no scene could be generated; see scene errors")
        failed = [s.scene_id for s in scenes if s.status != "GENERATED"]
        notes = [f"scenes failed to generate: {', '.join(failed)}"] if failed else []
        if store.get_lesson(lesson_id).math_verified is False:
            notes.append("the answer could not be verified by Python; double-check it")
        note = "; ".join(notes) or None
        if self.settings.auto_render:
            t = time.perf_counter()
            self._status(lesson_id, LessonStatus.RENDERING, "concat")
            try:
                self._finish_render(lesson_id)
            except Exception as exc:  # noqa: BLE001
                log.exception("render failed", extra=fields(lesson_id=lesson_id))
                self._status(
                    lesson_id, LessonStatus.FAILED, "render", error=str(exc)[:2000]
                )
            else:
                if (
                    note
                    and store.get_lesson(lesson_id).status
                    == LessonStatus.COMPLETED.value
                ):
                    self._status(lesson_id, LessonStatus.COMPLETED, None, error=note)
            self._phase(lesson_id, "concat", t)
            self.log_timings(lesson_id, store.get_lesson(lesson_id).status)
        else:
            self._status(lesson_id, LessonStatus.READY, None, error=note)
            self.log_timings(lesson_id, "READY")

    def solve(self, lesson_id: str, problem: ProblemIR, scope: ScopeIR) -> SolutionIR:
        """Reason + validate; on failure regenerate ONLY the solution, with validator feedback."""
        feedback: str | None = None
        previous: SolutionIR | None = None
        last: tuple[ValidationResult, ValidationResult] | None = None
        soft: tuple[SolutionIR, ValidationResult] | None = None
        best: tuple[int, SolutionIR] | None = None
        for attempt in range(self.settings.max_stage_retries + 1):
            solution = self._gen(
                lesson_id,
                self.llm.reason_about_problem,
                problem,
                scope,
                feedback=feedback,
                previous=previous,
            )
            math = self._validated(
                lesson_id, self.math_validator.validate(problem, solution)
            )
            scope_r = self._validated(
                lesson_id, self.scope_validator.validate_solution(solution, scope)
            )
            level = check_texts(
                {
                    st.id: f"{st.goal} {st.explanation} {st.why_valid}"
                    for st in solution.steps
                }
                | {"final_result": solution.final_result.statement},
                problem.language,
                "solution",
                scope,
                curriculum=True,
            )
            if (
                not level.passed
            ):  # out-of-curriculum wording is fixed by the same regeneration
                scope_r = ValidationResult.build(
                    "scope", "solution", [*scope_r.issues, *level.issues]
                )
                self._validated(lesson_id, level)
            store.update_lesson(
                lesson_id,
                solution_ir=solution.model_dump(mode="json"),
                math_verified=math.passed,
                verified_value=math.details.get("final_evaluated"),
            )
            if math.passed and scope_r.passed:
                return solution
            if all(i.code in _TEACHING_CODES for i in [*math.errors, *scope_r.errors]):
                # correct maths; only the teaching depth is lacking
                soft = (
                    solution,
                    ValidationResult.build(
                        "scope", "solution", [*math.errors, *scope_r.errors]
                    ),
                )
            last = (math, scope_r)
            n_err = 10 * len(math.errors) + len(
                scope_r.errors
            )  # wrong maths weighs more than wording
            if best is None or n_err < best[0]:
                best = (n_err, solution)
            feedback = _feedback(math, scope_r)
            previous = solution
            log.warning(
                "solution rejected, regenerating solution only",
                extra=fields(
                    lesson_id=lesson_id,
                    stage="reason",
                    attempt=attempt + 1,
                    feedback=feedback[:500],
                ),
            )
        if soft is not None:
            # The answer is verified; a named result is still used without being built up. Do not fail the
            # lesson: the planner must teach it from scratch (a scene deriving it on a tiny example) first.
            solution, scope_r = soft
            notes = "; ".join(sorted({i.message.split(".")[0] for i in scope_r.errors}))
            solution.scope_notes = (
                f"{solution.scope_notes}\nTEACHING NOTE (mandatory): {notes}. Before any step uses it, add a scene "
                "that builds it from basic counting / school geometry on a small concrete example, in everyday words."
            ).strip()
            log.warning(
                "solution accepted with a teaching note",
                extra=fields(lesson_id=lesson_id, stage="reason", note=notes[:300]),
            )
            store.update_lesson(
                lesson_id,
                solution_ir=solution.model_dump(mode="json"),
                math_verified=True,
            )
            return solution
        assert last is not None
        math, scope_r = last
        if self.settings.continue_on_failure and best is not None:
            # Keep going with the best attempt: the lesson is still useful, and the UI says the answer is
            # NOT verified by Python (math_verified = False) so the learner knows to double-check it.
            solution = best[1]
            solution.scope_notes = f"{solution.scope_notes}\nUNVERIFIED: {_feedback(math, scope_r)[:600]}".strip()
            log.warning(
                "continuing with an unverified solution",
                extra=fields(lesson_id=lesson_id, stage="reason"),
            )
            store.update_lesson(
                lesson_id,
                solution_ir=solution.model_dump(mode="json"),
                math_verified=False,
            )
            return solution
        reason = []
        if not math.passed:
            reason.append("mathematical validation failed")
        if not scope_r.passed:
            reason.append("solution violates the knowledge scope")
            if not scope.scope_sufficient:
                reason.append(f"(scope warning: {scope.explanation})")
        raise PipelineError(
            f"Solution rejected after retries: {'; '.join(reason)}.\n{_feedback(math, scope_r)}"
        )

    def plan_lesson(
        self, lesson_id: str, problem: ProblemIR, scope: ScopeIR, solution: SolutionIR
    ) -> LessonIR:
        feedback: str | None = None
        lesson: LessonIR | None = None
        for _ in range(self.settings.max_stage_retries + 1):
            lesson = self._gen(
                lesson_id,
                self.llm.create_lesson_plan,
                problem,
                scope,
                solution,
                feedback=feedback,
            )
            global_r = self._validated(
                lesson_id, self.ledger_validator.validate_ledger(lesson)
            )
            if global_r.passed:
                break
            feedback = _feedback(global_r)
        else:
            if not self.settings.continue_on_failure:
                raise PipelineError(
                    f"Lesson plan has inconsistent concept ledger:\n{feedback}"
                )
            log.warning(
                "continuing with an imperfect lesson plan",
                extra=fields(lesson_id=lesson_id, stage="plan_lesson"),
            )
        assert lesson is not None

        # Scene-level validation: an invalid scene is regenerated alone.
        for idx, scene in enumerate(lesson.scenes):
            for attempt in range(self.settings.max_stage_retries + 1):
                ledger_r = self._validated(
                    lesson_id,
                    self.ledger_validator.validate_scene(scene, lesson),
                    scene.scene_id,
                )
                scope_r = self._validated(
                    lesson_id,
                    self.scope_validator.validate_scene(scene, scope),
                    scene.scene_id,
                )
                lang_r = self._validated(
                    lesson_id,
                    check_texts(
                        {
                            "title": scene.title,
                            "learning_goal": scene.learning_goal,
                            "narration_plan": " ".join(scene.narration_plan),
                        },
                        problem.language,
                        f"scene:{scene.scene_id}",
                        scope,
                        curriculum=True,
                    ),
                    scene.scene_id,
                )
                if ledger_r.passed and scope_r.passed and lang_r.passed:
                    break
                if attempt == self.settings.max_stage_retries:
                    log.warning(
                        "scene still invalid after regeneration",
                        extra=fields(
                            lesson_id=lesson_id,
                            scene_id=scene.scene_id,
                            stage="plan_lesson",
                        ),
                    )
                    break
                new_scene = self._gen(
                    lesson_id,
                    self.llm.regenerate_scene,
                    problem,
                    scope,
                    solution,
                    lesson,
                    scene,
                    _feedback(ledger_r, scope_r, lang_r),
                    scene_id=scene.scene_id,
                )
                new_scene.scene_id = scene.scene_id
                lesson.scenes[idx] = scene = new_scene

        store.update_lesson(lesson_id, lesson_ir=lesson.model_dump(mode="json"))
        store.replace_scenes(
            lesson_id, [s.model_dump(mode="json") for s in lesson.scenes]
        )
        return lesson

    def _lesson_context(
        self, problem: ProblemIR, lesson: LessonIR, scene: SceneIR, row: Any = None
    ) -> dict[str, Any]:
        if row is not None and row.kind == "followup":
            parent = next(
                (s for s in lesson.scenes if s.scene_id == row.parent_scene_id), None
            )
            return {
                "lesson_title": lesson.title,
                "language": problem.language,
                "problem_summary": problem.summary,
                "this_scene_is": "a follow-up video answering the learner's question",
                "learner_question": row.question,
                "asked_while_watching": parent.title if parent else row.parent_scene_id,
                "answer_summary": (row.followup or {}).get("answer_summary"),
            }
        ids = [s.scene_id for s in lesson.scenes]
        idx = ids.index(scene.scene_id) if scene.scene_id in ids else 0
        return {
            "lesson_title": lesson.title,
            "language": problem.language,
            "problem_summary": problem.summary,
            "scene_number": idx + 1,
            "total_scenes": len(ids),
            "previous_scenes": [s.title for s in lesson.scenes[:idx]],
            "next_scene": lesson.scenes[idx + 1].title if idx + 1 < len(ids) else None,
        }

    def _scene_pipeline(
        self,
        lesson_id: str,
        scene_id: str,
        problem: ProblemIR,
        scope: ScopeIR,
        lesson: LessonIR,
        render: bool,
    ) -> None:
        """Generate one scene, then render it right away (other scenes keep generating meanwhile)."""
        if store.get_scene(lesson_id, scene_id).status != "GENERATED":
            self._generate_scene_safe(lesson_id, scene_id, problem, scope, lesson)
        if render and store.get_scene(lesson_id, scene_id).status == "GENERATED":
            store.update_scene(
                lesson_id, scene_id, render_status=RenderStatus.PENDING.value
            )
            self._render_scene_safe(lesson_id, scene_id, problem, lesson)

    def _generate_scene_safe(
        self,
        lesson_id: str,
        scene_id: str,
        problem: ProblemIR,
        scope: ScopeIR,
        lesson: LessonIR,
    ) -> None:
        try:
            with log_stage(
                log, "scene_artifacts", lesson_id=lesson_id, scene_id=scene_id
            ):
                self.generate_scene_artifacts(
                    lesson_id, scene_id, problem, scope, lesson
                )
        except Exception as exc:  # noqa: BLE001
            store.update_scene(
                lesson_id, scene_id, status="FAILED", error=str(exc)[:2000]
            )

    def generate_scene_artifacts(
        self,
        lesson_id: str,
        scene_id: str,
        problem: ProblemIR,
        scope: ScopeIR,
        lesson: LessonIR,
        only: list[str] | None = None,
        instruction: str | None = None,
    ) -> None:
        """Generate (or regenerate) the per-scene artifacts. `only` limits which artifacts are redone."""
        row = store.get_scene(lesson_id, scene_id)
        scene = SceneIR.model_validate(row.scene_ir)
        ledger = _ledger_for(lesson, row)
        redo = set(only) if only is not None else {"narration", "visual", "manim"}
        user_note = f"User request: {instruction}" if instruction else None
        store.update_scene(lesson_id, scene_id, status="GENERATING", error=None)

        # Narration (scope-validated; regenerate narration only)
        if "narration" in redo or not row.narration:
            feedback, previous = user_note, None
            for attempt in range(self.settings.max_stage_retries + 1):
                narration = self._gen(
                    lesson_id,
                    self.llm.generate_narration,
                    scene,
                    ledger,
                    scope,
                    self._lesson_context(problem, lesson, scene, row),
                    feedback=feedback,
                    previous=previous,
                    scene_id=scene_id,
                )
                narration.scene_id = scene_id
                result = self._validated(
                    lesson_id,
                    self.scope_validator.validate_narration(narration, scope),
                    scene_id,
                )
                lang_r = self._validated(
                    lesson_id,
                    check_texts(
                        {s.id: s.text for s in narration.segments},
                        problem.language,
                        f"narration:{scene_id}",
                        scope,
                        curriculum=True,
                    ),
                    scene_id,
                )
                if result.passed and lang_r.passed:
                    break
                if attempt == self.settings.max_stage_retries:
                    if not self.settings.continue_on_failure:
                        raise PipelineError(
                            f"narration rejected after retries:\n{_feedback(result, lang_r)}"
                        )
                    log.warning(
                        "continuing with imperfect narration",
                        extra=fields(lesson_id=lesson_id, scene_id=scene_id),
                    )
                    break
                feedback = "\n".join(
                    filter(None, [user_note, _feedback(result, lang_r)])
                )
                previous = narration
            store.update_scene(
                lesson_id, scene_id, narration=narration.model_dump(mode="json")
            )
        else:
            narration = NarrationIR.model_validate(row.narration)

        # Voiceover (Azure or local). Real clip durations replace the estimates so the visual plan and
        # Manim code are paced to the voice. A TTS failure leaves the scene silent, not broken.
        voice_job = None
        if "narration" in redo or not row.voiceover:
            voice_job = self._side.submit(
                self.synthesize_voiceover,
                lesson_id,
                scene_id,
                narration.model_copy(deep=True),
                problem.language,
            )
            voiceover = None
        else:
            voiceover = Voiceover.model_validate(row.voiceover)

        # Semantic visual plan: retrieved capabilities only; validated; regenerate the visual plan only.
        if "visual" in redo or not row.visual_plan:
            plan, meta = self.plan_visuals(
                lesson_id, scene, ledger, narration, problem, user_note
            )
            store.update_scene(
                lesson_id,
                scene_id,
                visual_plan=plan.model_dump(mode="json"),
                visual_meta=meta,
            )
        else:
            plan, meta = (
                VisualPlan.model_validate(row.visual_plan),
                dict(row.visual_meta or {}),
            )

        if voice_job is not None:
            voiceover = voice_job.result()
            store.update_scene(
                lesson_id,
                scene_id,
                voiceover=voiceover.model_dump(mode="json") if voiceover else None,
            )
        if voiceover:
            durations = {s.id: s.duration for s in voiceover.segments}
            for seg in narration.segments:
                seg.duration_estimate = round(
                    durations.get(seg.id, seg.duration_estimate), 2
                )
            store.update_scene(
                lesson_id, scene_id, narration=narration.model_dump(mode="json")
            )

        # Manim code: compiled deterministically from a valid visual plan; Gemini-written code is the fallback.
        if "manim" in redo or not row.manim_code:
            code, anim = self.compile_visuals(
                lesson_id, scene, plan, narration, meta, problem
            )
            if code is None:
                code = self.generate_manim(
                    lesson_id, scene, ledger, narration, plan, feedback=user_note
                )
            meta["code_source"] = "compiled" if anim is not None else "gemini"
            store.update_scene(
                lesson_id,
                scene_id,
                manim_code=code.model_dump(mode="json"),
                animation_plan=anim.model_dump(mode="json")
                if anim is not None
                else None,
                visual_meta=meta,
                render_status=RenderStatus.NOT_STARTED.value,
            )
        store.update_scene(lesson_id, scene_id, status="GENERATED", error=None)

    def plan_visuals(
        self,
        lesson_id: str,
        scene: SceneIR,
        ledger: ConceptLedger,
        narration: NarrationIR,
        problem: ProblemIR,
        user_note: str | None,
    ) -> tuple[VisualPlan, dict[str, Any]]:
        """Visual plan with three speed guards that keep the same validation (quality) bar:
        mechanical slips are repaired in Python instead of another LLM round, a call that thinks too long is
        cancelled, and retries run several candidates in parallel (first valid one wins)."""
        lesson_row = store.get_lesson(lesson_id)
        solution = (
            SolutionIR.model_validate(lesson_row.solution_ir)
            if lesson_row.solution_ir
            else None
        )
        caps = retrieve(problem, solution, scene)
        feedback = user_note
        best: tuple[int, VisualPlan, ValidationResult] | None = None
        max_moves = self.visual_validator.m.rule("max_camera_moves").value

        def attempt(fb: str | None) -> tuple[VisualPlan, ValidationResult, list[str]]:
            with deadline(self.settings.visual_plan_timeout_s):
                plan = self._gen(
                    lesson_id,
                    self.llm.generate_visual_plan,
                    scene,
                    ledger,
                    narration,
                    caps.for_prompt(),
                    feedback=fb,
                    scene_id=scene.scene_id,
                )
            plan.scene_id = scene.scene_id
            plan, notes = autofix(plan, ARITY, max_moves)
            result = self.visual_validator.validate(
                plan, scene, narration, caps.template_ids, problem
            )
            return plan, result, notes

        for round_ in range(self.settings.max_stage_retries + 1):
            width = (
                1 if round_ == 0 else max(1, self.settings.visual_plan_parallel_retries)
            )
            with ThreadPoolExecutor(
                max_workers=width, thread_name_prefix="vplan"
            ) as pool:
                futures = [pool.submit(attempt, feedback) for _ in range(width)]
                winner = None
                for fut in as_completed(futures):
                    try:
                        plan, result, notes = fut.result()
                    except (StageError, TransportError) as exc:
                        log.warning(
                            "visual plan call failed",
                            extra=fields(
                                lesson_id=lesson_id,
                                scene_id=scene.scene_id,
                                error=str(exc)[:300],
                            ),
                        )
                        continue
                    self._validated(lesson_id, result, scene.scene_id)
                    if result.passed:
                        winner = (plan, notes)
                        break
                    if best is None or len(result.errors) < best[0]:
                        best = (len(result.errors), plan, result)
            if winner:
                meta = {
                    "retrieved_templates": caps.template_ids,
                    "tags": caps.tags,
                    "valid": True,
                    "autofix": winner[1],
                }
                return winner[0], meta
            feedback = "\n".join(
                filter(
                    None,
                    [
                        user_note,
                        _feedback(best[2])
                        if best
                        else "previous attempt timed out; keep the plan simpler",
                    ],
                )
            )
        if best is None:
            raise PipelineError(
                "visual planning failed: every call errored or timed out"
            )
        # Prefer a pruned plan drawn by the engine over Gemini-written fallback code
        # (which places things at random).
        pruned = best[1]
        for _ in range(3):
            res = self.visual_validator.validate(
                pruned, scene, narration, caps.template_ids, problem
            )
            if res.passed:
                self._validated(lesson_id, res, scene.scene_id)
                meta = {
                    "retrieved_templates": caps.template_ids,
                    "tags": caps.tags,
                    "valid": True,
                    "pruned": True,
                }
                return pruned, meta
            cut = prune(pruned, res.issues)
            if cut is None:
                break
            pruned = cut[0]
        meta = {
            "retrieved_templates": caps.template_ids,
            "tags": caps.tags,
            "valid": False,
        }
        return best[1], meta

    def compile_visuals(
        self,
        lesson_id: str,
        scene: SceneIR,
        plan: VisualPlan,
        narration: NarrationIR,
        meta: dict[str, Any],
        problem: ProblemIR | None = None,
    ) -> tuple[ManimCode | None, AnimationPlan | None]:
        if not meta.get("valid"):
            return None, None
        class_name = class_name_for(scene.scene_id)
        with self._job(
            lesson_id, "visual_compile", scene.scene_id, "tutorly_visuals"
        ) as job:
            try:
                anim = compile_plan(plan, narration, class_name, scene.title, problem)
                code = ManimCode(
                    scene_id=scene.scene_id,
                    class_name=class_name,
                    code=render_source(anim),
                    events_covered=[b.id for b in plan.beats],
                    notes=f"compiled from visual plan (templates: {', '.join(plan.template_ids)})",
                )
            except Exception as exc:  # noqa: BLE001 - fall back to Gemini-written code
                job.update(status="FAILED", error=str(exc))
                return None, None
            result = self._validated(
                lesson_id, self.manim_validator.validate(code, plan), scene.scene_id
            )
            if not result.passed:
                job.update(status="FAILED", error=result.feedback())
        return (code, anim) if result.passed else (None, None)

    def synthesize_voiceover(
        self, lesson_id: str, scene_id: str, narration: NarrationIR, language: str
    ) -> Voiceover | None:
        if self.tts is None or not self.settings.voiceover:
            return None
        out_dir = self._media_dir(lesson_id) / "audio"
        version = store.get_scene(lesson_id, scene_id).regeneration_count
        paths = [
            out_dir / f"{scene_id}_v{version}_{seg.id}.wav"
            for seg in narration.segments
        ]
        texts = [spoken(seg.text, language) for seg in narration.segments]
        model, voice = self.tts.model_name, self.tts.voice
        try:
            with (
                self._job(lesson_id, "tts", scene_id, model) as job,
                log_stage(log, "tts", lesson_id=lesson_id, scene_id=scene_id),
            ):
                if hasattr(
                    self.tts, "synthesize_with_info"
                ):  # FallbackSpeech reports the voice it used
                    durations, model, voice = self.tts.synthesize_with_info(
                        texts, language, paths
                    )
                else:
                    durations = self.tts.synthesize_scene(texts, language, paths)
                job["model"] = model
        except Exception:  # noqa: BLE001 - voice is an enhancement; the lesson still works silently
            return None
        segments = [
            VoiceoverSegment(
                id=seg.id, visual_event=seg.visual_event, path=str(p), duration=d
            )
            for seg, p, d in zip(narration.segments, paths, durations)
        ]
        return Voiceover(model=model, voice=voice, segments=segments)

    def generate_manim(
        self,
        lesson_id: str,
        scene: SceneIR,
        ledger: Any,
        narration: NarrationIR,
        plan: VisualPlan,
        feedback: str | None = None,
        previous: ManimCode | None = None,
    ) -> ManimCode:
        class_name = class_name_for(scene.scene_id)
        for attempt in range(self.settings.max_stage_retries + 1):
            code = self._gen(
                lesson_id,
                self.llm.generate_manim_code,
                scene,
                ledger,
                narration,
                plan,
                class_name,
                feedback=feedback,
                previous=previous,
                scene_id=scene.scene_id,
            )
            code.scene_id = scene.scene_id
            result = self._validated(
                lesson_id, self.manim_validator.validate(code, plan), scene.scene_id
            )
            if result.passed:
                return code
            if attempt == self.settings.max_stage_retries:
                raise PipelineError(
                    f"generated Manim code rejected after retries:\n{result.feedback()}"
                )
            feedback = _feedback(result)
            previous = code
        raise AssertionError("unreachable")

    # ------------------------------------------------------------------ render

    def render_lesson(self, lesson_id: str, scene_ids: list[str] | None = None) -> None:
        t = time.perf_counter()
        try:
            self._render_lesson(lesson_id, scene_ids)
        except Exception as exc:  # noqa: BLE001
            log.exception("render failed", extra=fields(lesson_id=lesson_id))
            self._status(
                lesson_id, LessonStatus.FAILED, "render", error=str(exc)[:2000]
            )
        self._phase(lesson_id, "render+concat", t)
        self.log_timings(lesson_id, store.get_lesson(lesson_id).status)

    def _render_lesson(self, lesson_id: str, scene_ids: list[str] | None) -> None:
        lesson_row = store.get_lesson(lesson_id)
        if not lesson_row.lesson_ir:
            raise PipelineError("lesson has no plan yet; nothing to render")
        problem = ProblemIR.model_validate(lesson_row.problem_ir)
        lesson = LessonIR.model_validate(lesson_row.lesson_ir)
        self._status(lesson_id, LessonStatus.RENDERING, "render")
        targets = [
            s.scene_id
            for s in store.list_scenes(lesson_id)
            if s.manim_code and (scene_ids is None or s.scene_id in scene_ids)
        ]
        for sid in targets:
            store.update_scene(lesson_id, sid, render_status=RenderStatus.PENDING.value)
        with ThreadPoolExecutor(
            max_workers=max(1, self.settings.render_workers),
            thread_name_prefix="render",
        ) as pool:
            list(
                pool.map(
                    lambda sid: self._render_scene_safe(
                        lesson_id, sid, problem, lesson
                    ),
                    targets,
                )
            )
        self._finish_render(lesson_id)

    def _render_scene_safe(
        self, lesson_id: str, scene_id: str, problem: ProblemIR, lesson: LessonIR
    ) -> None:
        try:
            self.render_scene(lesson_id, scene_id, problem, lesson)
        except Exception as exc:  # noqa: BLE001
            store.update_scene(
                lesson_id,
                scene_id,
                render_status=RenderStatus.FAILED.value,
                error=str(exc)[:2000],
            )

    def render_scene(
        self, lesson_id: str, scene_id: str, problem: ProblemIR, lesson: LessonIR
    ) -> bool:
        """Render one scene; on failure regenerate ONLY its Manim code (with the error) and retry."""
        row = store.get_scene(lesson_id, scene_id)
        code = ManimCode.model_validate(row.manim_code)
        out_dir = self._media_dir(lesson_id)
        attempts = row.render_attempts
        for attempt in range(self.settings.max_render_retries + 1):
            attempts += 1
            store.update_scene(
                lesson_id,
                scene_id,
                render_status=RenderStatus.RENDERING.value,
                render_attempts=attempts,
            )
            out = out_dir / f"{scene_id}_v{attempts}.mp4"
            voice = (
                [
                    s.model_dump()
                    for s in Voiceover.model_validate(row.voiceover).segments
                ]
                if row.voiceover
                else None
            )
            with (
                self._job(lesson_id, "render", scene_id, "manim") as job,
                log_stage(
                    log,
                    "render",
                    lesson_id=lesson_id,
                    scene_id=scene_id,
                    attempt=attempt + 1,
                    voiceover=bool(voice),
                ),
            ):
                quality = (
                    store.get_lesson(lesson_id).render_quality
                    or self.settings.manim_quality
                )
                with self._render_slots:
                    result = self.renderer.render(
                        code.code,
                        code.class_name,
                        out,
                        voiceover=voice,
                        quality=quality,
                    )
                if not result.success:
                    job.update(
                        status="FAILED",
                        error=result.error
                        and f"{result.error}\n{result.stderr[-1500:]}",
                    )
            store.update_scene(
                lesson_id,
                scene_id,
                render_stdout=result.stdout,
                render_stderr=result.stderr,
                render_status=(
                    RenderStatus.COMPLETED if result.success else RenderStatus.FAILED
                ).value,
                video_path=str(out) if result.success else row.video_path,
                error=None if result.success else result.error,
            )
            if result.success:
                return True
            if attempt == self.settings.max_render_retries:
                return False
            # Local regeneration: only the Manim code of this scene.
            scene = SceneIR.model_validate(row.scene_ir)
            narration = NarrationIR.model_validate(row.narration)
            plan = VisualPlan.model_validate(row.visual_plan)
            err = f"Rendering failed: {result.error}\nstderr (tail):\n{result.stderr[-3000:]}"
            code = self.generate_manim(
                lesson_id,
                scene,
                _ledger_for(lesson, row),
                narration,
                plan,
                feedback=err,
                previous=code,
            )
            meta = {**(row.visual_meta or {}), "code_source": "gemini"}
            store.update_scene(
                lesson_id,
                scene_id,
                manim_code=code.model_dump(mode="json"),
                animation_plan=None,
                visual_meta=meta,
            )
            row = store.get_scene(lesson_id, scene_id)
        return False

    def _finish_render(self, lesson_id: str) -> None:
        scenes = store.list_scenes(lesson_id)
        done = [
            s
            for s in scenes
            if s.render_status == RenderStatus.COMPLETED.value and s.video_path
        ]
        failed = [
            s.scene_id
            for s in scenes
            if s.render_status != RenderStatus.COMPLETED.value
        ]
        if not done:
            self._status(
                lesson_id,
                LessonStatus.FAILED,
                "render",
                error="no scene could be rendered",
            )
            return
        lesson_video = (
            self._media_dir(lesson_id)
            / f"lesson_{sum(s.render_attempts for s in scenes)}.mp4"
        )
        with self._job(lesson_id, "concat", None, "ffmpeg") as job:
            ok = concat_videos([Path(s.video_path) for s in done], lesson_video)
            if not ok:
                job.update(status="FAILED", error="ffmpeg concat failed")
        video = str(lesson_video) if ok else None
        store.update_lesson(lesson_id, video_path=video)
        note = f"scenes not rendered: {', '.join(failed)}" if failed else None
        self._status(lesson_id, LessonStatus.COMPLETED, None, error=note)

    # ------------------------------------------------------------ regeneration

    def regenerate(
        self,
        lesson_id: str,
        scene_id: str,
        artifact: Artifact,
        instruction: str | None = None,
        render: bool = True,
    ) -> None:
        """Local regeneration of one scene artifact (and only what depends on it)."""
        if store.get_scene(lesson_id, scene_id).kind == "followup":
            self._regenerate_followup(lesson_id, scene_id, artifact, instruction)
            return
        try:
            lesson_row = store.get_lesson(lesson_id)
            problem = ProblemIR.model_validate(lesson_row.problem_ir)
            scope = ScopeIR.model_validate(lesson_row.scope_ir)
            solution = SolutionIR.model_validate(lesson_row.solution_ir)
            lesson = LessonIR.model_validate(lesson_row.lesson_ir)
            steps = _CASCADE[artifact]
            self._status(
                lesson_id, LessonStatus.GENERATING, f"regenerate:{scene_id}:{artifact}"
            )
            if "scene" in steps:
                idx = next(
                    i for i, s in enumerate(lesson.scenes) if s.scene_id == scene_id
                )
                feedback = (
                    f"User request: {instruction}"
                    if instruction
                    else "Improve clarity of this scene."
                )
                new_scene = self._gen(
                    lesson_id,
                    self.llm.regenerate_scene,
                    problem,
                    scope,
                    solution,
                    lesson,
                    lesson.scenes[idx],
                    feedback,
                    scene_id=scene_id,
                )
                new_scene.scene_id = scene_id
                ledger_r = self._validated(
                    lesson_id,
                    self.ledger_validator.validate_scene(new_scene, lesson),
                    scene_id,
                )
                scope_r = self._validated(
                    lesson_id,
                    self.scope_validator.validate_scene(new_scene, scope),
                    scene_id,
                )
                if not (ledger_r.passed and scope_r.passed):
                    raise PipelineError(
                        f"regenerated scene is invalid:\n{_feedback(ledger_r, scope_r)}"
                    )
                lesson.scenes[idx] = new_scene
                store.update_lesson(lesson_id, lesson_ir=lesson.model_dump(mode="json"))
                store.update_scene(
                    lesson_id,
                    scene_id,
                    scene_ir=new_scene.model_dump(mode="json"),
                    title=new_scene.title,
                )
            row = store.get_scene(lesson_id, scene_id)
            store.update_scene(
                lesson_id, scene_id, regeneration_count=row.regeneration_count + 1
            )
            self.generate_scene_artifacts(
                lesson_id,
                scene_id,
                problem,
                scope,
                lesson,
                only=[s for s in steps if s != "scene"],
                instruction=instruction,
            )
            if render:
                self._status(lesson_id, LessonStatus.RENDERING, "render")
                self.render_scene(lesson_id, scene_id, problem, lesson)
                self._finish_render(lesson_id)
            else:
                self._status(lesson_id, LessonStatus.READY)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "regeneration failed",
                extra=fields(lesson_id=lesson_id, scene_id=scene_id),
            )
            store.update_scene(lesson_id, scene_id, error=str(exc)[:2000])
            # The rest of the lesson is still valid: return to a usable state.
            lesson_row = store.get_lesson(lesson_id)
            status = (
                LessonStatus.COMPLETED
                if lesson_row.video_path
                or any(s.video_path for s in store.list_scenes(lesson_id))
                else LessonStatus.READY
            )
            self._status(
                lesson_id,
                status,
                None,
                error=f"regeneration of {scene_id}/{artifact} failed: {exc}"[:2000],
            )

    def _regenerate_followup(
        self, lesson_id: str, scene_id: str, artifact: Artifact, instruction: str | None
    ) -> None:
        """Follow-up scenes regenerate without touching the lesson's status."""
        if artifact == "scene":
            self.generate_followup(lesson_id, scene_id, instruction=instruction)
            return
        try:
            lesson_row = store.get_lesson(lesson_id)
            problem = ProblemIR.model_validate(lesson_row.problem_ir)
            scope = ScopeIR.model_validate(lesson_row.scope_ir)
            lesson = LessonIR.model_validate(lesson_row.lesson_ir)
            row = store.get_scene(lesson_id, scene_id)
            store.update_scene(
                lesson_id, scene_id, regeneration_count=row.regeneration_count + 1
            )
            self.generate_scene_artifacts(
                lesson_id,
                scene_id,
                problem,
                scope,
                lesson,
                only=_CASCADE[artifact],
                instruction=instruction,
            )
            self.render_scene(lesson_id, scene_id, problem, lesson)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "follow-up regeneration failed",
                extra=fields(lesson_id=lesson_id, scene_id=scene_id),
            )
            store.update_scene(
                lesson_id, scene_id, status="FAILED", error=str(exc)[:2000]
            )

    # ------------------------------------------------------------------ tutor

    def answer_in_chat(
        self, lesson_id: str, scene_id: str, question: str
    ) -> ChatAnswer:
        """Text answer with the whole lesson as context (scope, solution, scene, history). A video answer is
        only generated when the learner asks for it (create_followup)."""
        lesson_row = store.get_lesson(lesson_id)
        if not (
            lesson_row.scope_ir and lesson_row.solution_ir and lesson_row.lesson_ir
        ):
            raise PipelineError("lesson is not ready for questions yet")
        row = store.get_scene(lesson_id, scene_id)  # KeyError -> 404
        if not row.scene_ir:
            raise PipelineError("this scene has no plan yet")
        problem = ProblemIR.model_validate(lesson_row.problem_ir)
        scope = ScopeIR.model_validate(lesson_row.scope_ir)
        history = store.history(lesson_id)
        store.add_message(
            lesson_id, scene_id, "user", question, payload={"kind": "chat"}
        )
        feedback: str | None = None
        answer: ChatAnswer | None = None
        for attempt in range(self.settings.max_stage_retries + 1):
            answer = self._gen(
                lesson_id,
                self.llm.chat_answer,
                problem_text=lesson_row.problem_text,
                scope=scope,
                solution=SolutionIR.model_validate(lesson_row.solution_ir),
                lesson=LessonIR.model_validate(lesson_row.lesson_ir),
                scene=SceneIR.model_validate(row.scene_ir),
                narration=NarrationIR.model_validate(row.narration)
                if row.narration
                else None,
                history=history,
                question=question,
                feedback=feedback,
                scene_id=scene_id,
            )
            text_r = check_texts(
                {"answer": answer.answer},
                problem.language,
                f"chat:{scene_id}",
                scope,
                curriculum=True,
            )
            scope_r = self.scope_validator.validate_chat(answer.answer, scope)
            if (
                text_r.passed and scope_r.passed
            ) or attempt == self.settings.max_stage_retries:
                break
            feedback = _feedback(text_r, scope_r)
        assert answer is not None
        store.add_message(
            lesson_id,
            scene_id,
            "tutor",
            answer.answer,
            payload={
                "kind": "chat",
                "suggest_video": answer.suggest_video,
                "video_reason": answer.video_reason,
                "question": question,
            },
        )
        return answer

    def create_followup(
        self, lesson_id: str, parent_scene_id: str, question: str
    ) -> str:
        """Register a learner question; the answer is generated as a NEW video scene (see generate_followup)."""
        lesson_row = store.get_lesson(lesson_id)
        if not (
            lesson_row.scope_ir and lesson_row.solution_ir and lesson_row.lesson_ir
        ):
            raise PipelineError("lesson is not ready for questions yet")
        parent = store.get_scene(lesson_id, parent_scene_id)  # KeyError -> 404
        if parent.kind != "main" or not parent.scene_ir:
            raise PipelineError(
                "questions can be asked about planned lesson scenes only"
            )
        scene_id = store.add_followup_scene(lesson_id, parent_scene_id, question)
        store.add_message(
            lesson_id,
            parent_scene_id,
            "user",
            question,
            payload={"followup_scene_id": scene_id},
        )
        return scene_id

    def generate_followup(
        self, lesson_id: str, scene_id: str, instruction: str | None = None
    ) -> None:
        """Ask Tutor: plan a follow-up scene answering the question, validate it (scope, ledger, math),
        then generate narration → voice → visuals → Manim and render it as its own video."""
        try:
            with log_stage(log, "followup", lesson_id=lesson_id, scene_id=scene_id):
                self._generate_followup(lesson_id, scene_id, instruction)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "follow-up failed", extra=fields(lesson_id=lesson_id, scene_id=scene_id)
            )
            store.update_scene(
                lesson_id, scene_id, status="FAILED", error=str(exc)[:2000]
            )

    def _generate_followup(
        self, lesson_id: str, scene_id: str, instruction: str | None
    ) -> None:
        lesson_row = store.get_lesson(lesson_id)
        problem = ProblemIR.model_validate(lesson_row.problem_ir)
        scope = ScopeIR.model_validate(lesson_row.scope_ir)
        solution = SolutionIR.model_validate(lesson_row.solution_ir)
        lesson = LessonIR.model_validate(lesson_row.lesson_ir)
        row = store.get_scene(lesson_id, scene_id)
        parent = store.get_scene(lesson_id, row.parent_scene_id)
        parent_scene = SceneIR.model_validate(parent.scene_ir)
        narration = (
            NarrationIR.model_validate(parent.narration) if parent.narration else None
        )
        store.update_scene(lesson_id, scene_id, status="PLANNING", error=None)

        question = (
            row.question
            if not instruction
            else f"{row.question}\n(Additional request: {instruction})"
        )
        feedback: str | None = None
        plan: FollowupPlan | None = None
        for attempt in range(self.settings.max_stage_retries + 1):
            plan = self._gen(
                lesson_id,
                self.llm.plan_followup,
                problem_text=lesson_row.problem_text,
                scope=scope,
                solution=solution,
                lesson=lesson,
                scene=parent_scene,
                narration=narration,
                history=store.history(lesson_id),
                question=question,
                followup_scene_id=scene_id,
                feedback=feedback,
                scene_id=scene_id,
            )
            plan.scene.scene_id = scene_id
            for entry in plan.new_ledger_entries:
                entry.introduced_in = scene_id
            # Validate the follow-up as if it were appended to the lesson.
            extended = copy.deepcopy(lesson)
            extended.concept_ledger.entries.extend(plan.new_ledger_entries)
            extended.scenes.append(plan.scene)
            results = [
                self._validated(
                    lesson_id,
                    self.scope_validator.validate_followup(plan, scope),
                    scene_id,
                ),
                self._validated(
                    lesson_id, self.ledger_validator.validate_ledger(extended), scene_id
                ),
                self._validated(
                    lesson_id,
                    self.ledger_validator.validate_scene(plan.scene, extended),
                    scene_id,
                ),
                self._validated(
                    lesson_id,
                    self.math_validator.validate_scene_state(plan.scene),
                    scene_id,
                ),
            ]
            if all(r.passed for r in results):
                break
            if attempt == self.settings.max_stage_retries:
                raise PipelineError(
                    f"follow-up scene rejected after retries:\n{_feedback(*results)}"
                )
            feedback = _feedback(*results)
        assert plan is not None

        followup = {
            "answer_summary": plan.answer_summary,
            "concepts_used": plan.concepts_used,
            "stays_in_scope": plan.stays_in_scope,
        }
        store.update_scene(
            lesson_id,
            scene_id,
            scene_ir=plan.scene.model_dump(mode="json"),
            title=plan.scene.title,
            followup=followup,
            ledger_extra=[e.model_dump(mode="json") for e in plan.new_ledger_entries],
            # a re-plan invalidates every downstream artifact
            narration=None,
            voiceover=None,
            visual_plan=None,
            manim_code=None,
        )
        store.add_message(
            lesson_id,
            row.parent_scene_id,
            "tutor",
            plan.answer_summary,
            payload={"followup_scene_id": scene_id, **followup},
        )
        self.generate_scene_artifacts(lesson_id, scene_id, problem, scope, lesson)
        self.render_scene(lesson_id, scene_id, problem, lesson)
