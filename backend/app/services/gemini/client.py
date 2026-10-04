"""GeminiClient: the structured, stage-specific interface to the runtime mathematical AI.

Each public method:
  * loads its versioned prompt from prompts/,
  * sends the relevant IRs as JSON plus the output JSON schema,
  * validates the response with Pydantic,
  * on invalid output retries once with prompts/repair_json.md,
  * returns the parsed model together with generation metadata
    (model, prompt name/version, attempts, timing) for persistence.

It depends on an `LLMTransport`, never on the Gemini SDK directly, so it is replaceable
(tests inject a fake transport).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.logging import fields, get_logger
from app.schemas.generation import ChatAnswer, FollowupPlan, ManimCode, NarrationIR, VisualPlan
from app.schemas.lesson import ConceptLedger, LessonIR, SceneIR
from app.schemas.problem import ProblemIR
from app.schemas.scope import ScopeIR
from app.schemas.solution import SolutionIR
from app.services.gemini.schema import gemini_schema
from app.services.gemini.transport import LLMTransport, TransportError
from app.services.prompts import PromptStore

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class GenerationMeta:
    stage: str
    prompt_name: str
    prompt_version: str
    model: str
    started_at: datetime
    duration_ms: int = 0
    attempts: int = 0
    repaired: bool = False


@dataclass
class Generated(Generic[T]):
    value: T
    meta: GenerationMeta


@dataclass
class StageError(RuntimeError):
    stage: str
    message: str
    meta: GenerationMeta | None = None
    raw_output: str | None = None
    details: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{self.stage}] {self.message}"


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = _FENCE.sub("", s).strip()
    if not s.startswith("{"):
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            s = s[start : end + 1]
    return s


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    return obj


class GeminiClient:
    def __init__(self, transport: LLMTransport, prompts: PromptStore, max_repairs: int = 1):
        self.transport = transport
        self.prompts = prompts
        self.max_repairs = max_repairs

    @property
    def model_name(self) -> str:
        return self.transport.model_name

    # ------------------------------------------------------------------ core

    def _render_user(self, inputs: dict[str, Any], schema: dict[str, Any]) -> str:
        parts = ["# Inputs"]
        for key, value in inputs.items():
            if value is None:
                continue
            parts.append(f"## {key}")
            if isinstance(value, str):
                parts.append(value)
            else:
                parts.append("```json\n" + json.dumps(_dump(value), ensure_ascii=False, indent=1) + "\n```")
        parts.append("# Output JSON schema")
        parts.append("```json\n" + json.dumps(schema, ensure_ascii=False) + "\n```")
        parts.append("Return ONLY one JSON object that validates against this schema. No prose, no markdown.")
        return "\n\n".join(parts)

    def call(self, stage: str, prompt_name: str, inputs: dict[str, Any], out: type[T], ctx: dict[str, Any] | None = None) -> Generated[T]:
        prompt = self.prompts.get(prompt_name)
        schema = gemini_schema(out)
        meta = GenerationMeta(
            stage=stage,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            model=self.model_name,
            started_at=datetime.now(timezone.utc),
        )
        t0 = time.perf_counter()
        user = self._render_user(inputs, schema)
        raw: str | None = None
        error: str = ""
        try:
            for attempt in range(self.max_repairs + 1):
                meta.attempts = attempt + 1
                if attempt == 0:
                    raw = self.transport.generate(system=prompt.body, user=user, json_schema=schema)
                else:
                    repair = self.prompts.get("repair_json")
                    meta.repaired = True
                    raw = self.transport.generate(
                        system=repair.body,
                        user=self._render_user(
                            {
                                "original_task": prompt.body[:4000],
                                "invalid_output": raw or "",
                                "validation_error": error,
                            },
                            schema,
                        ),
                        json_schema=schema,
                    )
                try:
                    value = out.model_validate_json(_extract_json(raw))
                    meta.duration_ms = round((time.perf_counter() - t0) * 1000)
                    log.info(
                        "llm generation ok",
                        extra=fields(
                            stage=stage,
                            model=meta.model,
                            prompt=meta.prompt_name,
                            prompt_version=meta.prompt_version,
                            attempts=meta.attempts,
                            duration_ms=meta.duration_ms,
                            **(ctx or {}),
                        ),
                    )
                    return Generated(value=value, meta=meta)
                except ValidationError as exc:
                    error = str(exc)[:3000]
                except ValueError as exc:  # JSON decode problems
                    error = f"invalid JSON: {exc}"[:3000]
                log.warning(
                    "llm output invalid",
                    extra=fields(stage=stage, attempt=meta.attempts, error=error[:500], **(ctx or {})),
                )
        except TransportError as exc:
            meta.duration_ms = round((time.perf_counter() - t0) * 1000)
            raise StageError(stage, str(exc), meta=meta) from exc
        meta.duration_ms = round((time.perf_counter() - t0) * 1000)
        raise StageError(
            stage,
            f"model output failed schema validation after {meta.attempts} attempt(s): {error[:800]}",
            meta=meta,
            raw_output=raw,
        )

    # ------------------------------------------------------------ pipeline API

    def analyze_problem(self, problem_text: str, ctx: dict[str, Any] | None = None) -> Generated[ProblemIR]:
        return self.call("analyze_problem", "problem_analyzer", {"problem_text": problem_text}, ProblemIR, ctx)

    def compile_scope(self, problem: ProblemIR, scope_text: str | None, ctx: dict[str, Any] | None = None) -> Generated[ScopeIR]:
        return self.call(
            "compile_scope",
            "scope_compiler",
            {"problem_ir": problem, "user_scope": scope_text or "(none — the user did not restrict the scope)"},
            ScopeIR,
            ctx,
        )

    def reason_about_problem(
        self,
        problem: ProblemIR,
        scope: ScopeIR,
        feedback: str | None = None,
        previous: SolutionIR | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[SolutionIR]:
        return self.call(
            "reason",
            "math_reasoner",
            {
                "problem_ir": problem,
                "scope_ir": scope,
                "previous_solution": previous,
                "validator_feedback": feedback,
            },
            SolutionIR,
            ctx,
        )

    def create_lesson_plan(
        self,
        problem: ProblemIR,
        scope: ScopeIR,
        solution: SolutionIR,
        feedback: str | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[LessonIR]:
        return self.call(
            "plan_lesson",
            "lesson_planner",
            {"problem_ir": problem, "scope_ir": scope, "solution_ir": solution, "validator_feedback": feedback},
            LessonIR,
            ctx,
        )

    def regenerate_scene(
        self,
        problem: ProblemIR,
        scope: ScopeIR,
        solution: SolutionIR,
        lesson: LessonIR,
        scene: SceneIR,
        feedback: str,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[SceneIR]:
        outline = [{"scene_id": s.scene_id, "title": s.title, "learning_goal": s.learning_goal} for s in lesson.scenes]
        return self.call(
            "regenerate_scene",
            "lesson_planner",
            {
                "mode": "REGENERATE ONE SCENE. Return a single SceneIR object (not a LessonIR). "
                "Keep the same scene_id and keep consistent with the concept ledger.",
                "problem_ir": problem,
                "scope_ir": scope,
                "solution_ir": solution,
                "lesson_outline": outline,
                "concept_ledger": lesson.concept_ledger,
                "scene_to_regenerate": scene,
                "validator_feedback": feedback,
            },
            SceneIR,
            ctx,
        )

    def generate_narration(
        self,
        scene: SceneIR,
        ledger: ConceptLedger,
        scope: ScopeIR,
        lesson_context: dict[str, Any],
        feedback: str | None = None,
        previous: NarrationIR | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[NarrationIR]:
        return self.call(
            "narration",
            "narration_generator",
            {
                "lesson_context": lesson_context,
                "scene_ir": scene,
                "concept_ledger": ledger,
                "scope_ir": scope,
                "previous_narration": previous,
                "validator_feedback": feedback,
            },
            NarrationIR,
            ctx,
        )

    def generate_visual_plan(
        self,
        scene: SceneIR,
        ledger: ConceptLedger,
        narration: NarrationIR,
        capabilities: dict[str, Any] | None = None,
        feedback: str | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[VisualPlan]:
        return self.call(
            "visual_plan",
            "visual_planner",
            {
                "visual_capabilities": capabilities,
                "scene_ir": scene,
                "concept_ledger": ledger,
                "narration_ir": narration,
                "validator_feedback": feedback,
            },
            VisualPlan,
            ctx,
        )

    def generate_manim_code(
        self,
        scene: SceneIR,
        ledger: ConceptLedger,
        narration: NarrationIR,
        visual_plan: VisualPlan,
        class_name: str,
        feedback: str | None = None,
        previous: ManimCode | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[ManimCode]:
        return self.call(
            "manim_code",
            "manim_generator",
            {
                "required_class_name": class_name,
                "scene_ir": scene,
                "concept_ledger": ledger,
                "narration_ir": narration,
                "visual_plan": visual_plan,
                "previous_code": previous.code if previous else None,
                "error_feedback": feedback,
            },
            ManimCode,
            ctx,
        )

    def chat_answer(
        self,
        *,
        problem_text: str,
        scope: ScopeIR,
        solution: SolutionIR,
        lesson: LessonIR,
        scene: SceneIR,
        narration: NarrationIR | None,
        history: list[dict[str, str]],
        question: str,
        feedback: str | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[ChatAnswer]:
        """Answer a learner question in chat text, with the full lesson context."""
        return self.call(
            "chat",
            "chat_tutor",
            {
                "original_problem": problem_text,
                "scope_ir": scope,
                "solution_ir": solution,
                "lesson_outline": [{"scene_id": s.scene_id, "title": s.title, "learning_goal": s.learning_goal} for s in lesson.scenes],
                "current_scene": scene,
                "current_scene_narration": narration,
                "concept_ledger": lesson.concept_ledger,
                "conversation_history": history,
                "validator_feedback": feedback,
                "question": question,
            },
            ChatAnswer,
            ctx,
        )

    def plan_followup(
        self,
        *,
        problem_text: str,
        scope: ScopeIR,
        solution: SolutionIR,
        lesson: LessonIR,
        scene: SceneIR,
        narration: NarrationIR | None,
        history: list[dict[str, str]],
        question: str,
        followup_scene_id: str,
        feedback: str | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Generated[FollowupPlan]:
        """Answer a learner question with a NEW scene (rendered as a video), not with chat text."""
        return self.call(
            "ask_tutor",
            "ask_tutor",
            {
                "required_scene_id": followup_scene_id,
                "original_problem": problem_text,
                "scope_ir": scope,
                "solution_ir": solution,
                "lesson_ir": {
                    "title": lesson.title,
                    "learning_objectives": lesson.learning_objectives,
                    "scenes": [{"scene_id": s.scene_id, "title": s.title, "learning_goal": s.learning_goal} for s in lesson.scenes],
                },
                "current_scene": scene,
                "current_scene_narration": narration,
                "concept_ledger": lesson.concept_ledger,
                "conversation_history": history,
                "validator_feedback": feedback,
                "question": question,
            },
            FollowupPlan,
            ctx,
        )
