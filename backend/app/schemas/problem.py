"""ProblemIR: the structured, solution-free representation of a mathematical problem."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IRModel(BaseModel):
    """Base for all LLM-produced IRs: tolerant of unknown keys, strict on types."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class MathObject(IRModel):
    id: str = Field(description="Short identifier used across the lesson, e.g. 'A' or 'people'")
    kind: str = Field(description="e.g. person, set, number, graph, vertex, function")
    description: str
    properties: list[str] = Field(default_factory=list)


class Relation(IRModel):
    id: str
    kind: str = Field(description="e.g. arrangement_of, element_of, adjacent_to")
    subjects: list[str] = Field(default_factory=list, description="MathObject ids involved")
    description: str


class Constraint(IRModel):
    id: str
    kind: str = Field(description="e.g. not_adjacent, distinct, at_position")
    subjects: list[str] = Field(default_factory=list)
    description: str
    formal: str | None = Field(default=None, description="Optional formal statement")


class Goal(IRModel):
    kind: Literal["count", "compute", "prove", "find", "optimize", "decide", "other"]
    description: str
    target_quantity: str = Field(description="What exactly must be found, e.g. 'number of valid arrangements'")
    answer_type: Literal["integer", "rational", "real", "expression", "boolean", "set", "proof", "other"] = "integer"


EnumerationConstraintType = Literal[
    "adjacent",
    "not_adjacent",
    "at_position",
    "not_at_position",
    "before",
    "not_before",
    "at_an_end",
    "not_at_an_end",
]


class EnumerationConstraint(IRModel):
    type: EnumerationConstraintType
    items: list[str] = Field(description="Item labels the constraint refers to (1 or 2 items)")
    position: int | None = Field(default=None, description="1-based position for at_position / not_at_position")


class EnumerationSpec(IRModel):
    """Formalisation of a small arrangement problem so Python can brute-force the count.

    It is a restatement of the problem (not of the solution), produced by the analyzer
    and used only by the deterministic validator.
    """

    kind: Literal["permutation", "partial_permutation"] = "permutation"
    items: list[str] = Field(description="Distinct item labels, e.g. ['A','B','C','D','E']")
    length: int | None = Field(default=None, description="Arrangement length for partial permutations")
    constraints: list[EnumerationConstraint] = Field(default_factory=list)


class GraphEdge(IRModel):
    source: str
    target: str
    weight: float | None = None


GraphQuery = Literal[
    "shortest_path_length",
    "number_of_connected_components",
    "is_bipartite",
    "is_connected",
    "has_eulerian_circuit",
    "number_of_spanning_trees",
    "number_of_edges",
    "max_degree",
]


class GraphSpec(IRModel):
    directed: bool = False
    nodes: list[str]
    edges: list[GraphEdge]
    query: GraphQuery
    source: str | None = None
    target: str | None = None


GeometryQuery = Literal[
    "distance", "angle", "angle_line_plane", "distance_point_plane", "area", "volume", "perimeter",
    "revolution_volume", "revolution_surface", "surface_area", "lateral_area",
]
SolidKind = Literal[
    "cube", "cuboid", "prism_square", "prism_triangular", "pyramid_square", "pyramid_rectangular",
    "pyramid_triangular", "tetrahedron",
    # round solids
    "cylinder", "cone", "frustum", "sphere", "ball_pyramid",
    # plane figures (planimetry, and generators of solids of revolution)
    "regular_polygon", "triangle_equilateral", "right_triangle", "triangle", "square", "rectangle",
    "isosceles_trapezoid",
]


class GeometrySpec(IRModel):
    """Formalisation of a stereometry problem so Python can compute the answer exactly.

    Points are vertex labels or derived points: "mid(B,C)", "center(A,B,C,D)".
    query: distance [P, Q] | angle [P, V, Q] (angle at V) | angle_line_plane [P, Q, R, S, T] (line PQ,
    plane RST) | distance_point_plane [P, R, S, T] | area [polygon points, empty = whole figure] | volume [] |
    perimeter [] | surface_area [] | lateral_area [] | revolution_volume / revolution_surface [P, Q] (rotate the plane figure about line PQ).
    Dimensions may be symbolic: params ["a=a"].
    """

    solid: SolidKind
    params: list[str] = Field(description='dimensions, e.g. ["a=4"], ["a=6", "h=4"], ["n=6", "a=a"] (symbolic a)')
    labels: list[str] = Field(default_factory=list, description="vertex labels in the standard order (empty = default)")
    query: GeometryQuery
    points: list[str] = Field(default_factory=list)
    also: list[GeometryQuery] = Field(
        default_factory=list,
        description="further quantities asked in the same problem, in answer order (e.g. revolution_surface after revolution_volume)",
    )
    angle_function: Literal["none", "sin", "cos", "tan"] = Field(
        default="none", description="if the problem asks for sin/cos/tan of the angle instead of the angle itself"
    )


class ProblemIR(IRModel):
    original_text: str
    language: str = Field(default="en", description="ISO language code of the problem text, e.g. 'pl'")
    domain: str = Field(description="e.g. discrete_mathematics, algebra, geometry")
    subdomain: str = Field(description="e.g. combinatorics, graph_theory")
    problem_type: str = Field(description="e.g. permutation_with_constraint")
    summary: str = Field(description="One-sentence restatement of the problem")
    objects: list[MathObject]
    relations: list[Relation] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    goal: Goal
    assumptions: list[str] = Field(default_factory=list, description="Implicit assumptions made explicit")
    relevant_concepts: list[str] = Field(default_factory=list, description="snake_case concept names")
    enumeration_spec: EnumerationSpec | None = None
    graph_spec: GraphSpec | None = None
    geometry_spec: GeometrySpec | None = None
