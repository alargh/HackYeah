"""Real Manim rendering of a deterministic scene inside the sandbox (requires Manim + LaTeX)."""

import importlib.util
import shutil

import pytest

from app.services.manim import ManimRenderer
from tests.fixtures import manim_code_for

pytestmark = pytest.mark.render

_manim_ok = importlib.util.find_spec("manim") is not None and shutil.which("latex") is not None
needs_manim = pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")


def _manim_importable() -> bool:
    try:
        import manim  # noqa: F401

        return True
    except Exception:
        return False


@needs_manim
@pytest.mark.skipif(not _manim_importable(), reason="Manim cannot be imported on this host")
def test_render_deterministic_scene(tmp_path):
    out = tmp_path / "out" / "scene_1.mp4"
    result = ManimRenderer(quality="l", timeout_s=180).render(manim_code_for("scene_1", "TutorlyScene1"), "TutorlyScene1", out)
    assert result.success, result.stderr[-2000:]
    assert out.exists() and out.stat().st_size > 1000
    assert "RENDER_OK" in result.stdout


@needs_manim
@pytest.mark.skipif(not _manim_importable(), reason="Manim cannot be imported on this host")
@pytest.mark.parametrize(
    "payload,needle",
    [
        ("open('/tmp/../etc/tutorly_pwned', 'w').write('x')", "write outside sandbox blocked"),
        ("import socket; socket.create_connection(('example.com', 80))", "network access blocked"),
        ("import subprocess; subprocess.run(['id'])", "process 'id' blocked"),
    ],
)
def test_sandbox_blocks_escape_attempts(tmp_path, payload, needle):
    # Bypasses the AST validator on purpose: the sandbox is the second line of defence.
    code = manim_code_for("scene_1", "TutorlyScene1").replace(
        "self.wait(0.2)", f"self.wait(0.2)\n        {payload}"
    )
    result = ManimRenderer(quality="l", timeout_s=180).render(code, "TutorlyScene1", tmp_path / "x.mp4")
    assert not result.success
    assert needle in result.stderr


@needs_manim
@pytest.mark.skipif(not _manim_importable(), reason="Manim cannot be imported on this host")
def test_full_pipeline_with_real_manim(settings):
    """Mocked Gemini, real sandboxed Manim render of every scene + FFmpeg concatenation."""
    from pathlib import Path

    from app.core.db import session_scope
    from app.models import Lesson
    from app.services.pipeline import store
    from tests.conftest import make_pipeline
    from tests.fixtures import DEMO_PROBLEM, DEMO_SCOPE

    pipeline, _ = make_pipeline(settings, renderer=ManimRenderer(quality="l", timeout_s=180))
    with session_scope() as s:
        lesson = Lesson(problem_text=DEMO_PROBLEM, scope_text=DEMO_SCOPE)
        s.add(lesson)
        s.flush()
        lid = lesson.id
    pipeline.run_generation(lid)

    lesson = store.get_lesson(lid)
    assert lesson.status == "COMPLETED", lesson.error
    assert lesson.verified_value == "72"
    for scene in store.list_scenes(lid):
        assert scene.render_status == "COMPLETED", scene.render_stderr
        assert Path(scene.video_path).stat().st_size > 1000
    assert lesson.video_path and Path(lesson.video_path).stat().st_size > 1000


def test_event_markers_become_voice_hooks():
    from app.services.manim.renderer import inject_event_hooks

    src = manim_code_for("scene_1", "TutorlyScene1").replace("        # EVENT: scene_1_result", "# EVENT: scene_1_result")
    out = inject_event_hooks(src)
    assert '        _ml_event("scene_1_intro")' in out
    assert '        _ml_event("scene_1_result")' in out  # takes the indentation of the next code line
    assert "# EVENT" not in out


def test_event_hook_injection_falls_back_on_invalid_result():
    from app.services.manim.renderer import inject_event_hooks

    src = "x = (1,\n# EVENT: e\n 2)\n"
    assert inject_event_hooks(src) == src


def _duration(path) -> float:
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


@needs_manim
@pytest.mark.skipif(not _manim_importable(), reason="Manim cannot be imported on this host")
def test_render_with_voiceover_has_audio_and_waits_for_voice(tmp_path):
    from app.services.manim.renderer import has_audio
    from app.services.tts import silent_wav, wav_duration

    clips = []
    for i, (seg, event, secs) in enumerate([("n1", "scene_1_intro", 2.5), ("n2", "scene_1_result", 3.0)]):
        p = tmp_path / f"{seg}.wav"
        p.write_bytes(silent_wav(secs))
        clips.append({"id": seg, "visual_event": event, "path": str(p), "duration": wav_duration(p)})

    out = tmp_path / "voiced.mp4"
    result = ManimRenderer(quality="l", timeout_s=180).render(
        manim_code_for("scene_1", "TutorlyScene1"), "TutorlyScene1", out, voiceover=clips
    )
    assert result.success, result.stderr[-2000:]
    assert has_audio(out)
    # The animation alone is ~1.7 s; the voice (2.5 s + 3.0 s) must be allowed to finish.
    assert _duration(out) >= 5.5


@needs_manim
@pytest.mark.skipif(not _manim_importable(), reason="Manim cannot be imported on this host")
def test_render_timeout(tmp_path):
    code = manim_code_for("scene_1", "TutorlyScene1").replace("self.wait(0.2)", "self.wait(0.2)\n        [i for i in range(10**12)]")
    result = ManimRenderer(quality="l", timeout_s=8).render(code, "TutorlyScene1", tmp_path / "x.mp4")
    assert not result.success and "timed out" in (result.error or "")
