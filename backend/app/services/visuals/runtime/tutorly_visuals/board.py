"""Board: fixed screen layout for hand-written (fallback) scenes.

Generated code that does not go through the compiler still gets the Tutorly screen grammar:

  * title at the top, subtitles at the bottom (one at a time, quick sequential swap);
  * a right-hand formula column: lines stack top-down in the order they are derived, a line is only
    removed when the column is full (oldest first) or explicitly replaced in place;
  * a content area on the left where drawings are fitted (`board.place(mob)`).

Works in `Scene`, `MovingCameraScene` (positions are screen positions) and `ThreeDScene` (HUD objects are
fixed in frame).
"""

from __future__ import annotations

import numpy as np
from manim import UP, FadeIn, FadeOut, Mobject, TransformMatchingTex, VGroup, Write

from . import hud, primitives
from . import theme as T

COLUMN_X = 4.7
COLUMN_W = 3.9
COLUMN_TOP = 2.75
COLUMN_BOTTOM = -2.85
GAP = 0.32
CONTENT_CENTER = np.array([-1.9, 0.0, 0.0])
CONTENT_W, CONTENT_H = 9.0, 5.6


_TEX_WORDS = {
    r"\pi": "π", r"\cdot": "·", r"\times": "×", r"\sqrt": "√", r"\alpha": "α", r"\beta": "β",
    r"\approx": "≈", r"\neq": "≠", r"\leq": "≤", r"\geq": "≥", r"\degree": "°", r"^\circ": "°",
    "^2": "²", "^3": "³",
}


def plain(text: str) -> str:
    """Prose lines are Text, not LaTeX: turn stray TeX commands into their symbols."""
    for tex, sym in _TEX_WORDS.items():
        text = text.replace(tex, sym)
    return text.replace("$", "").replace("{", "").replace("}", "")


class Board:
    def __init__(self, scene, title: str | None = None):
        self.scene = scene
        scene.camera.background_color = T.BACKGROUND
        self.fixed = hasattr(scene, "add_fixed_in_frame_mobjects")
        self.caption_mob = None
        self.lines: list[Mobject] = []
        self.title = None
        if title:
            self.title = primitives.text(title, "title", "secondary")
            if self.title.width > 12.5:
                self.title.scale_to_fit_width(12.5)
            self.title.move_to(UP * T.TITLE_Y)
            self._hud(self.title)
            scene.play(FadeIn(self.title, shift=UP * 0.2), run_time=0.6)

    # ------------------------------------------------------------------ helpers
    def _hud(self, mob: Mobject) -> None:
        if self.fixed:
            self.scene.add_fixed_in_frame_mobjects(mob)

    def _layout(self, instant: Mobject | None = None) -> list:
        anims = []
        while len(self.lines) > 1:
            total = sum(m.height for m in self.lines) + GAP * (len(self.lines) - 1)
            if COLUMN_TOP - total >= COLUMN_BOTTOM:
                break
            anims.append(FadeOut(self.lines.pop(0)))
        y = COLUMN_TOP
        for m in self.lines:
            target = np.array([COLUMN_X, y - m.height / 2, 0.0])
            y -= m.height + GAP
            if m is instant:
                m.move_to(target)
            elif np.linalg.norm(m.get_center() - target) > 0.02:
                anims.append(m.animate.move_to(target))
        return anims

    def _add_line(self, mob: Mobject, run_time: float) -> Mobject:
        if mob.width > COLUMN_W:
            mob.scale_to_fit_width(COLUMN_W)
        self.lines.append(mob)
        moves = self._layout(instant=mob)
        if moves:
            self.scene.play(*moves, run_time=0.4)
        self._hud(mob)
        self.scene.play(Write(mob), run_time=run_time)
        return mob

    # ------------------------------------------------------------------ API
    def caption(self, text: str, duration: float = 3.0) -> None:
        """Subtitle for the narration segment that starts now (replaces the previous one)."""
        new = hud.subtitles(self.scene.renderer, text, duration)
        new.move_to(UP * T.CAPTION_Y)
        self._hud(new)
        hud.swap_caption(self.scene, self.caption_mob, new)
        self.caption_mob = new

    def formula(self, tex: str, role: str = "neutral", run_time: float = 0.9) -> Mobject:
        """Append a formula line (LaTeX) to the right column and write it."""
        return self._add_line(primitives.math(tex, role), run_time)

    def note(self, text: str, role: str = "secondary", run_time: float = 0.6) -> Mobject:
        """Append a short prose line (e.g. 'podstawiamy a = 4') to the right column."""
        return self._add_line(primitives.text(plain(text), "label", role), run_time)

    def replace(self, old: Mobject, tex: str, role: str = "neutral", run_time: float = 0.9) -> Mobject:
        """Next form of the same formula, transformed in place (e.g. simplification)."""
        new = primitives.math(tex, role)
        if new.width > COLUMN_W:
            new.scale_to_fit_width(COLUMN_W)
        new.move_to(old.get_center())
        if new.get_top()[1] > COLUMN_TOP:
            new.align_to(old, UP)
        self._hud(new)
        if old in self.lines:
            self.lines[self.lines.index(old)] = new
        self.scene.play(TransformMatchingTex(old, new), run_time=run_time)
        moves = self._layout()
        if moves:
            self.scene.play(*moves, run_time=0.4)
        return new

    def clear_column(self, run_time: float = 0.4) -> None:
        if self.lines:
            self.scene.play(*(FadeOut(m) for m in self.lines), run_time=run_time)
        self.lines = []

    def place(self, mob: Mobject) -> Mobject:
        """Fit a drawing into the content area left of the formula column (does not animate)."""
        if mob.width > CONTENT_W:
            mob.scale_to_fit_width(CONTENT_W)
        if mob.height > CONTENT_H:
            mob.scale_to_fit_height(CONTENT_H)
        mob.move_to(CONTENT_CENTER)
        return mob

    def group(self, *mobs: Mobject) -> VGroup:
        return VGroup(*mobs)
