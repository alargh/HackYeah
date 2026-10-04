"""Round solids, extra inscribed solids, teaching-depth and text-hygiene rules, live job rows."""

import copy

import pytest
import sympy

from app.schemas import ProblemIR, ScopeIR, SolutionIR, VisualPlan
from app.services.validation.independent import evaluate_geometry
from app.services.validation.language import check_texts, garbled_words, spoken
from app.services.validation.scope_validator import ScopeValidator
from app.services.validation.visual_validator import VisualPlanValidator
from app.services.visuals.compiler import compile_plan, render_source
from app.services.visuals.runtime.tutorly_visuals import geometry as geo
from tests.fixtures import PROBLEM_IR
from tests.visual_fixtures import STEREO_PLANS

V = VisualPlanValidator()
pi = sympy.pi


# ------------------------------------------------------------------------------ round solids


@pytest.mark.parametrize(
    "kind,params,volume,surface",
    [
        ("cylinder", ["r=2", "h=5"], 20 * pi, 28 * pi),
        ("cone", ["r=3", "h=4"], 12 * pi, 24 * pi),
        ("sphere", ["r=3"], 36 * pi, 36 * pi),
        (
            "frustum",
            ["r1=3", "r2=1", "h=3"],
            13 * pi,
            10 * pi + 4 * pi * sympy.sqrt(13),
        ),
        ("cube", ["a=2"], 8, 24),
    ],
)
def test_round_solid_measures(kind, params, volume, surface):
    s = geo.build_solid(kind, params)
    assert sympy.simplify(geo.volume(s) - volume) == 0
    assert sympy.simplify(geo.surface_area(s) - surface) == 0


def test_round_solid_points_and_symbolic_radius():
    cyl = geo.build_solid("cylinder", ["r=2", "h=5"])
    assert geo.distance(cyl.vertices["A"], cyl.vertices["B"]) == 4  # diameter
    assert geo.distance(cyl.vertices["A"], cyl.vertices["D"]) == sympy.sqrt(
        41
    )  # axial section diagonal
    cone = geo.build_solid("cone", ["r=r", "h=h"])
    assert (
        sympy.simplify(
            geo.distance(cone.vertices["A"], cone.vertices["S"])
            - sympy.sqrt(cone.dims["r"] ** 2 + cone.dims["h"] ** 2)
        )
        == 0
    )
    lo, hi = geo.bounding_box(geo.build_solid("sphere", ["r=2"]))
    assert list(lo) == [-2, -2, -2] and list(hi) == [2, 2, 2]


def _problem(spec):
    return ProblemIR.model_validate(
        {
            **PROBLEM_IR,
            "domain": "geometry",
            "subdomain": "stereometry",
            "problem_type": "round_solid",
            "enumeration_spec": None,
            "constraints": [],
            "geometry_spec": spec,
        }
    )


def test_surface_area_query_is_computed_independently():
    p = _problem(
        {
            "solid": "cone",
            "params": ["r=3", "h=4"],
            "query": "volume",
            "also": ["surface_area", "lateral_area"],
        }
    )
    assert evaluate_geometry(p.geometry_spec) == [12 * pi, 24 * pi, 15 * pi]


def _cyl_plan(extra=None):
    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"] = [
        {
            "id": "walec",
            "type": "solid",
            "value": "cylinder",
            "params": ["r=2", "h=4"],
            "members": [],
        },
        {"id": "AD", "type": "segment", "members": ["A", "D"]},
        {"id": "f_v", "type": "formula", "value": r"V = \pi r^2 h", "parent": "walec"},
    ] + (extra or [])
    data["beats"] = [
        {
            "id": "b1",
            "narration_event": "show",
            "purpose": "see the cylinder",
            "camera": "orbit",
            "actions": [{"operation": "create", "targets": ["walec"]}],
        },
        {
            "id": "b2",
            "narration_event": "diag",
            "purpose": "axial section diagonal",
            "actions": [
                {"operation": "create", "targets": ["AD"]},
                {"operation": "measure", "targets": ["AD"], "values": [r"4\sqrt{2}"]},
                {"operation": "create", "targets": ["f_v"]},
                {"operation": "emphasize_result", "targets": ["f_v"]},
            ],
        },
    ]
    return data


def test_cylinder_plan_is_valid():
    plan = VisualPlan.model_validate(_cyl_plan())
    r = V.validate(plan)
    assert r.passed, r.feedback()


def test_inscribed_sphere_shares_the_scene():
    extra = [
        {"id": "m", "type": "point", "members": ["O", "O1"]},
        {
            "id": "kula",
            "type": "solid",
            "value": "sphere",
            "params": ["at=m", "r=2"],
            "members": ["K", "P", "Q", "T"],
        },
        {"id": "KT", "type": "segment", "members": ["K", "T"]},
    ]
    r = V.validate(VisualPlan.model_validate(_cyl_plan(extra)))
    assert r.passed, r.feedback()
    # labels must not collide, extra solids must be round
    clash = copy.deepcopy(extra)
    clash[1][
        "members"
    ] = []  # default sphere labels O, A, B, N clash with the cylinder's: primed instead
    clash[2]["members"] = ["O'", "N"]
    r = V.validate(VisualPlan.model_validate(_cyl_plan(clash)))
    assert r.passed, r.feedback()
    assert "LABELS_RENAMED" in {i.code for i in r.issues}
    assert geo.free_labels("sphere", [], {"O", "A", "B"}) == ["O'", "A'", "B'", "N"]
    cube = copy.deepcopy(extra)
    cube[1].update(value="cube", params=["a=1"], members=list("ABCDEFGH"))
    assert "SOLID_COUNT" in {
        i.code for i in V.validate(VisualPlan.model_validate(_cyl_plan(cube))).errors
    }


def test_geometry_rejects_points_outside_the_declared_solid():
    result = V.validate(
        VisualPlan.model_validate(
            _cyl_plan(
                [
                    {"id": "far", "type": "point", "params": ["xyz=0,0,10"]},
                ]
            )
        )
    )
    assert "POINT_OUTSIDE_GEOMETRY" in {i.code for i in result.errors}


def test_inscribed_relation_requires_tangency():
    result = V.validate(
        VisualPlan.model_validate(
            _cyl_plan(
                [
                    {"id": "m", "type": "point", "members": ["O", "O1"]},
                    {
                        "id": "kula",
                        "type": "solid",
                        "value": "sphere",
                        "params": ["at=m", "fit=inscribed", "r=1"],
                        "members": ["K", "P", "Q", "T"],
                    },
                ]
            )
        )
    )
    assert "INVALID_FIT" in {i.code for i in result.errors}


def test_attached_solid_is_declared_after_its_point():
    from app.services.visuals.compiler import _declaration_order

    objs = [
        {"id": "kula", "type": "solid", "params": ["at=m", "r=2"]},
        {"id": "walec", "type": "solid", "params": ["r=2", "h=4"]},
        {"id": "m", "type": "point", "params": []},
        {"id": "f", "type": "formula", "params": []},
    ]
    order = [o["id"] for o in _declaration_order([objs[1], objs[2], objs[0], objs[3]])]
    assert order == ["walec", "m", "kula", "f"]


# ------------------------------------------------------------------------------ teaching depth


def _sol(steps):
    return SolutionIR.model_validate(
        {
            "selected_method": "counting",
            "steps": steps,
            "final_result": {"expression": "6", "value": "6", "statement": "6"},
            "verification": {"strategy": "x", "checks": []},
        }
    )


def _step(i, method, goal="g", concepts=(), explanation="e"):
    return {
        "id": f"s{i}",
        "goal": goal,
        "method": method,
        "expression": "6",
        "result_name": f"r{i}",
        "claimed_value": "6",
        "explanation": explanation, "why_valid": "it follows from the previous step",
        "concepts_used": list(concepts),
    }


OPEN = ScopeIR.model_validate({"mode": "open", "scope_sufficient": True})


def test_named_result_without_derivation_is_rejected():
    sol = _sol(
        [
            _step(
                1,
                "stirling_numbers",
                "partition into 2 groups",
                ["stirling_second_kind"],
            )
        ]
    )
    r = ScopeValidator().validate_solution(sol, OPEN)
    assert "SHORTCUT_NOT_EXPLAINED" in {i.code for i in r.errors}


def test_named_result_after_derivation_is_fine():
    sol = _sol(
        [
            _step(
                1,
                "derive_stirling",
                "build S(4,2) by hand: where does element 4 go",
                ["stirling_second_kind"],
            ),
            _step(2, "stirling_numbers", "use it", ["stirling_second_kind"]),
        ]
    )
    r = ScopeValidator().validate_solution(sol, OPEN)
    assert "SHORTCUT_NOT_EXPLAINED" not in {i.code for i in r.issues}


def test_named_result_allowed_by_the_learner():
    scope = ScopeIR.model_validate(
        {
            "mode": "restricted",
            "allowed_concepts": ["inclusion_exclusion"],
            "scope_sufficient": True,
        }
    )
    sol = _sol([_step(1, "inclusion_exclusion", "count", ["inclusion_exclusion"])])
    assert "SHORTCUT_NOT_EXPLAINED" not in {
        i.code for i in ScopeValidator().validate_solution(sol, scope).issues
    }


# ------------------------------------------------------------------------------ text hygiene


def test_garbled_polish_is_detected():
    assert garbled_words("Sp3jrzmy na sześcian", "pl") == ["Sp3jrzmy"]
    assert garbled_words("Wysokoőć ostrosłupa", "pl") == ["Wysokoőć"]
    assert garbled_words("krawędŹ leży", "pl") == ["krawędŹ"]
    assert garbled_words("Punkty A1, B2 i x2 leżą na krawędzi ściany", "pl") == []
    r = check_texts({"n1": "Sp3jrzmy", "n2": "Dobrze"}, "pl", "narration:x")
    assert not r.passed and r.errors[0].location == "n1"


def test_spoken_text_for_the_voice():
    assert (
        spoken(r"V = 9/2·π·a³ i kąt 30°", "pl")
        == "⟪V⟫ = 9 przez 2 razy pi razy a do sześcianu i kąt 30 stopni"
    )
    assert spoken(r"√3 \approx 1,73", "en").startswith("the square root of 3")


def test_garbled_labels_fail_the_visual_plan():
    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"].append({"id": "lbl", "type": "label", "value": "Przekątna śCiany"})
    data["objects"].append({"id": "lbl2", "type": "label", "value": "Prz3kątna"})
    prob = ProblemIR.model_validate({**PROBLEM_IR, "language": "pl"})
    r = V.validate(VisualPlan.model_validate(data), problem=prob)
    assert "GARBLED_TEXT" in {i.code for i in r.errors}


# ------------------------------------------------------------------------------ live jobs


def test_jobs_are_visible_while_running(settings):
    from app.services.pipeline import store
    from tests.test_pipeline import _new_lesson

    lid = _new_lesson()
    job = store.start_job(lid, "render", scene_id="scene_1", model="manim")
    with store.session_scope() as s:
        from app.models import GenerationJob

        row = s.get(GenerationJob, job)
        assert row.status == "RUNNING" and row.finished_at is None
    store.finish_job(job, "COMPLETED")
    with store.session_scope() as s:
        row = s.get(GenerationJob, job)
        assert (
            row.status == "COMPLETED"
            and row.duration_ms is not None
            and row.finished_at is not None
        )


def test_interrupted_running_jobs_are_closed_on_startup(settings):
    from app.models import GenerationJob
    from app.services.pipeline import store
    from app.workers.jobs import recover_interrupted
    from tests.test_pipeline import _new_lesson

    lid = _new_lesson()
    job = store.start_job(lid, "visual_plan", scene_id="scene_2")
    recover_interrupted()
    with store.session_scope() as s:
        assert s.get(GenerationJob, job).status == "FAILED"


def test_tuple_answers_written_with_tuple():
    from app.services.validation import expressions as ex

    assert ex.equal(
        ex.evaluate("Tuple(54*pi, 36*pi, 3/2)"), ex.evaluate("(54*pi, 36*pi, 3/2)")
    )


def test_board_notes_are_plain_text():
    pytest.importorskip("manim")
    from app.services.visuals.runtime.tutorly_visuals.board import plain

    assert plain(r"skracamy \pi") == "skracamy π"
    assert plain(r"$a^2 \cdot \sqrt{3}$") == "a² · √3"


def test_polish_voice_spells_variables_and_reads_cardinals():
    from app.services.tts import _say_letters
    from app.services.validation.language import letters_as_words

    s = spoken("Wysokość h wynosi 6. Promień to ha razy 3/2, a punkt A leży w O.", "pl")
    ssml = _say_letters(s, "pl")
    assert "<say-as interpret-as='characters'>h</say-as>" in ssml  # not "hektary"
    assert "<say-as interpret-as='cardinal'>6</say-as>." in ssml  # not "szóstą"
    assert "3 przez 2" in ssml  # not "trzeci lutego"
    assert (
        "<say-as interpret-as='characters'>A</say-as>" in ssml and " a punkt" in ssml
    )  # "a" is a word
    assert letters_as_words(s, "pl").startswith("Wysokość ha wynosi 6.")


def test_autofix_repairs_mechanical_plan_slips():
    from app.services.validation.visual_validator import ARITY
    from app.services.visuals.autofix import autofix

    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["beats"][1]["actions"].insert(
        0, {"operation": "highlight", "targets": ["CG"]}
    )  # CG not created yet
    for b in data["beats"]:
        b["camera"] = "three_quarter"
    plan = VisualPlan.model_validate(data)
    assert {"NOT_ON_STAGE", "TOO_MANY_CAMERA_MOVES"} <= {
        i.code for i in V.validate(plan).errors
    }
    fixed, notes = autofix(plan, ARITY, 3)
    assert notes and V.validate(fixed).passed, V.validate(fixed).feedback()


@pytest.mark.parametrize(
    "text, expected",
    [
        (r"a\sqrt{3}/2", sympy.sqrt(3) * sympy.Symbol("a", positive=True) / 2),
        (r"\frac{a}{2}", sympy.Symbol("a", positive=True) / 2),
        (r"3\sqrt{2}", 3 * sympy.sqrt(2)),
        ("2.5", sympy.Rational(5, 2)),
        (r"2\cdot\pi", 2 * sympy.pi),
    ],
)
def test_latex_dimensions_are_understood(text, expected):
    assert sympy.simplify(geo._num(text) - expected) == 0


def test_autofix_reorders_revolve_targets():
    from app.services.validation.visual_validator import ARITY
    from app.services.visuals.autofix import autofix

    data = copy.deepcopy(STEREO_PLANS["hexagon_revolution"])
    for b in data["beats"]:
        for a in b["actions"]:
            if a["operation"] == "revolve":
                a["targets"] = list(reversed(a["targets"]))
    plan = VisualPlan.model_validate(data)
    assert "BAD_TARGET_TYPE" in {i.code for i in V.validate(plan).errors}
    fixed, _ = autofix(plan, ARITY, 3)
    assert V.validate(fixed).passed, V.validate(fixed).feedback()


# ------------------------------------------------------------------------------ four balls in 3D


def four_balls_plan():
    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"] = [
        {
            "id": "centres",
            "type": "solid",
            "value": "tetrahedron",
            "params": [],
            "members": ["S1", "S2", "S3", "S4"],
            "emphasis": "secondary",
        },
        *(
            {
                "id": f"kula{i}",
                "type": "solid",
                "value": "sphere",
                "params": [f"at=S{i}", "r=a/2"],
                "members": [f"K{i}"],
            }
            for i in range(1, 5)
        ),
        {"id": "top", "type": "point", "members": [], "params": ["xyz=1/2,0,1"]},
        {"id": "f_d", "type": "formula", "value": r"d = R + h", "parent": "centres"},
    ]
    data["beats"] = [
        {
            "id": "b1",
            "narration_event": "balls",
            "purpose": "four balls",
            "camera": "orbit",
            "actions": [
                {
                    "operation": "create",
                    "targets": ["centres", "kula1", "kula2", "kula3", "kula4"],
                }
            ],
        },
        {
            "id": "b2",
            "narration_event": "d",
            "purpose": "distance",
            "actions": [
                {"operation": "create", "targets": ["f_d"]},
                {"operation": "emphasize_result", "targets": ["f_d"]},
            ],
        },
    ]
    return data


def test_four_balls_stay_in_3d():
    from app.services.validation.visual_validator import ARITY
    from app.services.visuals.autofix import autofix

    plan, notes = autofix(
        VisualPlan.model_validate(four_balls_plan()), ARITY, 3
    )  # as the pipeline does
    assert any("symbolic" in n for n in notes)
    r = V.validate(plan)
    assert r.passed, (
        r.feedback()
    )  # tetrahedron got a symbolic edge, sphere members filled in
    pts = {}
    p = geo.derived_point(pts, [], ["xyz=1/2,0,a"])
    assert list(p) == [sympy.Rational(1, 2), 0, sympy.Symbol("a", positive=True)]


def test_fallback_code_for_3d_plan_must_be_3d():
    from app.schemas.generation import ManimCode
    from app.services.validation.manim_validator import ManimValidator

    plan = VisualPlan.model_validate(four_balls_plan())
    flat = "from manim import *\n\nclass S1(Scene):\n    def construct(self):\n        # EVENT: balls\n        self.add(Circle())\n        # EVENT: d\n        self.wait(1)\n"
    r = ManimValidator().validate(
        ManimCode(scene_id="x", class_name="S1", code=flat), plan
    )
    assert "NEEDS_3D_SCENE" in {i.code for i in r.errors}
    solid = flat.replace("(Scene)", "(ThreeDScene)").replace(
        "Circle()", "Sphere(radius=1)"
    )
    r = ManimValidator().validate(
        ManimCode(scene_id="x", class_name="S1", code=solid), plan
    )
    assert "NEEDS_3D_SCENE" not in {i.code for i in r.issues}


# ------------------------------------------------------------------------------ curriculum level


def test_out_of_curriculum_terms():
    from app.services.validation.curriculum import out_of_curriculum

    assert [w for w, _ in out_of_curriculum("Linie i punkty antypodyczne")] == [
        "antypodyczne"
    ]
    assert out_of_curriculum("Zależność liniowa wektorów")
    assert out_of_curriculum("Obliczamy pole powierzchni całkowitej stożka") == []
    r = check_texts(
        {"t": "punkty antypodyczne"}, "pl", "scene:x", OPEN, curriculum=True
    )
    assert "OUT_OF_CURRICULUM" in {i.code for i in r.errors}
    opted_in = ScopeIR.model_validate(
        {
            "mode": "restricted",
            "allowed_concepts": ["antipodal_points"],
            "user_scope_text": "znam punkty antypodyczne",
            "scope_sufficient": True,
        }
    )
    assert check_texts(
        {"t": "punkty antypodyczne"}, "pl", "scene:x", opted_in, curriculum=True
    ).passed


def test_stirling_numbers_are_evaluated_and_compared_by_value():
    from app.services.validation import expressions as ex

    assert ex.evaluate("Stirling2(4, 2)") == 7
    v = ex.evaluate("factorial(k-1) * Stirling2(k+1, k-1)")
    right = ex.evaluate("factorial(k-1) * (binomial(k+1, 3) + 3 * binomial(k+1, 4))")
    wrong = ex.evaluate("factorial(k-1) * (binomial(k+1, 4) + 3 * binomial(k+1, 3))")
    assert ex.equal(v, right)
    assert not ex.equal(v, wrong)
    assert ex.counterexample(v, wrong).startswith("for k=")


# ------------------------------------------------------------------------------ where formulas come from


def test_3d_formula_needs_a_visible_source():
    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"][6].pop("parent")  # f_ac
    assert "FORMULA_WITHOUT_SOURCE" in {i.code for i in V.validate(VisualPlan.model_validate(data)).errors}
    data["objects"][6]["parent"] = "CG"  # CG is only created in the next beat
    assert "SOURCE_NOT_SHOWN" in {i.code for i in V.validate(VisualPlan.model_validate(data)).errors}


def test_autofix_attributes_formula_to_the_last_shown_segment():
    from app.services.validation.visual_validator import ARITY
    from app.services.visuals.autofix import autofix

    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    for o in data["objects"]:
        o.pop("parent", None)
    fixed, notes = autofix(VisualPlan.model_validate(data), ARITY, 3)
    parents = {o.id: o.parent for o in fixed.objects if o.type == "formula"}
    assert parents["f_ac"] == "AC" and parents["f_tan"] == "alpha"
    assert V.validate(fixed).passed, V.validate(fixed).feedback()


def test_combined_lengths_need_a_cross_section():
    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"] = [o for o in data["objects"] if o["id"] != "ACG"]
    data["objects"][-1]["parent"] = "CG"  # f_tan read from CG and AC: two lengths, no section
    for b in data["beats"]:
        b["actions"] = [a for a in b["actions"] if a["operation"] != "flatten" and "ACG" not in a["targets"]]
        if not b["actions"]:
            b["actions"] = [{"operation": "highlight", "targets": ["cube"]}]
    data["beats"][-1]["actions"] = [a for a in data["beats"][-1]["actions"] if "alpha" not in a["targets"]]
    codes = {i.code for i in V.validate(VisualPlan.model_validate(data)).errors}
    assert "NO_SECTION" in codes


def test_prune_keeps_the_valid_part_of_a_plan():
    from app.services.visuals.autofix import prune

    data = copy.deepcopy(STEREO_PLANS["cube_demo"])
    data["objects"].append({"id": "Z", "type": "point", "members": ["A", "nowhere"]})
    data["objects"].append({"id": "AZ", "type": "segment", "members": ["A", "Z"]})
    data["beats"][2]["actions"].append({"operation": "create", "targets": ["Z", "AZ"]})
    plan = VisualPlan.model_validate(data)
    r = V.validate(plan)
    assert not r.passed
    pruned, notes = prune(plan, r.issues)
    assert {"Z", "AZ"}.isdisjoint({o.id for o in pruned.objects})
    assert V.validate(pruned).passed, V.validate(pruned).feedback()


@pytest.mark.parametrize(
    "raw, shown",
    [(r"\text{[AB]}", "[AB]"), (r"N_{\text{all}}", "N_all"), ("$x$", "x"), (r"2 \cdot 3", "2 · 3"), ("[AB]", "[AB]")],
)
def test_text_labels_never_show_tex_source(raw, shown):
    from app.services.visuals.runtime.tutorly_visuals.primitives import plain

    assert plain(raw) == shown
