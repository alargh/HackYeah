"""MathValidator: deterministic verification of a SolutionIR.

Checks, in order:
1. every step expression parses and evaluates; claimed values match the evaluation
   (later steps may reference earlier `result_name`s — bound to the *evaluated* values);
2. the final expression evaluates to the claimed final value;
3. the model's own verification checks hold;
4. an independent computation (brute-force enumeration / NetworkX) agrees, when the
   ProblemIR provides a formal spec.
"""

from __future__ import annotations

from typing import Any

import sympy

from app.schemas.lesson import SceneIR
from app.schemas.problem import ProblemIR
from app.schemas.solution import SolutionIR
from app.schemas.validation import ValidationIssue, ValidationResult
from app.services.validation import expressions as ex
from app.services.validation.independent import (
    IndependentCheckError,
    count_arrangements,
    evaluate_geometry,
    evaluate_graph,
)

NAME = "math"


def _parse_value(text: str) -> sympy.Expr | None:
    try:
        return ex.evaluate(text)
    except ex.ExpressionError:
        return None


# Named results a matura-rozszerzona student knows (curriculum / "tablice maturalne"): not shortcuts.
SCHOOL_RESULTS = (
    "multiplication", "addition", "sum_rule", "product_rule", "complement", "division_rule", "pythagor",
    "thales", "talesa", "cosine", "cosinus", "sine", "sinus", "intercept", "inscribed_angle", "central_angle",
    "angle_bisector", "binomial_theorem", "newton", "vieta", "viete", "heron", "total_probability",
    "bayes", "triangle_inequality", "midline", "similar", "congruen", "power_rule", "chain_rule", "derivative",
)


class MathValidator:
    def validate_scene_state(self, scene: SceneIR) -> ValidationResult:
        """Check a scene's own claim `current_expression = current_value` (used for follow-up scenes,
        e.g. a "what if there were 6 people?" scene computing 6! - 2*5!)."""
        issues: list[ValidationIssue] = []
        state = scene.mathematical_state
        details: dict[str, Any] = {}
        if state.current_expression and state.current_value:
            claimed = _parse_value(state.current_value)
            try:
                value = ex.evaluate(state.current_expression)
                details["evaluated"] = ex.to_str(value)
                if claimed is not None and not ex.equal(value, claimed):
                    issues.append(
                        ValidationIssue(
                            code="STATE_MISMATCH",
                            message=f"{state.current_expression} evaluates to {value}, but the scene claims {state.current_value}",
                            location=scene.scene_id,
                        )
                    )
            except ex.ExpressionError as exc:
                # Scene states may be prose-like ("AB or BA"); that is not a math error.
                issues.append(
                    ValidationIssue(
                        code="STATE_UNCHECKED",
                        message=str(exc),
                        severity="warning",
                        location=scene.scene_id,
                    )
                )
        return ValidationResult.build(
            NAME, f"scene:{scene.scene_id}", issues, **details
        )

    def validate(self, problem: ProblemIR, solution: SolutionIR) -> ValidationResult:
        issues: list[ValidationIssue] = []
        names: dict[str, sympy.Expr] = {}
        evaluated_steps: dict[str, str] = {}
        checked = 0
        derived_named_results: set[str] = set()

        for step in solution.steps:
            if not step.explanation.strip() or not step.why_valid.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_REASONING",
                        message="every solution step must explain what is computed and why it is valid",
                        location=step.id,
                    )
                )
            if step.method.startswith("derive_"):
                derived_named_results.add(step.method.removeprefix("derive_").lower())
            lowered = f"{step.method} {step.explanation} {step.why_valid}".lower()
            school_result = any(k in step.method.lower() for k in SCHOOL_RESULTS)
            named_shortcut = not school_result and step.method.endswith(
                ("_theorem", "_lemma", "_rule")
            ) or any(
                phrase in lowered
                for phrase in (
                    "z twierdzenia",
                    "z lematu",
                    "from the theorem",
                    "by the theorem",
                )
            )
            named_key = step.method.rsplit("_", 1)[0].removesuffix("derive").strip("_")
            if named_shortcut and named_key not in derived_named_results:
                issues.append(
                    ValidationIssue(
                        code="NAMED_THEOREM_SHORTCUT",
                        message="derive or verify the named result from elementary cases before using it",
                        location=step.id,
                    )
                )
            if not step.expression:
                continue
            try:
                value = ex.evaluate(step.expression, names)
            except ex.ExpressionError as exc:
                # A step we cannot check is reported, not fatal: what CAN be checked still must agree.
                issues.append(
                    ValidationIssue(
                        code="EXPR_UNPARSEABLE",
                        message=str(exc),
                        severity="warning",
                        location=step.id,
                    )
                )
                continue
            checked += 1
            evaluated_steps[step.id] = ex.to_str(value)
            if step.result_name:
                names[step.result_name] = value
            if step.claimed_value:
                claimed = _parse_value(step.claimed_value)
                if claimed is None:
                    issues.append(
                        ValidationIssue(
                            code="CLAIM_UNPARSEABLE",
                            message=f"claimed value {step.claimed_value!r} is not a number",
                            severity="warning",
                            location=step.id,
                        )
                    )
                elif not ex.equal(value, claimed):
                    issues.append(
                        ValidationIssue(
                            code="STEP_MISMATCH",
                            message=(
                                f"{step.expression} evaluates to {value}, "
                                f"but the step claims {step.claimed_value}"
                                + (
                                    f" (they differ {cx})"
                                    if (cx := ex.counterexample(value, claimed))
                                    else ""
                                )
                            ),
                            location=step.id,
                        )
                    )

        # Final result
        numeric_goal = problem.goal.answer_type in ("integer", "rational", "real")
        final_eval: sympy.Expr | None = None
        try:
            final_eval = ex.evaluate(solution.final_result.expression, names)
            checked += 1
            if numeric_goal and not ex.is_numeric(final_eval):
                issues.append(
                    ValidationIssue(
                        code="FINAL_NOT_NUMERIC",
                        message=f"the goal asks for a number but the final expression is symbolic: {final_eval}",
                        location="final_result",
                    )
                )
        except ex.ExpressionError as exc:
            issues.append(
                ValidationIssue(
                    code="FINAL_UNPARSEABLE",
                    message=str(exc),
                    severity="error" if numeric_goal else "warning",
                    location="final_result",
                )
            )
        final_claim = _parse_value(solution.final_result.value)
        if final_claim is None:
            issues.append(
                ValidationIssue(
                    code="FINAL_VALUE_UNPARSEABLE",
                    message=f"final value {solution.final_result.value!r} is not a number",
                    severity="error" if numeric_goal else "warning",
                    location="final_result",
                )
            )
        elif final_eval is not None and not ex.equal(final_eval, final_claim):
            issues.append(
                ValidationIssue(
                    code="FINAL_MISMATCH",
                    message=(
                        f"final expression {solution.final_result.expression} evaluates to {final_eval}, "
                        f"but the claimed answer is {solution.final_result.value}"
                    ),
                    location="final_result",
                )
            )
        verified = final_eval if final_eval is not None else final_claim

        if (
            problem.goal.answer_type == "integer"
            and isinstance(verified, sympy.Expr)
            and ex.is_numeric(verified)
            and not verified.is_integer
        ):
            issues.append(
                ValidationIssue(
                    code="NOT_INTEGER",
                    message=f"answer {verified} should be an integer",
                    location="final_result",
                )
            )

        # Model-provided verification checks
        for i, check in enumerate(solution.verification.checks):
            try:
                got = ex.evaluate(check.expression, names)
            except ex.ExpressionError as exc:
                issues.append(
                    ValidationIssue(
                        code="CHECK_UNPARSEABLE",
                        message=str(exc),
                        severity="warning",
                        location=f"verification[{i}]",
                    )
                )
                continue
            expected = _parse_value(check.expected_value)
            if expected is not None and not ex.equal(got, expected):
                issues.append(
                    ValidationIssue(
                        code="CHECK_FAILED",
                        message=f"verification '{check.description}': {check.expression} = {got}, expected {check.expected_value}",
                        location=f"verification[{i}]",
                    )
                )

        # Independent computation from the problem formalisation
        independent: list[dict[str, Any]] = []
        if problem.enumeration_spec is not None:
            try:
                count = count_arrangements(problem.enumeration_spec)
                matches = verified is not None and ex.equal(
                    sympy.Integer(count), verified
                )
                independent.append(
                    {
                        "method": "brute_force_enumeration",
                        "value": str(count),
                        "matches": matches,
                    }
                )
                if not matches:
                    issues.append(
                        ValidationIssue(
                            code="INDEPENDENT_MISMATCH",
                            message=(
                                f"brute-force enumeration of all arrangements gives {count}, "
                                f"but the solution's answer is {verified}"
                            ),
                            location="final_result",
                        )
                    )
            except IndependentCheckError as exc:
                independent.append(
                    {"method": "brute_force_enumeration", "error": str(exc)}
                )
                issues.append(
                    ValidationIssue(
                        code="ENUMERATION_SKIPPED", message=str(exc), severity="warning"
                    )
                )
        if problem.graph_spec is not None:
            try:
                value = evaluate_graph(problem.graph_spec)
                expected = _parse_value(value)
                if expected is not None and verified is not None:
                    matches = ex.equal(expected, verified)
                else:
                    matches = (
                        value.lower() == solution.final_result.value.strip().lower()
                    )
                independent.append(
                    {
                        "method": f"networkx:{problem.graph_spec.query}",
                        "value": value,
                        "matches": matches,
                    }
                )
                if not matches:
                    issues.append(
                        ValidationIssue(
                            code="INDEPENDENT_MISMATCH",
                            message=f"NetworkX computes {value}, but the solution's answer is {solution.final_result.value}",
                            location="final_result",
                        )
                    )
            except (
                IndependentCheckError,
                Exception,
            ) as exc:  # networkx raises various errors
                independent.append({"method": "networkx", "error": str(exc)})
                issues.append(
                    ValidationIssue(
                        code="GRAPH_CHECK_SKIPPED", message=str(exc), severity="warning"
                    )
                )

        if problem.geometry_spec is not None:
            spec = problem.geometry_spec
            try:
                exacts = evaluate_geometry(spec)
                queries = [spec.query, *spec.also]

                def same(exact, got, q):
                    return ex.equal(exact, got) or (
                        q.startswith("angle")
                        and spec.angle_function == "none"
                        and ex.equal(exact * 180 / sympy.pi, got)
                    )  # angles may be answered in degrees

                answers = (
                    list(verified)
                    if isinstance(verified, (sympy.Tuple, tuple))
                    else [verified]
                )
                positional = (
                    verified is not None
                    and len(answers) >= 1
                    and all(same(e, a, q) for e, a, q in zip(exacts, answers, queries))
                )
                # The spec is the analyser's formalisation and may cover only part of a multi-part answer
                # (e.g. it only knows the cylinder of "a ball inscribed in a cylinder"): then every value
                # it CAN compute must appear somewhere in the answer, in any order.
                contained = verified is not None and all(
                    any(same(e, a, q) for a in answers) for e, q in zip(exacts, queries)
                )
                matches = positional or contained
                shown = ", ".join(str(e) for e in exacts)
                independent.append(
                    {
                        "method": f"exact_geometry:{'+'.join(queries)}",
                        "value": shown,
                        "matches": matches,
                    }
                )
                if not matches:
                    issues.append(
                        ValidationIssue(
                            code="INDEPENDENT_MISMATCH",
                            message=f"exact geometry gives {shown}, but the solution's answer is {verified}",
                            location="final_result",
                        )
                    )
            except IndependentCheckError as exc:
                independent.append({"method": "exact_geometry", "error": str(exc)})
                issues.append(
                    ValidationIssue(
                        code="GEOMETRY_CHECK_SKIPPED",
                        message=str(exc),
                        severity="warning",
                    )
                )

        if checked == 0 and not any(c.get("matches") for c in independent):
            issues.append(
                ValidationIssue(
                    code="UNVERIFIED",
                    message="no expression could be checked deterministically",
                    severity="warning",
                )
            )

        return ValidationResult.build(
            NAME,
            "solution",
            issues,
            evaluated_steps=evaluated_steps,
            final_evaluated=ex.to_str(verified) if verified is not None else None,
            independent_checks=independent,
        )
