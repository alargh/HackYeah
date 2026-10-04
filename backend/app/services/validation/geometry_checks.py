"""3D (stereometry) checks for semantic visual plans: geometry is valid and every measured label is TRUE.

A plan may only write "4\\sqrt{3}" on segment AG if |AG| really is 4*sqrt(3) for the declared solid —
computed exactly with SymPy from the same geometry module the renderer uses.
"""

from __future__ import annotations

import re

import sympy

from app.schemas.generation import SOLID_TYPES, VisualPlan
from app.schemas.validation import ValidationIssue
from app.services.validation import expressions as ex
from app.services.visuals.runtime.tutorly_visuals import geometry as geo

TWO_D_ONLY = {"item", "slot", "arrangement", "region", "node", "edge", "counter"}


def tex_to_sympy(
    tex: str, symbols: set[str] | None = None
) -> tuple[sympy.Expr, bool] | None:
    """Simple LaTeX (numbers, \\sqrt, \\frac, \\cdot, ^, \\pi, degrees) -> (value, is_degrees). None if not numeric."""
    s = tex.strip()
    if "=" in s:  # "|AG| = 4\\sqrt{3}" -> right-hand side
        s = s.split("=")[-1]
    degrees = bool(re.search(r"\^\s*\{?\s*\\circ\s*\}?|°", s))
    s = re.sub(r"\^\s*\{?\s*\\circ\s*\}?|°", "", s)
    s = (
        s.replace("\\left", "")
        .replace("\\right", "")
        .replace("\\,", "")
        .replace("\\!", "")
    )
    for _ in range(6):  # nested \frac / \sqrt
        s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
        s = re.sub(r"\\sqrt\[([^\]]+)\]\{([^{}]*)\}", r"((\2)**(1/(\1)))", s)
        s = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s)
    s = (
        s.replace("\\cdot", "*")
        .replace("\\times", "*")
        .replace("\\pi", "pi")
        .replace("{", "(")
        .replace("}", ")")
    )
    s = s.replace("^", "**")
    allowed = symbols or set()
    letters = set(re.findall(r"[A-Za-z]+", re.sub(r"sqrt|pi", "", s)))
    if "\\" in s or not letters <= allowed:
        return None  # symbols such as \alpha (or letters that are not dimensions): not checkable
    sym = "|".join(sorted(allowed, key=len, reverse=True)) or "(?!x)x"
    s = re.sub(rf"(\d)\s*(sqrt|pi|\(|{sym})", r"\1*\2", s)
    s = re.sub(rf"\)\s*(\(|\d|sqrt|pi|{sym})", r")*\1", s)
    s = re.sub(rf"\b({sym})\s*(sqrt|pi|\()", r"\1*\2", s)
    try:
        names = {n: sympy.Symbol(n, positive=True) for n in allowed}
        value = ex.evaluate(s, names, numeric=False)
        if value.free_symbols - set(names.values()):
            return None
        return value, degrees
    except ex.ExpressionError:
        return None


MAX_EXTRA_SOLIDS = 8


def _check_balls(spheres, err) -> None:
    """Two balls either touch (|centres| = r1 + r2) or are apart; cutting into each other, or missing a
    contact by a hair, is a drawing error (wrong centres). Checked for two sets of symbol values."""
    import itertools

    for (c1, r1, id1), (c2, r2, id2) in itertools.combinations(spheres, 2):
        syms = sorted(
            set().union(c1.free_symbols, c2.free_symbols, sympy.sympify(r1).free_symbols, sympy.sympify(r2).free_symbols),
            key=str,
        )
        for values in ((1, 1, 1), (1, sympy.Rational(7, 5), sympy.Rational(9, 5))):
            sub = {s: values[i % 3] for i, s in enumerate(syms)}
            try:
                dist = float(sympy.sqrt(((c1 - c2).T * (c1 - c2))[0]).subs(sub))
                touch = float(sympy.sympify(r1 + r2).subs(sub))
            except (TypeError, ValueError):
                break
            gap = (dist - touch) / touch
            if gap < -0.02 and dist > 1e-9:
                err(
                    "BALLS_OVERLAP",
                    f"balls '{id1}' and '{id2}' cut into each other (centre distance {dist:.2f} < r1 + r2 = {touch:.2f}); "
                    "touching balls need centre distance = r1 + r2 (or use solid 'ball_pyramid')",
                )
                break
            if 0.005 < gap < 0.15:
                err(
                    "BALLS_ALMOST_TOUCH",
                    f"balls '{id1}' and '{id2}' nearly touch but do not (gap {gap:.0%}); tangent balls need centre "
                    "distance = r1 + r2 exactly (or use solid 'ball_pyramid')",
                )
                break


def check_3d(plan: VisualPlan, rules, issues: list[ValidationIssue]) -> None:
    """Append 3D issues. `rules` is the manifest quality dict."""

    def err(code, msg, loc=None, rule=None):
        sev = rules[rule].severity if rule else "error"
        issues.append(
            ValidationIssue(code=code, message=msg, severity=sev, location=loc)
        )

    objects = {o.id: o for o in plan.objects}
    has_3d = (
        any(o.type in SOLID_TYPES for o in plan.objects) or plan.layout == "space_3d"
    )
    if not has_3d:
        if any(
            b.camera in ("orbit", "three_quarter", "top_view", "front_view")
            for b in plan.beats
        ):
            err(
                "CAMERA_3D_IN_2D",
                "3D camera presets need a 3D scene (a solid and layout space_3d)",
            )
        return

    if rules["forbid_mixed_2d_3d"].value:
        if plan.layout != "space_3d" or any(
            b.layout not in (None, "space_3d") for b in plan.beats
        ):
            err(
                "MIXED_2D_3D",
                "a scene with a solid must use layout space_3d throughout",
                rule="forbid_mixed_2d_3d",
            )
        mixed = [o.id for o in plan.objects if o.type in TWO_D_ONLY]
        if mixed:
            err(
                "MIXED_2D_3D",
                f"2D objects {mixed} cannot appear in a 3D scene",
                rule="forbid_mixed_2d_3d",
            )

    solids = [o for o in plan.objects if o.type in ("solid", "figure")]
    if not solids:
        err("SOLID_COUNT", "a geometry scene needs one solid or figure")
        return
    so, extra = solids[0], solids[1:]
    if len(extra) > MAX_EXTRA_SOLIDS or any(
        o.type != "solid" or o.value not in geo.ROUND_KINDS for o in extra
    ):
        err(
            "SOLID_COUNT",
            f"one main solid/figure per scene plus at most {MAX_EXTRA_SOLIDS} extra ROUND solids "
            "(cylinder, cone, frustum, sphere) placed with params ['at=<point>', ...] (e.g. balls whose centres are "
            "the vertices of a helper tetrahedron, or points declared with params ['xyz=x,y,z'])",
        )
        return
    try:
        solid = geo.build_solid(
            so.value, geo.split_attach(so.params)[0], so.members or None
        )
    except geo.GeometryError as exc:
        err("BAD_SOLID", f"solid '{so.id}': {exc}", so.id)
        return

    exact: dict[str, sympy.Matrix] = dict(solid.vertices)
    display = geo.display_values(solid)
    lo, hi = geo.bounding_box(solid, display)

    def in_scene_bounds(point: sympy.Matrix) -> bool:
        values = [float(sympy.sympify(v).subs(display)) for v in point]
        return all(
            float(a) - 1e-8 <= value <= float(b) + 1e-8
            for value, a, b in zip(values, lo, hi)
        )

    def fit_error(inner, relation: str | None) -> str | None:
        if relation != "inscribed":
            return None
        fit_display = {**display, **geo.display_values(inner)}
        if inner.kind == "sphere" and solid.kind == "cylinder":
            inner_centre, radius = inner.sphere
            centre = inner.vertices[inner_centre]
            base = solid.vertices[solid.axis[0]]
            outer_radius = solid.circles[0][1]
            height = solid.vertices[solid.axis[1]][2] - base[2]
            radial = sympy.sqrt((centre[0] - base[0]) ** 2 + (centre[1] - base[1]) ** 2)
            checks = (
                radial + radius - outer_radius,
                centre[2] - radius - base[2],
                centre[2] + radius - base[2] - height,
            )
            if not all(bool(sympy.simplify(c.subs(fit_display)) == 0) for c in checks):
                return "inscribed sphere must touch the cylinder wall and both bases"
        elif inner.kind == "sphere" and solid.kind == "sphere":
            outer_centre, outer_radius = solid.sphere
            inner_centre, inner_radius = inner.sphere
            clearance = (
                geo.distance(solid.vertices[outer_centre], inner.vertices[inner_centre])
                + inner_radius
            )
            if not bool(
                sympy.simplify((clearance - outer_radius).subs(fit_display)) == 0
            ):
                return "inscribed sphere must touch the containing sphere"
        return None

    spheres_seen = [(solid.vertices[c], r, so.id) for c, r in solid.spheres]
    bounds_checks: list[str] = []
    for o in plan.objects:  # derived points and extra solids, in declaration order
        if o.type == "point":
            try:
                exact[o.id] = geo.derived_point(exact, o.members, o.params or None)
                bounds_checks.append(o.id)  # checked once every solid of the scene is known
            except geo.GeometryError as exc:
                err("BAD_POINT", f"point '{o.id}': {exc}", o.id)
        elif o in extra:
            params, at = geo.split_attach(o.params)
            coords = geo.at_coordinates(at)  # "at=0,0,2": coordinates instead of a point name
            if at is not None and coords is None and at not in exact:
                err(
                    "UNKNOWN_POINT",
                    f"solid '{o.id}' is placed at unknown point '{at}' (declare that point first)",
                    o.id,
                )
                continue
            labels = geo.free_labels(o.value, o.members, exact)
            origin = coords if coords is not None else (exact[at] if at else None)
            try:
                sub = geo.build_solid(o.value, params, labels, origin=origin)
            except geo.GeometryError as exc:
                err("BAD_SOLID", f"solid '{o.id}': {exc}", o.id)
                continue
            relation_error = fit_error(sub, geo.fit_relation(o.params))
            if relation_error:
                err("INVALID_FIT", f"solid '{o.id}': {relation_error}", o.id)
            if labels != list(o.members or []):
                issues.append(
                    ValidationIssue(
                        code="LABELS_RENAMED",
                        severity="warning",
                        location=o.id,
                        message=f"solid '{o.id}' points are named {labels} (its labels clashed with existing points)",
                    )
                )
            exact.update(sub.vertices)
            spheres_seen.extend((sub.vertices[c], r, o.id) for c, r in sub.spheres)
            display = {**geo.display_values(sub), **display}
            s_lo, s_hi = geo.bounding_box(sub, display)
            lo, hi = [min(a, b) for a, b in zip(lo, s_lo)], [max(a, b) for a, b in zip(hi, s_hi)]
    for pid in bounds_checks:  # inside the union of all the scene's solids
        if not in_scene_bounds(exact[pid]):
            err("POINT_OUTSIDE_GEOMETRY", f"point '{pid}' is outside the declared figure/solid", pid)
    _check_balls(spheres_seen, err)
    for o in plan.objects:
        need = {"segment": 2, "angle": 3, "plane": 3}.get(o.type)
        if need is None:
            continue
        if len(o.members) < need or (o.type != "plane" and len(o.members) != need):
            err("BAD_MEMBERS", f"{o.type} '{o.id}' needs {need} point(s)", o.id)
            continue
        unknown = [m for m in o.members if m not in exact]
        if unknown:
            err(
                "UNKNOWN_POINT",
                f"{o.type} '{o.id}' uses unknown point(s) {unknown}; vertices are {list(solid.vertices)}",
                o.id,
            )

    # connect results in 3D are segments between known points
    segments: dict[str, list[str]] = {
        o.id: o.members for o in plan.objects if o.type == "segment"
    }
    for beat in plan.beats:
        for a in beat.actions:
            if a.operation == "connect":
                unknown = [t for t in a.targets if t not in exact]
                if unknown:
                    err(
                        "UNKNOWN_POINT",
                        f"connect uses unknown point(s) {unknown}",
                        beat.id,
                    )
                if a.results:
                    segments[a.results[0]] = a.targets[:2]

    # a flat figure needs no depth; a 360-degree revolution or a top/front/orbit view shows it
    depth_cue = (
        (
            so.type == "figure"
            and not any(a.operation == "revolve" for b in plan.beats for a in b.actions)
        )
        or any(a.operation == "revolve" for b in plan.beats for a in b.actions)
        or plan.camera in ("orbit", "top_view", "front_view")
    )
    for beat in plan.beats:
        for a in beat.actions:
            if a.operation != "revolve":
                continue
            fig, axis = (objects.get(t) for t in (a.targets + [None, None])[:2])
            if fig is None or fig.type != "figure":
                err("BAD_TARGET_TYPE", "revolve needs [figure, axis segment]", beat.id)
                continue
            axis_members = segments.get(a.targets[1]) if len(a.targets) > 1 else None
            if not axis_members or any(m not in exact for m in axis_members):
                err(
                    "BAD_TARGET_TYPE",
                    "the second revolve target must be a segment between known points (the axis)",
                    beat.id,
                )
                continue
            try:
                geo.revolution(
                    [exact[v] for v in solid.base],
                    exact[axis_members[0]],
                    exact[axis_members[1]],
                )
            except geo.GeometryError as exc:
                err("REVOLUTION_AXIS", str(exc), beat.id)
    for beat in plan.beats:
        if beat.camera in ("orbit", "top_view", "front_view"):
            depth_cue = True
        for a in beat.actions:
            if a.operation == "flatten":
                bad = [
                    t
                    for t in a.targets
                    if objects.get(t) is None or objects[t].type != "plane"
                ]
                if bad:
                    err("BAD_TARGET_TYPE", f"flatten needs a plane, got {bad}", beat.id)
            if a.operation != "measure" or not a.targets or not a.values:
                continue
            target = a.targets[0]
            o = objects.get(target)
            members = segments.get(target) or (
                o.members if o is not None and o.type == "angle" else None
            )
            if members is None or (
                o is not None and o.type not in ("segment", "angle")
            ):
                err(
                    "BAD_TARGET_TYPE",
                    f"measure needs a segment or angle, got '{target}'",
                    beat.id,
                )
                continue
            if not rules["require_measure_consistency"].value or any(
                m not in exact for m in members
            ):
                continue
            parsed = tex_to_sympy(
                a.values[0],
                symbols={str(s) for v in exact.values() for s in v.free_symbols},
            )
            if parsed is None:
                issues.append(
                    ValidationIssue(
                        code="MEASURE_UNCHECKED",
                        message=f"label {a.values[0]!r} on '{target}' is symbolic; not checked",
                        severity="warning",
                        location=beat.id,
                    )
                )
                continue
            value, degrees = parsed
            if o is not None and o.type == "angle":
                truth = geo.angle_at(*(exact[m] for m in members[:3]))
                ok = (
                    ex.equal(truth * 180 / sympy.pi, value)
                    if degrees
                    else (
                        ex.equal(truth, value)
                        or ex.equal(truth * 180 / sympy.pi, value)
                    )
                )
                shown = f"{sympy.N(truth * 180 / sympy.pi, 5)} deg"
            else:
                truth = geo.distance(exact[members[0]], exact[members[1]])
                ok = ex.equal(truth, value)
                shown = str(truth)
            if not ok:
                err(
                    "MEASURE_MISMATCH",
                    f"'{target}' is labelled {a.values[0]!r} but the exact value is {shown}",
                    beat.id,
                    rule="require_measure_consistency",
                )
    if rules["require_3d_depth_cue"].value and not depth_cue:
        err(
            "NO_DEPTH_CUE",
            "show the solid's depth: orbit once, or use a top/front view",
            rule="require_3d_depth_cue",
        )
    _check_formula_sources(plan, objects, segments, err)


GEOMETRIC_SOURCES = ("segment", "plane", "angle", "solid", "figure", "point")


def _vertex_of_created(pid: str, created: set, objects: dict) -> bool:
    """A vertex of an already created solid is on screen too."""
    return any(objects.get(c) is not None and objects[c].type in ("solid", "figure") and pid in (objects[c].members or []) for c in created)


def _check_formula_sources(plan: VisualPlan, objects: dict, segments: dict, err) -> None:
    """Stereometry: no formula appears out of nowhere. Every formula names (parent) the segment, angle,
    section plane, flattened section or solid it is read from, and that object is on screen by then.
    A computation that combines several lengths/angles happens on a cross-section the scene shows."""
    sources = {i for i, o in objects.items() if o.type in GEOMETRIC_SOURCES} | set(segments)
    sources |= {r for b in plan.beats for a in b.actions if a.operation in ("flatten", "revolve") for r in a.results}
    created: set[str] = set()
    used_sources: set[str] = set()
    for beat in plan.beats:
        for a in beat.actions:
            if a.operation in ("create", "grow", "connect", "flatten", "revolve"):
                for t in a.targets:
                    o = objects.get(t)
                    if o is not None and o.type == "formula":
                        if not o.parent:
                            err(
                                "FORMULA_WITHOUT_SOURCE",
                                f"formula '{t}' does not say where on the figure it comes from: set its parent to the "
                                "segment / angle / section plane / flattened section (or the solid, for volume and area) "
                                "it is read from, and create that object first",
                                beat.id,
                            )
                        elif o.parent not in sources:
                            err("FORMULA_WITHOUT_SOURCE", f"formula '{t}': parent '{o.parent}' is not a segment, angle, "
                                "section or solid of this scene", beat.id)
                        elif o.parent not in created and not _vertex_of_created(o.parent, created, objects):
                            err("SOURCE_NOT_SHOWN", f"formula '{t}' is read from '{o.parent}', which is not on screen yet: "
                                "create (or measure) it before the formula", beat.id)
                        else:
                            used_sources.add(o.parent)
                    elif o is not None:
                        created.add(t)
                created.update(a.results)
                if a.operation == "create":
                    created.update(a.targets)
            else:
                created.update(a.results)
    lengthy = {s for s in used_sources if (objects.get(s) and objects[s].type in ("segment", "angle")) or s in segments}
    has_section = any(o.type == "plane" for o in objects.values()) or any(
        a.operation == "flatten" for b in plan.beats for a in b.actions
    )
    if len(lengthy) >= 2 and not has_section:
        err(
            "NO_SECTION",
            "the computation combines several lengths/angles: show the cross-section it happens in (a plane through "
            "the 3 relevant points), flatten it next to the solid, and read the formulas from that flat triangle",
        )
