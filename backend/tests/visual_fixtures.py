"""Semantic visual plans for the permutation demo (what a good visual_planner answer looks like).

Story: five people occupy five positions → choices 5·4·3·2·1 → the A/B constraint becomes visible →
A and B merge into [AB] → four units are counted → [AB] opens into AB and BA → 2·4! forbidden
arrangements are carved out of all 5! and removed → 72 is emphasised.
"""

from __future__ import annotations

from typing import Any

PEOPLE = ["A", "B", "C", "D", "E"]


def _people(role_ab: str = "neutral") -> list[dict[str, Any]]:
    return [{"id": p, "type": "item", "value": p, "emphasis": role_ab if p in "AB" else "neutral"} for p in PEOPLE]


def _beat(bid: str, purpose: str, actions: list[dict], **kw) -> dict[str, Any]:
    return {"id": bid, "purpose": purpose, "actions": actions, **kw}


PLANS: dict[str, dict[str, Any]] = {
    "scene_1": {
        "scene_id": "scene_1",
        "template": "permutation_counter",
        "secondary_templates": ["problem_reveal"],
        "layout": "horizontal_row",
        "camera": "wide_establishing",
        "objects": _people()
        + [{"id": f"s{i}", "type": "slot", "value": str(i)} for i in range(1, 6)]
        + [{"id": "f_total", "type": "formula", "value": r"5 \cdot 4 \cdot 3 \cdot 2 \cdot 1 = 5! = 120"}],
        "beats": [
            _beat("scene_1_intro", "five_people_on_stage", [{"operation": "create", "targets": PEOPLE}]),
            _beat("scene_1_positions", "five_positions_to_fill", [{"operation": "create", "targets": [f"s{i}" for i in range(1, 6)]}]),
            _beat(
                "scene_1_choices", "choices_shrink_as_positions_fill",
                [{"operation": "fill_slots", "targets": [f"s{i}" for i in range(1, 6)], "results": ["f_total"],
                  "values": ["5", "4", "3", "2", "1", r"5 \cdot 4 \cdot 3 \cdot 2 \cdot 1 = 5! = 120"]}],
            ),
            _beat("scene_1_result", "all_arrangements_counted", [{"operation": "emphasize_result", "targets": ["f_total"]}]),
        ],
    },
    "scene_2": {
        "scene_id": "scene_2",
        "template": "block_method",
        "secondary_templates": ["constraint_reveal"],
        "layout": "horizontal_row",
        "camera": "wide_establishing",
        "objects": _people(),
        "beats": [
            _beat("scene_2_intro", "people_in_a_row", [{"operation": "create", "targets": PEOPLE}]),
            _beat(
                "scene_2_constraint", "adjacency_constraint_visible",
                [{"operation": "highlight", "targets": ["A", "B"], "emphasis": "forbidden"},
                 {"operation": "connect", "targets": ["A", "B"], "emphasis": "forbidden"}],
            ),
            _beat("scene_2_merge", "a_and_b_become_one_block",
                  [{"operation": "merge", "targets": ["A", "B"], "results": ["AB"], "values": ["[AB]"]}],
                  camera="follow_transform"),
            _beat(
                "scene_2_result", "count_the_four_units",
                [{"operation": "count", "targets": ["AB", "C", "D", "E"], "results": ["f_units"], "values": [r"4! = 24"]},
                 {"operation": "emphasize_result", "targets": ["f_units"]}],
                camera="wide_establishing",
            ),
        ],
    },
    "scene_3": {
        "scene_id": "scene_3",
        "template": "case_split",
        "secondary_templates": ["block_method", "formula_transform"],
        "layout": "horizontal_row",
        "camera": "wide_establishing",
        "objects": _people("transformation") + [{"id": "f_forb", "type": "formula", "value": r"2 \cdot 4!"}],
        "beats": [
            _beat("scene_3_intro", "recall_the_block",
                  [{"operation": "create", "targets": PEOPLE},
                   {"operation": "merge", "targets": ["A", "B"], "results": ["AB"], "values": ["[AB]"]}]),
            _beat("scene_3_result", "block_has_two_internal_orders",
                  [{"operation": "split", "targets": ["AB"], "results": ["case_ab", "case_ba"], "values": ["A B", "B A"]},
                   {"operation": "create", "targets": ["f_forb"]},
                   {"operation": "transform", "targets": ["f_forb"], "results": ["f_forb_val"], "values": [r"2 \cdot 4! = 48"], "emphasis": "forbidden"},
                   {"operation": "emphasize_result", "targets": ["f_forb_val"], "emphasis": "forbidden"}],
                  layout="split_view"),
        ],
    },
    "scene_4": {
        "scene_id": "scene_4",
        "template": "complement_counting",
        "secondary_templates": ["formula_transform", "summary"],
        "layout": "center_focus",
        "camera": "wide_establishing",
        "objects": [
            {"id": "all", "type": "region", "value": "5! = 120"},
            {"id": "f_diff", "type": "formula", "value": "120 - 48"},
        ],
        "beats": [
            _beat("scene_4_intro", "all_outcomes_then_forbidden_part",
                  [{"operation": "create", "targets": ["all"]},
                   {"operation": "partition", "targets": ["all"], "results": ["forb"], "values": [r"2 \cdot 4! = 48"]}]),
            _beat("scene_4_result", "remove_forbidden_keep_valid",
                  [{"operation": "remove", "targets": ["forb"], "emphasis": "forbidden"},
                   {"operation": "highlight", "targets": ["all"], "emphasis": "result"},
                   {"operation": "create", "targets": ["f_diff"]},
                   {"operation": "transform", "targets": ["f_diff"], "results": ["f_answer"], "values": ["120 - 48 = 72"]},
                   {"operation": "emphasize_result", "targets": ["f_answer"]}]),
        ],
    },
}


def plan_for(scene_id: str) -> dict[str, Any]:
    return PLANS[scene_id]


# Plans exercising the rest of the library (graphs, trees, comparison, spotlight, summary).
EXTRA_PLANS: dict[str, dict[str, Any]] = {
    "graph_demo": {
        "scene_id": "graph_demo",
        "template": "graph_traversal",
        "secondary_templates": ["graph_build", "highlight_path"],
        "layout": "graph_layout",
        "objects": [{"id": n, "type": "node", "value": n.upper()} for n in "abcde"]
        + [{"id": f"e_{u}{v}", "type": "edge", "members": [u, v]} for u, v in ["ab", "bc", "cd", "de", "ea", "bd"]]
        + [{"id": "f_d", "type": "formula", "value": "d(A, D) = 2"}],
        "beats": [
            _beat("g_build", "build_the_graph", [{"operation": "grow", "targets": list("abcde")},
                                                 {"operation": "grow", "targets": ["e_ab", "e_bc", "e_cd", "e_de", "e_ea", "e_bd"]}]),
            _beat("g_walk", "walk_from_a_to_d", [{"operation": "traverse", "targets": ["a", "b", "d"]}]),
            _beat("g_result", "distance_found", [{"operation": "create", "targets": ["f_d"]},
                                                 {"operation": "emphasize_result", "targets": ["f_d"]}]),
        ],
    },
    "tree_demo": {
        "scene_id": "tree_demo",
        "template": "counting_tree",
        "secondary_templates": ["formula_transform"],
        "layout": "tree_layout",
        "objects": [{"id": "root", "type": "node", "value": "*"}, {"id": "f_leaves", "type": "formula", "value": r"3 \cdot 2"}],
        "beats": [
            _beat("t_root", "first_choice", [{"operation": "create", "targets": ["root"]},
                                             {"operation": "branch", "targets": ["root"], "results": ["x_a", "x_b", "x_c"], "values": ["A", "B", "C"]}]),
            _beat("t_second", "second_choice_depends_on_first",
                  [{"operation": "branch", "targets": ["x_a"], "results": ["x_ab", "x_ac"], "values": ["B", "C"]},
                   {"operation": "branch", "targets": ["x_b"], "results": ["x_ba", "x_bc"], "values": ["A", "C"]},
                   {"operation": "branch", "targets": ["x_c"], "results": ["x_ca", "x_cb"], "values": ["A", "B"]}]),
            _beat("t_count", "count_the_leaves",
                  [{"operation": "count", "targets": ["x_ab", "x_ac", "x_ba", "x_bc", "x_ca", "x_cb"]},
                   {"operation": "create", "targets": ["f_leaves"]},
                   {"operation": "transform", "targets": ["f_leaves"], "results": ["f_six"], "values": [r"3 \cdot 2 = 6"]},
                   {"operation": "emphasize_result", "targets": ["f_six"]}]),
        ],
    },
    "compare_demo": {
        "scene_id": "compare_demo",
        "template": "comparison",
        "secondary_templates": ["spotlight", "summary"],
        "layout": "split_view",
        "objects": [{"id": "ord_ab", "type": "arrangement", "value": "A B C"}, {"id": "ord_ba", "type": "arrangement", "value": "B A C"},
                    {"id": "f_same", "type": "formula", "value": r"AB \neq BA"}],
        "beats": [
            _beat("c_compare", "two_orders_side_by_side", [{"operation": "compare", "targets": ["ord_ab", "ord_ba"]}]),
            _beat("c_focus", "they_differ_only_inside_the_pair", [{"operation": "focus", "targets": ["ord_ba"]},
                                                                  {"operation": "highlight", "targets": ["ord_ba"], "emphasis": "focus"},
                                                                  {"operation": "unfocus"}]),
            _beat("c_result", "so_both_count", [{"operation": "create", "targets": ["f_same"]},
                                                {"operation": "emphasize_result", "targets": ["f_same"]}]),
        ],
    },
}
EXTRA_PLANS["wide_columns"] = {
    # Regression: Gemini put two long arrangements in columns next to a block (they used to overlap).
    "scene_id": "wide_columns",
    "template": "case_split",
    "secondary_templates": ["block_method"],
    "layout": "split_view",
    "objects": [{"id": p, "type": "item", "value": p} for p in "AB"]
    + [{"id": "units", "type": "arrangement", "value": "(AB) C D E"}],
    "beats": [
        _beat("w_block", "glue", [{"operation": "create", "targets": ["A", "B"]},
                                  {"operation": "merge", "targets": ["A", "B"], "results": ["AB"], "values": ["[AB]"]},
                                  {"operation": "create", "targets": ["units"]}]),
        _beat("w_cases", "two_concrete_rows",
              [{"operation": "split", "targets": ["units"], "results": ["row1", "row2"], "values": ["A B C D E", "B A C D E"]},
               {"operation": "highlight", "targets": ["row2"], "emphasis": "focus"}]),
    ],
}
EXTRA_PLANS["combine_demo"] = {
    # Several formulas combine into one result (pattern Gemini uses: 4! = 24 and 2! = 2 -> 24 * 2 = 48).
    "scene_id": "combine_demo",
    "template": "block_method",
    "secondary_templates": ["formula_transform"],
    "layout": "horizontal_row",
    "objects": _people() + [{"id": "f_units", "type": "formula", "value": "4! = 24"}, {"id": "f_inside", "type": "formula", "value": "2! = 2"}],
    "beats": [
        _beat("k_block", "glue", [{"operation": "create", "targets": PEOPLE},
                                  {"operation": "merge", "targets": ["A", "B"], "results": ["AB"], "values": ["[AB]"]}]),
        _beat("k_parts", "two_factors", [{"operation": "create", "targets": ["f_units", "f_inside"]},
                                         {"operation": "transform", "targets": ["f_units", "f_inside"], "results": ["f_total"], "values": [r"24 \cdot 2 = 48"]},
                                         {"operation": "emphasize_result", "targets": ["f_total"], "emphasis": "forbidden"}]),
    ],
}


# ------------------------------------------------------------------ stereometry: cube diagonal and its angle
CUBE = list("ABCDEFGH")
STEREO_PLANS: dict[str, dict[str, Any]] = {
    "cube_demo": {
        "scene_id": "cube_demo",
        "template": "section_flatten",
        "secondary_templates": ["solid_reveal", "space_construction"],
        "layout": "space_3d",
        "camera": "three_quarter",
        "objects": [
            {"id": "cube", "type": "solid", "value": "cube", "params": ["a=4"], "members": CUBE},
            {"id": "AC", "type": "segment", "members": ["A", "C"], "emphasis": "active"},
            {"id": "CG", "type": "segment", "members": ["C", "G"], "emphasis": "active"},
            {"id": "AG", "type": "segment", "members": ["A", "G"], "emphasis": "focus"},
            {"id": "ACG", "type": "plane", "members": ["A", "C", "G"], "emphasis": "transformation"},
            {"id": "alpha", "type": "angle", "members": ["C", "A", "G"], "emphasis": "focus"},
            {"id": "f_ac", "type": "formula", "value": r"|AC| = \sqrt{4^2+4^2} = 4\sqrt{2}", "parent": "AC"},
            {"id": "f_tan", "type": "formula", "value": r"\tan\alpha = \frac{|CG|}{|AC|}", "parent": "alpha"},
        ],
        "beats": [
            _beat("s_cube", "the_cube_in_space", [{"operation": "create", "targets": ["cube"]}], camera="orbit"),
            _beat("s_base", "base_diagonal_by_pythagoras",
                  [{"operation": "create", "targets": ["AC"]},
                   {"operation": "measure", "targets": ["AC"], "values": [r"4\sqrt{2}"]},
                   {"operation": "create", "targets": ["f_ac"]}], camera="three_quarter"),
            _beat("s_diag", "space_diagonal_and_its_triangle",
                  [{"operation": "create", "targets": ["CG", "AG"]},
                   {"operation": "measure", "targets": ["CG"], "values": ["4"]},
                   {"operation": "create", "targets": ["ACG"]}]),
            _beat("s_flat", "lay_the_right_triangle_flat",
                  [{"operation": "flatten", "targets": ["ACG"], "results": ["panel"]},
                   {"operation": "measure", "targets": ["AG"], "values": [r"4\sqrt{3}"]}]),
            _beat("s_angle", "the_angle_from_the_triangle",
                  [{"operation": "create", "targets": ["alpha"]},
                   {"operation": "measure", "targets": ["alpha"], "values": [r"\alpha"]},
                   {"operation": "create", "targets": ["f_tan"]},
                   {"operation": "transform", "targets": ["f_tan"], "results": ["f_tan2"], "values": [r"\tan\alpha = \frac{4}{4\sqrt{2}} = \frac{\sqrt{2}}{2}"]},
                   {"operation": "emphasize_result", "targets": ["f_tan2"]}]),
        ],
    },
}

# ------------------------------------------------------------------ permutations: every arrangement of 4 people
GALLERY_PLANS: dict[str, dict[str, Any]] = {
    "gallery_demo": {
        "scene_id": "gallery_demo",
        "template": "arrangement_gallery",
        "secondary_templates": ["formula_transform"],
        "layout": "grid_layout",
        "objects": [{"id": p, "type": "item", "value": p} for p in "ABCD"]
        + [{"id": "f_all", "type": "formula", "value": r"4! = 24"}],
        "beats": [
            _beat("g_people", "four_people", [{"operation": "create", "targets": list("ABCD")}]),
            _beat("g_all", "every_possible_order", [{"operation": "enumerate", "targets": list("ABCD"), "results": ["gal"]}]),
            _beat("g_count", "how_many", [{"operation": "create", "targets": ["f_all"]},
                                          {"operation": "transform", "targets": ["f_all"], "results": ["f_valid"], "values": [r"3! \cdot 2 = 12"]},
                                          {"operation": "emphasize_result", "targets": ["f_valid"]}]),
        ],
    },
}

HEX = list("ABCDEF")
STEREO_PLANS["hexagon_revolution"] = {
    # The user's problem: a regular hexagon with side a rotated about the line containing side AB.
    "scene_id": "hexagon_revolution",
    "template": "solid_of_revolution",
    "secondary_templates": ["plane_figure", "formula_transform"],
    "layout": "space_3d",
    "camera": "top_view",
    "objects": [
        {"id": "hex", "type": "figure", "value": "regular_polygon", "params": ["n=6", "a=a"], "members": HEX},
        {"id": "AB", "type": "segment", "members": ["A", "B"], "emphasis": "focus"},
        {"id": "EA", "type": "segment", "members": ["E", "A"], "emphasis": "active"},
        {"id": "f_v", "type": "formula", "value": r"V = 2\pi \cdot \frac{\sqrt{3}}{2}a \cdot \frac{3\sqrt{3}}{2}a^2", "parent": "solid"},
        {"id": "f_s", "type": "formula", "value": r"S = 6\sqrt{3}\pi a^2", "parent": "solid"},
    ],
    "beats": [
        _beat("h_figure", "the_hexagon_flat", [{"operation": "create", "targets": ["hex"]}]),
        _beat("h_axis", "the_axis_is_side_AB",
              [{"operation": "create", "targets": ["AB"]},
               {"operation": "measure", "targets": ["AB"], "values": ["a"]},
               {"operation": "create", "targets": ["EA"]},
               {"operation": "measure", "targets": ["EA"], "values": [r"a\sqrt{3}"]}], camera="three_quarter"),
        _beat("h_revolve", "rotate_about_AB",
              [{"operation": "revolve", "targets": ["hex", "AB"], "results": ["solid"]}]),
        _beat("h_volume", "pappus_volume",
              [{"operation": "create", "targets": ["f_v"]},
               {"operation": "transform", "targets": ["f_v"], "results": ["f_v2"], "values": [r"V = \frac{9}{2}\pi a^3"]},
               {"operation": "create", "targets": ["f_s"]},
               {"operation": "emphasize_result", "targets": ["f_v2", "f_s"]}]),
    ],
}

STEREO_PLANS["pyramid_demo"] = {
    # Reusability: a different solid, a derived point (base centre) and a different right triangle.
    "scene_id": "pyramid_demo",
    "template": "section_flatten",
    "secondary_templates": ["space_construction"],
    "layout": "space_3d",
    "objects": [
        {"id": "pyr", "type": "solid", "value": "pyramid_square", "params": ["a=6", "h=4"], "members": ["A", "B", "C", "D", "S"]},
        {"id": "O", "type": "point", "value": "O", "members": ["A", "B", "C", "D"]},
        {"id": "SO", "type": "segment", "members": ["S", "O"], "emphasis": "active"},
        {"id": "OA", "type": "segment", "members": ["O", "A"], "emphasis": "active"},
        {"id": "SA", "type": "segment", "members": ["S", "A"], "emphasis": "focus"},
        {"id": "SOA", "type": "plane", "members": ["S", "O", "A"], "emphasis": "transformation"},
        {"id": "f_sa", "type": "formula", "value": r"|SA| = \sqrt{4^2 + (3\sqrt{2})^2}", "parent": "SOA"},
    ],
    "beats": [
        _beat("p_solid", "the_pyramid", [{"operation": "create", "targets": ["pyr"]}], camera="orbit"),
        _beat("p_height", "height_falls_to_the_centre",
              [{"operation": "create", "targets": ["O", "SO", "OA"]},
               {"operation": "measure", "targets": ["SO"], "values": ["4"]},
               {"operation": "measure", "targets": ["OA"], "values": [r"3\sqrt{2}"]}], camera="three_quarter"),
        _beat("p_flat", "the_right_triangle_SOA",
              [{"operation": "create", "targets": ["SA", "SOA"]},
               {"operation": "flatten", "targets": ["SOA"], "results": ["panel"]},
               {"operation": "create", "targets": ["f_sa"]},
               {"operation": "transform", "targets": ["f_sa"], "results": ["f_sa2"], "values": [r"|SA| = \sqrt{34}"]},
               {"operation": "measure", "targets": ["SA"], "values": [r"\sqrt{34}"]},
               {"operation": "emphasize_result", "targets": ["f_sa2"]}]),
    ],
}
