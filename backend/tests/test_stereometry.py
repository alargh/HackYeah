"""Stereometry and galleries: exact geometry, independent answer check, 3D plan validation, compilation, rendering."""

import copy
import importlib.util
import shutil

import pytest
import sympy

from app.schemas import ProblemIR, SolutionIR, VisualPlan
from app.services.validation import MathValidator
from app.services.validation.geometry_checks import tex_to_sympy
from app.services.validation.visual_validator import VisualPlanValidator
from app.services.visuals.compiler import compile_plan, gallery, render_source
from app.services.visuals.retrieval import retrieve
from app.services.visuals.runtime.tutorly_visuals import geometry as geo
from tests.fixtures import PROBLEM_IR
from tests.visual_fixtures import GALLERY_PLANS, STEREO_PLANS

V = VisualPlanValidator()
S2, S3 = sympy.sqrt(2), sympy.sqrt(3)


def plan(pid, mutate=None):
    data = copy.deepcopy({**STEREO_PLANS, **GALLERY_PLANS}[pid])
    if mutate:
        mutate(data)
    return VisualPlan.model_validate(data)


def errors(r):
    return {i.code for i in r.errors}


# ----------------------------------------------------------------------------------------- geometry


def test_cube_diagonals_and_angle_are_exact():
    c = geo.build_solid("cube", ["a=4"])
    v = c.vertices
    assert geo.distance(v["A"], v["C"]) == 4 * S2
    assert geo.distance(v["A"], v["G"]) == 4 * S3
    angle = geo.angle_line_plane(v["A"], v["G"], v["A"], v["B"], v["C"])
    assert sympy.simplify(sympy.tan(angle) - S2 / 2) == 0
    assert geo.is_right_angle(v["A"], v["C"], v["G"])
    assert len(c.edges) == 12 and len(c.faces) == 6 and geo.volume(c) == 64


def test_pyramid_and_derived_points():
    p = geo.build_solid("pyramid_square", ["a=6", "h=4"])
    o = geo.derived_point(p.vertices, ["A", "B", "C", "D"])
    assert list(o) == [3, 3, 0]
    assert geo.distance(p.vertices["S"], p.vertices["A"]) == sympy.sqrt(34)
    m = geo.resolve(p.vertices, "mid(B,C)")
    assert geo.distance(p.vertices["S"], m) == 5  # slant height
    assert geo.volume(p) == 48
    t = geo.build_solid("tetrahedron", ["a=2"])
    assert all(geo.distance(t.vertices[a], t.vertices[b]) == 2 for a, b in t.edges)


@pytest.mark.parametrize("kind,params", [("cube", []), ("cube", ["a=-1"]), ("cube", ["a=0"]), ("dodecahedron", ["a=1"])])
def test_bad_solids_are_rejected(kind, params):
    with pytest.raises(geo.GeometryError):
        geo.build_solid(kind, params)


def test_custom_vertex_labels():
    labels = ["A", "B", "C", "D", "A'", "B'", "C'", "D'"]
    c = geo.build_solid("cube", ["a=2"], labels)
    assert geo.distance(c.vertices["A"], c.vertices["C'"]) == 2 * S3


# ----------------------------------------------------------------------------------------- answer check


def _cube_problem(query="distance", points=("A", "G"), fn="none"):
    return ProblemIR.model_validate({
        **PROBLEM_IR, "domain": "geometry", "subdomain": "stereometry", "problem_type": "cube_diagonal",
        "enumeration_spec": None, "constraints": [], "relevant_concepts": ["pythagorean_theorem", "diagonal", "cube"],
        "objects": [{"id": "cube", "kind": "cube", "description": "cube with edge 4"}],
        "goal": {"kind": "compute", "description": "d", "target_quantity": "d", "answer_type": "real"},
        "geometry_spec": {"solid": "cube", "params": ["a=4"], "query": query, "points": list(points), "angle_function": fn},
    })


def _solution(expr, value):
    return SolutionIR.model_validate({
        "selected_method": "pythagoras",
        "steps": [{"id": "s1", "goal": "AC", "method": "pythagoras", "expression": "sqrt(4**2+4**2)", "result_name": "ac",
                   "claimed_value": "4*sqrt(2)", "explanation": "base diagonal", "why_valid": "it follows from the previous step"}],
        "final_result": {"expression": expr, "value": value, "statement": "x"},
        "verification": {"strategy": "coordinates", "checks": []},
    })


def test_space_diagonal_verified_independently():
    r = MathValidator().validate(_cube_problem(), _solution("sqrt(ac**2 + 4**2)", "4*sqrt(3)"))
    assert r.passed, r.feedback()
    assert r.details["independent_checks"][0]["method"] == "exact_geometry:distance"


def test_wrong_geometry_answer_is_caught():
    r = MathValidator().validate(_cube_problem(), _solution("4*sqrt(2)", "4*sqrt(2)"))
    assert "INDEPENDENT_MISMATCH" in errors(r)


def test_angle_answers_in_degrees_or_as_tangent():
    plane = ("A", "G", "A", "B", "C")
    deg = _solution("atan(sqrt(2)/2)*180/pi", "atan(sqrt(2)/2)*180/pi")
    assert MathValidator().validate(_cube_problem("angle_line_plane", plane), deg).passed
    tan = _solution("4/(4*sqrt(2))", "sqrt(2)/2")
    assert MathValidator().validate(_cube_problem("angle_line_plane", plane, "tan"), tan).passed


@pytest.mark.parametrize(
    "tex,value,degrees",
    [
        (r"4\sqrt{2}", 4 * S2, False),
        (r"|AG| = 4\sqrt{3}", 4 * S3, False),
        (r"\frac{\sqrt{2}}{2}", S2 / 2, False),
        (r"45^\circ", 45, True),
        (r"\sqrt{34}", sympy.sqrt(34), False),
        (r"2\cdot 3", 6, False),
    ],
)
def test_latex_measure_values(tex, value, degrees):
    got, deg = tex_to_sympy(tex)
    assert sympy.simplify(got - value) == 0 and deg == degrees


def test_symbolic_labels_are_not_numbers():
    assert tex_to_sympy(r"\alpha") is None and tex_to_sympy(r"a\sqrt{3}") is None


# ----------------------------------------------------------------------------------------- 3D plans


@pytest.mark.parametrize("pid", list(STEREO_PLANS))
def test_reference_3d_plans_are_valid(pid):
    r = V.validate(plan(pid))
    assert r.passed, r.feedback()


def test_wrong_measurement_is_rejected():
    def lie(d):
        d["beats"][1]["actions"][1]["values"] = [r"4\sqrt{3}"]  # AC is 4*sqrt(2)

    assert "MEASURE_MISMATCH" in errors(V.validate(plan("cube_demo", lie)))


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda d: d["objects"].append({"id": "x", "type": "item", "value": "A"}), "MIXED_2D_3D"),
        (lambda d: d.update(layout="center_focus"), "MIXED_2D_3D"),
        (lambda d: d["objects"].append({"id": "XY", "type": "segment", "members": ["A", "Z"]}), "UNKNOWN_POINT"),
        (lambda d: d["objects"][0].update(params=["b=4"]), "BAD_SOLID"),
        (lambda d: d["objects"].append(dict(d["objects"][0], id="cube2")), "SOLID_COUNT"),
        (lambda d: d["beats"][3]["actions"][0].update(targets=["AG"]), "BAD_TARGET_TYPE"),
    ],
)
def test_3d_plan_errors(mutate, code):
    assert code in errors(V.validate(plan("cube_demo", mutate)))


def test_depth_cue_and_2d_camera_rules():
    def flat(d):
        d["beats"][0]["camera"] = "three_quarter"

    r = V.validate(plan("cube_demo", flat))
    assert r.passed and "NO_DEPTH_CUE" in {i.code for i in r.issues}
    gal = plan("gallery_demo", lambda d: d["beats"][0].update(camera="orbit"))
    assert "CAMERA_3D_IN_2D" in errors(V.validate(gal))


def test_3d_compiles_to_threedscene_with_orbit_and_solid_first():
    anim = compile_plan(plan("cube_demo"), None, "TutorlyCube", "Sześcian")
    src = render_source(anim)
    assert "class TutorlyCube(ThreeDScene)" in src and "Stage3D(self" in src
    assert src.index("st.declare('cube'") < src.index("st.declare('AC'")
    presets = [s.params.get("preset") for s in anim.steps if s.primitive == "camera"]
    assert presets[:2] == ["orbit", "orbit_stop"] and "three_quarter" in presets
    assert [s.primitive for s in anim.steps if s.beat == "s_flat"][0] == "flatten"


def test_stereometry_retrieval():
    ids = set(retrieve(_cube_problem(), None, None).template_ids)
    assert {"solid_reveal", "space_construction", "section_flatten"} <= ids
    assert not ids & {"permutation_counter", "block_method", "graph_traversal"}


# ----------------------------------------------------------------------------------------- gallery


def _four_people(constraint="adjacent"):
    return ProblemIR.model_validate({**PROBLEM_IR, "enumeration_spec": {
        "kind": "permutation", "items": list("ABCD"), "constraints": [{"type": constraint, "items": ["A", "B"]}]}})


def test_gallery_is_classified_by_python():
    arrangements, flags, total, valid = gallery(list("ABCD"), _four_people())
    assert len(arrangements) == 24 and total == 24 and valid == 12 and sum(flags) == 12
    assert flags[arrangements.index("A B C D")] and not flags[arrangements.index("A C B D")]
    big, flags5, total5, valid5 = gallery(list("ABCDE"), None)
    assert len(big) == 24 and total5 == 120 and valid5 == 120 and all(flags5)


def test_gallery_compiles_with_flags():
    anim = compile_plan(plan("gallery_demo"), None, "TutorlyGallery", "t", _four_people())
    step = next(s for s in anim.steps if s.primitive == "enumerate")
    assert step.params["valid_total"] == 12 and len(step.params["arrangements"]) == 24
    assert V.validate(plan("gallery_demo")).passed


def test_gallery_retrieval_for_small_permutation_problems():
    assert "arrangement_gallery" in retrieve(_four_people(), None, None).template_ids


# ----------------------------------------------------------------------------------------- rendering

_manim_ok = importlib.util.find_spec("manim") is not None and shutil.which("latex") is not None


@pytest.mark.render
@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
@pytest.mark.parametrize("pid", ["cube_demo", "pyramid_demo", "gallery_demo"])
def test_examples_render(tmp_path, pid):
    from app.services.manim import ManimRenderer

    anim = compile_plan(plan(pid), None, "TutorlyX", "Render test", _four_people())
    out = tmp_path / f"{pid}.mp4"
    result = ManimRenderer(quality="l", timeout_s=300).render(render_source(anim), "TutorlyX", out)
    assert result.success, result.stderr[-3000:]
    assert out.stat().st_size > 20000
