"""Exact solid geometry for stereometry lessons (pure Python + SymPy, no Manim).

Used by BOTH the render runtime (to draw solids) and the backend validators (to check lengths/angles
the plan claims and to compute the answer independently). Coordinates are exact SymPy values.

Conventions (Polish/US high-school textbooks):
  cube / cuboid      ABCD = bottom face (counter-clockwise), EFGH = top face, E above A, F above B, ...
  prism_triangular   ABC = bottom (regular triangle), DEF = top, D above A
  prism_square       like a cuboid with a square base (a, h)
  pyramid_square     ABCD = square base, S = apex above the base centre (labels may rename S)
  pyramid_rectangular ABCD rectangle a x b, apex above the centre
  pyramid_triangular ABC regular triangle base, D apex above the centroid (regular tetrahedron if h omitted)

Plane figures (planimetry, and the generators of solids of revolution) lie in the z = 0 plane:
  regular_polygon (n, a)   A, B, C, ... counter-clockwise, side AB on the x-axis
  triangle_equilateral (a), right_triangle (a, b: legs, right angle at C), triangle (a, b, c: |BC|, |CA|, |AB|)
  square (a), rectangle (a, b), isosceles_trapezoid (a: long base, b: short base, h)

Round solids (axis = z, base centre O at the origin; A, B end a diameter of the base on the x-axis):
  cylinder (r, h)        O, O1 = base / top centres, A, B = bottom rim, C, D = top rim (C above A, D above B)
  cone (r, h)            O = base centre, S = apex, A, B = rim (axial section ABS)
  frustum (r1, r2, h)    r1 bottom radius, r2 top radius; O, O1, A, B (bottom rim), C, D (top rim, C on A's side)
  sphere (r)             O = centre, A, B = ends of a horizontal diameter, N = top pole
An extra round solid can share the scene (inscribed / circumscribed): build_solid(..., origin=point).

Dimensions may be numbers or a symbol (params ["a=a"]): exact results stay symbolic (e.g. 9*pi*a**3/2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp

Point = sp.Matrix


@dataclass
class Solid:
    kind: str
    dims: dict[str, sp.Expr]
    vertices: dict[str, Point]
    edges: list[tuple[str, str]]
    faces: list[list[str]]
    base: list[str] = field(default_factory=list)
    # round solids: horizontal circles (centre label, radius) and a sphere (centre label, radius)
    circles: list[tuple[str, sp.Expr]] = field(default_factory=list)
    sphere: tuple[str, sp.Expr] | None = None
    axis: tuple[str, str] | None = None
    extra_spheres: list[tuple[str, sp.Expr]] = field(
        default_factory=list
    )  # ball arrangements

    @property
    def spheres(self) -> list[tuple[str, sp.Expr]]:
        return ([self.sphere] if self.sphere else []) + list(self.extra_spheres)

    @property
    def round(self) -> bool:
        return bool(self.circles or self.spheres)


DEFAULT_LABELS = {
    "cube": list("ABCDEFGH"),
    "cuboid": list("ABCDEFGH"),
    "prism_square": list("ABCDEFGH"),
    "prism_triangular": list("ABCDEF"),
    "pyramid_square": ["A", "B", "C", "D", "S"],
    "pyramid_rectangular": ["A", "B", "C", "D", "S"],
    "pyramid_triangular": ["A", "B", "C", "D"],
    "tetrahedron": ["A", "B", "C", "D"],
}
ROUND_LABELS = {
    "cylinder": ["O", "O1", "A", "B", "C", "D"],
    "cone": ["O", "S", "A", "B"],
    "frustum": ["O", "O1", "A", "B", "C", "D"],
    "sphere": ["O", "A", "B", "N"],
    # three equal balls (radius r) lying on a table, each touching the other two, and a fourth ball (radius
    # R) resting on them: A, B, C = centres of the bottom balls, D = centre of the top ball, P = highest point
    # of the top ball, Q = point of the table under D. Every tangency is exact.
    "ball_pyramid": ["A", "B", "C", "D", "P", "Q"],
}
DEFAULT_LABELS |= ROUND_LABELS
ROUND_KINDS = tuple(ROUND_LABELS)
FIGURE_LABELS = {
    "triangle_equilateral": list("ABC"),
    "right_triangle": list("ABC"),
    "triangle": list("ABC"),
    "square": list("ABCD"),
    "rectangle": list("ABCD"),
    "isosceles_trapezoid": list("ABCD"),
    "regular_polygon": None,  # depends on n
}
KINDS = tuple(DEFAULT_LABELS)
FIGURE_KINDS = tuple(FIGURE_LABELS)


class GeometryError(ValueError):
    pass


def _plain_math(text: str) -> str:
    """LaTeX-ish dimension ("a\\sqrt{3}/2", "\\frac{a}{2}", "2\\cdot\\pi") -> sympy syntax."""
    import re

    t = text.strip().strip("$").replace("^", "**").replace("\\cdot", "*").replace("\\times", "*")
    t = t.replace("\\left", "").replace("\\right", "").replace("\\pi", " pi ")
    for _ in range(3):  # nested fractions
        t = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", t)
    t = re.sub(r"\\sqrt\{([^{}]*)\}", r" sqrt(\1)", t)
    t = re.sub(r"\\sqrt\s*(\d+|[a-zA-Z])", r" sqrt(\1)", t)
    return t.replace("{", "(").replace("}", ")").replace("\\", "").strip()


def _num(value: str | int | float | sp.Expr) -> sp.Expr:
    if isinstance(value, sp.Basic):
        return value
    text = _plain_math(str(value))
    if text.isidentifier() and len(text) <= 3:  # a symbolic dimension such as "a"
        return sp.Symbol(text, positive=True)
    try:
        from sympy.parsing.sympy_parser import implicit_application, implicit_multiplication, parse_expr, standard_transformations

        e = parse_expr(text, local_dict={"sqrt": sp.sqrt, "pi": sp.pi},
                       transformations=standard_transformations + (implicit_multiplication, implicit_application))
        e = e.xreplace({f: sp.Rational(str(f)) for f in e.atoms(sp.Float)})
    except Exception as exc:
        raise GeometryError(f"bad dimension {value!r}") from exc
    if e.free_symbols:
        e = e.subs({sym: sp.Symbol(sym.name, positive=True) for sym in e.free_symbols})
    if e.is_positive is False or (not e.free_symbols and not e.is_positive):
        raise GeometryError(f"dimension must be positive, got {value!r}")
    return e


def display_values(solid: "Solid") -> dict:
    """Numbers to draw a symbolic figure with (a -> 1); the shape is the same up to scale."""
    syms = (
        set().union(*(v.free_symbols for v in solid.vertices.values()))
        if solid.vertices
        else set()
    )
    return {sym: 1 for sym in syms}


def parse_params(params: list[str] | dict) -> dict[str, sp.Expr]:
    """["a=4", "h=3"] -> {"a": 4, "h": 3}."""
    if isinstance(params, dict):
        items = params.items()
    else:
        items = (p.split("=", 1) for p in params if "=" in p)
    return {k.strip(): _num(v.strip()) for k, v in items}


def _prism(
    base: list[Point], h: sp.Expr, labels: list[str]
) -> tuple[dict, list, list, list]:
    n = len(base)
    top = [p + sp.Matrix([0, 0, h]) for p in base]
    names = labels
    verts = {names[i]: base[i] for i in range(n)} | {
        names[n + i]: top[i] for i in range(n)
    }
    edges = [(names[i], names[(i + 1) % n]) for i in range(n)]
    edges += [(names[n + i], names[n + (i + 1) % n]) for i in range(n)]
    edges += [(names[i], names[n + i]) for i in range(n)]
    faces = [names[:n], names[n:]] + [
        [names[i], names[(i + 1) % n], names[n + (i + 1) % n], names[n + i]]
        for i in range(n)
    ]
    return verts, edges, faces, names[:n]


def _pyramid(
    base: list[Point], h: sp.Expr, labels: list[str]
) -> tuple[dict, list, list, list]:
    n = len(base)
    centre = sum(base, sp.zeros(3, 1)) / n
    apex = centre + sp.Matrix([0, 0, h])
    verts = {labels[i]: base[i] for i in range(n)} | {labels[n]: apex}
    edges = [(labels[i], labels[(i + 1) % n]) for i in range(n)] + [
        (labels[i], labels[n]) for i in range(n)
    ]
    faces = [labels[:n]] + [
        [labels[i], labels[(i + 1) % n], labels[n]] for i in range(n)
    ]
    return verts, edges, faces, labels[:n]


def _rect(a: sp.Expr, b: sp.Expr) -> list[Point]:
    return [
        sp.Matrix([0, 0, 0]),
        sp.Matrix([a, 0, 0]),
        sp.Matrix([a, b, 0]),
        sp.Matrix([0, b, 0]),
    ]


def _triangle(a: sp.Expr) -> list[Point]:
    return [
        sp.Matrix([0, 0, 0]),
        sp.Matrix([a, 0, 0]),
        sp.Matrix([a / 2, a * sp.sqrt(3) / 2, 0]),
    ]


def _figure(kind: str, d: dict, labels: list[str] | None) -> Solid:
    def need(*keys: str) -> list[sp.Expr]:
        missing = [k for k in keys if k not in d]
        if missing:
            raise GeometryError(f"{kind} needs parameter(s) {', '.join(missing)}")
        return [d[k] for k in keys]

    if kind == "regular_polygon":
        n, a = need("n", "a")
        if not (n.is_integer and 3 <= n <= 12):
            raise GeometryError("regular_polygon needs an integer n between 3 and 12")
        n = int(n)
        pts, cur, ang = [], sp.Matrix([0, 0, 0]), sp.Integer(0)
        for _ in range(
            n
        ):  # walk the boundary: side AB on the x-axis, counter-clockwise
            pts.append(cur)
            cur = cur + a * sp.Matrix([sp.cos(ang), sp.sin(ang), 0])
            ang += 2 * sp.pi / n
        pts = [sp.Matrix([sp.nsimplify(sp.simplify(x)) for x in p]) for p in pts]
    elif kind == "triangle_equilateral":
        (a,) = need("a")
        pts = [
            sp.Matrix([0, 0, 0]),
            sp.Matrix([a, 0, 0]),
            sp.Matrix([a / 2, a * sp.sqrt(3) / 2, 0]),
        ]
    elif kind == "right_triangle":
        a, b = need("a", "b")  # legs BC = a, AC = b, right angle at C
        pts = [sp.Matrix([b, 0, 0]), sp.Matrix([0, a, 0]), sp.Matrix([0, 0, 0])]
    elif kind == "triangle":
        a, b, c = need("a", "b", "c")  # |BC| = a, |CA| = b, |AB| = c
        x = (b**2 + c**2 - a**2) / (2 * c)
        y = sp.sqrt(b**2 - x**2)
        if y.is_real is False:
            raise GeometryError("these side lengths do not form a triangle")
        pts = [
            sp.Matrix([0, 0, 0]),
            sp.Matrix([c, 0, 0]),
            sp.Matrix([sp.simplify(x), sp.simplify(y), 0]),
        ]
    elif kind == "square":
        (a,) = need("a")
        pts = _rect(a, a)
    elif kind == "rectangle":
        a, b = need("a", "b")
        pts = _rect(a, b)
    else:  # isosceles_trapezoid
        a, b, h = need("a", "b", "h")
        pts = [
            sp.Matrix([0, 0, 0]),
            sp.Matrix([a, 0, 0]),
            sp.Matrix([(a + b) / 2, h, 0]),
            sp.Matrix([(a - b) / 2, h, 0]),
        ]
    default = FIGURE_LABELS[kind] or [chr(ord("A") + i) for i in range(len(pts))]
    names = list(labels) if labels else default
    if len(names) != len(pts):
        raise GeometryError(f"{kind} needs {len(pts)} vertex labels, got {len(names)}")
    verts = dict(zip(names, pts))
    edges = [(names[i], names[(i + 1) % len(names)]) for i in range(len(names))]
    return Solid(
        kind=kind, dims=d, vertices=verts, edges=edges, faces=[names], base=names
    )


def is_figure(kind: str) -> bool:
    return kind in FIGURE_KINDS


def _round(kind: str, need, names: list[str], d: dict | None = None) -> Solid:
    P = lambda x, y, z: sp.Matrix([x, y, z])  # noqa: E731
    if kind == "ball_pyramid":
        (r,) = need("r")
        R = (d or {}).get("R", r)
        a, b, c, top, peak, foot = names
        rise2 = sp.simplify(
            (r + R) ** 2 - sp.Rational(4, 3) * r**2
        )  # height of D above the plane ABC, squared
        if rise2.is_number and rise2 <= 0:
            raise GeometryError(
                "the top ball is too small: it falls between the bottom balls (needs R > r(2/sqrt(3) - 1))"
            )
        g = P(
            0, 0, r
        )  # centroid of ABC; the centres sit at height r above the table (z = 0)
        k = 2 * r / sp.sqrt(3)  # distance centroid -> centre
        verts = {
            a: g + P(k, 0, 0),
            b: g + P(-k / 2, r, 0),
            c: g + P(-k / 2, -r, 0),
            top: g + P(0, 0, sp.sqrt(rise2)),
            peak: g + P(0, 0, sp.sqrt(rise2) + R),
            foot: P(0, 0, 0),
        }
        edges = [(a, b), (b, c), (c, a), (a, top), (b, top), (c, top)]
        return Solid(
            kind,
            {},
            verts,
            edges,
            [],
            [a, b, c],
            circles=[],
            extra_spheres=[(a, r), (b, r), (c, r), (top, R)],
        )
    if kind == "sphere":
        (r,) = need("r")
        o, a, b, n = names
        verts = {o: P(0, 0, 0), a: P(-r, 0, 0), b: P(r, 0, 0), n: P(0, 0, r)}
        return Solid(kind, {}, verts, [], [], [], circles=[], sphere=(o, r))
    if kind == "cone":
        r, h = need("r", "h")
        o, s_, a, b = names
        verts = {o: P(0, 0, 0), s_: P(0, 0, h), a: P(-r, 0, 0), b: P(r, 0, 0)}
        return Solid(
            kind,
            {},
            verts,
            [(a, s_), (b, s_)],
            [[a, b, s_]],
            [a, b],
            circles=[(o, r)],
            axis=(o, s_),
        )
    if kind == "cylinder":
        r, h = need("r", "h")
        r1 = r2 = r
    else:  # frustum
        r1, r2, h = need("r1", "r2", "h")
    o, o1, a, b, c, d = names
    verts = {
        o: P(0, 0, 0),
        o1: P(0, 0, h),
        a: P(-r1, 0, 0),
        b: P(r1, 0, 0),
        c: P(-r2, 0, h),
        d: P(r2, 0, h),
    }
    return Solid(
        kind,
        {},
        verts,
        [(a, c), (b, d)],
        [[a, b, d, c]],
        [a, b],
        circles=[(o, r1), (o1, r2)],
        axis=(o, o1),
    )


def build_solid(
    kind: str,
    params: list[str] | dict,
    labels: list[str] | None = None,
    origin: Point | None = None,
) -> Solid:
    solid = _build(kind, params, labels)
    if origin is not None:
        solid.vertices = {k: v + origin for k, v in solid.vertices.items()}
    return solid


def _build(
    kind: str, params: list[str] | dict, labels: list[str] | None = None
) -> Solid:
    if kind in FIGURE_KINDS:
        return _figure(kind, parse_params(params), labels)
    if kind not in DEFAULT_LABELS:
        raise GeometryError(
            f"unknown shape '{kind}' (solids: {', '.join(KINDS)}; plane figures: {', '.join(FIGURE_KINDS)})"
        )
    d = parse_params(params)
    names = list(labels) if labels else DEFAULT_LABELS[kind]
    if len(names) != len(DEFAULT_LABELS[kind]):
        raise GeometryError(
            f"{kind} needs {len(DEFAULT_LABELS[kind])} vertex labels, got {len(names)}"
        )
    if len(set(names)) != len(names):
        raise GeometryError("vertex labels must be distinct")

    def need(*keys: str) -> list[sp.Expr]:
        missing = [k for k in keys if k not in d]
        if missing:
            raise GeometryError(f"{kind} needs parameter(s) {', '.join(missing)}")
        return [d[k] for k in keys]

    if kind in ROUND_KINDS:
        solid = _round(kind, need, names, d)
        solid.dims = d
        return solid
    if kind == "cube":
        (a,) = need("a")
        verts, edges, faces, base = _prism(_rect(a, a), a, names)
    elif kind == "cuboid":
        a, b, c = need("a", "b", "c")
        verts, edges, faces, base = _prism(_rect(a, b), c, names)
    elif kind == "prism_square":
        a, h = need("a", "h")
        verts, edges, faces, base = _prism(_rect(a, a), h, names)
    elif kind == "prism_triangular":
        a, h = need("a", "h")
        verts, edges, faces, base = _prism(_triangle(a), h, names)
    elif kind == "pyramid_square":
        a, h = need("a", "h")
        verts, edges, faces, base = _pyramid(_rect(a, a), h, names)
    elif kind == "pyramid_rectangular":
        a, b, h = need("a", "b", "h")
        verts, edges, faces, base = _pyramid(_rect(a, b), h, names)
    else:  # pyramid_triangular / tetrahedron
        (a,) = need("a")
        h = d.get("h", a * sp.sqrt(sp.Rational(2, 3)))  # regular tetrahedron by default
        verts, edges, faces, base = _pyramid(_triangle(a), h, names)
    return Solid(kind=kind, dims=d, vertices=verts, edges=edges, faces=faces, base=base)


REQUIRED_PARAMS = {
    "cube": ["a"],
    "cuboid": ["a", "b", "c"],
    "prism_square": ["a", "h"],
    "prism_triangular": ["a", "h"],
    "pyramid_square": ["a", "h"],
    "pyramid_rectangular": ["a", "b", "h"],
    "pyramid_triangular": ["a"],
    "tetrahedron": ["a"],
    "ball_pyramid": ["r"],
    "cylinder": ["r", "h"],
    "cone": ["r", "h"],
    "frustum": ["r1", "r2", "h"],
    "sphere": ["r"],
    "regular_polygon": ["n", "a"],
    "triangle_equilateral": ["a"],
    "right_triangle": ["a", "b"],
    "triangle": ["a", "b", "c"],
    "square": ["a"],
    "rectangle": ["a", "b"],
    "isosceles_trapezoid": ["a", "b", "h"],
}


def at_coordinates(at: str | None) -> Point | None:
    """'at=0,0,2' gives coordinates instead of a point name (exact; symbols such as r are allowed)."""
    if not at or at.count(",") != 2:
        return None
    try:
        coords = [
            sp.sympify(
                x.strip().replace("^", "**"),
                locals={"sqrt": sp.sqrt, "pi": sp.pi},
                rational=True,
            )
            for x in at.split(",")
        ]
    except Exception:  # noqa: BLE001
        return None
    return sp.Matrix(
        [
            c.subs({s_: sp.Symbol(s_.name, positive=True) for s_ in c.free_symbols})
            for c in coords
        ]
    )


def split_attach(params: list[str]) -> tuple[list[str], str | None]:
    """A second solid in a scene is placed at an existing point: params ["at=O", "r=2"] -> (["r=2"], "O")."""
    rest, at = [], None
    for p in params or []:
        k, _, v = p.partition("=")
        if k.strip() == "at" and v.strip():
            at = v.strip()
        elif k.strip() == "fit":
            continue
        else:
            rest.append(p)
    return rest, at


def fit_relation(params: list[str] | None) -> str | None:
    """Return an explicit spatial relation without mixing it into numeric dimensions."""
    for p in params or []:
        key, _, value = p.partition("=")
        if key.strip() == "fit":
            return value.strip().lower() or None
    return None


def free_labels(kind: str, members: list[str] | None, taken) -> list[str]:
    """Labels for a second solid: the given ones (the centre first) completed with the defaults, primed
    until free (O -> O', A -> A', ...), so names never collide with points already in the scene."""
    defaults = list(DEFAULT_LABELS.get(kind) or members or [])
    given = list(members or [])[: len(defaults)]
    out: list[str] = []
    for i, d in enumerate(defaults):
        n = given[i] if i < len(given) else d
        while n in taken or n in out:
            n += "'"
        out.append(n)
    return out


def bounding_box(solid: Solid, subs: dict | None = None):
    """Numeric (lo, hi) corners including round rims and the sphere."""
    import numpy as np

    subs = subs or {}
    f = lambda e: float(sp.sympify(e).subs(subs))  # noqa: E731
    pts = [np.array([f(x) for x in v]) for v in solid.vertices.values()]
    for c, r in solid.circles:
        cc, rr = np.array([f(x) for x in solid.vertices[c]]), f(r)
        pts += [
            cc + np.array([dx, dy, 0.0])
            for dx, dy in ((rr, 0), (-rr, 0), (0, rr), (0, -rr))
        ]
    for centre, radius in solid.spheres:
        cc, rr = np.array([f(x) for x in solid.vertices[centre]]), f(radius)
        pts += [
            cc + rr * np.array(d, dtype=float)
            for d in (
                (1, 0, 0),
                (-1, 0, 0),
                (0, 1, 0),
                (0, -1, 0),
                (0, 0, 1),
                (0, 0, -1),
            )
        ]
    arr = np.array(pts)
    return arr.min(axis=0), arr.max(axis=0)


# ----------------------------------------------------------------------------- derived points


def derived_point(
    points: dict[str, Point], members: list[str], params: list[str] | dict | None = None
) -> Point:
    """Midpoint of two points, centroid of 3+, P + t (Q - P) with param t, or an absolute point
    params ["xyz=x,y,z"] (exact values or symbols, e.g. centres of several balls)."""
    raw_params = (
        dict(p.split("=", 1) for p in (params or []) if "=" in p)
        if not isinstance(params, dict)
        else (params or {})
    )
    if "xyz" in raw_params:
        parts = [x.strip() for x in str(raw_params["xyz"]).split(",")]
        if len(parts) != 3:
            raise GeometryError("xyz needs three coordinates: xyz=x,y,z")
        try:
            coords = [
                sp.sympify(
                    x.replace("^", "**"),
                    locals={"sqrt": sp.sqrt, "pi": sp.pi},
                    rational=True,
                )
                for x in parts
            ]
        except Exception as exc:
            raise GeometryError(f"bad coordinates {raw_params['xyz']!r}") from exc
        coords = [
            c.subs({s: sp.Symbol(s.name, positive=True) for s in c.free_symbols})
            for c in coords
        ]
        base = sp.Matrix(coords)
        return base + (
            sum((points[m] for m in members if m in points), sp.zeros(3, 1))
            / len(members)
            if members
            else sp.zeros(3, 1)
        )
    missing = [m for m in members if m not in points]
    if missing:
        raise GeometryError(f"unknown point(s) {missing}")
    ps = [points[m] for m in members]
    if not ps:
        raise GeometryError("a derived point needs members")
    t = None
    if params:
        raw = (
            dict(p.split("=", 1) for p in params if "=" in p)
            if not isinstance(params, dict)
            else params
        )
        if "t" in raw:
            t = sp.sympify(str(raw["t"]), rational=True)
    if t is not None and len(ps) == 2:
        if t.is_number and not (0 <= t <= 1):
            raise GeometryError("division parameter t must be between 0 and 1")
        return ps[0] + t * (ps[1] - ps[0])
    return sum(ps, sp.zeros(3, 1)) / len(ps)


def resolve(points: dict[str, Point], spec: str) -> Point:
    """'A' | 'mid(B,C)' | 'center(A,B,C,D)'."""
    s = spec.replace(" ", "")
    if s in points:
        return points[s]
    for fn in ("mid", "center", "centre"):
        if s.startswith(fn + "(") and s.endswith(")"):
            return derived_point(points, s[len(fn) + 1 : -1].split(","))
    raise GeometryError(f"unknown point '{spec}'")


# ----------------------------------------------------------------------------- measurements


def distance(p: Point, q: Point) -> sp.Expr:
    return sp.nsimplify(sp.sqrt(sp.simplify((q - p).dot(q - p))))


def angle_at(p: Point, v: Point, q: Point) -> sp.Expr:
    """Angle PVQ in radians (exact when possible)."""
    u, w = p - v, q - v
    return sp.simplify(
        sp.acos(sp.simplify(u.dot(w) / (sp.sqrt(u.dot(u)) * sp.sqrt(w.dot(w)))))
    )


def plane_normal(a: Point, b: Point, c: Point) -> Point:
    n = (b - a).cross(c - a)
    if n == sp.zeros(3, 1):
        raise GeometryError("plane points are collinear")
    return n


def angle_line_plane(p: Point, q: Point, a: Point, b: Point, c: Point) -> sp.Expr:
    d, n = q - p, plane_normal(a, b, c)
    return sp.simplify(
        sp.asin(sp.Abs(d.dot(n)) / (sp.sqrt(d.dot(d)) * sp.sqrt(n.dot(n))))
    )


def distance_point_plane(p: Point, a: Point, b: Point, c: Point) -> sp.Expr:
    n = plane_normal(a, b, c)
    return sp.nsimplify(sp.simplify(sp.Abs((p - a).dot(n)) / sp.sqrt(n.dot(n))))


def polygon_area(points: list[Point]) -> sp.Expr:
    if len(points) < 3:
        raise GeometryError("a polygon needs 3+ points")
    total = sp.zeros(3, 1)
    for i in range(1, len(points) - 1):
        total += (points[i] - points[0]).cross(points[i + 1] - points[0])
    return sp.nsimplify(sp.simplify(sp.sqrt(total.dot(total)) / 2))


def volume(solid: Solid) -> sp.Expr:
    d = solid.dims
    if solid.kind == "ball_pyramid":
        return sp.simplify(
            sum(sp.Rational(4, 3) * sp.pi * r**3 for _, r in solid.spheres)
        )
    if solid.kind == "sphere":
        return sp.Rational(4, 3) * sp.pi * d["r"] ** 3
    if solid.kind == "cylinder":
        return sp.pi * d["r"] ** 2 * d["h"]
    if solid.kind == "cone":
        return sp.pi * d["r"] ** 2 * d["h"] / 3
    if solid.kind == "frustum":
        R, r, h = d["r1"], d["r2"], d["h"]
        return sp.simplify(sp.pi * h * (R**2 + R * r + r**2) / 3)
    if solid.kind == "cube":
        return d["a"] ** 3
    if solid.kind == "cuboid":
        return d["a"] * d["b"] * d["c"]
    base_pts = [solid.vertices[v] for v in solid.base]
    top = [v for v in solid.vertices if v not in solid.base]
    h = solid.vertices[top[-1]][2]
    area = polygon_area(base_pts)
    if solid.kind.startswith("pyramid") or solid.kind == "tetrahedron":
        return sp.simplify(area * h / 3)
    return sp.simplify(area * h)


def surface_area(solid: Solid) -> sp.Expr:
    """Total surface area (all faces / bases + lateral surface)."""
    d = solid.dims
    if solid.kind == "ball_pyramid":
        return sp.simplify(sum(4 * sp.pi * r**2 for _, r in solid.spheres))
    if solid.kind == "sphere":
        return 4 * sp.pi * d["r"] ** 2
    if solid.kind == "cylinder":
        return sp.simplify(2 * sp.pi * d["r"] ** 2 + 2 * sp.pi * d["r"] * d["h"])
    if solid.kind == "cone":
        slant = sp.sqrt(d["r"] ** 2 + d["h"] ** 2)
        return sp.simplify(sp.pi * d["r"] ** 2 + sp.pi * d["r"] * slant)
    if solid.kind == "frustum":
        R, r, h = d["r1"], d["r2"], d["h"]
        slant = sp.sqrt((R - r) ** 2 + h**2)
        return sp.simplify(sp.pi * (R**2 + r**2) + sp.pi * (R + r) * slant)
    if is_figure(solid.kind):
        return polygon_area([solid.vertices[v] for v in solid.base])
    return sp.nsimplify(
        sp.simplify(
            sum(polygon_area([solid.vertices[v] for v in f]) for f in solid.faces)
        )
    )


def lateral_area(solid: Solid) -> sp.Expr:
    d = solid.dims
    if solid.kind == "cylinder":
        return 2 * sp.pi * d["r"] * d["h"]
    if solid.kind == "cone":
        return sp.simplify(sp.pi * d["r"] * sp.sqrt(d["r"] ** 2 + d["h"] ** 2))
    if solid.kind == "frustum":
        R, r, h = d["r1"], d["r2"], d["h"]
        return sp.simplify(sp.pi * (R + r) * sp.sqrt((R - r) ** 2 + h**2))
    if solid.kind == "sphere":
        return 4 * sp.pi * d["r"] ** 2
    bases = (
        solid.faces[:2]
        if solid.kind in ("cube", "cuboid", "prism_square", "prism_triangular")
        else solid.faces[:1]
    )
    return sp.nsimplify(
        sp.simplify(
            sum(
                polygon_area([solid.vertices[v] for v in f])
                for f in solid.faces
                if f not in bases
            )
        )
    )


def perimeter(points: list[Point]) -> sp.Expr:
    return sp.nsimplify(
        sp.simplify(
            sum(
                distance(points[i], points[(i + 1) % len(points)])
                for i in range(len(points))
            )
        )
    )


# ----------------------------------------------------------------------------- solids of revolution


def distance_to_line(x: Point, p: Point, q: Point) -> sp.Expr:
    d = q - p
    c = d.cross(x - p)
    return sp.simplify(sp.sqrt(c.dot(c)) / sp.sqrt(d.dot(d)))


def _side(x: Point, p: Point, q: Point, normal: Point) -> sp.Expr:
    return sp.simplify((q - p).cross(x - p).dot(normal))


def revolution(points: list[Point], p: Point, q: Point) -> dict[str, sp.Expr]:
    """Volume and surface of the solid made by rotating a plane polygon about the line PQ (in its plane, not
    crossing it). Volume: Pappus (area x path of the centroid). Surface: each edge sweeps a cone/frustum/
    cylinder band pi (r1 + r2) L; edges lying on the axis sweep nothing."""
    n = len(points)
    normal = (points[1] - points[0]).cross(points[2] - points[0])
    sides = [_side(x, p, q, normal) for x in points]
    if any(s.is_negative for s in sides) and any(s.is_positive for s in sides):
        raise GeometryError(
            "the axis crosses the figure; Pappus' theorem needs it on one side"
        )
    # polygon centroid (area-weighted, via a triangle fan)
    area_total, moment = sp.Integer(0), sp.zeros(3, 1)
    for i in range(1, n - 1):
        cr = (points[i] - points[0]).cross(points[i + 1] - points[0])
        a_i = sp.sqrt(cr.dot(cr)) / 2
        area_total += a_i
        moment += a_i * (points[0] + points[i] + points[i + 1]) / 3
    centroid = moment / area_total
    volume = sp.nsimplify(
        sp.simplify(2 * sp.pi * distance_to_line(centroid, p, q) * area_total)
    )
    surface = sp.Integer(0)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        r1, r2 = distance_to_line(a, p, q), distance_to_line(b, p, q)
        if sp.simplify(r1) == 0 and sp.simplify(r2) == 0:
            continue  # the edge lies on the axis
        surface += sp.pi * (r1 + r2) * distance(a, b)
    return {
        "volume": volume,
        "surface": sp.nsimplify(sp.simplify(surface)),
        "area": sp.simplify(area_total),
    }


def is_right_angle(p: Point, v: Point, q: Point) -> bool:
    return sp.simplify((p - v).dot(q - v)) == 0
