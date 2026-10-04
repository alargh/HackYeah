"""Layout presets: deterministic positions for every visible object, by semantic role.

Zones: title (top), caption (bottom), main stage in between. A layout decides where units (items,
blocks, arrangements), slots, columns (cases), regions, formulas, counters, labels and nodes go.
"""

from __future__ import annotations

import math

import numpy as np

from . import theme as T

UNIT_TYPES = ("item", "block", "arrangement")


def _row_xs(n: int, spacing: float, max_width: float = 11.5) -> list[float]:
    if n <= 0:
        return []
    step = min(spacing, max_width / max(n, 1))
    start = -step * (n - 1) / 2
    return [start + i * step for i in range(n)]


def _fit(objs, gap: float, max_width: float) -> list[float]:
    """Centres for a row of objects; objects are scaled down (once, instantly) if the row is too wide."""
    widths = [o.mob.width for o in objs]
    total = sum(widths) + gap * max(len(objs) - 1, 0)
    if objs and total > max_width:
        factor = (max_width - gap * (len(objs) - 1)) / sum(widths)
        for o in objs:
            o.mob.scale(factor)
        widths = [o.mob.width for o in objs]
    return _row_by_width(widths, gap, max_width)


def _row_by_width(
    widths: list[float], gap: float = 0.4, max_width: float = 11.5
) -> list[float]:
    """Centres for objects of different widths (a block is wider than a person) without overlaps."""
    if not widths:
        return []
    total = sum(widths) + gap * (len(widths) - 1)
    if total > max_width and len(widths) > 1:
        gap = max(0.1, (max_width - sum(widths)) / (len(widths) - 1))
        total = sum(widths) + gap * (len(widths) - 1)
    xs, x = [], -total / 2
    for w in widths:
        xs.append(x + w / 2)
        x += w + gap
    return xs


def _spread(n: int, half_width: float) -> list[float]:
    if n == 1:
        return [0.0]
    return list(np.linspace(-half_width, half_width, n))


def _resolve_overlaps(stage, pos: dict[str, np.ndarray]) -> None:
    """Separate visible layout rectangles after category-specific placement."""
    objects = [
        o for o in stage.order if o.id in pos and o.visible and o.mob is not None and not o.in_slot
    ]  # a unit standing in its slot sits on the slot line on purpose
    priority = {"formula": 1, "label": 2, "counter": 3}
    for _ in range(24):
        changed = False
        for i, first in enumerate(objects):
            for second in objects[i + 1 :]:
                a, b = pos[first.id], pos[second.id]
                dx = (first.mob.width + second.mob.width) / 2 + 0.18 - abs(a[0] - b[0])
                dy = (
                    (first.mob.height + second.mob.height) / 2 + 0.18 - abs(a[1] - b[1])
                )
                if dx <= 0 or dy <= 0:
                    continue
                moved = (
                    first
                    if priority.get(first.type, 0) < priority.get(second.type, 0)
                    else second
                )
                if dx < dy:
                    direction = 1.0 if pos[moved.id][0] >= 0 else -1.0
                    pos[moved.id] += np.array([direction * dx, 0.0, 0.0])
                else:
                    direction = 1.0 if pos[moved.id][1] >= 0 else -1.0
                    pos[moved.id] += np.array([0.0, direction * dy, 0.0])
                changed = True
        if not changed:
            break


STAGE_TOP = 2.95  # nothing above this line: the pinned title lives there
UNDER_MARGIN = 1.05  # counts / captions written under objects (≈0.8) + a result frame around the formula (0.2)


def _clear_formula_band(stage, pos: dict[str, np.ndarray], stack) -> None:
    """Lift the rest of the scene above the formula stack, so counts written under slots/columns, partition
    captions and result frames never touch a formula. A set that is too tall is scaled down to fit."""
    f_top = max(pos[o.id][1] + o.mob.height / 2 for o in stack)
    floor = f_top + UNDER_MARGIN
    main = [o for o in stage.order if o.id in pos and o.visible and o.type not in ("formula", "counter", "label")]
    if not main:
        return
    bottom = min(pos[o.id][1] - o.mob.height / 2 for o in main)
    if bottom >= floor:
        return
    top = max(pos[o.id][1] + o.mob.height / 2 for o in main)
    delta = min(floor - bottom, max(0.0, STAGE_TOP - top))
    for o in main:
        pos[o.id] = pos[o.id] + np.array([0.0, delta, 0.0])
    for o in main:  # still not enough room: shrink tall sets (regions) between the floor and the stage top
        lo, hi = pos[o.id][1] - o.mob.height / 2, pos[o.id][1] + o.mob.height / 2
        if lo < floor and o.type == "region" and hi - floor > 1.0:
            o.mob.scale((hi - floor) / o.mob.height)
            pos[o.id] = np.array([pos[o.id][0], (hi + floor) / 2, 0.0])


FORMULA_BOTTOM = -2.6  # lowest formula edge; two subtitle lines reach up to about -3.05
FORMULA_GAP = 0.45  # room for a result frame (buff 0.2) between stacked formulas


def compute(stage) -> dict[str, np.ndarray]:
    """Positions (centres) for all visible, layout-managed objects of the stage."""
    L = stage.layout
    vis = [o for o in stage.order if o.visible and not o.attached_to]
    pos: dict[str, np.ndarray] = {}

    columns = [o for o in vis if o.column]
    units = [o for o in vis if o.type in UNIT_TYPES and not o.column and not o.in_slot]
    slots = [o for o in vis if o.type == "slot"]
    regions = [o for o in vis if o.type == "region" and not o.column]
    formulas = [o for o in vis if o.type == "formula" and not o.column]
    counters = [o for o in vis if o.type == "counter"]
    free_labels = [o for o in vis if o.type == "label"]
    nodes = [o for o in vis if o.type == "node"]

    has_lower = bool(formulas)
    # --- graphs and trees -------------------------------------------------------------
    if nodes and L == "graph_layout":
        cx = -1.6 if (formulas or counters) else 0.0
        r = 2.25 if len(nodes) > 3 else 1.6
        for i, o in enumerate(nodes):
            a = math.pi / 2 - 2 * math.pi * i / len(nodes)
            pos[o.id] = np.array([cx + r * math.cos(a), 0.15 + r * math.sin(a), 0.0])
    elif nodes:
        levels: dict[int, list] = {}
        for o in nodes:
            levels.setdefault(stage.depth(o.id), []).append(o)
        top = 2.35 if not has_lower else 2.5
        step = min(1.45, (top + 1.6) / max(len(levels), 1))
        prev_x: dict[str, float] = {}
        for d in sorted(levels):
            row = levels[d]
            row.sort(
                key=lambda o: (prev_x.get(o.parent or "", 0.0), stage.order.index(o))
            )
            xs = _spread(len(row), min(6.2, 0.85 * len(row)))
            for o, x in zip(row, xs):
                pos[o.id] = np.array([x, top - d * step, 0.0])
                prev_x[o.id] = x

    # --- rows of units and slots ------------------------------------------------------
    if columns:
        unit_y, col_y = 2.0, -0.25
    elif slots:
        # people still waiting stand clearly above the ones already in their places (and the counts under them)
        seated = [o.mob.height for o in stage.order if o.visible and o.in_slot]
        seat_y = T.SLOT_Y - 0.2 + (0.2 if has_lower else 0.0)
        unit_y = min(2.45, max(T.ROW_Y + 0.55, seat_y + max(seated) + 1.65)) if seated else T.ROW_Y + 0.55
        col_y = 0.0
    elif has_lower or regions:
        unit_y, col_y = T.ROW_Y, 0.0
    else:
        unit_y, col_y = 0.35, 0.0
    if L == "center_focus" and not slots and not columns and not has_lower:
        unit_y = 0.3
    for o, x in zip(units, _fit(units, 0.4, 12.0)):
        pos[o.id] = np.array([x, unit_y, 0.0])
    # slots are as wide as what stands in them (a block of two people needs a wider place)
    occupant = {o.slot_of: o for o in stage.order if o.visible and o.in_slot and o.slot_of}
    widths = [max(1.0, s.mob.width, occupant[s.id].mob.width if s.id in occupant else 0.0) for s in slots]
    slot_y = T.SLOT_Y - 0.2 + (0.2 if has_lower else 0.0)  # formulas below need the space under the counts
    for o, x in zip(slots, _row_by_width(widths, 0.35, 12.4)):
        pos[o.id] = np.array([x, slot_y, 0.0])
        u = occupant.get(o.id)
        if u is not None:
            pos[u.id] = np.array([x, slot_y + u.mob.height / 2 + 0.16, 0.0])

    # --- columns (cases, compared objects) -----------------------------------------------
    if columns:
        y = col_y if units else (0.8 if has_lower else 0.45)  # leave the lower band to formulas
        gap = 1.2 if len(columns) <= 3 else 0.6
        xs = _fit(columns, gap, 12.6)
        if len(columns) == 2 and sum(o.mob.width for o in columns) + 2.4 < 9.2:
            xs = [
                -2.3 - max(0.0, columns[0].mob.width / 2 - 1.2),
                2.3 + max(0.0, columns[1].mob.width / 2 - 1.2),
            ]
        for o, x in zip(columns, xs):
            pos[o.id] = np.array([x, y, 0.0])

    # --- regions (sets) -------------------------------------------------------------------
    # several sets (e.g. "all 120" and "valid 72") sit side by side, scaled to fit
    ry = 0.55 if has_lower else 0.2
    for o, x in zip(regions, _fit(regions, 0.8, 12.8)):
        pos[o.id] = np.array([x, ry, 0.0])

    # --- formulas: a stack whose newest line sits lowest -----------------------------------
    gallery = any(o.visible and o.attached_to == "__gallery__" for o in stage.order)
    pure_formula_scene = not (units or slots or columns or regions or nodes or gallery)
    if formulas:
        if pure_formula_scene:
            ys = (
                _spread(len(formulas), 0.65 * (len(formulas) - 1))
                if len(formulas) > 1
                else [0.3]
            )
            for o, y in zip(formulas, reversed(ys)):
                pos[o.id] = np.array([0.0, y + 0.3, 0.0])
        else:
            base_x = 2.6 if (nodes and L == "graph_layout") else 0.0
            # bottom-anchored above the subtitles, stacked by real heights (tall fractions never collide)
            y = FORMULA_BOTTOM
            for o in reversed(formulas[-2:]):
                pos[o.id] = np.array([base_x, y + o.mob.height / 2, 0.0])
                y += o.mob.height + FORMULA_GAP
            for o in formulas[:-2]:
                o.stale = True  # older formulas are faded by the stage
            _clear_formula_band(stage, pos, formulas[-2:])

    # --- counters (top right) and free labels (top left) ------------------------------------
    for i, o in enumerate(counters):
        pos[o.id] = np.array(T.COUNTER_POS) + np.array([0.0, -1.0 * i, 0.0])
    y = 2.6
    for o in free_labels:
        w = o.mob.width
        pos[o.id] = np.array([-6.6 + w / 2, y, 0.0])
        y -= o.mob.height + 0.25
    _resolve_overlaps(stage, pos)
    return pos
