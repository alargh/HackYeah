"""Tutorly design tokens. The ONLY place where colours, fonts, sizes and strokes are defined.

Generated plans name semantic roles (e.g. emphasis="forbidden"); this module decides what they look like.
"""

from manim import ManimColor

BACKGROUND = ManimColor("#0F1220")

ROLE_COLORS = {
    "neutral": ManimColor("#E6E8EF"),
    "secondary": ManimColor("#7D8597"),
    "active": ManimColor("#4FC3F7"),
    "focus": ManimColor("#FFCA28"),
    "forbidden": ManimColor("#FF5C70"),
    "result": ManimColor("#5EE6A0"),
    "transformation": ManimColor("#B794F6"),
}
# Soft fills behind tokens/regions (same hue, low opacity is applied by the primitives).
ROLE_FILL_OPACITY = 0.18

FONT = "Noto Sans"
FONT_SIZES = {"title": 30, "label": 28, "caption": 22, "item": 38, "small": 22, "counter": 30}
MATH_SCALE = {"formula": 1.25, "small": 0.95, "big": 1.5}

STROKE = {"thin": 2.0, "normal": 3.0, "thick": 5.0}
ITEM_RADIUS = 0.5
SLOT_WIDTH = 1.0
# Regions whose caption ends in a count ("5! = 120") show that many dots, up to this limit.
MAX_REGION_DOTS = 400
DOT_RADIUS = 0.075
CORNER_RADIUS = 0.18

DIM_OPACITY = 0.22
CAPTIONS = True
CAPTION_CHARS = 84  # characters per subtitle line

# Stage geometry (Manim default frame is 14.22 x 8).
FRAME_WIDTH = 14.222
TITLE_Y = 3.45
CAPTION_Y = -3.45
ROW_Y = 1.15
SLOT_Y = -0.15
FORMULA_Y = -2.15
COUNTER_POS = (5.4, 2.55, 0.0)


def color(role: str | None) -> ManimColor:
    return ROLE_COLORS.get(role or "neutral", ROLE_COLORS["neutral"])
