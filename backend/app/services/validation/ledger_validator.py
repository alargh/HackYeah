"""LedgerValidator: notation consistency across scenes (LLM2Manim-style symbol ledger)."""

from __future__ import annotations

from app.schemas.lesson import LessonIR, SceneIR
from app.schemas.validation import ValidationIssue, ValidationResult

NAME = "ledger"


def _norm_meaning(m: str) -> str:
    return " ".join(m.lower().split()).rstrip(".")


class LedgerValidator:
    def validate_ledger(self, lesson: LessonIR) -> ValidationResult:
        """Global checks: duplicate scene ids, conflicting ledger entries."""
        issues: list[ValidationIssue] = []
        ids = [s.scene_id for s in lesson.scenes]
        for sid in {i for i in ids if ids.count(i) > 1}:
            issues.append(ValidationIssue(code="DUPLICATE_SCENE_ID", message=f"scene id '{sid}' is used twice"))
        if not lesson.scenes:
            issues.append(ValidationIssue(code="NO_SCENES", message="lesson has no scenes"))

        meanings: dict[str, str] = {}
        for entry in lesson.concept_ledger.entries:
            prev = meanings.get(entry.symbol)
            if prev is not None and _norm_meaning(prev) != _norm_meaning(entry.meaning):
                issues.append(
                    ValidationIssue(
                        code="LEDGER_CONFLICT",
                        message=f"symbol '{entry.symbol}' defined as both '{prev}' and '{entry.meaning}'",
                    )
                )
            meanings.setdefault(entry.symbol, entry.meaning)
            if entry.introduced_in not in ids:
                issues.append(
                    ValidationIssue(
                        code="LEDGER_UNKNOWN_SCENE",
                        message=f"symbol '{entry.symbol}' introduced in unknown scene '{entry.introduced_in}'",
                        severity="warning",
                    )
                )
        return ValidationResult.build(NAME, "ledger", issues)

    def validate_scene(self, scene: SceneIR, lesson: LessonIR) -> ValidationResult:
        """Checks for a single scene against the ledger and scene order."""
        issues: list[ValidationIssue] = []
        ledger = lesson.concept_ledger
        order = {s.scene_id: i for i, s in enumerate(lesson.scenes)}
        my_idx = order.get(scene.scene_id, len(order))

        if not scene.learning_goal.strip():
            issues.append(ValidationIssue(code="NO_LEARNING_GOAL", message="scene has no learning goal"))

        for sym in scene.introduces:
            entry = ledger.get(sym)
            if entry is None:
                issues.append(
                    ValidationIssue(code="LEDGER_MISSING", message=f"introduces '{sym}' which is not in the ledger")
                )
            elif entry.introduced_in != scene.scene_id:
                issues.append(
                    ValidationIssue(
                        code="SYMBOL_REDEFINED",
                        message=(
                            f"re-introduces '{sym}', already introduced in {entry.introduced_in} "
                            f"as '{entry.meaning}'"
                        ),
                    )
                )

        for sym in scene.uses:
            entry = ledger.get(sym)
            if entry is None:
                issues.append(
                    ValidationIssue(code="LEDGER_UNKNOWN_SYMBOL", message=f"uses '{sym}' which is not in the ledger")
                )
                continue
            intro_idx = order.get(entry.introduced_in)
            if intro_idx is not None and intro_idx > my_idx:
                issues.append(
                    ValidationIssue(
                        code="USED_BEFORE_INTRODUCED",
                        message=f"uses '{sym}' before it is introduced in {entry.introduced_in}",
                    )
                )

        for obj in scene.visual_objects:
            if obj.ledger_symbol and ledger.get(obj.ledger_symbol) is None:
                issues.append(
                    ValidationIssue(
                        code="LEDGER_UNKNOWN_SYMBOL",
                        message=f"visual object '{obj.id}' depicts unknown symbol '{obj.ledger_symbol}'",
                    )
                )

        for dep in scene.dependencies:
            if dep not in order:
                issues.append(ValidationIssue(code="UNKNOWN_DEPENDENCY", message=f"depends on unknown scene '{dep}'"))
            elif order[dep] >= my_idx:
                issues.append(
                    ValidationIssue(code="FORWARD_DEPENDENCY", message=f"depends on later scene '{dep}'")
                )

        return ValidationResult.build(NAME, f"scene:{scene.scene_id}", issues)
