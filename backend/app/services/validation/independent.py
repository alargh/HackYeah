"""Independent, method-agnostic computations of the answer (brute force, NetworkX).

These do not look at the model's solution at all — only at the formalised problem.
"""

from __future__ import annotations

import itertools
import math

import networkx as nx

from app.schemas.problem import EnumerationConstraint, EnumerationSpec, GraphSpec

MAX_ENUMERATION = 3_000_000


class IndependentCheckError(ValueError):
    pass


def _satisfies(c: EnumerationConstraint, arrangement: tuple[str, ...]) -> bool:
    pos = {item: i for i, item in enumerate(arrangement)}
    items = c.items
    last = len(arrangement) - 1

    def present(*xs: str) -> bool:
        return all(x in pos for x in xs)

    t = c.type
    if t in ("adjacent", "not_adjacent"):
        x, y = items[0], items[1]
        adj = present(x, y) and abs(pos[x] - pos[y]) == 1
        return adj if t == "adjacent" else not adj
    if t in ("before", "not_before"):
        x, y = items[0], items[1]
        if not present(x, y):
            return t == "not_before"
        before = pos[x] < pos[y]
        return before if t == "before" else not before
    if t in ("at_position", "not_at_position"):
        if c.position is None:
            raise IndependentCheckError(f"constraint {t} needs a position")
        idx = c.position - 1
        at = idx < len(arrangement) and arrangement[idx] == items[0]
        return at if t == "at_position" else not at
    if t in ("at_an_end", "not_at_an_end"):
        x = items[0]
        at_end = present(x) and pos[x] in (0, last)
        return at_end if t == "at_an_end" else not at_end
    raise IndependentCheckError(f"unsupported constraint type {t}")


def count_arrangements(spec: EnumerationSpec) -> int:
    items = spec.items
    if len(set(items)) != len(items):
        raise IndependentCheckError("enumeration items must be distinct")
    length = spec.length if spec.kind == "partial_permutation" and spec.length else len(items)
    if length > len(items):
        raise IndependentCheckError("arrangement length exceeds number of items")
    if math.perm(len(items), length) > MAX_ENUMERATION:
        raise IndependentCheckError("search space too large for brute force")
    for c in spec.constraints:
        need = 2 if c.type in ("adjacent", "not_adjacent", "before", "not_before") else 1
        if len(c.items) < need:
            raise IndependentCheckError(f"constraint {c.type} needs {need} item(s)")
        unknown = [x for x in c.items[:need] if x not in items]
        if unknown:
            raise IndependentCheckError(f"constraint refers to unknown items {unknown}")
    return sum(
        1
        for arrangement in itertools.permutations(items, length)
        if all(_satisfies(c, arrangement) for c in spec.constraints)
    )


def evaluate_geometry(spec) -> list:
    """Exact answer(s) of a geometry problem from its GeometrySpec (independent of the model's solution):
    the main query first, then `also` queries, in answer order."""
    import sympy

    from app.services.visuals.runtime.tutorly_visuals import geometry as geo

    try:
        solid = geo.build_solid(spec.solid, spec.params, spec.labels or None)
        P = [geo.resolve(solid.vertices, p) for p in spec.points]
        figure = [solid.vertices[v] for v in solid.base] if geo.is_figure(spec.solid) else None
        values = []
        for q in [spec.query, *spec.also]:
            need = {"distance": 2, "angle": 3, "angle_line_plane": 5, "distance_point_plane": 4,
                    "revolution_volume": 2, "revolution_surface": 2}.get(q, 0)
            if len(P) < need:
                raise IndependentCheckError(f"{q} needs {need} points")
            if q == "distance":
                value = geo.distance(P[0], P[1])
            elif q == "angle":
                value = geo.angle_at(P[0], P[1], P[2])
            elif q == "angle_line_plane":
                value = geo.angle_line_plane(*P[:5])
            elif q == "distance_point_plane":
                value = geo.distance_point_plane(*P[:4])
            elif q == "area":
                value = geo.polygon_area(P if len(P) >= 3 else (figure or []))
            elif q == "perimeter":
                value = geo.perimeter(P if len(P) >= 3 else (figure or []))
            elif q == "surface_area":
                value = geo.surface_area(solid)
            elif q == "lateral_area":
                value = geo.lateral_area(solid)
            elif q in ("revolution_volume", "revolution_surface"):
                if figure is None:
                    raise IndependentCheckError("a solid of revolution needs a plane figure")
                value = geo.revolution(figure, P[0], P[1])["volume" if q == "revolution_volume" else "surface"]
            else:
                value = geo.volume(solid)
            if q in ("angle", "angle_line_plane") and spec.angle_function != "none":
                value = sympy.simplify(getattr(sympy, spec.angle_function)(value))
            values.append(value)
    except geo.GeometryError as exc:
        raise IndependentCheckError(str(exc)) from exc
    return values


def evaluate_graph(spec: GraphSpec) -> str:
    g: nx.Graph = nx.DiGraph() if spec.directed else nx.Graph()
    g.add_nodes_from(spec.nodes)
    for e in spec.edges:
        if e.weight is None:
            g.add_edge(e.source, e.target)
        else:
            g.add_edge(e.source, e.target, weight=e.weight)
    q = spec.query
    if q == "shortest_path_length":
        if spec.source is None or spec.target is None:
            raise IndependentCheckError("shortest_path_length needs source and target")
        weighted = any(e.weight is not None for e in spec.edges)
        length = nx.shortest_path_length(g, spec.source, spec.target, weight="weight" if weighted else None)
        return _num(length)
    if q == "number_of_connected_components":
        ug = g.to_undirected() if spec.directed else g
        return str(nx.number_connected_components(ug))
    if q == "is_bipartite":
        return str(nx.is_bipartite(g))
    if q == "is_connected":
        return str(nx.is_weakly_connected(g) if spec.directed else nx.is_connected(g))
    if q == "has_eulerian_circuit":
        return str(nx.is_eulerian(g))
    if q == "number_of_spanning_trees":
        if spec.directed:
            raise IndependentCheckError("spanning tree count only for undirected graphs")
        return _num(round(nx.number_of_spanning_trees(g)))
    if q == "number_of_edges":
        return str(g.number_of_edges())
    if q == "max_degree":
        return str(max((d for _, d in g.degree()), default=0))
    raise IndependentCheckError(f"unsupported graph query {q}")


def _num(x: float | int) -> str:
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)
