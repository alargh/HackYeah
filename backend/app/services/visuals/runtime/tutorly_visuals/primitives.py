"""Visual primitives: one constructor per semantic object type. Styling comes only from theme.py."""

from __future__ import annotations

from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    Circle,
    DashedVMobject,
    Line,
    MathTex,
    RoundedRectangle,
    Text,
    VGroup,
)

from . import theme as T


_TEX_SYMBOLS = {r"\cdot": "·", r"\times": "×", r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\to": "→", r"\pi": "π",
                r"\ldots": "…", r"\dots": "…", r"\,": " ", r"\;": " ", r"\ ": " "}


def plain(value: str) -> str:
    """Text objects never show TeX source: '\\text{[AB]}' -> '[AB]', 'N_{\\text{all}}' -> 'N_all', '$x$' -> 'x'."""
    import re

    if "\\" not in value and "$" not in value and "{" not in value:
        return value
    s = value.replace("$", "")
    for k, v in _TEX_SYMBOLS.items():
        s = s.replace(k, v)
    for _ in range(3):  # nested \text{\textbf{..}}
        s = re.sub(r"\\(?:text|mathrm|mathbf|textbf|mathit|operatorname|boldsymbol)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)  # any other command
    return s.replace("{", "").replace("}", "").strip() or value


def text(value: str, size: str = "label", role: str | None = "neutral", weight: str = "NORMAL") -> Text:
    return Text(plain(value), font=T.FONT, font_size=T.FONT_SIZES[size], color=T.color(role), weight=weight)


def math(tex: str, role: str | None = "neutral", scale: str = "formula") -> MathTex:
    m = MathTex(tex)
    m.set_color(T.color(role))
    return m.scale(T.MATH_SCALE[scale])


def item(label: str, role: str = "neutral", radius: float = T.ITEM_RADIUS) -> VGroup:
    disc = Circle(radius=radius, stroke_width=T.STROKE["normal"])
    disc.set_stroke(T.color(role)).set_fill(T.color(role), opacity=T.ROLE_FILL_OPACITY)
    tag = text(label, "item", role, weight="BOLD")
    if tag.width > radius * 1.6:
        tag.scale_to_fit_width(radius * 1.6)
    tag.move_to(disc)
    g = VGroup(disc, tag)
    g.ml_kind = "item"
    return g


def slot(label: str = "", role: str = "secondary") -> VGroup:
    line = Line(LEFT * T.SLOT_WIDTH / 2, RIGHT * T.SLOT_WIDTH / 2, stroke_width=T.STROKE["thick"], color=T.color(role))
    g = VGroup(line)  # the position itself is the visual; choice counts are written under it when filled
    g.ml_kind = "slot"
    return g


def label(value: str, role: str = "neutral") -> Text:
    t = text(value, "label", role)
    if t.width > 7.5:
        t.scale_to_fit_width(7.5)
    t.ml_kind = "label"
    return t


def formula(tex: str, role: str = "neutral") -> MathTex:
    m = math(tex, role)
    if m.width > 11:
        m.scale_to_fit_width(11)
    m.ml_kind = "formula"
    return m


def counter(value: str, caption: str = "", role: str = "active") -> VGroup:
    num = math(value, role, "big")
    g = VGroup(num)
    if caption:
        g.add(text(caption, "small", "secondary").next_to(num, DOWN, buff=0.1))
    g.ml_kind = "counter"
    return g


def arrangement(value: str, role: str = "neutral") -> VGroup:
    """A concrete ordering, e.g. 'A B' -> two small tokens side by side, with a soft frame."""
    labels = [v for v in value.replace(",", " ").split() if v] or [value]
    tokens = VGroup(*[item(v, role, radius=T.ITEM_RADIUS * 0.8) for v in labels]).arrange(RIGHT, buff=0.12)
    frame = RoundedRectangle(
        corner_radius=T.CORNER_RADIUS, width=tokens.width + 0.4, height=tokens.height + 0.35,
        stroke_width=T.STROKE["thin"], stroke_color=T.color(role),
    ).move_to(tokens)
    g = VGroup(frame, tokens)
    g.ml_kind = "arrangement"
    return g


def block_frame(target, tag: str, role: str = "transformation") -> VGroup:
    frame = RoundedRectangle(
        corner_radius=T.CORNER_RADIUS, width=target.width + 0.35, height=target.height + 0.35,
        stroke_width=T.STROKE["thick"], stroke_color=T.color(role),
    ).set_fill(T.color(role), opacity=0.08).move_to(target)
    g = VGroup(frame)
    if tag:
        g.add(text(tag, "small", role, weight="BOLD").next_to(frame, UP, buff=0.12))
    return g


def trailing_count(value: str) -> int | None:
    """'5! = 120' -> 120 (the number of elements a region stands for)."""
    import re

    m = re.search(r"(\d+)\s*$", value.strip())
    return int(m.group(1)) if m else None


def dot_grid(n: int, role: str, rows: int | None = None) -> VGroup:
    """n dots filled column by column, so the last k dots always form a block on the right."""
    if rows is None:
        target = (n / 2.6) ** 0.5  # ~2.6:1 aspect
        exact = [r for r in range(3, 9) if n % r == 0]
        rows = min(exact, key=lambda r: abs(r - target)) if exact else max(1, min(8, round(target)))
    cols = -(-n // rows)
    dots = VGroup()
    for i in range(n):
        c, r = divmod(i, rows)
        d = Circle(radius=T.DOT_RADIUS, stroke_width=0).set_fill(T.color(role), opacity=0.9)
        d.move_to(RIGHT * c * 0.36 + DOWN * r * 0.36)
        dots.add(d)
    return dots.move_to(ORIGIN) if cols else dots


def region(caption: str, role: str = "neutral", width: float = 8.0, height: float = 3.6, dashed: bool = False) -> VGroup:
    """A set drawn as an area. index 0 = border, 1 = fill, 2 = caption, 3 = element dots (optional)."""
    n = trailing_count(caption) if not dashed else None
    dots = dot_grid(n, "secondary") if n and 2 <= n <= T.MAX_REGION_DOTS else None
    if dots is not None:
        width = max(width, dots.width + 0.9)
        height = max(height, dots.height + 1.5)
    rect = RoundedRectangle(corner_radius=0.3, width=width, height=height, stroke_width=T.STROKE["normal"], stroke_color=T.color(role))
    fill = rect.copy().set_stroke(opacity=0).set_fill(T.color(role), opacity=0.07)
    border = DashedVMobject(rect, num_dashes=48) if dashed else rect.set_fill(opacity=0)
    cap = caption_mobject(caption, role) if caption else VGroup()
    if caption:
        cap.move_to(rect.get_corner(UP + LEFT) + RIGHT * (cap.width / 2 + 0.3) + DOWN * (cap.height / 2 + 0.22))
    g = VGroup(border, fill, cap)
    if dots is not None:
        dots.move_to(rect.get_center() + DOWN * 0.3)
        g.add(dots)
        g.ml_dots = dots
    g.ml_kind = "region"
    return g


def caption_mobject(value: str, role: str):
    """Region captions may be LaTeX-ish ('5! = 120') or text; pick the right renderer."""
    if any(c in value for c in "!=^\\") and value.isascii():
        return math(value, role, "small")
    return text(value, "label", role)


def node(label_value: str, role: str = "neutral") -> VGroup:
    g = item(label_value, role, radius=0.34)
    g.ml_kind = "node"
    return g


def edge(start, end, role: str = "secondary") -> Line:
    ln = Line(start, end, stroke_width=T.STROKE["normal"], color=T.color(role))
    ln.ml_kind = "edge"
    return ln


def build(obj_type: str, value: str, role: str):
    builders = {
        "item": lambda: item(value, role),
        "slot": lambda: slot(value),
        "label": lambda: label(value, role),
        "formula": lambda: formula(value, role),
        "counter": lambda: counter(value, "", role),
        "arrangement": lambda: arrangement(value, role),
        "region": lambda: region(value, role),
        "node": lambda: node(value, role),
        "block": lambda: VGroup(),  # filled by the enclose primitive from its members
    }
    return builders[obj_type]()


def recolor(mob, role: str) -> None:
    """Restyle any Tutorly object to a semantic role (stroke + soft fill for shapes, colour for text)."""
    c = T.color(role)
    kind = getattr(mob, "ml_kind", None)
    if kind in ("item", "node"):
        mob[0].set_stroke(c).set_fill(c, opacity=T.ROLE_FILL_OPACITY)
        mob[1].set_color(c)
    elif kind == "arrangement":
        mob[0].set_stroke(c)
        for tok in mob[1]:
            recolor(tok, role)
    elif kind == "slot":
        mob[0].set_color(c)
    elif kind == "region":
        mob[0].set_stroke(c)
        mob[1].set_fill(c, opacity=0.07)
        mob[2].set_color(c)
        if len(mob) > 3:
            for d in mob[3]:
                if not getattr(d, "ml_removed", False):
                    d.set_fill(c, opacity=0.9)
    else:
        mob.set_color(c)
