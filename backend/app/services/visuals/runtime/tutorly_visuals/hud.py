"""Screen furniture shared by 2D and 3D stages: timed subtitles."""

from __future__ import annotations

import textwrap

from manim import VGroup

from . import primitives
from . import theme as T


CAPTION_OUT_S = 0.15  # old subtitle disappears quickly ...
CAPTION_IN_S = 0.25  # ... before the next one fades in: two captions are never on screen together


def swap_caption(scene, old, new, extra=()) -> None:
    """Sequential caption swap: fade the old one out first, then fade the new one in (with any layout moves)."""
    from manim import FadeIn, FadeOut

    if old is not None:
        old.clear_updaters()
        scene.play(FadeOut(old), run_time=CAPTION_OUT_S)
    anims = list(extra)
    if new is not None:
        anims.append(FadeIn(new))
    if anims:
        scene.play(*anims, run_time=CAPTION_IN_S if not extra else 0.45)


def subtitles(renderer, caption: str, duration: float) -> VGroup:
    """Narration as timed subtitles: 2-line chunks shown one after another across the beat.

    Returned centred at the origin; the caller positions it (pinned to the 2D camera frame, or fixed in
    frame for 3D scenes)."""
    lines = textwrap.wrap(caption, T.CAPTION_CHARS)
    chunks = ["\n".join(lines[i : i + 2]) for i in range(0, len(lines), 2)] or [caption]
    mobs = [primitives.text(c, "caption", "secondary") for c in chunks]
    width = max(m.width for m in mobs)
    for m in mobs:
        if m.width > 12.8:
            m.scale_to_fit_width(12.8)
    total = sum(len(c) for c in chunks) or 1
    bounds, acc = [], 0.0
    for c in chunks:
        acc += len(c) / total * max(duration, 1.0)
        bounds.append(acc)
    group = VGroup(*mobs)
    start = renderer.time

    def switch(g):
        t = renderer.time - start
        idx = min(next((i for i, b in enumerate(bounds) if t < b), len(bounds) - 1), len(g) - 1)
        for i, m in enumerate(g):
            m.set_opacity(1.0 if i == idx else 0.0)

    switch(group)
    group.add_updater(switch)
    group.ml_width = min(width, 12.8)
    return group
