"""Live Gemini integration test. Runs only when GEMINI_API_KEY (or GOOGLE_API_KEY) is set.

GEMINI_API_KEY=... pytest -m integration -s
"""

import os

import pytest

from app.core.container import build_pipeline, build_tts
from app.core.db import session_scope
from app.models import Lesson
from app.services.gemini import GoogleGenAITransport
from app.services.pipeline import store
from tests.fixtures import DEMO_PROBLEM, DEMO_SCOPE

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not API_KEY, reason="GEMINI_API_KEY not set"),
]


def test_demo_problem_with_real_gemini(settings):
    settings.auto_render = os.environ.get("INTEGRATION_RENDER", "0") == "1"
    model = os.environ.get("GEMINI_MODEL", settings.gemini_model)
    tts = build_tts(settings)
    assert tts is not None
    pipeline = build_pipeline(
        settings, GoogleGenAITransport(api_key=API_KEY, model=model), tts
    )
    with session_scope() as s:
        lesson = Lesson(problem_text=DEMO_PROBLEM, scope_text=DEMO_SCOPE)
        s.add(lesson)
        s.flush()
        lid = lesson.id

    pipeline.run_generation(lid)
    lesson = store.get_lesson(lid)
    assert lesson.status in ("READY", "COMPLETED"), lesson.error
    assert lesson.math_verified and lesson.verified_value == "72"
    assert lesson.scope_ir["mode"] == "restricted"
    assert all(s.manim_code for s in store.list_scenes(lid) if s.status == "GENERATED")
    assert any(s.voiceover for s in store.list_scenes(lid)), "TTS produced no voiceover"

    sid = pipeline.create_followup(
        lid, store.list_scenes(lid)[-1].scene_id, "Dlaczego mnożymy przez 2?"
    )
    pipeline.generate_followup(lid, sid)
    followup = store.get_scene(lid, sid)
    assert followup.status == "GENERATED", followup.error
    assert followup.manim_code and followup.followup["answer_summary"]
