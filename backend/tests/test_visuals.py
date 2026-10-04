"""Visual design system: manifest, retrieval, semantic plan validation, grammar/compiler, tokens, rendering."""

import ast
import copy
import importlib.util
import re
import shutil
import typing

import pytest

from app.schemas import NarrationIR, ProblemIR, SceneIR, SolutionIR, VisualPlan
from app.schemas import generation as gen
from app.services.validation import ManimValidator
from app.services.validation.visual_validator import VisualPlanValidator
from app.services.visuals.compiler import compile_plan, render_source
from app.services.visuals.manifest import MANIFEST_PATH, get_manifest, load_manifest
from app.services.visuals.retrieval import retrieve
from tests.fixtures import LESSON_IR, PROBLEM_IR, narration_for, solution_ir
from tests.visual_fixtures import EXTRA_PLANS, PLANS

M = get_manifest()
V = VisualPlanValidator()
SCENES = {s["scene_id"]: SceneIR.model_validate(s) for s in LESSON_IR["scenes"]}
CORE_TEMPLATES = {
    "problem_reveal",
    "constraint_reveal",
    "permutation_counter",
    "block_method",
    "case_split",
    "counting_tree",
    "complement_counting",
    "graph_build",
    "graph_traversal",
    "highlight_path",
    "formula_transform",
    "before_after",
    "comparison",
    "spotlight",
    "summary",
    # permutation galleries and stereometry
    "arrangement_gallery",
    "solid_reveal",
    "space_construction",
    "section_flatten",
    # plane figures and solids of revolution
    "plane_figure",
    "solid_of_revolution",
}


def plan(pid: str, mutate=None) -> VisualPlan:
    data = copy.deepcopy({**PLANS, **EXTRA_PLANS}[pid])
    if mutate:
        mutate(data)
    return VisualPlan.model_validate(data)


def codes(result) -> set[str]:
    return {i.code for i in result.errors}


# ------------------------------------------------------------------------------------------- manifest


def test_manifest_loads_with_initial_template_set():
    assert {t.id for t in M.templates} == CORE_TEMPLATES
    assert {
        "merge",
        "split",
        "branch",
        "transform",
        "connect",
        "emphasize_result",
    } <= M.ids("operations")
    assert all(t.supports and t.good_for for t in M.templates)


def test_manifest_is_metadata_not_code():
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "def " not in text and "import " not in text and "self." not in text


@pytest.mark.parametrize(
    "alias,section",
    [
        (gen.Emphasis, "emphasis"),
        (gen.ObjectType, "object_types"),
        (gen.Operation, "operations"),
        (gen.Layout, "layouts"),
        (gen.Camera, "cameras"),
    ],
)
def test_schema_vocabulary_matches_manifest(alias, section):
    assert set(typing.get_args(alias)) == M.ids(section)


def test_broken_manifest_is_rejected(tmp_path):
    bad = MANIFEST_PATH.read_text(encoding="utf-8").replace(
        "supports: [merge, split, count, transform]", "supports: [merge, teleport]"
    )
    p = tmp_path / "manifest.yaml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="teleport"):
        load_manifest(p)


# ------------------------------------------------------------------------------------------- retrieval


def test_retrieval_for_permutation_problem():
    caps = retrieve(
        ProblemIR.model_validate(PROBLEM_IR),
        SolutionIR.model_validate(solution_ir()),
        SCENES["scene_2"],
    )
    ids = set(caps.template_ids)
    assert {
        "permutation_counter",
        "constraint_reveal",
        "block_method",
        "case_split",
        "complement_counting",
        "formula_transform",
    } <= ids
    assert not ids & {"graph_build", "graph_traversal", "highlight_path"}
    assert "adjacency_constraints" in caps.tags


def test_retrieval_for_graph_problem():
    graph_problem = ProblemIR.model_validate(
        {
            **PROBLEM_IR,
            "subdomain": "graph_theory",
            "problem_type": "shortest_path",
            "relevant_concepts": ["graph", "shortest_path"],
            "constraints": [],
            "enumeration_spec": None,
            "graph_spec": {
                "nodes": ["a", "b"],
                "edges": [{"source": "a", "target": "b"}],
                "query": "shortest_path_length",
                "source": "a",
                "target": "b",
            },
        }
    )
    ids = set(retrieve(graph_problem, None, None).template_ids)
    assert {"graph_traversal", "highlight_path", "graph_build"} <= ids
    assert not ids & {"block_method", "permutation_counter"}


def test_prompt_exposes_only_retrieved_capabilities():
    caps = retrieve(
        ProblemIR.model_validate(PROBLEM_IR),
        SolutionIR.model_validate(solution_ir()),
        SCENES["scene_1"],
    )
    shown = caps.for_prompt()
    assert {t["id"] for t in shown["templates"]} == set(caps.template_ids)
    assert {o["id"] for o in shown["operations"]} == M.allowed_operations(
        caps.template_ids
    )
    assert not {t["id"] for t in shown["templates"]} & {
        "graph_build",
        "graph_traversal",
        "highlight_path",
    }
    assert {e["id"] for e in shown["emphasis"]} == M.ids("emphasis")


def test_retrieval_is_deterministic():
    args = (
        ProblemIR.model_validate(PROBLEM_IR),
        SolutionIR.model_validate(solution_ir()),
        SCENES["scene_3"],
    )
    assert retrieve(*args).template_ids == retrieve(*args).template_ids


# ------------------------------------------------------------------------------------------- validation


@pytest.mark.parametrize("pid", list(PLANS) + list(EXTRA_PLANS))
def test_reference_plans_are_valid(pid):
    scene = SCENES.get(pid)
    narration = NarrationIR.model_validate(narration_for(pid)) if pid in PLANS else None
    r = V.validate(plan(pid), scene, narration)
    assert r.passed, r.feedback()


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda d: d.update(template="fireworks"), "UNKNOWN_TEMPLATE"),
        (
            lambda d: d["beats"][1]["actions"].append(
                {"operation": "traverse", "targets": ["A", "B"]}
            ),
            "UNSUPPORTED_OPERATION",
        ),
        (
            lambda d: d["beats"][1]["actions"].append(
                {"operation": "highlight", "targets": ["Z"]}
            ),
            "UNKNOWN_TARGET",
        ),
        (
            lambda d: d["beats"][0]["actions"].insert(
                0, {"operation": "highlight", "targets": ["A"]}
            ),
            "NOT_ON_STAGE",
        ),
        (
            lambda d: d["objects"].append(
                {"id": "x", "type": "label", "value": "color: #ff0000"}
            ),
            "ARBITRARY_STYLE",
        ),
        (lambda d: d["beats"][2]["actions"][0].update(results=[]), "MISSING_RESULT"),
        (lambda d: d["beats"][1].update(purpose=""), "DECORATIVE_BEAT"),
        (
            lambda d: d["objects"].append({"id": "g", "type": "region", "value": "x"}),
            "UNSUPPORTED_OBJECT_TYPE",
        ),
    ],
)
def test_semantic_operation_errors(mutate, code):
    assert code in codes(V.validate(plan("scene_2", mutate), SCENES["scene_2"]))


def test_cases_need_spatial_separation():
    def mutate(d):
        d["beats"][1]["layout"] = None
        d["layout"] = "center_focus"

    assert "CASES_NOT_SEPARATED" in codes(
        V.validate(plan("scene_3", mutate), SCENES["scene_3"])
    )


def test_text_only_scene_is_rejected():
    text_plan = VisualPlan.model_validate(
        {
            "scene_id": "scene_1",
            "template": "formula_transform",
            "layout": "center_focus",
            "objects": [
                {"id": f"f{i}", "type": "formula", "value": v}
                for i, v in enumerate(["5!", "120", "48", "72"])
            ],
            "beats": [
                {
                    "id": f"b{i}",
                    "purpose": "state",
                    "actions": [{"operation": "create", "targets": [f"f{i}"]}],
                }
                for i in range(4)
            ],
        }
    )
    scene = SCENES["scene_1"].model_copy(update={"solution_steps": ["step_1"]})
    found = codes(V.validate(text_plan, scene))
    assert {
        "TOO_FEW_VISUAL_OBJECTS",
        "CONSECUTIVE_TEXT_BEATS",
        "NO_MATH_VISUAL",
        "NO_EMPHASIS",
    } <= found


def test_static_graph_and_camera_limits():
    def static(d):
        d["beats"][0]["actions"] = [
            {
                "operation": "create",
                "targets": [o["id"] for o in d["objects"] if o["type"] != "formula"],
            }
        ]
        d["beats"][1]["actions"] = [{"operation": "focus", "targets": ["a"]}]
        d["beats"][2]["actions"] = [{"operation": "create", "targets": ["f_d"]}]

    assert "STATIC_GRAPH" in codes(V.validate(plan("graph_demo", static)))

    def shaky(d):
        for b in d["beats"]:
            b["camera"] = "focus_subject"
        d["beats"] += [
            dict(
                d["beats"][0],
                id=f"x{i}",
                actions=[{"operation": "highlight", "targets": ["a"]}],
            )
            for i in range(2)
        ]

    assert "TOO_MANY_CAMERA_MOVES" in codes(V.validate(plan("graph_demo", shaky)))


def test_formula_tex_is_restricted():
    def mutate(d):
        d["objects"][-1]["value"] = r"\input{/etc/passwd} ż"

    found = codes(V.validate(plan("scene_3", mutate), SCENES["scene_3"]))
    assert {"UNSUPPORTED_TEX", "FORMULA_NOT_ASCII"} <= found


def test_quality_rules_are_configurable():
    strict = get_manifest().model_copy(deep=True)
    strict.quality["max_camera_moves"].value = 0
    assert "TOO_MANY_CAMERA_MOVES" in codes(
        VisualPlanValidator(strict).validate(plan("scene_2"), SCENES["scene_2"])
    )
    lenient = get_manifest().model_copy(deep=True)
    lenient.quality["max_camera_moves"].severity = "warning"
    lenient.quality["max_camera_moves"].value = 0
    assert (
        VisualPlanValidator(lenient).validate(plan("scene_2"), SCENES["scene_2"]).passed
    )


def test_legacy_free_text_plans_still_load_but_do_not_compile():
    legacy = VisualPlan.model_validate(
        {
            "scene_id": "s",
            "layout": "x",
            "events": [{"id": "e1", "action": "show", "description": "d"}],
        }
    )
    assert legacy.beats[0].id == "e1"
    assert not V.validate(legacy).passed


# ------------------------------------------------------------------------------------------- compiler


def test_several_formulas_can_combine_into_one():
    def mutate(d):
        d["objects"].append({"id": "f_two", "type": "formula", "value": "2! = 2"})
        d["beats"][1]["actions"][1:3] = [
            {"operation": "create", "targets": ["f_forb", "f_two"]},
            {
                "operation": "transform",
                "targets": ["f_forb", "f_two"],
                "results": ["f_forb_val"],
                "values": [r"2 \cdot 4! = 48"],
            },
        ]

    p = plan("scene_3", mutate)
    assert V.validate(p, SCENES["scene_3"]).passed
    step = next(
        s
        for s in compile_plan(p, None, "X", "t").steps
        if s.primitive == "transform_tex"
    )
    assert step.targets == ["f_forb", "f_two"]


def test_merge_expands_into_semantic_motion_sequence():
    anim = compile_plan(plan("scene_2"), None, "TutorlyScene2", "Glue")
    merge_steps = [s.primitive for s in anim.steps if s.beat == "scene_2_merge"]
    assert merge_steps[:3] == ["indicate", "move_adjacent", "enclose"]
    assert "camera" in merge_steps  # follow_transform
    enclose = next(s for s in anim.steps if s.primitive == "enclose")
    assert enclose.params == {"result": "AB", "value": "[AB]", "role": "transformation"}


def test_compiled_source_is_deterministic_valid_and_synchronised():
    narration = NarrationIR.model_validate(narration_for("scene_2"))
    narration.segments[0].duration_estimate = 6.0
    a = render_source(
        compile_plan(plan("scene_2"), narration, "TutorlyScene2", "Sklejamy A i B")
    )
    b = render_source(
        compile_plan(plan("scene_2"), narration, "TutorlyScene2", "Sklejamy A i B")
    )
    assert a == b
    ast.parse(a)
    for beat in PLANS["scene_2"]["beats"]:
        assert f"# EVENT: {beat['id']}" in a
    code = gen.ManimCode(scene_id="scene_2", class_name="TutorlyScene2", code=a)
    assert ManimValidator().validate(code, plan("scene_2")).passed
    # Beat timing follows the voice: the 6 s narration segment fills its beat.
    anim = compile_plan(plan("scene_2"), narration, "TutorlyScene2", "t")
    assert anim.beat_durations["scene_2_intro"] == 6.0
    assert sum(
        s.run_time for s in anim.steps if s.beat == "scene_2_intro"
    ) == pytest.approx(5.5, abs=0.15)


def test_compiler_escapes_untrusted_values():
    def mutate(d):
        d["objects"][0]["value"] = 'A")\nimport os  #'

    src = render_source(
        compile_plan(
            plan("scene_2", mutate), None, "TutorlyScene2", "x'); import os; ('"
        )
    )
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import)]
    assert (
        ManimValidator()
        .validate(gen.ManimCode(scene_id="s", class_name="TutorlyScene2", code=src))
        .passed
    )


def test_design_tokens_own_all_styling():
    for pid in list(PLANS) + list(EXTRA_PLANS):
        src = render_source(compile_plan(plan(pid), None, "TutorlyX", "t"))
        assert not re.search(r"#[0-9a-fA-F]{6}|font=|color=", src)
    theme_src = (
        MANIFEST_PATH.parent / "runtime" / "tutorly_visuals" / "theme.py"
    ).read_text(encoding="utf-8")
    roles = set(re.findall(r'^\s+"(\w+)": ManimColor', theme_src, re.MULTILINE))
    assert roles == M.ids("emphasis")


# ------------------------------------------------------------------------------------------- rendering

_manim_ok = (
    importlib.util.find_spec("manim") is not None and shutil.which("latex") is not None
)


@pytest.mark.render
@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
@pytest.mark.parametrize(
    "pid",
    [
        "scene_2",
        "scene_4",
        "graph_demo",
        "tree_demo",
        "compare_demo",
        "wide_columns",
        "combine_demo",
    ],
)
def test_representative_templates_render(tmp_path, pid):
    from app.services.manim import ManimRenderer

    anim = compile_plan(plan(pid), None, "TutorlyX", "Render test")
    out = tmp_path / f"{pid}.mp4"
    result = ManimRenderer(quality="l", timeout_s=200).render(
        render_source(anim), "TutorlyX", out
    )
    assert result.success, result.stderr[-2500:]
    assert out.stat().st_size > 5000


@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
@pytest.mark.parametrize(
    "n_cols,value", [(2, "A B C D E"), (3, "A B C D"), (4, "A B C D E F")]
)
def test_layout_keeps_objects_apart_and_in_frame(n_cols, value):
    from manim import MovingCameraScene

    from app.services.visuals.runtime.tutorly_visuals import Stage
    from app.services.visuals.runtime.tutorly_visuals.layouts import compute

    st = Stage(MovingCameraScene(), title="", layout="split_view")
    for i in range(6):
        st.declare(f"p{i}", "item", "ABCDEF"[i]).visible = True
    for i in range(n_cols):
        o = st.declare(f"c{i}", "arrangement", value)
        o.visible, o.column = True, True
    for oid, pos in compute(st).items():
        st.get(oid).mob.move_to(pos)

    def boxes(prefix):
        return sorted(
            (o.mob.get_left()[0], o.mob.get_right()[0])
            for o in st.order
            if o.id.startswith(prefix)
        )

    for prefix in ("p", "c"):
        bx = boxes(prefix)
        assert all(a[1] < b[0] for a, b in zip(bx, bx[1:])), (
            f"{prefix} objects overlap: {bx}"
        )
        assert bx[0][0] > -7.1 and bx[-1][1] < 7.1, (
            f"{prefix} objects leave the frame: {bx}"
        )


@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
def test_several_sets_are_laid_out_side_by_side():
    from manim import MovingCameraScene

    from app.services.visuals.runtime.tutorly_visuals import Stage
    from app.services.visuals.runtime.tutorly_visuals.layouts import compute

    st = Stage(MovingCameraScene(), title="", layout="center_focus")
    st.declare("all", "region", "5! = 120").visible = True
    st.declare("valid", "region", "72").visible = True
    for oid, pos in compute(st).items():
        st.get(oid).mob.move_to(pos)
    a, v = st.get("all").mob, st.get("valid").mob
    assert a.get_right()[0] < v.get_left()[0]
    assert a.get_left()[0] > -7.1 and v.get_right()[0] < 7.1


@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
def test_layout_resolves_cross_category_overlaps():
    from manim import MovingCameraScene

    from app.services.visuals.runtime.tutorly_visuals import Stage
    from app.services.visuals.runtime.tutorly_visuals.layouts import compute

    st = Stage(MovingCameraScene(), title="", layout="center_focus")
    for oid, kind, value in (
        ("item", "item", "A"),
        ("formula", "formula", r"r = \frac{a\sqrt{3}}{6}"),
        ("label", "label", "promien"),
    ):
        st.declare(oid, kind, value).visible = True
    for oid, pos in compute(st).items():
        st.get(oid).mob.move_to(pos)
    visible = [st.get(oid).mob for oid in ("item", "formula", "label")]
    for i, first in enumerate(visible):
        for second in visible[i + 1 :]:
            separated = first.get_right()[0] + 0.05 < second.get_left()[0]
            separated |= second.get_right()[0] + 0.05 < first.get_left()[0]
            separated |= first.get_top()[1] + 0.05 < second.get_bottom()[1]
            separated |= second.get_top()[1] + 0.05 < first.get_bottom()[1]
            assert separated
