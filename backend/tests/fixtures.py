"""Mocked Gemini responses for the demo problem (test-only; never used by the application)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.services.gemini.transport import TransportError

DEMO_PROBLEM = (
    "Danych jest 5 różnych osób: A,B,C,D,E. Osoby te ustawiają się w jednym szeregu. "
    "Ile istnieje różnych sposobów ustawienia tych osób, jeśli osoby A i B nie mogą stać obok siebie?"
)
DEMO_SCOPE = "Use only permutations, factorials and the multiplication rule."

PROBLEM_IR: dict[str, Any] = {
    "original_text": DEMO_PROBLEM,
    "language": "pl",
    "domain": "discrete_mathematics",
    "subdomain": "combinatorics",
    "problem_type": "permutation_with_constraint",
    "summary": "Count linear arrangements of 5 distinct people where A and B are not adjacent.",
    "objects": [
        {
            "id": p,
            "kind": "person",
            "description": f"person {p}",
            "properties": ["distinct"],
        }
        for p in "ABCDE"
    ],
    "relations": [
        {
            "id": "r1",
            "kind": "arrangement_of",
            "subjects": list("ABCDE"),
            "description": "people stand in one row",
        }
    ],
    "constraints": [
        {
            "id": "c1",
            "kind": "not_adjacent",
            "subjects": ["A", "B"],
            "description": "A and B may not stand next to each other",
        }
    ],
    "goal": {
        "kind": "count",
        "description": "number of valid arrangements",
        "target_quantity": "number of arrangements with A and B not adjacent",
        "answer_type": "integer",
    },
    "assumptions": ["people are distinguishable", "order in the row matters"],
    "relevant_concepts": ["permutation", "factorial", "multiplication_rule"],
    "enumeration_spec": {
        "kind": "permutation",
        "items": list("ABCDE"),
        "constraints": [{"type": "not_adjacent", "items": ["A", "B"]}],
    },
}

SCOPE_IR_RESTRICTED: dict[str, Any] = {
    "user_scope_text": DEMO_SCOPE,
    "mode": "restricted",
    "allowed_concepts": ["permutation", "factorial", "multiplication_rule"],
    "forbidden_concepts": ["inclusion_exclusion", "combination"],
    "allowed_methods": ["block_method", "complement_counting"],
    "forbidden_methods": ["inclusion_exclusion"],
    "method_justifications": [
        {
            "method": "block_method",
            "built_from": ["permutation", "multiplication_rule"],
            "justification": "glue A and B",
        },
        {
            "method": "complement_counting",
            "built_from": ["subtraction"],
            "justification": "all minus bad",
        },
    ],
    "required_concepts": [],
    "assumptions": [],
    "scope_sufficient": True,
    "missing_concepts": [],
    "explanation": "Scope is sufficient.", "why_valid": "it follows from the previous step",
}

SCOPE_IR_OPEN: dict[str, Any] = {"mode": "open", "scope_sufficient": True}


def solution_ir(
    final_value: str = "72",
    method: str = "complement_counting",
    extra_concepts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "selected_method": method,
        "selected_method_concepts": ["permutation", "factorial", "multiplication_rule"],
        "candidate_methods": [
            {
                "name": "complement_counting",
                "description": "all minus forbidden",
                "concepts": ["permutation"],
                "in_scope": True,
                "reason": "uses only allowed concepts",
            },
            {
                "name": "inclusion_exclusion",
                "description": "PIE",
                "concepts": ["inclusion_exclusion"],
                "in_scope": False,
                "reason": "forbidden",
            },
        ],
        "assumptions": ["people are distinguishable"],
        "steps": [
            {
                "id": "step_1",
                "goal": "Count all arrangements",
                "method": "permutation",
                "expression": "5!",
                "result_name": "total",
                "claimed_value": "120",
                "explanation": "5 people in a row", "why_valid": "it follows from the previous step",
                "why_valid": "permutations of 5 objects",
                "concepts_used": ["permutation", "factorial"],
            },
            {
                "id": "step_2",
                "goal": "Arrange the block with C, D, E",
                "method": "block_method",
                "expression": "factorial(4)",
                "result_name": "block_arrangements",
                "claimed_value": "24",
                "explanation": "treat [AB] as one object", "why_valid": "it follows from the previous step",
                "why_valid": "4 objects",
                "concepts_used": ["block_method", "factorial"],
            },
            {
                "id": "step_3",
                "goal": "Order inside the block",
                "method": "permutation",
                "expression": "2!",
                "result_name": "inside",
                "claimed_value": "2",
                "explanation": "AB or BA", "why_valid": "it follows from the previous step",
                "why_valid": "2 people",
                "concepts_used": ["permutation"],
            },
            {
                "id": "step_4",
                "goal": "Count arrangements where A and B are adjacent",
                "method": "multiplication_rule",
                "expression": "block_arrangements * inside",
                "result_name": "forbidden",
                "claimed_value": "48",
                "explanation": "2 * 4!", "why_valid": "it follows from the previous step",
                "why_valid": "independent choices multiply",
                "concepts_used": ["multiplication_rule"] + (extra_concepts or []),
                "depends_on": ["step_2", "step_3"],
            },
            {
                "id": "step_5",
                "goal": "Subtract",
                "method": "complement_counting",
                "expression": "total - forbidden",
                "result_name": "valid",
                "claimed_value": final_value,
                "explanation": "120 - 48", "why_valid": "it follows from the previous step",
                "why_valid": "every arrangement is either valid or forbidden",
                "concepts_used": ["complement_counting", "subtraction"],
                "depends_on": ["step_1", "step_4"],
            },
        ],
        "final_result": {
            "expression": "5! - 2*4!",
            "value": final_value,
            "statement": f"Jest {final_value} ustawień.",
        },
        "verification": {
            "strategy": "place C, D, E first, then put A and B into distinct gaps",
            "checks": [
                {
                    "description": "gap method",
                    "expression": "3! * 4 * 3",
                    "expected_value": "72",
                }
            ],
        },
        "concepts_used": [
            "permutation",
            "factorial",
            "multiplication_rule",
            "block_method",
            "complement_counting",
        ]
        + (extra_concepts or []),
        "scope_notes": "Only permutations, factorials and the multiplication rule are used.",
    }


def _scene(
    sid: str,
    title: str,
    intro: list[str],
    uses: list[str],
    deps: list[str],
    concepts: list[str],
    value: str,
) -> dict[str, Any]:
    return {
        "scene_id": sid,
        "title": title,
        "learning_goal": f"Understand: {title}",
        "concepts": concepts,
        "introduces": intro,
        "uses": uses,
        "mathematical_state": {
            "known_facts": [title],
            "current_expression": None,
            "current_value": value,
        },
        "visual_objects": [{"id": "formula", "kind": "math", "content": value}],
        "narration_plan": [title],
        "visual_plan": [title],
        "duration_estimate": 12,
        "dependencies": deps,
    }


LESSON_IR: dict[str, Any] = {
    "title": "A i B nie obok siebie",
    "summary": "Count all, subtract the forbidden ones.",
    "learning_objectives": ["count arrangements", "use the block method"],
    "prerequisites": ["factorial"],
    "concept_ledger": {
        "entries": [
            {
                "symbol": "A",
                "meaning": "person A",
                "kind": "object",
                "introduced_in": "scene_1",
            },
            {
                "symbol": "B",
                "meaning": "person B",
                "kind": "object",
                "introduced_in": "scene_1",
            },
            {
                "symbol": "5!",
                "meaning": "all arrangements of 5 people",
                "kind": "quantity",
                "introduced_in": "scene_1",
                "value": "120",
            },
            {
                "symbol": "[AB]",
                "meaning": "block containing A and B",
                "kind": "object",
                "introduced_in": "scene_2",
            },
            {
                "symbol": "4!",
                "meaning": "arrangements of four objects",
                "kind": "quantity",
                "introduced_in": "scene_2",
                "value": "24",
            },
            {
                "symbol": "2*4!",
                "meaning": "arrangements with A and B adjacent",
                "kind": "quantity",
                "introduced_in": "scene_3",
                "value": "48",
            },
        ]
    },
    "scenes": [
        _scene(
            "scene_1",
            "All arrangements",
            ["A", "B", "5!"],
            ["A", "B", "5!"],
            [],
            ["permutation", "factorial"],
            "120",
        ),
        _scene(
            "scene_2",
            "Glue A and B",
            ["[AB]", "4!"],
            ["A", "B", "[AB]", "4!"],
            ["scene_1"],
            ["block_method", "factorial"],
            "24",
        ),
        _scene(
            "scene_3",
            "Two orders in the block",
            ["2*4!"],
            ["[AB]", "4!", "2*4!"],
            ["scene_2"],
            ["permutation", "multiplication_rule"],
            "48",
        ),
        _scene(
            "scene_4",
            "Subtract",
            [],
            ["5!", "2*4!"],
            ["scene_1", "scene_3"],
            ["complement_counting", "subtraction"],
            "72",
        ),
    ],
}

SCENE_TEX = {
    "scene_1": r"5! = 120",
    "scene_2": r"4! = 24",
    "scene_3": r"2 \cdot 4! = 48",
    "scene_4": r"120 - 48 = 72",
}


def scene_id_of(user: str) -> str:
    m = re.search(r'"scene_id":\s*"([^"]+)"', user)
    return m.group(1) if m else "scene_1"


def narration_for(sid: str, text_extra: str = "") -> dict[str, Any]:
    return {
        "scene_id": sid,
        "segments": [
            {
                "id": "n1",
                "text": f"Spójrzmy na krok {sid}. {text_extra}".strip(),
                "visual_event": f"{sid}_intro",
                "concepts": ["permutation"],
            },
            {
                "id": "n2",
                "text": "Oto wynik tego kroku.",
                "visual_event": f"{sid}_result",
                "concepts": ["factorial"],
            },
        ],
    }


def visual_plan_for(sid: str) -> dict[str, Any]:
    """A valid semantic visual plan; follow-up scenes reuse the block-method plan with their own ids."""
    import copy
    import json

    from tests.visual_fixtures import PLANS

    if sid in PLANS:
        return copy.deepcopy(PLANS[sid])
    return json.loads(json.dumps(PLANS["scene_2"]).replace("scene_2", sid))


def two_beat_plan(sid: str = "scene_1") -> dict[str, Any]:
    """Minimal valid plan whose beats match manim_code_for's EVENT markers."""
    return {
        "scene_id": sid,
        "template": "formula_transform",
        "layout": "center_focus",
        "objects": [{"id": "f", "type": "formula", "value": "5!"}],
        "beats": [
            {
                "id": f"{sid}_intro",
                "purpose": "state",
                "actions": [{"operation": "create", "targets": ["f"]}],
            },
            {
                "id": f"{sid}_result",
                "purpose": "evaluate",
                "actions": [
                    {
                        "operation": "transform",
                        "targets": ["f"],
                        "results": ["g"],
                        "values": ["5! = 120"],
                    }
                ],
            },
        ],
    }


def manim_code_for(sid: str, class_name: str, tex: str | None = None) -> str:
    tex = tex or SCENE_TEX.get(sid, "1+1=2")
    return f'''from manim import *


class {class_name}(Scene):
    def construct(self):
        title = Text("Tutorly {sid}", font_size=36).to_edge(UP)
        # EVENT: {sid}_intro
        self.play(Write(title), run_time=0.5)
        formula = MathTex(r"{tex}")
        # EVENT: {sid}_result
        self.play(FadeIn(formula), run_time=0.5)
        self.play(Indicate(formula), run_time=0.5)
        self.wait(0.2)
'''


def class_name_of(user: str) -> str:
    m = re.search(r"## required_class_name\s+(\S+)", user)
    return m.group(1) if m else "TutorlyScene1"


def manim_for(user: str, bad: bool = False) -> dict[str, Any]:
    sid, cls = scene_id_of(user), class_name_of(user)
    code = manim_code_for(sid, cls)
    if bad:
        code = "import os\n" + code
    return {
        "scene_id": sid,
        "class_name": cls,
        "code": code,
        "events_covered": [f"{sid}_intro", f"{sid}_result"],
    }


def followup_plan_for(user: str, value: str = "480") -> dict[str, Any]:
    """'What if there were 6 people?' answered as a new scene (6! - 2*5! = 480)."""
    m = re.search(r"## required_scene_id\s+(\S+)", user)
    sid = m.group(1) if m else "scene_3_q1"
    scene = _scene(
        sid,
        "Sześć osób",
        ["6!", "2*5!"],
        ["[AB]", "6!", "2*5!"],
        ["scene_3"],
        ["permutation", "multiplication_rule"],
        value,
    )
    scene["mathematical_state"]["current_expression"] = "6! - 2*5!"
    return {
        "answer_summary": "Dla 6 osób: 6! - 2·5! = 480.",
        "concepts_used": ["permutation", "factorial", "multiplication_rule"],
        "stays_in_scope": True,
        "scene": scene,
        "new_ledger_entries": [
            {
                "symbol": "6!",
                "meaning": "all arrangements of 6 people",
                "kind": "quantity",
                "introduced_in": sid,
                "value": "720",
            },
            {
                "symbol": "2*5!",
                "meaning": "arrangements of 6 people with A and B adjacent",
                "kind": "quantity",
                "introduced_in": sid,
                "value": "240",
            },
        ],
    }


Responder = Callable[[str], Any] | Any

MARKERS = {
    "PROBLEM ANALYZER": "problem_analyzer",
    "SCOPE COMPILER": "scope_compiler",
    "MATH REASONER": "math_reasoner",
    "PEDAGOGICAL PLANNER": "lesson_planner",
    "NARRATION GENERATOR": "narration_generator",
    "VISUAL PLANNER": "visual_planner",
    "MANIM GENERATOR": "manim_generator",
    "ASK TUTOR": "ask_tutor",
    "CHAT TUTOR": "chat_tutor",
    "You repair structured output": "repair_json",
}


class FakeTransport:
    """Deterministic stand-in for Gemini. Responses are keyed by prompt name; a value may be
    a dict, a JSON string, a callable(user)->value, or a list consumed in order (last one repeats)."""

    model_name = "fake-gemini"

    def __init__(self, responses: dict[str, Responder]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def count(self, prompt: str) -> int:
        return sum(1 for p, _ in self.calls if p == prompt)

    def generate(self, *, system: str, user: str, json_schema: dict | None) -> str:
        prompt = next(
            (name for marker, name in MARKERS.items() if marker in system), None
        )
        if prompt is None:
            raise TransportError("unknown prompt")
        self.calls.append((prompt, user))
        spec = self.responses.get(prompt)
        if spec is None:
            raise TransportError(f"no fake response for {prompt}")
        if isinstance(spec, list):
            idx = min(self.count(prompt) - 1, len(spec) - 1)
            spec = spec[idx]
        value = spec(user) if callable(spec) else spec
        return (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )


def default_responses(scoped: bool = True) -> dict[str, Responder]:
    return {
        "problem_analyzer": PROBLEM_IR,
        "scope_compiler": SCOPE_IR_RESTRICTED if scoped else SCOPE_IR_OPEN,
        "math_reasoner": solution_ir(),
        "lesson_planner": LESSON_IR,
        "narration_generator": lambda u: narration_for(scene_id_of(u)),
        "visual_planner": lambda u: visual_plan_for(scene_id_of(u)),
        "manim_generator": lambda u: manim_for(u),
        "ask_tutor": followup_plan_for,
    }


class FakeRenderer:
    """Records render calls; writes a placeholder file instead of running Manim."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls: list[str] = []
        self.voiceovers: list[list[dict] | None] = []

    def render(
        self,
        code: str,
        class_name: str,
        output_path: Path,
        voiceover: list[dict] | None = None,
        quality: str | None = None,
    ):
        from app.services.manim.renderer import RenderResult

        self.calls.append(class_name)
        self.voiceovers.append(voiceover)
        if len(self.calls) <= self.fail_times:
            return RenderResult(
                success=False,
                stdout="",
                stderr="NameError: name 'Foo' is not defined",
                error="manim exited with code 1",
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4")
        return RenderResult(
            success=True, stdout="RENDER_OK", stderr="", video_path=output_path
        )


class FakeTTS:
    """Writes real (silent) WAV files whose length depends on the text, like a voice would."""

    model_name = "fake-tts"
    voice = "test"

    def __init__(self, fail: bool = False, seconds_per_char: float = 0.02):
        self.fail = fail
        self.seconds_per_char = seconds_per_char
        self.calls: list[tuple[str, str]] = []

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        """One call per scene, one WAV per narration segment."""
        from app.services.tts import silent_wav, wav_duration

        self.calls.append((" | ".join(texts), language))
        if self.fail:
            raise RuntimeError("TTS quota exceeded")
        durations = []
        for text, path in zip(texts, out_paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(silent_wav(max(0.3, len(text) * self.seconds_per_char)))
            durations.append(wav_duration(path))
        return durations
