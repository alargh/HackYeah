"""Stage: the runtime state of one Tutorly scene (objects, layout, camera, captions).

Compiled scenes only call `declare`, `beat`, `do`, `wait` and `finish`; all choreography is in motion.py.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

import numpy as np
from manim import UP, AnimationGroup, FadeIn, FadeOut, Mobject, VGroup

from . import camera as cam
from . import hud, layouts, motion, primitives
from . import theme as T


@dataclass(eq=False)
class Obj:
    id: str
    type: str
    value: str = ""
    role: str = "neutral"
    members: list[str] = field(default_factory=list)
    parent: str | None = None
    mob: Mobject | None = None
    visible: bool = False
    column: bool = False
    in_slot: bool = False
    slot_of: str | None = None  # the slot this unit stands in (layout keeps them together)
    attached_to: str | None = None
    stale: bool = False


class Stage:
    def __init__(self, scene, title: str = "", layout: str = "horizontal_row", camera: str = "wide_establishing"):
        self.scene = scene
        scene.camera.background_color = T.BACKGROUND
        self.frame = scene.camera.frame
        self.layout = layout
        self.camera_preset = camera
        self.objs: dict[str, Obj] = {}
        self.order: list[Obj] = []
        self.decor: list[Mobject] = []
        self.dimmed: list[Mobject] = []
        self.caption = None
        self.last_result: str | None = None
        self.title = None
        if title:
            self.title = primitives.text(title, "title", "secondary")
            self._pin(self.title, np.array([0.0, T.TITLE_Y, 0.0]), max_width=12.0)
            scene.play(FadeIn(self.title, shift=UP * 0.2), run_time=0.6)

    # ------------------------------------------------------------------ registry
    def declare(self, oid: str, otype: str, value: str = "", role: str = "neutral", members=(), parent=None, params=()) -> Obj:
        o = Obj(id=oid, type=otype, value=value, role=role, members=list(members), parent=parent)
        if otype == "edge":
            o.mob = motion.make_edge(self, o)
        elif otype == "label" and o.members:
            o.mob = primitives.label(value, role)
            o.attached_to = o.members[0]
        else:
            o.mob = primitives.build(otype, value, role)
        self.objs[oid] = o
        self.order.append(o)
        return o

    def get(self, oid: str) -> Obj:
        if oid not in self.objs:
            raise KeyError(f"unknown visual object '{oid}'")
        return self.objs[oid]

    def mobs(self, ids) -> list[Mobject]:
        return [self.get(i).mob for i in ids]

    def depth(self, oid: str) -> int:
        d, o = 0, self.objs.get(oid)
        while o is not None and o.parent and d < 12:
            d, o = d + 1, self.objs.get(o.parent)
        return d

    # ------------------------------------------------------------------ layout
    def relayout_animations(self, exclude=()) -> list:
        anims = []
        positions = layouts.compute(self)
        for oid, p in positions.items():
            o = self.objs[oid]
            if oid in exclude:
                o.mob.move_to(p)
                continue
            if np.linalg.norm(o.mob.get_center() - p) > 0.02:
                anims.append(o.mob.animate.move_to(p))
        for o in self.order:
            if o.stale and o.visible:
                o.visible, o.stale = False, False
                anims.append(FadeOut(o.mob))
        return anims

    # ------------------------------------------------------------------ HUD (title, captions)
    def _pin(self, mob, offset: np.ndarray, max_width: float) -> None:
        if mob.width > max_width:
            mob.scale_to_fit_width(max_width)
        base_w, frame = mob.width, self.frame

        def follow(m):
            s = frame.width / T.FRAME_WIDTH
            m.scale_to_fit_width(base_w * s)
            m.move_to(frame.get_center() + offset * s)

        follow(mob)
        mob.add_updater(follow)

    def _subtitles(self, caption: str, duration: float):
        """Narration as timed subtitles: 2-line chunks shown one after another across the beat."""
        lines = textwrap.wrap(caption, T.CAPTION_CHARS)
        chunks = ["\n".join(lines[i : i + 2]) for i in range(0, len(lines), 2)] or [caption]
        mobs = [primitives.text(c, "caption", "secondary") for c in chunks]
        for m in mobs:
            self._pin(m, np.array([0.0, T.CAPTION_Y, 0.0]), max_width=12.8)
        total = sum(len(c) for c in chunks) or 1
        bounds, acc = [], 0.0
        for c in chunks:
            acc += len(c) / total * max(duration, 1.0)
            bounds.append(acc)
        group = VGroup(*mobs)
        renderer = self.scene.renderer
        start = renderer.time

        def switch(g):
            t = renderer.time - start
            idx = min(next((i for i, b in enumerate(bounds) if t < b), len(bounds) - 1), len(g) - 1)
            for i, m in enumerate(g):
                m.set_opacity(1.0 if i == idx else 0.0)

        switch(group)
        group.add_updater(switch)
        return group

    def beat(self, beat_id: str, caption: str = "", layout: str | None = None, duration: float = 4.0) -> None:
        if layout:
            self.layout = layout
        extra = self.relayout_animations() if layout else []
        if T.CAPTIONS and caption:
            new = self._subtitles(caption, duration)
            hud.swap_caption(self.scene, self.caption, new, extra)
            self.caption = new
        elif extra:
            self.scene.play(*extra, run_time=0.5)

    # ------------------------------------------------------------------ execution
    def do(self, primitive: str, targets=(), run_time: float = 0.8, **params) -> None:
        fn = getattr(motion, f"p_{primitive}", None)
        if fn is None:
            raise ValueError(f"unknown primitive '{primitive}'")
        fn(self, list(targets), run_time=run_time, **params)

    def play(self, *anims, run_time: float = 0.8, lag_ratio: float = 0.0) -> None:
        anims = [a for a in anims if a is not None]
        if anims:
            self.scene.play(AnimationGroup(*anims, lag_ratio=lag_ratio), run_time=max(run_time, 0.2))

    def camera(self, preset: str, target: str | None = None, run_time: float = 1.0) -> None:
        mob = self.get(target).mob if target and target in self.objs else None
        self.scene.play(cam.PRESETS[preset](self.frame, mob), run_time=run_time)

    def wait(self, seconds: float) -> None:
        if seconds > 0.05:
            self.scene.wait(seconds)

    def finish(self) -> None:
        self.scene.wait(0.4)
