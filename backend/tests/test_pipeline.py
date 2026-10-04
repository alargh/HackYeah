"""End-to-end lesson generation with mocked Gemini (no API key, no Manim)."""

from app.core.db import session_scope
from app.models import GenerationJob, Lesson, ValidationRecord
from app.services.pipeline import store
from tests.conftest import make_pipeline
from tests.fixtures import DEMO_PROBLEM, DEMO_SCOPE, FakeRenderer, default_responses, manim_for, scene_id_of, solution_ir


def _new_lesson(scope: str | None = DEMO_SCOPE) -> str:
    with session_scope() as s:
        lesson = Lesson(problem_text=DEMO_PROBLEM, scope_text=scope)
        s.add(lesson)
        s.flush()
        return lesson.id


def test_full_pipeline_with_mocked_gemini(settings):
    pipeline, transport = make_pipeline(settings)
    lid = _new_lesson()
    pipeline.run_generation(lid)

    lesson = store.get_lesson(lid)
    assert lesson.status == "COMPLETED", lesson.error
    # The answer is verified by SymPy + brute force, not copied from the model.
    assert lesson.math_verified is True
    assert lesson.verified_value == "72"
    assert lesson.problem_ir["domain"] == "discrete_mathematics"
    assert lesson.scope_ir["mode"] == "restricted"
    assert len(lesson.lesson_ir["scenes"]) == 4

    scenes = store.list_scenes(lid)
    assert [s.scene_id for s in scenes] == ["scene_1", "scene_2", "scene_3", "scene_4"]
    for s in scenes:
        assert s.narration and s.visual_plan and s.manim_code
        assert "from manim import *" in s.manim_code["code"]
        assert s.render_status == "COMPLETED" and s.video_path
    # Exactly one call per stage when everything is valid; Manim code is compiled, not written by Gemini.
    assert transport.count("math_reasoner") == 1
    assert transport.count("visual_planner") == 4
    assert transport.count("manim_generator") == 0
    for s in scenes:
        assert "from tutorly_visuals import Stage" in s.manim_code["code"]
        assert s.visual_meta["valid"] and s.visual_meta["code_source"] == "compiled"
        assert s.animation_plan["steps"] and s.visual_plan["template"]
    # Retrieval kept graph templates away from a permutation problem.
    assert not any(t.startswith("graph") for t in scenes[0].visual_meta["retrieved_templates"])

    with session_scope() as s:
        jobs = s.query(GenerationJob).filter_by(lesson_id=lid).all()
        assert all(j.prompt_version for j in jobs if j.stage not in ("render", "tts", "visual_compile", "concat"))
        assert {j.model for j in jobs if j.stage == "tts"} == {"fake-tts"}
        assert {j.model for j in jobs} >= {"fake-gemini", "manim"}
        assert s.query(ValidationRecord).filter_by(lesson_id=lid, validator="math", passed=True).count() == 1


def test_wrong_math_regenerates_only_the_solution(settings):
    responses = default_responses()
    responses["math_reasoner"] = [solution_ir("70"), solution_ir("72")]
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)

    assert store.get_lesson(lid).status == "COMPLETED"
    assert transport.count("math_reasoner") == 2
    assert transport.count("problem_analyzer") == 1  # earlier stages reused
    assert transport.count("scope_compiler") == 1
    # The second call received the validator feedback.
    second_call = [u for p, u in transport.calls if p == "math_reasoner"][1]
    assert "STEP_MISMATCH" in second_call and "## previous_solution" in second_call


def test_scope_violation_is_rejected_and_regenerated(settings):
    responses = default_responses()
    responses["math_reasoner"] = [solution_ir(method="inclusion_exclusion"), solution_ir()]
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)

    lesson = store.get_lesson(lid)
    assert lesson.status == "COMPLETED"
    assert lesson.solution_ir["selected_method"] == "complement_counting"
    assert transport.count("math_reasoner") == 2
    with session_scope() as s:
        failed = s.query(ValidationRecord).filter_by(lesson_id=lid, validator="scope", target="solution", passed=False).all()
        assert failed and any(i["code"] == "SCOPE_FORBIDDEN" for i in failed[0].issues)


def test_persistent_wrong_math_continues_unverified(settings):
    responses = default_responses()
    responses["math_reasoner"] = solution_ir("70")
    pipeline, _ = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    lesson = store.get_lesson(lid)
    assert lesson.status == "COMPLETED"  # keeps going with the best attempt ...
    assert lesson.math_verified is False  # ... clearly marked as not verified
    assert "could not be verified" in (lesson.error or "")


def test_persistent_wrong_math_fails_with_useful_error(settings):
    settings.continue_on_failure = False
    responses = default_responses()
    responses["math_reasoner"] = solution_ir("70")
    pipeline, _ = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    lesson = store.get_lesson(lid)
    assert lesson.status == "FAILED"
    assert "mathematical validation failed" in lesson.error
    assert lesson.problem_ir and lesson.scope_ir  # valid stages are kept


def test_invalid_visual_plan_is_replanned_locally(settings):
    from tests.fixtures import visual_plan_for

    responses = default_responses()
    seen: set[str] = set()

    def planner(user):
        sid = scene_id_of(user)
        plan = visual_plan_for(sid)
        if sid == "scene_2" and sid not in seen:  # scenes run in parallel: fail only scene_2's first plan
            plan["template"] = "fireworks"  # not in the visual library
        seen.add(sid)
        return plan

    responses["visual_planner"] = planner
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    assert store.get_lesson(lid).status == "COMPLETED"
    width = settings.visual_plan_parallel_retries  # a re-plan runs several candidates at once
    assert transport.count("visual_planner") == 4 + width  # 4 scenes + one parallel local re-plan
    assert transport.count("narration_generator") == 4
    replan = [u for p, u in transport.calls if p == "visual_planner" and "UNKNOWN_TEMPLATE" in u]
    assert len(replan) == width and "visual_capabilities" in replan[0]
    assert transport.count("manim_generator") == 0


def test_unusable_visual_plan_falls_back_to_gemini_manim(settings):
    from tests.fixtures import visual_plan_for

    responses = default_responses()

    def planner(user):
        plan = visual_plan_for(scene_id_of(user))
        plan["template"] = "fireworks"
        return plan

    calls = {"n": 0}

    def manim(user):
        calls["n"] += 1
        return manim_for(user, bad=calls["n"] == 1)  # very first fallback code imports os

    responses["visual_planner"] = planner
    responses["manim_generator"] = manim
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    assert store.get_lesson(lid).status == "COMPLETED"
    assert transport.count("manim_generator") == 5  # 4 fallback scenes + 1 local regeneration
    assert all(s.visual_meta["code_source"] == "gemini" and s.animation_plan is None for s in store.list_scenes(lid))


def test_render_failure_regenerates_only_that_scenes_manim(settings):
    renderer = FakeRenderer(fail_times=1)
    pipeline, transport = make_pipeline(settings, renderer=renderer)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    assert store.get_lesson(lid).status == "COMPLETED"
    assert transport.count("manim_generator") == 1  # only the scene whose compiled render failed
    feedback_calls = [u for p, u in transport.calls if p == "manim_generator" and "Rendering failed" in u]
    assert len(feedback_calls) == 1 and "NameError" in feedback_calls[0]
    assert len(renderer.calls) == 5


def test_invalid_scene_is_regenerated_alone(settings):
    import copy

    from tests.fixtures import LESSON_IR

    bad = copy.deepcopy(LESSON_IR)
    bad["scenes"][1]["uses"].append("Ω")  # unknown ledger symbol
    good_scene = copy.deepcopy(LESSON_IR["scenes"][1])
    responses = default_responses()
    responses["lesson_planner"] = [bad, good_scene]
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    assert store.get_lesson(lid).status == "COMPLETED"
    assert transport.count("lesson_planner") == 2
    planner_calls = [u for p, u in transport.calls if p == "lesson_planner"]
    assert "REGENERATE ONE SCENE" in planner_calls[1]
    assert "LEDGER_UNKNOWN_SYMBOL" in planner_calls[1]
    assert '"scene_id": "scene_2"' in planner_calls[1]


def test_local_regeneration_of_narration(settings):
    pipeline, transport = make_pipeline(settings)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    before = {s.scene_id: s.manim_code for s in store.list_scenes(lid)}

    pipeline.regenerate(lid, "scene_3", "narration", instruction="explain more slowly")

    assert transport.count("narration_generator") == 5
    assert transport.count("math_reasoner") == 1
    assert transport.count("lesson_planner") == 1
    after = {s.scene_id: s for s in store.list_scenes(lid)}
    assert after["scene_3"].regeneration_count == 1
    for sid in ("scene_1", "scene_2", "scene_4"):
        assert after[sid].manim_code == before[sid]
    assert "explain more slowly" in [u for p, u in transport.calls if p == "narration_generator"][-1]
    assert store.get_lesson(lid).status == "COMPLETED"


def _followup(pipeline, lid, question="What if there were 6 people?", parent="scene_3"):
    sid = pipeline.create_followup(lid, parent, question)
    pipeline.generate_followup(lid, sid)
    return sid


def test_question_is_answered_with_a_new_video_scene(settings):
    pipeline, transport = make_pipeline(settings)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    lesson_video = store.get_lesson(lid).video_path

    sid = _followup(pipeline, lid)

    assert sid == "scene_3_q1"
    row = store.get_scene(lid, sid)
    assert row.kind == "followup" and row.parent_scene_id == "scene_3"
    assert row.status == "GENERATED", row.error
    assert row.render_status == "COMPLETED" and row.video_path  # answered as a video, not chat
    assert row.narration and row.voiceover and row.visual_plan and row.manim_code
    assert [e["symbol"] for e in row.ledger_extra] == ["6!", "2*5!"]
    assert row.followup["answer_summary"].startswith("Dla 6 osób")

    # The tutor received the full lesson context.
    user = [u for p, u in transport.calls if p == "ask_tutor"][-1]
    for part in ("required_scene_id", "original_problem", "scope_ir", "solution_ir", "current_scene",
                 "concept_ledger", "conversation_history", "question"):
        assert f"## {part}" in user
    # Follow-ups never change the main lesson or its video.
    assert [s.scene_id for s in store.list_scenes(lid)] == ["scene_1", "scene_2", "scene_3", "scene_4"]
    assert store.get_lesson(lid).video_path == lesson_video
    assert store.get_lesson(lid).status == "COMPLETED"
    assert [m["role"] for m in store.history(lid)] == ["user", "tutor"]


def test_followup_with_wrong_math_is_rejected_and_replanned(settings):
    from tests.fixtures import followup_plan_for

    responses = default_responses()
    responses["ask_tutor"] = [lambda u: followup_plan_for(u, value="500"), followup_plan_for]
    pipeline, transport = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    sid = _followup(pipeline, lid)

    assert transport.count("ask_tutor") == 2
    assert "STATE_MISMATCH" in [u for p, u in transport.calls if p == "ask_tutor"][1]
    assert store.get_scene(lid, sid).render_status == "COMPLETED"


def test_followup_outside_scope_is_rejected(settings):
    from tests.fixtures import followup_plan_for

    def bad(u):
        plan = followup_plan_for(u)
        plan["concepts_used"].append("inclusion_exclusion")
        return plan

    responses = default_responses()
    responses["ask_tutor"] = bad
    pipeline, _ = make_pipeline(settings, responses)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    sid = _followup(pipeline, lid)
    row = store.get_scene(lid, sid)
    assert row.status == "FAILED" and "SCOPE_FORBIDDEN" in row.error
    assert store.get_lesson(lid).status == "COMPLETED"  # the lesson itself is unaffected


def test_voiceover_is_generated_and_drives_timing(settings):
    from pathlib import Path

    renderer = FakeRenderer()
    pipeline, _ = make_pipeline(settings, renderer=renderer)
    lid = _new_lesson()
    pipeline.run_generation(lid)

    scene = store.list_scenes(lid)[0]
    vo = scene.voiceover
    assert vo["model"] == "fake-tts" and len(vo["segments"]) == 2
    seg = vo["segments"][0]
    assert seg["visual_event"] == "scene_1_intro" and seg["duration"] > 0
    assert Path(seg["path"]).is_file()
    # Real voice durations replace the narration estimates (they pace the Manim code).
    assert scene.narration["segments"][0]["duration_estimate"] == round(seg["duration"], 2)
    # The renderer received the clips for every scene.
    assert all(v and len(v) == 2 for v in renderer.voiceovers)


def test_tts_failure_keeps_the_lesson_working_silently(settings):
    from tests.fixtures import FakeTTS

    renderer = FakeRenderer()
    pipeline, _ = make_pipeline(settings, renderer=renderer, tts=FakeTTS(fail=True))
    lid = _new_lesson()
    pipeline.run_generation(lid)
    assert store.get_lesson(lid).status == "COMPLETED"
    assert all(s.voiceover is None for s in store.list_scenes(lid))
    assert renderer.voiceovers == [None] * 4
    with session_scope() as s:
        assert s.query(GenerationJob).filter_by(lesson_id=lid, stage="tts", status="FAILED").count() == 4


def test_regenerating_narration_regenerates_voice(settings):
    from tests.fixtures import FakeTTS

    tts = FakeTTS()
    pipeline, _ = make_pipeline(settings, tts=tts)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    n = len(tts.calls)
    pipeline.regenerate(lid, "scene_2", "manim")
    assert len(tts.calls) == n  # code-only regeneration keeps the voice
    pipeline.regenerate(lid, "scene_2", "narration")
    assert len(tts.calls) == n + 1  # one TTS request per scene


def test_restart_marks_interrupted_followups_failed(settings):
    from app.workers.jobs import recover_interrupted

    pipeline, _ = make_pipeline(settings)
    lid = _new_lesson()
    pipeline.run_generation(lid)
    sid = pipeline.create_followup(lid, "scene_2", "Why?")
    store.update_scene(lid, sid, status="GENERATING")  # the server dies mid-generation

    assert recover_interrupted() == 1
    row = store.get_scene(lid, sid)
    assert row.status == "FAILED" and "restart" in row.error
    assert store.get_lesson(lid).status == "COMPLETED"  # finished lessons are untouched


def test_stage_timings_are_logged_and_exposed(settings, capsys):
    pipeline, _ = make_pipeline(settings)
    lid = _new_lesson()
    pipeline.run_generation(lid)

    lesson = store.get_lesson(lid)
    assert {"analyze_problem", "compile_scope", "reason+verify", "plan_lesson", "scenes(narr+voice+visual+render)", "concat"} <= set(lesson.timings)
    stages = {r["stage"]: r for r in store.stage_timings(lid)}
    assert stages["narration"]["calls"] == 4 and stages["render"]["calls"] == 4 and stages["tts"]["calls"] == 4
    table = capsys.readouterr().out
    assert f"Tutorly timings  lesson={lid}  outcome=COMPLETED" in table
    assert "phases (wall clock):" in table and "visual_plan" in table
