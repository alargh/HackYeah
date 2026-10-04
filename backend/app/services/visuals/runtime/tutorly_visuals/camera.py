"""Camera presets for MovingCameraScene. Moves are deliberate and few (the validator limits them)."""

from __future__ import annotations

from manim import ORIGIN

from . import theme as T

MIN_FOCUS_WIDTH = 12.9  # never zoom in more than ~1.1x: title, subtitles and context stay clear


def wide(frame):
    return frame.animate.move_to(ORIGIN).set(width=T.FRAME_WIDTH)


def focus(frame, mob):
    """A gentle push-in that never moves content under the pinned title or the subtitles: the frame stays
    centred vertically and zooms at most ~1.1x (the subject itself is emphasised by the motion presets)."""
    width = max(mob.width * 2.6, mob.height * 2.6 * 16 / 9, MIN_FOCUS_WIDTH)
    x = max(-0.8, min(0.8, float(mob.get_center()[0]) * 0.3))
    return frame.animate.move_to([x, 0.0, 0.0]).set(width=min(width, T.FRAME_WIDTH))


PRESETS = {
    "wide_establishing": lambda frame, mob: wide(frame),
    "split_view": lambda frame, mob: wide(frame),
    "focus_subject": lambda frame, mob: focus(frame, mob) if mob is not None else wide(frame),
    "follow_transform": lambda frame, mob: focus(frame, mob) if mob is not None else wide(frame),
}
