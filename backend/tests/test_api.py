from fastapi.testclient import TestClient

from app.core.container import Container
from app.main import create_app
from app.services.prompts import PromptStore
from app.workers.jobs import InlineJobRunner
from tests.fixtures import DEMO_PROBLEM, DEMO_SCOPE


def _client(settings, container) -> TestClient:
    return TestClient(create_app(settings, container))


def test_lesson_lifecycle_via_api(settings, make_container):
    container, transport = make_container()
    with _client(settings, container) as client:
        assert client.get("/api/health").json()["gemini_configured"] is True

        r = client.post("/api/lessons", json={"problem": DEMO_PROBLEM, "scope": DEMO_SCOPE})
        assert r.status_code == 202
        lid = r.json()["lesson_id"]

        lesson = client.get(f"/api/lessons/{lid}").json()
        assert lesson["status"] == "COMPLETED", lesson["error"]
        assert lesson["verified_value"] == "72" and lesson["math_verified"]
        assert lesson["scope_ir"]["mode"] == "restricted"
        assert lesson["scope_warning"] is None
        assert any(v["validator"] == "math" and v["passed"] for v in lesson["validations"])

        scenes = client.get(f"/api/lessons/{lid}/scenes").json()
        assert len(scenes) == 4 and scenes[0]["video_url"].startswith(f"/media/lessons/{lid}/")
        assert client.get(scenes[0]["video_url"]).status_code == 200

        media = client.get(f"/api/lessons/{lid}/media").json()
        assert all(s["render_status"] == "COMPLETED" for s in media["scenes"])

        ans = client.post(f"/api/lessons/{lid}/ask", json={"scene_id": "scene_3", "question": "Why do we multiply by 2?"})
        assert ans.status_code == 202
        fid = ans.json()["scene_id"]
        assert fid == "scene_3_q1"
        lesson = client.get(f"/api/lessons/{lid}").json()
        assert len(lesson["scenes"]) == 4
        (fu,) = lesson["followups"]
        assert fu["scene_id"] == fid and fu["question"] == "Why do we multiply by 2?"
        assert fu["render_status"] == "COMPLETED" and fu["video_url"] and fu["voiceover"]
        assert fu["followup"]["answer_summary"]
        assert client.post(f"/api/lessons/{lid}/ask", json={"scene_id": "nope", "question": "?"}).status_code == 404

        r = client.post(f"/api/lessons/{lid}/scenes/scene_2/regenerate", json={"artifact": "manim"})
        assert r.status_code == 202
        assert client.get(f"/api/lessons/{lid}").json()["status"] == "COMPLETED"

        r = client.post(f"/api/lessons/{lid}/render", json={"scene_ids": ["scene_1"]})
        assert r.status_code == 202

        jobs = client.get(f"/api/lessons/{lid}/jobs").json()
        assert {"analyze_problem", "compile_scope", "reason", "plan_lesson", "narration", "visual_plan", "visual_compile", "render"} <= {
            j["stage"] for j in jobs
        }
        assert len(client.get(f"/api/lessons/{lid}/messages").json()) == 2
        assert client.get("/api/lessons").json()[0]["id"] == lid


def test_unknown_lesson_404(settings, make_container):
    container, _ = make_container()
    with _client(settings, container) as client:
        assert client.get("/api/lessons/nope").status_code == 404
        assert client.post("/api/lessons/nope/ask", json={"scene_id": "s", "question": "q"}).status_code == 404


def test_without_gemini_key_creation_is_503(settings):
    container = Container(settings, None, InlineJobRunner(), PromptStore(settings.prompts_dir), llm_error="GEMINI_API_KEY is not set")
    with _client(settings, container) as client:
        assert client.get("/api/health").json()["gemini_configured"] is False
        r = client.post("/api/lessons", json={"problem": DEMO_PROBLEM})
        assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
