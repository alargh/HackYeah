"""Stage3D: deterministic stereometry scenes on Manim Community's ThreeDScene.

Cinematography follows the storytelling references (manim-storytelling-skills camera/style guides):
  * resting view phi = 70 deg, theta = -50 deg (three-quarter, never dead-on), zoom so the solid fills ~60%;
  * slow ambient orbit (0.12 rad/s) only during "look at the shape" beats, stopped before reading beats;
  * HUD (title, subtitles, formulas, the flattened panel) is fixed in frame; labels anchored to 3D points
    keep their 3D position but always face the camera (fixed orientation);
  * wireframes are drawn edge by edge (sweep reveal), not faded in.
Exact coordinates come from geometry.py, so lengths/angles drawn are the true ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import sympy as sp
from manim import (
    DEGREES,
    DOWN,
    LEFT,
    OUT,
    RIGHT,
    UP,
    AnimationGroup,
    Create,
    DashedLine,
    DashedVMobject,
    Dot,
    Dot3D,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    Indicate,
    LaggedStart,
    Line,
    MathTex,
    ParametricFunction,
    Polygon,
    RightAngle,
    Surface,
    Succession,
    SurroundingRectangle,
    VGroup,
    VMobject,
    Write,
)

from . import geometry as geo
from . import hud, primitives
from . import theme as T

PHI, THETA, ZOOM = 70 * DEGREES, -50 * DEGREES, 0.82
ORBIT_RATE = 0.12
SOLID_SIZE = 3.4  # world units for the solid's largest extent
PANEL_CENTER = np.array([4.55, 1.05, 0.0])
PANEL_BOX = (3.3, 2.3)  # max width/height of a flattened polygon
FORMULA_X = 4.55
FORMULA_MAX_W = 4.1  # keeps a result box (with its padding) inside the frame
HUD_SHIFT = 2.3  # when the right column is in use the solid sits this far left of centre


def screen_right_in_world(phi: float, theta: float) -> np.ndarray:
    """World vector that projects onto the screen's +x axis for this camera orientation
    (mirrors Manim CE ThreeDCamera: R = Rx(-phi) . Rz(-theta - 90deg), screen = R . world)."""
    from manim import rotation_about_z, rotation_matrix

    R = rotation_matrix(-phi, RIGHT) @ rotation_about_z(-theta - 90 * DEGREES)
    return R.T @ np.array([1.0, 0.0, 0.0])


def view_axes(phi: float, theta: float) -> tuple[np.ndarray, np.ndarray]:
    """(screen-right, towards-camera) world vectors for an orthographic view."""
    from manim import rotation_about_z, rotation_matrix

    R = rotation_matrix(-phi, RIGHT) @ rotation_about_z(-theta - 90 * DEGREES)
    return R.T @ np.array([1.0, 0.0, 0.0]), R.T @ np.array([0.0, 0.0, 1.0])


def tex_label(name: str) -> str:
    """Vertex names with an index render with a subscript: O1 -> O_{1}."""
    import re

    return re.sub(r"^([A-Za-z]+)(\d+)$", r"\1_{\2}", name)


@dataclass(eq=False)
class Obj3D:
    id: str
    type: str
    value: str = ""
    role: str = "neutral"
    members: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    mob: object = None
    visible: bool = False
    fixed: bool = False  # fixed in frame (HUD)
    parts: dict = field(default_factory=dict)
    parent: str | None = None  # formula: the segment / angle / section it is read from


def _c(role):
    return T.color(role)


class Stage3D:
    def __init__(self, scene, title: str = "", layout: str = "space_3d", camera: str = "three_quarter"):
        self.scene = scene
        scene.camera.background_color = T.BACKGROUND
        if camera == "top_view":  # plane figures start flat, seen from above
            scene.set_camera_orientation(phi=0, theta=-90 * DEGREES, zoom=ZOOM)
        else:
            scene.set_camera_orientation(phi=PHI, theta=THETA, zoom=ZOOM)
        self.layout = layout
        self.objs: dict[str, Obj3D] = {}
        self.exact: dict[str, sp.Matrix] = {}
        self.pts: dict[str, np.ndarray] = {}
        self.scale = 1.0
        self.offset = np.zeros(3)
        self.subs: dict = {}  # symbolic dimensions -> display numbers (a -> 1)
        self.solid_zoom = ZOOM
        self.center = np.zeros(3)
        self.measures: dict[frozenset, str] = {}
        self.angle_measures: dict[tuple, str] = {}
        self.formulas: list[str] = []
        self.panel: str | None = None
        self.panel_shape: dict[str, np.ndarray] = {}
        self.hud_active = False
        self.caption = None
        self.orbiting = False
        self.last_result: str | None = None
        self.title = None
        if title:
            self.title = primitives.text(title, "title", "secondary")
            if self.title.width > 12:
                self.title.scale_to_fit_width(12)
            scene.add_fixed_in_frame_mobjects(self.title)
            self.title.move_to(UP * T.TITLE_Y)
            scene.play(FadeIn(self.title), run_time=0.6)

    # ------------------------------------------------------------------ geometry helpers
    def _world(self, exact: sp.Matrix) -> np.ndarray:
        v = np.array([float(sp.sympify(x).subs(self.subs)) for x in exact], dtype=float)
        return (v - self.offset) * self.scale

    def _outward(self, p: np.ndarray, amount: float = 0.38) -> np.ndarray:
        d = p - self.center
        n = np.linalg.norm(d)
        return p + (d / n if n > 1e-6 else OUT) * amount

    def _beside(self, a: np.ndarray, b: np.ndarray, amount: float) -> np.ndarray:
        """A point next to segment ab as seen on screen (never on the line, even for an inner segment like the height)."""
        cam = self.scene.camera
        phi, theta = cam.get_phi(), cam.get_theta()
        view = np.array([math.sin(phi) * math.cos(theta), math.sin(phi) * math.sin(theta), math.cos(phi)])
        mid = (a + b) / 2
        perp = np.cross(b - a, view)
        n = np.linalg.norm(perp)
        if n < 1e-6:
            return self._outward(mid, amount)
        perp /= n
        away = mid - self.center
        if np.dot(perp, away) < 0 or (np.linalg.norm(away) < 0.3 and perp[0] + perp[1] < 0):
            perp = -perp
        return mid + perp * amount

    def _label3d(self, text: str, at: np.ndarray, role: str, size: str = "item"):
        lbl = primitives.text(text, "label", role, weight="BOLD") if not text.isascii() else MathTex(text).set_color(_c(role))
        lbl.scale(0.75 if size == "item" else 0.65)
        lbl.move_to(at)
        self.scene.add_fixed_orientation_mobjects(lbl)
        return lbl

    # ------------------------------------------------------------------ registry
    def declare(self, oid, otype, value="", role="neutral", members=(), parent=None, params=()):
        o = Obj3D(id=oid, type=otype, value=value, role=role, members=list(members), params=list(params), parent=parent)
        self.objs[oid] = o
        if otype in ("solid", "figure"):
            self._build_solid(o)
        elif otype == "point":
            self.exact[oid] = geo.derived_point(self.exact, o.members, o.params or None)
            self.pts[oid] = self._world(self.exact[oid])
            dot = Dot3D(self.pts[oid], radius=0.06, color=_c(role), resolution=(6, 6))
            o.parts = {"dot": dot}
            o.mob = VGroup(dot)
        elif otype == "segment":
            a, b = (self.pts[m] for m in o.members[:2])
            o.mob = Line(a, b, stroke_width=T.STROKE["thick"], color=_c(role))
        elif otype == "plane":
            corners = [self.pts[m] for m in o.members]
            o.mob = Polygon(*corners, stroke_width=T.STROKE["normal"], color=_c(role)).set_fill(_c(role), opacity=0.28)
        elif otype == "angle":
            o.mob = self._arc(*o.members[:3], role=role)
        elif otype in ("formula", "label"):
            o.mob = primitives.formula(value, role) if otype == "formula" else primitives.label(value, role)
            o.fixed = True
        else:
            raise ValueError(f"object type '{otype}' is not available in 3D scenes")
        return o

    def _build_solid(self, o: Obj3D) -> None:
        params, at = geo.split_attach(o.params)
        attached = any(x.type in ("solid", "figure") and x is not o and x.parts for x in self.objs.values())
        if attached:  # a second solid (inscribed / circumscribed) shares the first solid's coordinates
            coords = geo.at_coordinates(at)
            if at is not None and coords is None and at not in self.exact:
                raise ValueError(f"solid '{o.id}': unknown point '{at}'")
            origin = coords if coords is not None else (self.exact[at] if at is not None else None)
            solid = geo.build_solid(o.value, params, geo.free_labels(o.value, o.members, self.exact), origin=origin)
            self.subs = {**geo.display_values(solid), **self.subs}
        else:
            solid = geo.build_solid(o.value, params, o.members or None)
            self.subs = geo.display_values(solid)
            lo, hi = geo.bounding_box(solid, self.subs)
            self.offset = (lo + hi) / 2
            self.scale = SOLID_SIZE / max(float((hi - lo).max()), 1e-6)
        for name, v in solid.vertices.items():
            self.exact[name] = v
            self.pts[name] = self._world(v)
        if not attached:
            self.center = np.mean([self.pts[n] for n in solid.vertices], axis=0)
            if solid.round:
                lo, hi = geo.bounding_box(solid, self.subs)
                self.center = ((lo + hi) / 2 - self.offset) * self.scale
        self._fit_view(solid, reset=not attached)
        if solid.round:
            edges, faces = self._round_parts(solid, o.role)
        else:
            edges = VGroup(*(Line(self.pts[a], self.pts[b], stroke_width=T.STROKE["normal"], color=_c(o.role)) for a, b in solid.edges))
            face_opacity = 0.2 if geo.is_figure(solid.kind) else 0.07
            faces = VGroup(
                *(
                    Polygon(*(self.pts[v] for v in face), stroke_width=0).set_fill(_c(o.role), opacity=face_opacity)
                    for face in solid.faces
                )
            )
        labels = VGroup()
        # an extra solid (balls of a pyramid, an inscribed sphere) gets no automatic vertex labels: its centre
        # coincides with a point that is already labelled; its points still exist for segments / measures
        for name in ([] if attached else solid.vertices):
            lbl = MathTex(tex_label(name)).set_color(_c("secondary")).scale(0.7)
            lbl.move_to(self._outward(self.pts[name], 0.32))
            labels.add(lbl)
        o.parts = {"edges": edges, "faces": faces, "labels": labels, "solid": solid}
        o.mob = VGroup(faces, edges)
        # every vertex is addressable as a point object
        for name in solid.vertices:
            p = Obj3D(id=name, type="point", value=name, members=[])
            p.mob = VGroup()
            p.visible = True
            self.objs.setdefault(name, p)

    def _fit_view(self, solid, reset: bool) -> None:
        """Frame everything declared so far: the first solid sets the scale; extra solids (e.g. balls around
        a helper tetrahedron) widen the box, and the camera zooms out so they all fit."""
        lo, hi = geo.bounding_box(solid, self.subs)
        lo, hi = (np.array(lo, dtype=float) - self.offset) * self.scale, (np.array(hi, dtype=float) - self.offset) * self.scale
        if reset or not hasattr(self, "_box"):
            self._box = (lo, hi)
            return
        lo, hi = np.minimum(self._box[0], lo), np.maximum(self._box[1], hi)
        self._box = (lo, hi)
        self.center = (lo + hi) / 2
        extent = float((hi - lo).max())
        self.solid_zoom = ZOOM * min(1.0, SOLID_SIZE * 1.45 / max(extent, 1e-6))
        self.scene.set_camera_orientation(zoom=self.solid_zoom, frame_center=self._frame_center(PHI, THETA))

    # ------------------------------------------------------------------ round solids
    @staticmethod
    def _circle_pt(c: np.ndarray, r: float, t: float) -> np.ndarray:
        return c + r * np.array([math.cos(t), math.sin(t), 0.0])

    def _radius(self, r) -> float:
        return float(sp.sympify(r).subs(self.subs)) * self.scale

    def _round_parts(self, solid, role: str) -> tuple[VGroup, VGroup]:
        """Textbook drawing of a round solid: translucent surface, visible rim arcs solid, hidden arcs
        dashed, silhouette generators / outline. The lines are recomputed whenever the camera turns."""
        color = _c(role)
        rims = [(self.pts[c], self._radius(r)) for c, r in solid.circles]
        surf = dict(fill_color=color, checkerboard_colors=False, stroke_color=color)
        faces = VGroup()
        if solid.spheres:
            for centre, radius in solid.spheres:
                c, r = self.pts[centre], self._radius(radius)
                faces.add(
                    Surface(
                        lambda u, v, c=c, r=r: c + r * np.array([math.cos(u) * math.sin(v), math.sin(u) * math.sin(v), math.cos(v)]),
                        u_range=[0, 2 * math.pi], v_range=[0, math.pi], resolution=(24, 12),
                        fill_opacity=0.1, stroke_width=0.4, stroke_opacity=0.12, **surf,
                    )
                )
        else:
            (cb, rb) = rims[0]
            ct, rt = rims[1] if len(rims) > 1 else (self.pts[solid.axis[1]], 0.0)
            faces.add(
                Surface(
                    lambda u, v: (1 - v) * self._circle_pt(cb, rb, u) + v * self._circle_pt(ct, rt, u),
                    u_range=[0, 2 * math.pi], v_range=[0, 1], resolution=(28, 4),
                    fill_opacity=0.1, stroke_width=0.4, stroke_opacity=0.12, **surf,
                )
            )
            for cc, rr in rims:
                faces.add(
                    Surface(
                        lambda u, v, cc=cc, rr=rr: self._circle_pt(cc, rr * v, u),
                        u_range=[0, 2 * math.pi], v_range=[0, 1], resolution=(24, 1),
                        fill_opacity=0.06, stroke_width=0, **surf,
                    )
                )
        cam = self.scene.camera
        state = {"view": (cam.get_phi(), cam.get_theta())}
        lines = self._round_lines(solid, rims, *state["view"], color)

        def refresh(m):
            view = (cam.get_phi(), cam.get_theta())
            if max(abs(view[0] - state["view"][0]), abs(view[1] - state["view"][1])) < 0.004:
                return
            state["view"] = view
            col, op = m.get_stroke_color(), m.get_stroke_opacity()
            m.become(self._round_lines(solid, rims, *view, col).set_stroke(opacity=op))

        lines.add_updater(refresh)
        axis = VGroup()
        if solid.axis:
            axis.add(DashedLine(self.pts[solid.axis[0]], self.pts[solid.axis[1]], dash_length=0.08,
                                stroke_width=T.STROKE["thin"], color=_c("secondary")))
        return VGroup(lines, axis), faces

    def _round_lines(self, solid, rims, phi: float, theta: float, color) -> VGroup:
        right, toward = view_axes(phi, theta)
        w = T.STROKE["normal"]
        out = VGroup()

        def arc(c, r, t0, t1, dashed):
            if t1 - t0 < 1e-3 or r < 1e-6:
                return
            curve = ParametricFunction(lambda t: self._circle_pt(c, r, t), t_range=[t0, t1], stroke_width=w, color=color)
            if dashed:
                curve = DashedVMobject(curve, num_dashes=max(6, int(5 * (t1 - t0) * r)), dashed_ratio=0.55)
                curve.set_stroke(color=color, width=w * 0.75)
            out.add(curve)

        if solid.spheres:
            up = np.cross(toward, right)
            for centre, radius in solid.spheres:
                c, r = self.pts[centre], self._radius(radius)
                out.add(ParametricFunction(lambda t, c=c, r=r: c + r * (math.cos(t) * right + math.sin(t) * up),
                                           t_range=[0, 2 * math.pi], stroke_width=w, color=color))
                if abs(toward[2]) < 0.999:  # equator: front half solid, back half dashed
                    a = math.atan2(toward[1], toward[0])
                    arc(c, r, a - math.pi / 2, a + math.pi / 2, False)
                    arc(c, r, a + math.pi / 2, a + 3 * math.pi / 2, True)
            if solid.kind == "ball_pyramid":  # helper edges between the centres, dashed
                for p, q in solid.edges:
                    out.add(DashedLine(self.pts[p], self.pts[q], dash_length=0.08, stroke_width=T.STROKE["thin"], color=color))
            return out
        (cb, rb) = rims[0]
        ct, rt = rims[1] if len(rims) > 1 else (self.pts[solid.axis[1]], 0.0)

        # silhouette generators: along a generator of a cylinder/cone/frustum the surface normal is
        # constant; the generator is on the outline where that normal is perpendicular to the view
        def g(t):
            tangent = np.array([-math.sin(t), math.cos(t), 0.0])
            gen = self._circle_pt(ct, rt, t) - self._circle_pt(cb, rb, t)
            return float(np.dot(np.cross(tangent, gen), toward))

        ts = np.linspace(0, 2 * math.pi, 721)
        vals = [g(t) for t in ts]
        sil = [float(ts[i]) for i in range(720) if vals[i] * vals[i + 1] < 0 or vals[i] == 0]
        if len(sil) >= 2 and abs(toward[2]) < 0.999:
            t0, t1 = sil[0], sil[1]
            for t in (t0, t1):
                out.add(Line(self._circle_pt(cb, rb, t), self._circle_pt(ct, rt, t), stroke_width=w, color=color))
            mid = (t0 + t1) / 2
            facing = np.dot(np.array([math.cos(mid), math.sin(mid), 0.0]), toward) > 0
            front = (t0, t1) if facing else (t1, t0 + 2 * math.pi)
            back = (t1, t0 + 2 * math.pi) if facing else (t0, t1)
            seen_from_above = toward[2] > 0  # then the bottom rim's back arc is behind the surface
            for c, r, bottom in ((cb, rb, True), (ct, rt, False)):
                arc(c, r, *front, False)
                arc(c, r, *back, bottom == seen_from_above)
        else:  # looking along the axis (or no outline found): full circles
            arc(cb, rb, 0, 2 * math.pi, False)
            arc(ct, rt, 0, 2 * math.pi, False)
        return out

    def _arc(self, p: str, v: str, q: str, role: str, radius: float = 0.55) -> VMobject:
        V, P, Q = self.pts[v], self.pts[p], self.pts[q]
        u = (P - V) / np.linalg.norm(P - V)
        w = Q - V
        w_perp = w - np.dot(w, u) * u
        w_perp /= np.linalg.norm(w_perp)
        theta = math.acos(max(-1.0, min(1.0, float(np.dot(u, (Q - V) / np.linalg.norm(Q - V))))))
        if abs(theta - math.pi / 2) < 1e-3:  # right angle: small square
            s = radius * 0.55
            corner = VMobject(stroke_width=T.STROKE["normal"], color=_c(role))
            corner.set_points_as_corners([V + s * u, V + s * u + s * w_perp, V + s * w_perp])
            return corner
        return ParametricFunction(
            lambda t: V + radius * (math.cos(t) * u + math.sin(t) * w_perp),
            t_range=[0, theta], stroke_width=T.STROKE["normal"], color=_c(role),
        )

    def get(self, oid: str) -> Obj3D:
        if oid not in self.objs:
            raise KeyError(f"unknown visual object '{oid}'")
        return self.objs[oid]

    # ------------------------------------------------------------------ beats
    def beat(self, beat_id: str, caption: str = "", layout: str | None = None, duration: float = 4.0) -> None:
        if T.CAPTIONS and caption:
            new = hud.subtitles(self.scene.renderer, caption, duration)
            self.scene.add_fixed_in_frame_mobjects(new)
            new.move_to(UP * T.CAPTION_Y)
            hud.swap_caption(self.scene, self.caption, new)
            self.caption = new

    def do(self, primitive: str, targets=(), run_time: float = 0.8, **params) -> None:
        fn = getattr(self, f"p_{primitive}", None)
        if fn is None:
            raise ValueError(f"unknown 3D primitive '{primitive}'")
        fn(list(targets), run_time=run_time, **params)

    def play(self, *anims, run_time: float = 0.8, lag_ratio: float = 0.0) -> None:
        anims = [a for a in anims if a is not None]
        if anims:
            self.scene.play(AnimationGroup(*anims, lag_ratio=lag_ratio), run_time=max(run_time, 0.2))

    def wait(self, seconds: float) -> None:
        if seconds > 0.05:
            self.scene.wait(seconds)

    def finish(self) -> None:
        if self.orbiting:
            self.scene.stop_ambient_camera_rotation()
            self.orbiting = False
        self.scene.wait(0.4)

    # ------------------------------------------------------------------ HUD placement
    def _column_top(self) -> float:
        if self.panel:
            return self.get(self.panel).mob.get_bottom()[1] - 0.35
        return 2.75

    def _layout_formulas(self, instant: str | None = None) -> list:
        """Right column: flattened panel on top, formulas stacked below by their real heights;
        when the column is full the oldest lines leave first."""
        bottom_limit, gap = -2.85, 0.32
        visible = [self.get(f) for f in self.formulas if self.get(f).visible]
        anims = []
        while visible:
            total = sum(o.mob.height for o in visible) + gap * (len(visible) - 1)
            if self._column_top() - total >= bottom_limit or len(visible) == 1:
                break
            old = visible.pop(0)
            old.visible = False
            anims.append(FadeOut(old.mob))
        y = self._column_top()
        for o in visible:
            target = np.array([FORMULA_X, y - o.mob.height / 2, 0.0])
            y -= o.mob.height + gap
            if o.id == instant:
                o.mob.move_to(target)
            elif np.linalg.norm(o.mob.get_center() - target) > 0.02:
                anims.append(o.mob.animate.move_to(target))
        return anims

    def _activate_hud(self) -> None:
        """First use of the right column: re-aim the camera so the solid sits left of centre."""
        if self.hud_active:
            return
        self.hud_active = True
        if self.orbiting:
            self.scene.stop_ambient_camera_rotation()
            self.orbiting = False
        self.scene.move_camera(phi=PHI, theta=THETA, zoom=self.solid_zoom, frame_center=self._frame_center(PHI, THETA), run_time=0.8)

    def _frame_center(self, phi: float, theta: float) -> np.ndarray:
        shift = screen_right_in_world(phi, theta) * HUD_SHIFT / (self.solid_zoom / ZOOM) if self.hud_active else np.zeros(3)
        return self.center + shift

    # sources get distinct colours so every formula can be matched to its place on the figure
    SOURCE_ROLES = ("focus", "active", "transformation", "result")

    def _show_source(self, formula: Obj3D) -> list:
        """A formula is written in the colour of the segment / angle / section it comes from, and that
        object lights up at the same moment: the learner sees where on the figure the formula is read."""
        src = self.objs.get(formula.parent or "")
        if src is None or src.mob is None or not src.visible:
            return []
        if "source_role" not in src.parts:
            used = {o.parts.get("source_role") for o in self.objs.values() if o.parts.get("source_role")}
            free = [r for r in self.SOURCE_ROLES if r not in used] or list(self.SOURCE_ROLES)
            src.parts["source_role"] = free[0]
        color = _c(src.parts["source_role"])
        formula.mob.set_color(color)
        target = src.parts.get("edges", src.mob) if src.type in ("solid", "figure") else src.mob
        if src.type == "point":
            target = src.parts.get("dot", src.mob)
        # flash first, then keep the colour (Indicate restores the old state when it ends)
        flash = Indicate(target, color=color, scale_factor=1.06)
        recolor = target.animate.set_color(color) if src.type != "panel" else target.animate.set_stroke(color)
        return [Succession(flash, recolor)]

    def _place_formula(self, o: Obj3D) -> None:
        """Add a formula at the bottom of the right column (written in place by the caller)."""
        self._activate_hud()
        if o.mob.width > FORMULA_MAX_W:
            o.mob.scale_to_fit_width(FORMULA_MAX_W)
        self.formulas.append(o.id)
        o.visible = True
        moves = self._layout_formulas(instant=o.id)
        if moves:  # older lines move / leave first; the new line is not on screen until it is written
            self.scene.play(*moves, run_time=0.4)
        self.scene.add_fixed_in_frame_mobjects(o.mob)
        self.scene.remove(o.mob)  # registered as fixed-in-frame; Write brings it on screen

    # ------------------------------------------------------------------ primitives
    def p_appear(self, targets, run_time=1.0, role=None, lag=0.15):
        anims = []
        for t in targets:
            o = self.get(t)
            if o.visible:
                continue
            o.visible = True
            if o.type in ("solid", "figure"):
                labels = o.parts["labels"]
                self.scene.add_fixed_orientation_mobjects(*labels)
                parts = [LaggedStart(*(Create(e) for e in o.parts["edges"]), lag_ratio=0.12), FadeIn(o.parts["faces"])]
                if len(labels):
                    parts.append(LaggedStart(*(FadeIn(lbl) for lbl in labels), lag_ratio=0.1))
                anims.append(AnimationGroup(*parts, lag_ratio=0.35))
                o.mob = VGroup(o.parts["faces"], o.parts["edges"], labels)
            elif o.type == "point":
                lbl = self._label3d(o.value or o.id, self._outward(self.pts[t], 0.3), "secondary")
                o.parts["label"] = lbl
                o.mob.add(lbl)
                anims.append(AnimationGroup(GrowFromCenter(o.parts["dot"]), FadeIn(lbl)))
            elif o.type in ("segment", "angle"):
                anims.append(Create(o.mob))
            elif o.type == "plane":
                anims.append(AnimationGroup(Create(o.mob), lag_ratio=0))
            elif o.type in ("formula", "label"):
                self._place_formula(o)
                anims.append(Write(o.mob))
                anims.extend(self._show_source(o))
        self.play(*anims, run_time=run_time, lag_ratio=lag)

    p_grow = p_appear

    def p_disappear(self, targets, run_time=0.6, role=None):
        mobs = []
        for t in targets:
            o = self.get(t)
            if o.visible:
                o.visible = False
                mobs.append(o.mob)
        self.play(*(FadeOut(m) for m in mobs), run_time=run_time)

    def p_cross_out(self, targets, run_time=0.6, role="forbidden"):
        self.p_recolor(targets, run_time=run_time, role="forbidden")

    def _recolor_anims(self, o: Obj3D, role: str):
        o.role = role
        if o.type in ("solid", "figure"):
            return o.parts["edges"].animate.set_color(_c(role))
        if o.type == "plane":
            return o.mob.animate.set_stroke(_c(role)).set_fill(_c(role), opacity=0.3)
        if o.type == "point":
            return o.parts["dot"].animate.set_color(_c(role))
        return o.mob.animate.set_color(_c(role))

    def p_recolor(self, targets, run_time=0.5, role="active"):
        self.play(*(self._recolor_anims(self.get(t), role) for t in targets if self.get(t).mob is not None), run_time=run_time)

    def p_indicate(self, targets, run_time=0.6, role="focus"):
        mobs = [self.get(t).mob for t in targets if self.get(t).type not in ("point",) or self.get(t).parts]
        mobs = [m.parts["dot"] if False else m for m in mobs]
        self.play(*(Indicate(m, color=_c(role), scale_factor=1.08) for m in mobs if len(m.get_family()) > 0), run_time=run_time)

    def p_emphasize(self, targets, run_time=1.2, role="result"):
        for t in targets:
            o = self.get(t)
            if o.fixed:
                box = SurroundingRectangle(o.mob, color=_c(role), buff=0.18, corner_radius=T.CORNER_RADIUS, stroke_width=T.STROKE["thick"])
                over = box.get_right()[0] - (T.FRAME_WIDTH / 2 - 0.15)  # keep the box inside the frame
                if over > 0:
                    o.mob.shift(LEFT * over)
                    box.shift(LEFT * over)
                self.scene.add_fixed_in_frame_mobjects(box)
                self.play(o.mob.animate.set_color(_c(role)), run_time=run_time * 0.3)
                self.play(Create(box), run_time=run_time * 0.4)
                self.play(Indicate(o.mob, color=_c(role), scale_factor=1.08), run_time=run_time * 0.3)
            else:
                self.play(self._recolor_anims(o, role), run_time=run_time * 0.4)
                if o.type in ("segment", "plane", "angle"):
                    self.play(o.mob.animate.set_stroke(width=T.STROKE["thick"] * 1.6), run_time=run_time * 0.3)
                self.play(Indicate(o.mob, color=_c(role), scale_factor=1.05), run_time=run_time * 0.3)
            self.last_result = t

    def p_connect(self, targets, run_time=0.8, result=None, role="active"):
        a, b = targets[0], targets[1]
        oid = result or f"{a}__{b}"
        line = DashedLine(self.pts[a], self.pts[b], dash_length=0.12, stroke_width=T.STROKE["normal"], color=_c(role))
        o = Obj3D(id=oid, type="segment", role=role, members=[a, b], mob=line, visible=True)
        self.objs[oid] = o
        self.play(Create(line), run_time=run_time)
        self.last_result = oid

    def p_measure(self, targets, run_time=0.8, value="", role="focus"):
        o = self.get(targets[0])
        if o.type == "angle":
            p, v, q = o.members[:3]
            bis = (self.pts[p] - self.pts[v]) / np.linalg.norm(self.pts[p] - self.pts[v]) + (self.pts[q] - self.pts[v]) / np.linalg.norm(self.pts[q] - self.pts[v])
            at = self.pts[v] + 0.95 * bis / max(np.linalg.norm(bis), 1e-6)
            self.angle_measures[(p, v, q)] = value
        else:
            a, b = o.members[:2]
            mid = (self.pts[a] + self.pts[b]) / 2
            at = self._beside(self.pts[a], self.pts[b], 0.4)
            self.measures[frozenset((a, b))] = value
        lbl = MathTex(value).set_color(_c(role)).scale(0.62)
        lbl.move_to(at)
        self.scene.add_fixed_orientation_mobjects(lbl)
        o.parts["measure"] = lbl
        extra = None
        if self.panel:  # the flat copy shows the same measurement
            extra = self._panel_angle(*o.members[:3], value) if o.type == "angle" else self._panel_edge_label(*o.members[:2], value)
            if extra is not None:
                self.scene.add_fixed_in_frame_mobjects(extra)
                self.get(self.panel).mob.add(extra)
        anims = [FadeIn(lbl, scale=0.6), Indicate(o.mob, color=_c(role), scale_factor=1.04)]
        if extra is not None:
            anims.append(FadeIn(extra, scale=0.6))
        self.play(*anims, run_time=run_time)

    def _panel_edge_label(self, a: str, b: str, value: str):
        if a not in self.panel_shape or b not in self.panel_shape:
            return None
        pa, pb = self.panel_shape[a], self.panel_shape[b]
        cen = np.mean(list(self.panel_shape.values()), axis=0)
        mid = (pa + pb) / 2
        dirv = (mid - cen) / max(np.linalg.norm(mid - cen), 1e-6)
        return MathTex(value).set_color(_c("focus")).scale(0.62).move_to(mid + dirv * 0.38)

    def _panel_angle(self, p: str, v: str, q: str, value: str):
        if not all(n in self.panel_shape for n in (p, v, q)):
            return None
        from manim import Arc

        V = self.panel_shape[v]
        a1, a2 = self.panel_shape[p] - V, self.panel_shape[q] - V
        start, end = math.atan2(a2[1], a2[0]), math.atan2(a1[1], a1[0])
        sweep = (end - start + math.pi) % (2 * math.pi) - math.pi
        arc = Arc(radius=0.5, start_angle=start, angle=sweep, arc_center=V, color=_c("focus"), stroke_width=T.STROKE["normal"])
        bis = a1 / np.linalg.norm(a1) + a2 / np.linalg.norm(a2)
        lbl = MathTex(value).set_color(_c("focus")).scale(0.6).move_to(V + 0.85 * bis / max(np.linalg.norm(bis), 1e-6))
        return VGroup(arc, lbl)

    def p_flatten(self, targets, run_time=1.6, result="panel", role="focus"):
        """Lift a plane polygon out of the solid: draw its TRUE shape flat in the side panel."""
        o = self.get(targets[0])
        names = list(o.members)
        exact = [self.exact[n] for n in names]
        # put the right-angle vertex first so legs lie along the axes
        for i in range(len(names)):
            if len(names) == 3 and geo.is_right_angle(exact[i - 1], exact[i], exact[(i + 1) % 3]):
                names = names[i:] + names[:i]
                exact = exact[i:] + exact[:i]
                break
        d = lambda i, j: float(geo.distance(exact[i], exact[j]).subs(self.subs))  # noqa: E731
        flat = [np.array([0.0, 0.0, 0.0]), np.array([d(0, 1), 0.0, 0.0])]
        L = d(0, 1)
        for k in range(2, len(names)):
            d0, d1 = d(0, k), d(1, k)
            x = (d0**2 - d1**2 + L**2) / (2 * L)
            flat.append(np.array([x, math.sqrt(max(d0**2 - x**2, 0.0)), 0.0]))
        shape = np.array(flat)
        size = shape.max(axis=0) - shape.min(axis=0)
        k = min(PANEL_BOX[0] / max(size[0], 1e-6), PANEL_BOX[1] / max(size[1], 1e-6))
        shape = (shape - (shape.max(axis=0) + shape.min(axis=0)) / 2) * k + PANEL_CENTER
        poly = Polygon(*shape, stroke_width=T.STROKE["thick"], color=_c(role)).set_fill(_c(role), opacity=0.18)
        parts = VGroup(poly)
        cen = shape.mean(axis=0)
        for name, p in zip(names, shape):
            lbl = MathTex(name).set_color(_c("secondary")).scale(0.7)
            dirv = (p - cen) / max(np.linalg.norm(p - cen), 1e-6)
            parts.add(lbl.move_to(p + dirv * 0.32))
        n = len(names)
        self.panel_shape = {name: p for name, p in zip(names, shape)}
        for i in range(n):
            a, b = names[i], names[(i + 1) % n]
            val = self.measures.get(frozenset((a, b)))
            lbl = self._panel_edge_label(a, b, val) if val else None
            if lbl is not None:
                parts.add(lbl)
        for i in range(n):
            prev, cur, nxt = exact[i - 1], exact[i], exact[(i + 1) % n]
            if geo.is_right_angle(prev, cur, nxt):
                parts.add(RightAngle(Line(shape[i], shape[(i + 1) % n]), Line(shape[i], shape[i - 1]), length=0.25, color=_c("secondary")))
            key = next((kk for kk in self.angle_measures if kk[1] == names[i] and {kk[0], kk[2]} == {names[i - 1], names[(i + 1) % n]}), None)
            if key:
                ang = self._panel_angle(key[0], key[1], key[2], self.angle_measures[key])
                if ang is not None:
                    parts.add(ang)
        self.panel = result
        self._activate_hud()
        panel = Obj3D(id=result, type="panel", role=role, members=names, mob=parts, visible=True, fixed=True)
        self.objs[result] = panel
        moves = self._layout_formulas()  # make room under the panel first, so nothing overlaps it
        if moves:
            self.scene.play(*moves, run_time=0.5)
        self.scene.add_fixed_in_frame_mobjects(parts)
        self.play(Indicate(o.mob, color=_c(role), scale_factor=1.06), run_time=run_time * 0.3)
        self.play(Create(poly), LaggedStart(*(FadeIn(m) for m in parts[1:]), lag_ratio=0.15), run_time=run_time * 0.7)
        self.last_result = result

    def p_revolve(self, targets, run_time=4.0, result="revolution", role="transformation"):
        """The plane figure turns 360 degrees about the axis; the surface it sweeps grows with the angle."""
        from manim import TAU, Surface, ValueTracker, always_redraw

        fig, axis = self.get(targets[0]), self.get(targets[1])
        a_name, b_name = axis.members[:2]
        P, Q = self.pts[a_name], self.pts[b_name]
        d = (Q - P) / np.linalg.norm(Q - P)
        poly = [self.pts[v] for v in fig.parts["solid"].base]

        def rot(x: np.ndarray, ang: float) -> np.ndarray:  # Rodrigues rotation about the axis line
            v = x - P
            return P + v * math.cos(ang) + np.cross(d, v) * math.sin(ang) + d * np.dot(d, v) * (1 - math.cos(ang))

        def dist_axis(x: np.ndarray) -> float:
            return float(np.linalg.norm(np.cross(d, x - P)))

        bands = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        bands = [(a, b) for a, b in bands if dist_axis(a) > 1e-6 or dist_axis(b) > 1e-6]  # edges on the axis sweep nothing
        angle = ValueTracker(0.001)

        def surfaces():
            th = max(angle.get_value(), 0.001)
            res_v = max(2, int(36 * th / TAU))
            g = VGroup()
            for a, b in bands:
                g.add(
                    Surface(
                        lambda u, v, a=a, b=b: rot(a + (b - a) * u, v),
                        u_range=[0, 1], v_range=[0, th], resolution=(1, res_v),
                        fill_color=_c(role), fill_opacity=0.32, stroke_color=_c(role), stroke_width=0.4,
                        checkerboard_colors=False,
                    )
                )
            return g

        swept = always_redraw(surfaces)
        ghost = Polygon(*poly, stroke_width=T.STROKE["thick"], color=_c("focus")).set_fill(_c("focus"), opacity=0.35)
        ghost.add_updater(lambda m: m.set_points_as_corners([rot(x, angle.get_value()) for x in poly + poly[:1]]))
        # the axis, extended beyond the figure, dashed
        ext = 0.9 * self.scale if self.scale else 0.9
        axis_line = DashedLine(P - d * ext, Q + d * ext, dash_length=0.15, stroke_width=T.STROKE["normal"], color=_c("secondary"))
        self.scene.add(swept, ghost)
        self.play(Create(axis_line), Indicate(fig.mob, color=_c("focus"), scale_factor=1.03), run_time=0.8)
        self.scene.play(angle.animate.set_value(TAU), run_time=max(run_time - 1.4, 1.5), rate_func=lambda t: t)
        swept.clear_updaters()
        ghost.clear_updaters()
        self.play(FadeOut(ghost), run_time=0.6)
        o = Obj3D(id=result, type="revolution", role=role, members=[a_name, b_name], mob=VGroup(swept, axis_line), visible=True)
        self.objs[result] = o
        # re-frame on the new solid: it is centred on the axis and as wide as twice the largest radius
        self.center = (P + Q) / 2
        reach = max(max(dist_axis(x) for x in poly) * 2, float(np.linalg.norm(Q - P)) + 2 * ext)
        self.solid_zoom = ZOOM * min(1.0, SOLID_SIZE * 1.15 / max(reach, 1e-6))
        self.scene.move_camera(zoom=self.solid_zoom, frame_center=self._frame_center(PHI, THETA), run_time=1.0)
        self.last_result = result

    def p_transform_tex(self, targets, run_time=1.0, result="", value="", role="transformation"):
        sources = [self.get(t) for t in targets]
        new = self.objs.get(result) or self.declare(result, "formula", value, role, parent=sources[0].parent)
        if new.parent is None:
            new.parent = sources[0].parent
        src = self.objs.get(new.parent or "")
        if src is not None and src.parts.get("source_role") and role != "result":
            new.mob.set_color(_c(src.parts["source_role"]))
        new.mob.move_to(sources[0].mob)
        if new.mob.width > FORMULA_MAX_W:
            new.mob.scale_to_fit_width(FORMULA_MAX_W)
        self.scene.add_fixed_in_frame_mobjects(new.mob)
        new.visible = True
        idx = self.formulas.index(sources[0].id) if sources[0].id in self.formulas else len(self.formulas)
        for s in sources:
            s.visible = False
            if s.id in self.formulas:
                self.formulas.remove(s.id)
        self.formulas.insert(min(idx, len(self.formulas)), new.id)
        # cross-fade, not TransformMatchingTex: its in-flight copies are not fixed in frame, so they would be drawn
        # skewed inside the 3D space next to the solid
        lift = UP * 0.12
        self.play(*(FadeOut(s.mob, shift=lift) for s in sources), FadeIn(new.mob, shift=lift), run_time=run_time)
        moves = self._layout_formulas()
        if moves:
            self.play(*moves, run_time=0.4)
        self.last_result = new.id

    def p_dim_others(self, targets, run_time=0.6, role=None):
        keep = {t for t in targets}
        anims = []
        for o in self.objs.values():
            if o.visible and o.id not in keep and o.type in ("solid", "figure", "segment", "plane", "revolution") and o.mob is not None:
                anims.append(o.mob.animate.set_opacity(0.25))
        self.play(*anims, run_time=run_time)

    def p_undim(self, targets, run_time=0.5, role=None):
        anims = []
        for o in self.objs.values():
            if o.visible and o.type in ("solid", "figure"):
                anims += [o.parts["edges"].animate.set_stroke(opacity=1), o.parts["labels"].animate.set_opacity(1)]
            elif o.visible and o.type in ("segment", "plane"):
                anims.append(o.mob.animate.set_stroke(opacity=1))
        self.play(*anims, run_time=run_time)

    # ------------------------------------------------------------------ camera
    def p_camera(self, targets, run_time=1.0, preset="three_quarter", role=None):
        s = self.scene
        if preset == "orbit":
            if not self.orbiting:
                if self.hud_active:  # orbit around the solid itself, not around the shifted frame centre
                    s.move_camera(frame_center=self.center, run_time=0.6)
                s.begin_ambient_camera_rotation(rate=ORBIT_RATE)
                self.orbiting = True
            return
        if preset == "orbit_stop":
            if self.orbiting:
                s.stop_ambient_camera_rotation()
                self.orbiting = False
            return
        if self.orbiting:
            s.stop_ambient_camera_rotation()
            self.orbiting = False
        if preset == "top_view":
            phi, theta, zoom = 0.0, -90 * DEGREES, self.solid_zoom
        elif preset == "front_view":
            phi, theta, zoom = 85 * DEGREES, -90 * DEGREES, self.solid_zoom
        elif preset in ("focus_subject", "follow_transform") and targets and targets[0] in self.objs and not self.get(targets[0]).fixed:
            phi, theta, zoom = PHI, THETA, self.solid_zoom * 1.18
        else:  # three_quarter, wide_establishing, split_view
            phi, theta, zoom = PHI, THETA, self.solid_zoom
        s.move_camera(phi=phi, theta=theta, zoom=zoom, frame_center=self._frame_center(phi, theta), run_time=run_time)

    def p_wait(self, targets, run_time=0.5, role=None):
        self.wait(run_time)
