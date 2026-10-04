import copy

from app.schemas import LessonIR
from app.services.validation import LedgerValidator
from tests.fixtures import LESSON_IR

V = LedgerValidator()


def _lesson(mutate=None) -> LessonIR:
    data = copy.deepcopy(LESSON_IR)
    if mutate:
        mutate(data)
    return LessonIR.model_validate(data)


def test_consistent_lesson_passes():
    lesson = _lesson()
    assert V.validate_ledger(lesson).passed
    for scene in lesson.scenes:
        r = V.validate_scene(scene, lesson)
        assert r.passed, (scene.scene_id, r.feedback())


def test_conflicting_ledger_definition():
    def m(d):
        d["concept_ledger"]["entries"].append(
            {"symbol": "[AB]", "meaning": "the pair of people A and B standing apart", "introduced_in": "scene_3"}
        )

    r = V.validate_ledger(_lesson(m))
    assert not r.passed and r.errors[0].code == "LEDGER_CONFLICT"


def test_scene_redefining_existing_symbol():
    def m(d):
        d["scenes"][2]["introduces"] = ["[AB]", "2*4!"]

    lesson = _lesson(m)
    r = V.validate_scene(lesson.scenes[2], lesson)
    assert any(i.code == "SYMBOL_REDEFINED" for i in r.errors)


def test_symbol_used_before_introduction():
    def m(d):
        d["scenes"][0]["uses"] = ["A", "B", "5!", "[AB]"]

    lesson = _lesson(m)
    r = V.validate_scene(lesson.scenes[0], lesson)
    assert any(i.code == "USED_BEFORE_INTRODUCED" for i in r.errors)


def test_unknown_symbol_and_forward_dependency():
    def m(d):
        d["scenes"][1]["uses"].append("Ω")
        d["scenes"][1]["dependencies"] = ["scene_3"]

    lesson = _lesson(m)
    codes = {i.code for i in V.validate_scene(lesson.scenes[1], lesson).errors}
    assert {"LEDGER_UNKNOWN_SYMBOL", "FORWARD_DEPENDENCY"} <= codes
