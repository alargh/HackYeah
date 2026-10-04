import pytest

from app.schemas import ManimCode, VisualPlan
from app.services.pipeline import class_name_for
from app.services.validation import ManimValidator
from tests.fixtures import manim_code_for, two_beat_plan

V = ManimValidator()


def _code(src: str, cls: str = "TutorlyScene1") -> ManimCode:
    return ManimCode(scene_id="scene_1", class_name=cls, code=src)


def test_class_name_generation():
    assert class_name_for("scene_1") == "TutorlyScene1"
    assert class_name_for("intro-scene") == "TutorlyIntroScene"


def test_generated_source_passes_and_has_event_markers():
    plan = VisualPlan.model_validate(two_beat_plan("scene_1"))
    r = V.validate(_code(manim_code_for("scene_1", "TutorlyScene1")), plan)
    assert r.passed, r.feedback()
    assert not r.issues  # all events marked


@pytest.mark.parametrize(
    "snippet,code",
    [
        ("import os", "FORBIDDEN_IMPORT"),
        ("from subprocess import run", "FORBIDDEN_IMPORT"),
        ("x = open('/etc/passwd').read()", "FORBIDDEN_NAME"),
        ("y = (1).__class__", "PRIVATE_ATTRIBUTE"),
        ("z = eval('1')", "FORBIDDEN_NAME"),
        ("q = Path('x')", "FORBIDDEN_NAME"),
        ("config.media_dir = '/'", "FORBIDDEN_NAME"),
        ("w = requests_get('http://x')", "DISALLOWED_CALL"),
        ("c = Circle(color='#ff0000')", "ARBITRARY_COLOR"),
        ("t = Text('x', font='Comic Sans')", "ARBITRARY_FONT"),
    ],
)
def test_dangerous_code_rejected(snippet, code):
    src = manim_code_for("scene_1", "TutorlyScene1") + "\n" + snippet + "\n"
    r = V.validate(_code(src))
    assert not r.passed
    assert code in {i.code for i in r.errors}


def test_while_loop_rejected():
    src = manim_code_for("scene_1", "TutorlyScene1").replace("self.wait(0.2)", "while True:\n            self.wait(1)")
    assert "DISALLOWED_SYNTAX" in {i.code for i in V.validate(_code(src)).errors}


def test_structure_checks():
    assert "SYNTAX_ERROR" in {i.code for i in V.validate(_code("def (")).errors}
    assert "SCENE_CLASS_COUNT" in {i.code for i in V.validate(_code("from manim import *\nx = 1\n")).errors}
    src = manim_code_for("scene_1", "Other")
    assert "CLASS_NAME_MISMATCH" in {i.code for i in V.validate(_code(src)).errors}


def test_missing_event_markers_is_warning():
    plan = VisualPlan.model_validate(two_beat_plan("scene_1"))
    src = manim_code_for("scene_1", "TutorlyScene1").replace("# EVENT: scene_1_result", "")
    r = V.validate(_code(src), plan)
    assert r.passed
    assert r.issues[0].code == "EVENT_MARKERS_MISSING"
