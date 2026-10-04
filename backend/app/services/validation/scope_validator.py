"""ScopeValidator: detects use of forbidden / non-allowed concepts and methods.

Structured metadata is checked first (concept/method tags). Prose is then scanned with a
lexicon for concepts that are forbidden — or, in a restricted scope, simply not allowed.
"""

from __future__ import annotations

from app.schemas.generation import FollowupPlan, NarrationIR
from app.schemas.lesson import SceneIR
from app.schemas.scope import ScopeIR
from app.schemas.solution import SolutionIR
from app.schemas.validation import ValidationIssue, ValidationResult
from app.services.validation.concepts import ELEMENTARY, LEXICON, mentioned_concepts, normalize_all, normalize_concept

NAME = "scope"

# Named results a learner cannot be expected to know: used without being built up first they are a black box.
SHORTCUTS: dict[str, tuple[str, ...]] = {
    "stirling": ("stirling",),
    "bell_number": ("bell_number", "bell number", "liczby bella", "liczba bella"),
    "catalan": ("catalan",),
    "inclusion_exclusion": ("inclusion_exclusion", "inclusion-exclusion", "inclusion exclusion", "włączeń i wyłączeń", "wlaczen i wylaczen"),
    "multinomial": ("multinomial", "wielomianow"),
    "derangement": ("derangement", "subfactorial", "nieporządk", "podsilni"),
    "stars_and_bars": ("stars_and_bars", "stars and bars", "gwiazdki i kreski"),
    "burnside": ("burnside",),
    "pappus": ("pappus", "guldin"),
}


def shortcuts_in(text: str) -> set[str]:
    low = text.lower()
    return {name for name, keys in SHORTCUTS.items() if any(k in low for k in keys)}


class ScopeValidator:
    def _sets(self, scope: ScopeIR) -> tuple[set[str], set[str]]:
        forbidden = normalize_all(scope.forbidden_concepts) | normalize_all(scope.forbidden_methods)
        allowed = (
            normalize_all(scope.allowed_concepts)
            | normalize_all(scope.allowed_methods)
            | normalize_all(scope.required_concepts)
            | normalize_all([m.method for m in scope.method_justifications])
            | set(ELEMENTARY)
        )
        return forbidden, allowed - forbidden

    def _check_tags(
        self, tags: list[str], scope: ScopeIR, location: str, issues: list[ValidationIssue]
    ) -> None:
        forbidden, allowed = self._sets(scope)
        for raw in tags:
            tag = normalize_concept(raw)
            if not tag:
                continue
            if tag in forbidden:
                issues.append(
                    ValidationIssue(
                        code="SCOPE_FORBIDDEN",
                        message=f"uses forbidden concept/method '{raw}'",
                        location=location,
                    )
                )
            elif scope.mode == "restricted" and tag not in allowed:
                issues.append(
                    ValidationIssue(
                        code="SCOPE_NOT_ALLOWED",
                        message=(
                            f"uses '{raw}', which is not in the allowed scope "
                            f"({', '.join(sorted(allowed - set(ELEMENTARY)))})"
                        ),
                        location=location,
                    )
                )

    def _check_text(
        self,
        text: str,
        scope: ScopeIR,
        location: str,
        issues: list[ValidationIssue],
        severity: str = "error",
    ) -> None:
        forbidden, allowed = self._sets(scope)
        watch = set(forbidden)
        if scope.mode == "restricted":
            watch |= {c for c in LEXICON if c not in allowed}
        for concept in sorted(mentioned_concepts(text, watch)):
            issues.append(
                ValidationIssue(
                    code="SCOPE_MENTION",
                    message=f"text refers to '{concept}', which is outside the allowed scope",
                    severity=severity,  # type: ignore[arg-type]
                    location=location,
                )
            )

    def _check_shortcuts(self, solution: SolutionIR, scope: ScopeIR, issues: list[ValidationIssue]) -> None:
        """Teach from the ground up: a named result (Stirling numbers, inclusion-exclusion, Pappus, ...) may
        only be used after a `derive_<name>` step builds it from basic counting / geometry, unless the
        learner put it in their scope."""
        _, allowed = self._sets(scope)
        derived: set[str] = set()
        for step in solution.steps:
            tags = " ".join([step.method, *step.concepts_used])
            if step.method.lower().startswith(("derive", "build", "explain")):
                derived |= shortcuts_in(f"{tags} {step.goal}")
                continue
            used = shortcuts_in(f"{tags} {step.goal} {step.explanation} {step.why_valid}")
            for name in sorted(used - derived):
                if name in allowed or any(name in a for a in allowed):
                    continue
                issues.append(
                    ValidationIssue(
                        code="SHORTCUT_NOT_EXPLAINED",
                        message=(
                            f"step uses the named result '{name}' as a black box. The learner gave no context, so "
                            f"explain from the basics: either solve with elementary reasoning only, or add an earlier "
                            f"step with method 'derive_{name}' that builds the idea from scratch on a small concrete case "
                            f"(why it counts / measures exactly this), then use it"
                        ),
                        location=step.id,
                    )
                )

    # --- public API -------------------------------------------------------------

    def validate_solution(self, solution: SolutionIR, scope: ScopeIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        self._check_tags([solution.selected_method, *solution.selected_method_concepts], scope, "selected_method", issues)
        self._check_tags(solution.concepts_used, scope, "concepts_used", issues)
        for step in solution.steps:
            self._check_tags([step.method, *step.concepts_used], scope, step.id, issues)
            self._check_text(f"{step.goal} {step.explanation} {step.why_valid}", scope, step.id, issues)
        self._check_text(solution.final_result.statement, scope, "final_result", issues)
        self._check_shortcuts(solution, scope, issues)
        # Candidate methods may legitimately mention out-of-scope methods, but must flag them.
        forbidden, allowed = self._sets(scope)
        for cand in solution.candidate_methods:
            name = normalize_concept(cand.name)
            out = name in forbidden or (scope.mode == "restricted" and name not in allowed)
            if cand.in_scope and out:
                issues.append(
                    ValidationIssue(
                        code="SCOPE_MISLABELED",
                        message=f"candidate method '{cand.name}' is marked in_scope but is not allowed",
                        severity="warning",
                        location="candidate_methods",
                    )
                )
        return ValidationResult.build(NAME, "solution", _dedupe(issues))

    def validate_chat(self, text: str, scope: ScopeIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        self._check_text(text, scope, "answer", issues)
        return ValidationResult.build(NAME, "chat", _dedupe(issues))

    def validate_scene(self, scene: SceneIR, scope: ScopeIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        self._check_tags(scene.concepts, scope, scene.scene_id, issues)
        self._check_text(
            " ".join([scene.title, scene.learning_goal, *scene.narration_plan, *scene.mathematical_state.known_facts]),
            scope,
            scene.scene_id,
            issues,
        )
        return ValidationResult.build(NAME, f"scene:{scene.scene_id}", _dedupe(issues))

    def validate_narration(self, narration: NarrationIR, scope: ScopeIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        for seg in narration.segments:
            loc = f"{narration.scene_id}/{seg.id}"
            self._check_tags(seg.concepts, scope, loc, issues)
            self._check_text(seg.text, scope, loc, issues)
        return ValidationResult.build(NAME, f"narration:{narration.scene_id}", _dedupe(issues))

    def validate_followup(self, plan: FollowupPlan, scope: ScopeIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        sid = plan.scene.scene_id
        self._check_tags([*plan.concepts_used, *plan.scene.concepts], scope, sid, issues)
        self._check_text(
            " ".join([plan.scene.title, plan.scene.learning_goal, *plan.scene.narration_plan]), scope, sid, issues
        )
        # The summary may *name* an out-of-scope idea while declining to use it, so prose there is a warning.
        self._check_text(plan.answer_summary, scope, f"{sid}/answer_summary", issues, severity="warning")
        return ValidationResult.build(NAME, f"followup:{sid}", _dedupe(issues))


def _dedupe(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    seen: set[tuple[str, str, str | None]] = set()
    out: list[ValidationIssue] = []
    for i in issues:
        key = (i.code, i.message, i.location)
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out
