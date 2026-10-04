import json

import pytest

from app.schemas import ProblemIR
from app.services.gemini import GeminiClient, StageError
from tests.fixtures import PROBLEM_IR, FakeTransport


def test_valid_response_parsed_with_metadata(prompts):
    t = FakeTransport({"problem_analyzer": PROBLEM_IR})
    out = GeminiClient(t, prompts).analyze_problem("x")
    assert isinstance(out.value, ProblemIR)
    assert out.meta.model == "fake-gemini"
    assert out.meta.prompt_name == "problem_analyzer" and out.meta.prompt_version == prompts.get("problem_analyzer").version
    assert out.meta.attempts == 1 and not out.meta.repaired
    # The schema and inputs are sent to the model
    assert "Output JSON schema" in t.calls[0][1]


def test_fenced_json_is_accepted(prompts):
    t = FakeTransport({"problem_analyzer": "```json\n" + json.dumps(PROBLEM_IR) + "\n```"})
    assert GeminiClient(t, prompts).analyze_problem("x").value.domain == "discrete_mathematics"


def test_invalid_output_is_repaired(prompts):
    t = FakeTransport({"problem_analyzer": {"domain": "x"}, "repair_json": PROBLEM_IR})
    out = GeminiClient(t, prompts).analyze_problem("x")
    assert out.meta.repaired and out.meta.attempts == 2
    assert t.count("repair_json") == 1
    assert "validation_error" in t.calls[-1][1]


def test_still_invalid_after_repair_fails_stage(prompts):
    t = FakeTransport({"problem_analyzer": "not json", "repair_json": "still not json"})
    with pytest.raises(StageError) as exc:
        GeminiClient(t, prompts).analyze_problem("x")
    assert exc.value.stage == "analyze_problem"
    assert exc.value.raw_output == "still not json"


def test_prompts_are_versioned(prompts):
    versions = prompts.versions()
    expected = {
        "problem_analyzer", "scope_compiler", "math_reasoner", "lesson_planner", "narration_generator",
        "visual_planner", "manim_generator", "ask_tutor", "repair_json",
    }
    assert expected <= set(versions)
    assert all(v != "0.0.0" for v in versions.values())
