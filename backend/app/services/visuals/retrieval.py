"""Visual capability retrieval: pick only the templates/presets relevant to one scene.

Deterministic and simple on purpose (no embeddings): the problem, solution and scene are reduced to a set
of normalised tags, and each template is scored by how many of its `good_for` tags match. General-purpose
templates (formula_transform, summary, ...) are always available but rank after specific matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.lesson import SceneIR
from app.schemas.problem import ProblemIR
from app.schemas.solution import SolutionIR
from app.services.validation.concepts import normalize_concept
from app.services.visuals.manifest import Manifest, TemplateSpec, get_manifest

# Map vocabulary that appears in IRs onto the manifest's `good_for` tags.
TAG_ALIASES: dict[str, list[str]] = {
    "permutation": ["permutations", "arrangements"],
    "permutation_with_constraint": ["permutations", "constraints", "arrangements"],
    "arrangement": ["arrangements", "permutations"],
    "factorial": ["factorial", "permutations"],
    "multiplication_rule": ["multiplication_rule", "choices"],
    "not_adjacent": ["adjacency_constraints", "constraints"],
    "adjacent": ["adjacency_constraints", "constraints"],
    "adjacency": ["adjacency_constraints"],
    "block_method": ["block_method", "grouping", "adjacency_constraints"],
    "complement_counting": ["complement_counting", "forbidden_outcomes", "subtraction"],
    "subtraction": ["subtraction"],
    "combinatoric": ["permutations", "choices"],
    "case": ["case_analysis"],
    "case_analysis": ["case_analysis"],
    "gap_method": ["permutations", "positions", "constraints"],
    "graph": ["graphs"],
    "graph_theory": ["graphs"],
    "vertex": ["graphs"],
    "edge": ["graphs"],
    "shortest_path": ["shortest_path", "paths", "graphs"],
    "path": ["paths"],
    "bfs": ["traversal", "bfs"],
    "dfs": ["traversal", "dfs"],
    "traversal": ["traversal"],
    "eulerian": ["eulerian", "traversal"],
    "connected": ["connectivity"],
    "spanning_tree": ["trees", "graphs"],
    "tree": ["trees"],
    "probability": ["probability_trees"],
    "sequence": ["sequences"],
    "algebra": ["algebra"],
    "equation": ["algebra", "simplification"],
    "verification": ["verification"],
    # stereometry
    "geometry": ["geometry_3d"],
    "solid_geometry": ["stereometry", "solid_geometry"],
    "stereometry": ["stereometry", "solid_geometry"],
    "stereometria": ["stereometry", "solid_geometry"],
    "cube": ["cube", "stereometry"],
    "cuboid": ["cuboid", "stereometry"],
    "pyramid": ["pyramid", "stereometry"],
    "prism": ["prism", "stereometry"],
    "tetrahedron": ["tetrahedron", "stereometry"],
    "diagonal": ["diagonal", "distance"],
    "distance": ["distance"],
    "angle": ["angle"],
    "height": ["height"],
    "pythagorean_theorem": ["pythagorean_theorem", "right_triangle"],
    "pythagoras": ["pythagorean_theorem", "right_triangle"],
    "trigonometry": ["trigonometry", "angle"],
    "cross_section": ["cross_section"],
    "midpoint": ["midpoint"],
    "planimetry": ["planimetry", "geometry_2d"],
    "plane_geometry": ["planimetry", "geometry_2d"],
    "polygon": ["polygon", "planimetry"],
    "regular_polygon": ["regular_polygon", "polygon", "planimetry"],
    "hexagon": ["hexagon", "polygon", "planimetry"],
    "triangle": ["triangle", "planimetry"],
    "area": ["area"],
    "perimeter": ["perimeter"],
    "solid_of_revolution": ["solid_of_revolution", "revolution", "stereometry"],
    "revolution": ["solid_of_revolution", "revolution"],
    "rotation": ["rotation", "revolution"],
    "cylinder": ["cylinder", "solid_of_revolution"],
    "cone": ["cone", "solid_of_revolution"],
    "pappus": ["pappus", "solid_of_revolution"],
    "final_answer": ["final_answer", "summary"],
}

# Phrases in free text (goals, titles) that reveal an operation, EN + PL (accent-folded).
TEXT_HINTS: dict[str, list[str]] = {
    "adjacency_constraints": ["obok siebie", "next to each other", "adjacent", "sasiad"],
    "grouping": ["block", "blok", "glue", "sklej"],
    "internal_orders": ["internal order", "wewnatrz", "ab and ba", "ab i ba", "ab lub ba", "ab albo ba"],
    "complement_counting": ["subtract", "odejm", "complement", "dopelnien", "wszystkich minus"],
    "case_analysis": ["case", "przypad"],
    "final_answer": ["answer", "odpowiedz", "wynik koncowy", "final"],
    "summary": ["summary", "podsumow", "recap"],
    "positions": ["position", "miejsc", "pozycj", "gap", "przerw", "luk"],
    "choices": ["choice", "wybor", "mozliwosc"],
    "stereometry": ["szescian", "prostopadloscian", "ostroslup", "graniastoslup", "czworoscian", "cube", "pyramid", "prism", "cuboid"],
    "solid_of_revolution": ["bryl obrotow", "bryly obrotowej", "bryla obrotowa", "obrot", "solid of revolution", "rotat", "revolv"],
    "planimetry": ["szesciokat", "pieciokat", "trojkat", "kwadrat", "prostokat", "trapez", "romb", "hexagon", "triangle", "polygon", "wielokat"],
    "hexagon": ["szesciokat", "hexagon"],
    "diagonal": ["przekatn", "diagonal"],
    "angle": ["kat ", "kata", "nachylenia", "angle"],
    "distance": ["odleglosc", "dlugosc", "distance", "length"],
    "verification": ["all possible", "wszystkie mozliwe", "every arrangement", "kazde ustawienie"],
}

SPECIFIC_LIMIT = 6


@dataclass
class Capabilities:
    tags: list[str]
    templates: list[TemplateSpec]
    scores: dict[str, int] = field(default_factory=dict)

    @property
    def template_ids(self) -> list[str]:
        return [t.id for t in self.templates]

    def for_prompt(self, manifest: Manifest | None = None) -> dict[str, Any]:
        """The manifest subset shown to the visual planner."""
        m = manifest or get_manifest()
        ops = m.allowed_operations(self.template_ids)
        layouts = {t.default_layout for t in self.templates} | {"center_focus", "split_view"}
        cameras = {t.default_camera for t in self.templates} | {"wide_establishing", "focus_subject"}
        types = set().union(*(t.object_types for t in self.templates)) if self.templates else set()
        return {
            "templates": [
                {k: v for k, v in t.model_dump().items() if k in ("id", "description", "supports", "object_types", "default_layout", "default_camera")}
                for t in self.templates
            ],
            "operations": [e.model_dump() for e in m.operations if e.id in ops],
            "common_operations": m.common_operations,
            "object_types": [e.model_dump() for e in m.object_types if e.id in types | {"label", "formula"}],
            "layouts": [e.model_dump() for e in m.layouts if e.id in layouts],
            "cameras": [e.model_dump() for e in m.cameras if e.id in cameras],
            "emphasis": [e.model_dump() for e in m.emphasis],
        }


def _fold(text: str) -> str:
    from app.services.validation.concepts import fold

    return fold(text)


def extract_tags(problem: ProblemIR | None, solution: SolutionIR | None, scene: SceneIR | None) -> set[str]:
    raw: list[str] = []
    text: list[str] = []
    if problem is not None:
        raw += [problem.domain, problem.subdomain, problem.problem_type, *problem.relevant_concepts]
        raw += [c.kind for c in problem.constraints]
        if problem.enumeration_spec is not None:
            raw += ["arrangement"] + [c.type for c in problem.enumeration_spec.constraints]
        if problem.graph_spec is not None:
            raw += ["graph", problem.graph_spec.query]
        if problem.geometry_spec is not None:
            spec = problem.geometry_spec
            raw += [spec.solid, spec.query, *spec.also]
            raw.append("solid_of_revolution" if spec.query.startswith("revolution") else
                       ("planimetry" if spec.solid in ("regular_polygon", "triangle_equilateral", "right_triangle", "triangle",
                                                       "square", "rectangle", "isosceles_trapezoid") else "stereometry"))
    if solution is not None:
        steps = solution.steps
        if scene is not None and scene.solution_steps:
            steps = [s for s in solution.steps if s.id in scene.solution_steps] or steps
        raw += [solution.selected_method]
        for s in steps:
            raw += [s.method, *s.concepts_used]
            text.append(f"{s.goal} {s.explanation}")
    if scene is not None:
        raw += scene.concepts
        text += [scene.title, scene.learning_goal, *scene.visual_plan, *scene.narration_plan]

    tags: set[str] = set()
    for r in raw:
        if not r:
            continue
        norm = normalize_concept(r)
        tags.add(norm)
        for piece in [norm, *norm.split("_")]:
            tags.update(TAG_ALIASES.get(piece, []))
    folded = _fold(" ".join(text))
    for tag, hints in TEXT_HINTS.items():
        if any(h in folded for h in hints):
            tags.add(tag)
    if re.search(r"\b(final|ostateczn|koncow)", folded):
        tags.add("final_answer")
    return tags


def retrieve(
    problem: ProblemIR | None,
    solution: SolutionIR | None,
    scene: SceneIR | None,
    manifest: Manifest | None = None,
    limit: int = SPECIFIC_LIMIT,
) -> Capabilities:
    m = manifest or get_manifest()
    tags = extract_tags(problem, solution, scene)
    scores = {t.id: len(tags & set(t.good_for)) for t in m.templates}
    specific = sorted(
        (t for t in m.templates if not t.general and scores[t.id] > 0),
        key=lambda t: (-scores[t.id], m.templates.index(t)),
    )[:limit]
    general = [t for t in m.templates if t.general]
    return Capabilities(tags=sorted(tags), templates=specific + general, scores={t.id: scores[t.id] for t in specific + general})
