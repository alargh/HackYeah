import json

import pytest
from pydantic import ValidationError

from app.schemas import LessonIR, ProblemIR, ScopeIR, SolutionIR
from app.services.gemini.schema import gemini_schema
from tests.fixtures import LESSON_IR, PROBLEM_IR, SCOPE_IR_OPEN, SCOPE_IR_RESTRICTED, solution_ir


def test_problem_ir_parses_demo():
    p = ProblemIR.model_validate(PROBLEM_IR)
    assert p.domain == "discrete_mathematics"
    assert p.goal.kind == "count"
    assert p.enumeration_spec is not None and p.enumeration_spec.items == list("ABCDE")
    assert p.constraints[0].kind == "not_adjacent"


def test_problem_ir_rejects_bad_goal_kind():
    bad = {**PROBLEM_IR, "goal": {**PROBLEM_IR["goal"], "kind": "dance"}}
    with pytest.raises(ValidationError):
        ProblemIR.model_validate(bad)


def test_problem_ir_requires_objects():
    bad = {k: v for k, v in PROBLEM_IR.items() if k != "objects"}
    with pytest.raises(ValidationError):
        ProblemIR.model_validate(bad)


def test_scope_ir_restricted_and_warning():
    s = ScopeIR.model_validate(SCOPE_IR_RESTRICTED)
    assert s.mode == "restricted"
    assert "inclusion_exclusion" in s.forbidden_concepts
    assert s.warning is None
    insufficient = ScopeIR.model_validate(
        {**SCOPE_IR_RESTRICTED, "scope_sufficient": False, "missing_concepts": ["factorial"], "explanation": "need factorials", "why_valid": "it follows from the previous step"}
    )
    assert insufficient.warning is not None
    assert insufficient.warning.missing_concepts == ["factorial"]


def test_scope_ir_open_defaults():
    s = ScopeIR.model_validate(SCOPE_IR_OPEN)
    assert s.allowed_concepts == [] and s.scope_sufficient


def test_solution_ir_structured_steps():
    sol = SolutionIR.model_validate(solution_ir())
    assert [s.id for s in sol.steps] == ["step_1", "step_2", "step_3", "step_4", "step_5"]
    assert sol.steps[3].depends_on == ["step_2", "step_3"]
    assert sol.final_result.value == "72"


def test_solution_ir_requires_final_result():
    bad = {k: v for k, v in solution_ir().items() if k != "final_result"}
    with pytest.raises(ValidationError):
        SolutionIR.model_validate(bad)


def test_lesson_ir_parses():
    lesson = LessonIR.model_validate(LESSON_IR)
    assert len(lesson.scenes) == 4
    assert lesson.concept_ledger.get("[AB]").meaning == "block containing A and B"


@pytest.mark.parametrize("model", [ProblemIR, ScopeIR, SolutionIR, LessonIR])
def test_gemini_schema_is_inlined(model):
    schema = gemini_schema(model)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    assert schema["type"] == "object"
