"""Plane figures and solids of revolution (the hexagon-rotated-about-its-side problem)."""

import copy
import importlib.util
import shutil

import pytest
import sympy

from app.schemas import ProblemIR, SolutionIR, VisualPlan
from app.services.validation import MathValidator
from app.services.validation.geometry_checks import tex_to_sympy
from app.services.validation.visual_validator import VisualPlanValidator
from app.services.visuals.compiler import compile_plan, render_source
from app.services.visuals.retrieval import retrieve
from app.services.visuals.runtime.tutorly_visuals import geometry as geo
from tests.fixtures import PROBLEM_IR
from tests.visual_fixtures import STEREO_PLANS

a = sympy.Symbol("a", positive=True)
V = VisualPlanValidator()
TEXT = "Oblicz objętość i pole powierzchni bryły obrotowej powstałej z obrotu sześciokąta foremnego o boku a wokół prostej zawierającej bok sześciokąta."


def hexagon_problem(**spec):
    return ProblemIR.model_validate({
        **PROBLEM_IR, "original_text": TEXT, "domain": "geometry", "subdomain": "stereometry",
        "problem_type": "solid_of_revolution", "enumeration_spec": None, "constraints": [],
        "relevant_concepts": ["solid_of_revolution", "regular_polygon", "pappus"],
        "objects": [{"id": "hexagon", "kind": "regular_polygon", "description": "regular hexagon with side a"}],
        "goal": {"kind": "compute", "description": "V and S", "target_quantity": "volume and surface", "answer_type": "expression"},
        "geometry_spec": {"solid": "regular_polygon", "params": ["n=6", "a=a"], "query": "revolution_volume",
                          "also": ["revolution_surface"], "points": ["A", "B"], **spec},
    })


def solution(final_expr, final_value):
    return SolutionIR.model_validate({
        "selected_method": "pappus",
        "steps": [{"id": "s1", "goal": "area", "method": "area", "expression": "3*sqrt(3)/2*a**2", "result_name": "area",
                   "claimed_value": "3*sqrt(3)*a**2/2", "explanation": "six equilateral triangles", "why_valid": "it follows from the previous step"}],
        "final_result": {"expression": final_expr, "value": final_value, "statement": "V, S"},
        "verification": {"strategy": "parts", "checks": []},
    })


# ----------------------------------------------------------------------------- exact geometry


def test_hexagon_revolution_is_exact():
    h = geo.build_solid("regular_polygon", ["n=6", "a=a"])
    r = geo.revolution([h.vertices[v] for v in h.base], h.vertices["A"], h.vertices["B"])
    assert sympy.simplify(r["volume"] - sympy.Rational(9, 2) * sympy.pi * a**3) == 0
    assert sympy.simplify(r["surface"] - 6 * sympy.sqrt(3) * sympy.pi * a**2) == 0
    assert sympy.simplify(r["area"] - 3 * sympy.sqrt(3) / 2 * a**2) == 0


def test_square_about_its_side_is_a_cylinder():
    s = geo.build_solid("square", ["a=2"])
    r = geo.revolution([s.vertices[v] for v in s.base], s.vertices["A"], s.vertices["B"])
    assert r["volume"] == 8 * sympy.pi  # pi r^2 h with r = h = 2
    assert r["surface"] == 16 * sympy.pi  # side 2*pi*r*h + two discs pi r^2


def test_axis_through_the_figure_is_rejected():
    h = geo.build_solid("regular_polygon", ["n=6", "a=1"])
    with pytest.raises(geo.GeometryError):
        geo.revolution([h.vertices[v] for v in h.base], h.vertices["A"], h.vertices["D"])


@pytest.mark.parametrize("kind,params,n", [("triangle_equilateral", ["a=a"], 3), ("right_triangle", ["a=3", "b=4"], 3),
                                           ("triangle", ["a=5", "b=4", "c=3"], 3), ("rectangle", ["a=2", "b=1"], 4),
                                           ("isosceles_trapezoid", ["a=6", "b=2", "h=3"], 4), ("regular_polygon", ["n=5", "a=1"], 5)])
def test_plane_figures(kind, params, n):
    f = geo.build_solid(kind, params)
    assert len(f.vertices) == n and geo.is_figure(kind)
    assert geo.polygon_area([f.vertices[v] for v in f.base]).is_positive


# ----------------------------------------------------------------------------- answer check


def test_both_answers_are_verified_independently():
    r = MathValidator().validate(hexagon_problem(), solution("(9*pi*a**3/2, 6*sqrt(3)*pi*a**2)", "(9*pi*a**3/2, 6*sqrt(3)*pi*a**2)"))
    assert r.passed, r.feedback()
    assert r.details["independent_checks"][0]["matches"]


def test_wrong_surface_is_caught():
    r = MathValidator().validate(hexagon_problem(), solution("(9*pi*a**3/2, 4*sqrt(3)*pi*a**2)", "(9*pi*a**3/2, 4*sqrt(3)*pi*a**2)"))
    assert "INDEPENDENT_MISMATCH" in {i.code for i in r.errors}


def test_symbolic_measure_labels():
    value, _ = tex_to_sympy(r"a\sqrt{3}", symbols={"a"})
    assert sympy.simplify(value - a * sympy.sqrt(3)) == 0
    assert tex_to_sympy(r"a\sqrt{3}") is None  # unknown letters are not checkable


# ----------------------------------------------------------------------------- visual plans


def plan(mutate=None):
    data = copy.deepcopy(STEREO_PLANS["hexagon_revolution"])
    if mutate:
        mutate(data)
    return VisualPlan.model_validate(data)


def test_reference_revolution_plan_is_valid():
    r = V.validate(plan(), problem=hexagon_problem())
    assert r.passed, r.feedback()
    assert not r.issues


def test_wrong_radius_label_is_rejected():
    def lie(d):
        d["beats"][1]["actions"][3]["values"] = [r"2a"]  # EA is a*sqrt(3)

    assert "MEASURE_MISMATCH" in {i.code for i in V.validate(plan(lie)).errors}


def test_axis_crossing_the_figure_is_rejected():
    def cross(d):
        d["objects"].append({"id": "AD", "type": "segment", "members": ["A", "D"]})
        d["beats"][1]["actions"].append({"operation": "create", "targets": ["AD"]})
        d["beats"][2]["actions"][0]["targets"] = ["hex", "AD"]

    assert "REVOLUTION_AXIS" in {i.code for i in V.validate(plan(cross)).errors}


def test_geometry_drawn_as_tokens_is_rejected():
    """The failure the user saw: the hexagon drawn as a labelled circle."""
    tokens = VisualPlan.model_validate({
        "scene_id": "s", "template": "problem_reveal", "layout": "horizontal_row",
        "objects": [{"id": "hexagon_2d", "type": "item", "value": "Sześciokąt"},
                    {"id": "axis_line", "type": "item", "value": "Oś"}],
        "beats": [{"id": "b", "purpose": "show", "actions": [{"operation": "create", "targets": ["hexagon_2d", "axis_line"]},
                                                            {"operation": "highlight", "targets": ["hexagon_2d"]}]}],
    })
    assert "GEOMETRY_WITHOUT_FIGURE" in {i.code for i in V.validate(tokens, problem=hexagon_problem()).errors}


def test_retrieval_offers_revolution_and_not_counting():
    ids = set(retrieve(hexagon_problem(), None, None).template_ids)
    assert {"solid_of_revolution", "plane_figure"} <= ids
    assert not ids & {"block_method", "permutation_counter", "graph_traversal", "arrangement_gallery"}


def test_revolution_compiles_to_threedscene_starting_flat():
    src = render_source(compile_plan(plan(), None, "TutorlyHex", "Bryła obrotowa"))
    assert "(ThreeDScene)" in src and "camera='top_view'" in src and "st.do('revolve', ['hex', 'AB']" in src


_manim_ok = importlib.util.find_spec("manim") is not None and shutil.which("latex") is not None


@pytest.mark.render
@pytest.mark.skipif(not _manim_ok, reason="Manim/LaTeX not installed")
def test_revolution_renders(tmp_path):
    from app.services.manim import ManimRenderer

    out = tmp_path / "hex.mp4"
    result = ManimRenderer(quality="l", timeout_s=300).render(render_source(compile_plan(plan(), None, "TutorlyHex", "t")), "TutorlyHex", out)
    assert result.success, result.stderr[-3000:]
    assert out.stat().st_size > 50000
