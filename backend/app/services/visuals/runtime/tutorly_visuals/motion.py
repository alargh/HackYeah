"""Motion presets: deterministic implementations of the animation primitives.

Each `p_<name>(stage, targets, run_time, **params)` is one step of an AnimationPlan. The compiler expands
semantic operations (merge, split, ...) into sequences of these steps.
"""

from __future__ import annotations

import numpy as np
from manim import (
    DOWN,
    LEFT,
    PI,
    RIGHT,
    UP,
    AnimationGroup,
    ArcBetweenPoints,
    Arrow,
    Circumscribe,
    Create,
    CurvedArrow,
    Cross,
    DashedLine,
    DashedVMobject,
    FadeIn,
    FadeOut,
    Flash,
    GrowFromCenter,
    Indicate,
    Line,
    MathTex,
    MoveToTarget,
    Rectangle,
    ReplacementTransform,
    SurroundingRectangle,
    TransformFromCopy,
    TransformMatchingTex,
    VGroup,
    Write,
    always_redraw,
)

from . import primitives
from . import theme as T

# ---------------------------------------------------------------------------- helpers


def G(*anims, lag_ratio: float = 0.0):
    """AnimationGroup that tolerates empty input (Manim rejects empty groups)."""
    anims = [a for a in anims if a is not None]
    return AnimationGroup(*anims, lag_ratio=lag_ratio) if anims else None


def _decor(stage, mob, owners) -> None:
    mob.ml_owners = set(owners)
    stage.decor.append(mob)


def _owned_decor(stage, ids) -> list:
    ids = set(ids)
    out = [d for d in stage.decor if d.ml_owners & ids]
    stage.decor = [d for d in stage.decor if d not in out]
    return out


def _creation(o):
    m = o.mob
    if o.type in ("item", "node"):
        return GrowFromCenter(m)
    if o.type in ("slot", "edge"):
        return Create(m)
    if o.type == "formula":
        return Write(m)
    if o.type == "region":
        return G(Create(m[0]), FadeIn(VGroup(*m[1:])))
    if o.type == "counter":
        return FadeIn(m, scale=0.8)
    return FadeIn(m, shift=UP * 0.15)


def _place_attached(stage, o) -> None:
    if o.type == "label" and o.attached_to:
        anchor = stage.get(o.attached_to).mob
        o.mob.next_to(anchor, UP, buff=0.25)
        o.mob.add_updater(lambda m, a=anchor: m.next_to(a, UP, buff=0.25))


def _members_of(stage, oid) -> list:
    return [o for o in stage.order if o.attached_to == oid and o.type != "label"]


def make_edge(stage, o):
    a, b = o.members[0], o.members[1]

    def draw():
        A, B = stage.get(a).mob, stage.get(b).mob
        return Line(
            A.get_center(),
            B.get_center(),
            buff=0.38,
            stroke_width=T.STROKE["normal"],
            color=T.color(o.role),
        )

    m = always_redraw(draw)
    m.ml_kind = "edge"
    return m


def _recolor_anim(o, role):
    o.role = role
    if o.type == "edge":
        return None  # edges redraw from o.role every frame
    if o.type == "block":
        frame = o.mob[-1]
        return G(
            frame[0].animate.set_stroke(T.color(role)),
            *(f.animate.set_color(T.color(role)) for f in frame[1:]),
        )
    o.mob.generate_target()
    primitives.recolor(o.mob.target, role)
    return MoveToTarget(o.mob)


# ---------------------------------------------------------------------------- creation / removal


def p_appear(stage, targets, run_time=0.8, lag=0.15, role=None):
    new = [stage.get(t) for t in targets if not stage.get(t).visible]
    for o in new:
        o.visible = True
        _place_attached(stage, o)
    moves = stage.relayout_animations(exclude={o.id for o in new})
    creations = [_creation(o) for o in new]
    if moves:  # make room first, then draw: a new formula never writes over one that is still moving away
        stage.play(*moves, run_time=min(0.5, run_time * 0.35))
        run_time = max(0.3, run_time * 0.65)
    stage.play(G(*creations, lag_ratio=lag), run_time=run_time)


def p_grow(stage, targets, run_time=1.2, role=None):
    p_appear(stage, targets, run_time=run_time, lag=0.55)


def p_disappear(stage, targets, run_time=0.6, role=None):
    mobs = []
    for t in targets:
        o = stage.get(t)
        if not o.visible:
            continue
        o.visible = False
        for member in _members_of(stage, t):
            member.visible = False
        mobs.append(o.mob)
    mobs += _owned_decor(stage, targets)
    if not mobs:
        return
    anims = []
    for m in mobs:
        if getattr(m, "ml_kind", None) == "partition":
            # its dots also belong to the parent set: hide them for good instead of FadeOut
            frame, cap, sel = m
            for d in sel:
                d.ml_removed = True
            frame.clear_updaters()
            cap.clear_updaters()
            anims += [sel.animate.set_fill(opacity=0), FadeOut(frame), FadeOut(cap)]
        else:
            anims.append(FadeOut(m))
    stage.play(*anims, run_time=run_time / 2)
    stage.play(*stage.relayout_animations(), run_time=run_time / 2)


def p_cross_out(stage, targets, run_time=0.6, role="forbidden"):
    crosses = []
    for t in targets:
        cross = Cross(
            stage.get(t).mob,
            stroke_color=T.color("forbidden"),
            stroke_width=T.STROKE["thick"],
            scale_factor=0.85,
        )
        _decor(stage, cross, [t])
        crosses.append(Create(cross))
    stage.play(*crosses, run_time=run_time)


# ---------------------------------------------------------------------------- emphasis


def p_recolor(stage, targets, run_time=0.4, role="active"):
    stage.play(*(_recolor_anim(stage.get(t), role) for t in targets), run_time=run_time)


def p_indicate(stage, targets, run_time=0.6, role="focus"):
    stage.play(
        *(
            Indicate(stage.get(t).mob, color=T.color(role), scale_factor=1.15)
            for t in targets
        ),
        run_time=run_time,
        lag_ratio=0.25,
    )


def p_emphasize(stage, targets, run_time=1.2, role="result"):
    anims, boxes = [], []
    for t in targets:
        o = stage.get(t)
        anims.append(_recolor_anim(o, role))
        box = SurroundingRectangle(
            o.mob,
            color=T.color(role),
            buff=0.2,
            corner_radius=T.CORNER_RADIUS,
            stroke_width=T.STROKE["thick"],
        )
        box.add_updater(lambda b, m=o.mob: b.move_to(m))  # the frame travels with its formula on relayout
        _decor(stage, box, [t])
        boxes.append(box)
    stage.play(*anims, run_time=run_time * 0.3)
    stage.play(
        *(Create(b) for b in boxes),
        *(
            Flash(stage.get(t).mob, color=T.color(role), line_length=0.3, num_lines=14)
            for t in targets
        ),
        run_time=run_time * 0.5,
    )
    stage.play(
        *(
            Indicate(stage.get(t).mob, color=T.color(role), scale_factor=1.08)
            for t in targets
        ),
        run_time=run_time * 0.2,
    )
    stage.last_result = targets[-1] if targets else stage.last_result


def p_dim_others(stage, targets, run_time=0.6, role=None):
    overlay = Rectangle(width=T.FRAME_WIDTH * 3, height=24, stroke_width=0).set_fill(
        T.BACKGROUND, opacity=1 - T.DIM_OPACITY
    )
    overlay.move_to(stage.frame.get_center())
    stage.dimmed.append(overlay)
    keep = [stage.get(t).mob for t in targets] + [
        m for m in (stage.title, stage.caption) if m is not None
    ]
    stage.scene.add(overlay)
    stage.scene.bring_to_front(*keep)
    overlay.set_opacity(0)
    stage.play(
        overlay.animate.set_fill(T.BACKGROUND, opacity=1 - T.DIM_OPACITY),
        run_time=run_time,
    )


def p_undim(stage, targets, run_time=0.5, role=None):
    if stage.dimmed:
        stage.play(*(FadeOut(o) for o in stage.dimmed), run_time=run_time)
        stage.dimmed = []


# ---------------------------------------------------------------------------- grouping / cases


def p_move_adjacent(stage, targets, run_time=0.8, role=None):
    objs = [stage.get(t) for t in targets]
    first = min(stage.order.index(o) for o in objs)
    rest = [o for o in stage.order if o not in objs]
    insert_at = len([o for o in stage.order[:first] if o not in objs])
    stage.order = rest[:insert_at] + objs + rest[insert_at:]
    stage.play(*stage.relayout_animations(), run_time=run_time)


def p_enclose(
    stage, targets, run_time=1.0, result="block", value="", role="transformation"
):
    members = [stage.get(t) for t in targets]
    group = VGroup(*(m.mob for m in members))
    frame = primitives.block_frame(group, value, role)
    block = stage.declare(result, "block", value, role)
    block.mob = VGroup(*(m.mob for m in members), frame)
    block.mob.ml_kind = "block"
    block.visible = True
    idx = min(stage.order.index(m) for m in members)
    stage.order.remove(block)
    stage.order.insert(idx, block)
    for m in members:
        m.attached_to = result
    links = [d for d in stage.decor if d.ml_owners >= set(targets)]
    stage.decor = [d for d in stage.decor if d not in links]
    stage.play(
        Create(frame[0]),
        *(FadeIn(f, shift=DOWN * 0.1) for f in frame[1:]),
        *(FadeOut(d) for d in links),
        run_time=run_time * 0.6,
    )
    stage.play(*stage.relayout_animations(), run_time=run_time * 0.4)
    stage.last_result = result


def _new_columns(stage, src, results, values, role, otype="arrangement"):
    news = []
    for rid, val in zip(results, values):
        o = stage.objs.get(rid) or stage.declare(rid, otype, val, role)
        o.column, o.visible = True, True
        news.append(o)
    return news


def p_spawn_copies(stage, targets, run_time=1.4, results=(), values=(), role="active"):
    src = stage.get(targets[0])
    news = _new_columns(stage, src, results, values, role)
    moves = stage.relayout_animations(exclude={o.id for o in news})
    copies = [TransformFromCopy(src.mob, o.mob) for o in news]
    stage.play(G(*moves), run_time=run_time * 0.3)
    stage.play(*copies, run_time=run_time * 0.7, lag_ratio=0.45)
    stage.last_result = news[-1].id if news else None


def p_branch(stage, targets, run_time=1.4, results=(), values=(), role="active"):
    src = stage.get(targets[0])
    if src.type == "node":
        news = []
        for rid, val in zip(results, values):
            o = stage.objs.get(rid) or stage.declare(
                rid, "node", val, role, parent=src.id
            )
            o.parent = src.id
            news.append(o)
            stage.declare(
                f"{src.id}__{rid}", "edge", "", "secondary", members=[src.id, rid]
            )
        p_appear(
            stage,
            [o.id for o in news] + [f"{src.id}__{o.id}" for o in news],
            run_time=run_time,
            lag=0.25,
        )
        return
    news = _new_columns(stage, src, results, values, role)
    stage.play(
        G(*stage.relayout_animations(exclude={o.id for o in news})),
        run_time=run_time * 0.3,
    )
    lines = []
    for o in news:
        ln = always_redraw(
            lambda s=src, n=o: Line(
                s.mob.get_bottom(),
                n.mob.get_top(),
                buff=0.15,
                stroke_width=T.STROKE["thin"],
                color=T.color("secondary"),
            )
        )
        _decor(stage, ln, [src.id, o.id])
        lines.append(ln)
    stage.play(
        *(Create(ln) for ln in lines),
        *(TransformFromCopy(src.mob, o.mob) for o in news),
        run_time=run_time * 0.7,
        lag_ratio=0.3,
    )


def p_compare(stage, targets, run_time=1.0, role=None):
    objs = [stage.get(t) for t in targets]
    new = [o for o in objs if not o.visible]
    for o in objs:
        o.column, o.visible = True, True
    stage.layout = "split_view"
    moves = stage.relayout_animations(exclude={o.id for o in new})
    stage.play(*moves, *(_creation(o) for o in new), run_time=run_time * 0.5)
    if len(objs) >= 2:
        mid = (objs[0].mob.get_right() + objs[1].mob.get_left()) / 2
        top, bottom = mid + UP * 1.3, mid + DOWN * 1.3
        divider = DashedLine(
            top, bottom, color=T.color("secondary"), stroke_width=T.STROKE["thin"]
        )
        _decor(stage, divider, targets)
        stage.play(
            Create(divider),
            *(Indicate(o.mob, color=T.color("focus"), scale_factor=1.08) for o in objs),
            run_time=run_time * 0.5,
        )


# ---------------------------------------------------------------------------- rewriting


def _replace_in_order(stage, old, new) -> None:
    if new in stage.order:
        stage.order.remove(new)
    stage.order.insert(stage.order.index(old), new)


def p_transform_tex(
    stage, targets, run_time=1.0, result="", value="", role="transformation"
):
    sources = [stage.get(t) for t in targets]
    src = sources[0]
    new = stage.objs.get(result) or stage.declare(result, "formula", value, role)
    new.mob.move_to(VGroup(*(s.mob for s in sources)) if len(sources) > 1 else src.mob)
    new.column, new.visible = src.column, True
    for s in sources:
        s.visible = False
    _replace_in_order(stage, src, new)
    for s in sources[1:]:
        if s in stage.order:
            stage.order.remove(s)
    stale_decor = _owned_decor(stage, targets)  # e.g. a result frame drawn around the old formula
    if (
        len(sources) == 1
        and isinstance(src.mob, MathTex)
        and isinstance(new.mob, MathTex)
    ):
        anim = TransformMatchingTex(src.mob, new.mob, path_arc=PI / 6)
    else:  # several formulas combine into one
        anim = ReplacementTransform(VGroup(*(s.mob for s in sources)), new.mob)
    stage.play(anim, *(FadeOut(d) for d in stale_decor), run_time=run_time)
    stage.play(*stage.relayout_animations(), run_time=0.3)
    stage.last_result = new.id


def p_morph(stage, targets, run_time=1.0, result="", role=None):
    src, dst = stage.get(targets[0]), stage.get(result)
    dst.mob.move_to(src.mob)
    dst.column, dst.visible = src.column, True
    src.visible = False
    _replace_in_order(stage, src, dst)
    stage.play(ReplacementTransform(src.mob, dst.mob), run_time=run_time)
    stage.play(*stage.relayout_animations(), run_time=0.3)
    stage.last_result = dst.id


# ---------------------------------------------------------------------------- relations


def p_connect(stage, targets, run_time=0.8, result=None, role="active"):
    a, b = stage.get(targets[0]), stage.get(targets[1])
    if a.type == "node" and b.type == "node":
        eid = result or f"{a.id}__{b.id}"
        if eid not in stage.objs:
            stage.declare(eid, "edge", "", role, members=[a.id, b.id])
        p_appear(stage, [eid], run_time=run_time)
        return
    forbidden = role == "forbidden"

    def draw():
        if abs(a.mob.get_y() - b.mob.get_y()) > 0.5:
            # different rows (a free place below -> the person who takes it): a straight arrow edge to edge
            up = b.mob.get_y() > a.mob.get_y()
            s = (a.mob.get_top() + UP * 0.08) if up else (a.mob.get_bottom() + DOWN * 0.08)
            e = (b.mob.get_bottom() + DOWN * 0.1) if up else (b.mob.get_top() + UP * 0.1)
            line_cls = DashedLine if forbidden else Arrow
            arrow = line_cls(s, e, buff=0.0, stroke_width=T.STROKE["normal"], color=T.color(role))
            if line_cls is Arrow:
                arrow.set_stroke(width=T.STROKE["normal"])
            return VGroup(arrow)
        # same row: an arc over the two objects (a flat arrow between neighbours is only a few pixels long)
        start, end = a.mob.get_top() + UP * 0.08, b.mob.get_top() + UP * 0.08
        if start[0] > end[0]:
            start, end = end, start
        span = max(np.linalg.norm(end - start), 0.4)
        angle = -PI * 0.45 if span < 3 else -PI * 0.35  # a low arc: it must not reach the row above
        if forbidden:
            arc = ArcBetweenPoints(start, end, angle=angle, stroke_width=T.STROKE["normal"], color=T.color(role))
            mark = VGroup(
                Line(UP * 0.16 + LEFT * 0.16, DOWN * 0.16 + RIGHT * 0.16),
                Line(UP * 0.16 + RIGHT * 0.16, DOWN * 0.16 + LEFT * 0.16),
            ).set_stroke(T.color("forbidden"), T.STROKE["thick"])
            mark.move_to(arc.point_from_proportion(0.5))
            return VGroup(DashedVMobject(arc, num_dashes=12, dashed_ratio=0.6), mark)
        return CurvedArrow(start, end, angle=angle, stroke_width=T.STROKE["normal"], color=T.color(role), tip_length=0.2)

    link = always_redraw(draw)
    _decor(stage, link, [a.id, b.id])
    stage.play(Create(link), run_time=run_time)


def p_traverse(stage, targets, run_time=1.6, role="active"):
    per = run_time / max(len(targets), 1)
    prev = None
    for t in targets:
        o = stage.get(t)
        if prev is not None:
            edge = next(
                (
                    e
                    for e in stage.order
                    if e.type == "edge" and set(e.members) == {prev, t}
                ),
                None,
            )
            if edge is not None:
                edge.role = "focus"  # edges redraw from their role every frame
        # Indicate restores the colour it started from, so it runs first and the visited colour sticks.
        stage.play(
            Indicate(o.mob, color=T.color("focus"), scale_factor=1.2),
            run_time=per * 0.6,
        )
        stage.play(_recolor_anim(o, role), run_time=per * 0.4)
        prev = t


# ---------------------------------------------------------------------------- counting


def p_count_up(stage, targets, run_time=1.6, result=None, value="", role="active"):
    numbers = []
    per = run_time * 0.7 / max(len(targets), 1)
    for i, t in enumerate(targets, start=1):
        mob = stage.get(t).mob
        written = [d for d in stage.decor if t in d.ml_owners and getattr(d, "ml_kind", "") == "slot_number"]
        if written:  # the slot already shows its count: point at it instead of writing another number on top
            stage.play(
                Indicate(written[0], color=T.color(role), scale_factor=1.25),
                Indicate(mob, color=T.color(role), scale_factor=1.08),
                run_time=per,
            )
            continue
        num = primitives.math(str(i), "focus", "small")
        if stage.get(t).type in ("item", "node"):
            # a person gets an index at its lower-right corner: the space under it belongs to arcs and slots
            place = lambda m, a=mob: m.move_to(a.get_corner(DOWN + RIGHT) + np.array([0.12, 0.05, 0.0]))  # noqa: E731
        else:
            place = lambda m, a=mob: m.next_to(a, DOWN, buff=0.22)  # noqa: E731
        place(num)
        num.add_updater(place)  # stays with its object on relayout
        _decor(stage, num, [t])
        numbers.append(num)
        stage.play(
            FadeIn(num, shift=UP * 0.15),
            Indicate(mob, color=T.color(role), scale_factor=1.12),
            run_time=per,
        )
    if result:
        if result not in stage.objs:
            stage.declare(result, "formula", value or str(len(targets)), role)
        p_appear(stage, [result], run_time=run_time * 0.3)
        stage.last_result = result


def p_fill_slots(
    stage, targets, run_time=2.4, values=(), result=None, value="", role="focus"
):
    slots = [stage.get(t) for t in targets]
    # filling the same slots again replaces their numbers (never writes digits over digits)
    old = _owned_decor(stage, targets)
    if old:
        stage.play(*(FadeOut(d) for d in old), run_time=0.3)
    taken = {o.slot_of for o in stage.order if o.in_slot and o.slot_of}
    units = [
        o
        for o in stage.order
        if o.visible
        and o.type in ("item", "block")
        and not o.in_slot
        and not o.attached_to
    ]
    occupant = {}
    for s, u in zip([s for s in slots if s.id not in taken], units):
        u.in_slot, u.slot_of = True, s.id
        occupant[s.id] = u
        if u.mob.width > s.mob.width:  # a block needs a place as wide as itself
            s.mob.stretch_to_fit_width(u.mob.width * 0.92)
    # slots spread out first (wider places for blocks), then each unit walks into its place
    from . import layouts

    positions = layouts.compute(stage)
    moving = {u.id for u in occupant.values()}
    first = [
        stage.get(oid).mob.animate.move_to(p)
        for oid, p in positions.items()
        if oid not in moving and np.linalg.norm(stage.get(oid).mob.get_center() - p) > 0.02
    ]
    if first:
        stage.play(*first, run_time=min(0.6, run_time * 0.2))
    per = run_time * 0.7 / max(len(slots), 1)
    prev_num = None
    for i, s in enumerate(slots):
        anims = []
        u = occupant.get(s.id)
        if u is not None and u.id in positions:
            anims.append(u.mob.animate.move_to(positions[u.id]))
        if i < len(values):
            num = primitives.math(values[i], role).next_to(s.mob, DOWN, buff=0.3)
            num.ml_kind = "slot_number"
            num.add_updater(lambda m, sm=s.mob: m.next_to(sm, DOWN, buff=0.3))
            _decor(stage, num, [s.id])
            anims.append(FadeIn(num, shift=UP * 0.2))
            if prev_num is not None:
                times = primitives.math(r"\times", "secondary", "small")
                times.add_updater(lambda m, a=prev_num, b=num: m.move_to((a.get_center() + b.get_center()) / 2))
                _decor(stage, times, [s.id])
                anims.append(FadeIn(times))
            prev_num = num
        anims.append(Indicate(s.mob, color=T.color(role)))
        stage.play(*anims, run_time=per)
    if result:
        if result not in stage.objs:
            stage.declare(result, "formula", value, "result")
        p_appear(stage, [result], run_time=run_time * 0.2)
        stage.last_result = result


def p_partition(stage, targets, run_time=1.2, result="", value="", role="forbidden"):
    parent = stage.get(targets[0])
    dots = getattr(parent.mob, "ml_dots", None)
    k = primitives.trailing_count(value)
    if dots is not None and k and 0 < k < len(dots):
        # Carve the last k elements (a block on the right) out of the set and name them.
        sel = VGroup(*dots[-k:])
        box = SurroundingRectangle(
            sel,
            buff=0.14,
            corner_radius=0.12,
            color=T.color(role),
            stroke_width=T.STROKE["normal"],
        )
        frame = DashedVMobject(box, num_dashes=36)
        frame.add_updater(lambda m, s=sel: m.move_to(s))
        cap = primitives.caption_mobject(value, role)
        cap.add_updater(
            lambda m, f=frame, p=parent: m.next_to(p.mob[0], DOWN, buff=0.18).set_x(
                f.get_x()
            )
        )
        child = stage.objs.get(result) or stage.declare(result, "region", "", role)
        child.mob = VGroup(frame, cap, sel)
        child.mob.ml_kind = "partition"
        child.attached_to, child.visible = parent.id, True
        stage.play(
            sel.animate.set_fill(T.color(role), opacity=0.95), run_time=run_time * 0.45
        )
        stage.play(Create(frame), FadeIn(cap, shift=UP * 0.1), run_time=run_time * 0.55)
        stage.last_result = child.id
        return
    pw, ph = parent.mob[0].width, parent.mob[0].height
    child = stage.objs.get(result) or stage.declare(result, "region", "", role)
    child.mob = primitives.region(
        value, role, width=pw * 0.42, height=ph * 0.72, dashed=True
    )
    child.mob.ml_kind = "region"
    child.attached_to = parent.id
    child.visible = True

    def stick(m, p=parent):
        m.move_to(p.mob[0].get_right() + LEFT * (m.width / 2 + 0.3) + DOWN * 0.15)

    stick(child.mob)
    child.mob.add_updater(stick)
    stage.play(Create(child.mob[0]), FadeIn(VGroup(*child.mob[1:])), run_time=run_time)
    stage.last_result = child.id


# ---------------------------------------------------------------------------- camera / time


def p_camera(stage, targets, run_time=1.0, preset="wide_establishing", role=None):
    target = targets[0] if targets else stage.last_result
    stage.camera(preset, target, run_time=run_time)


def p_wait(stage, targets, run_time=0.5, role=None):
    stage.wait(run_time)


# ---------------------------------------------------------------------------- galleries (all possibilities)


def p_enumerate(
    stage,
    targets,
    run_time=3.0,
    result="gallery",
    arrangements=(),
    flags=(),
    total=0,
    valid_total=0,
    role="forbidden",
):
    """Concrete arrangements as a grid; ones that break the constraint are struck through, never deleted.
    Which ones are forbidden was decided by Python (compiler), not by the model."""
    import math

    from manim import LaggedStart

    from .stage import Obj

    n = max(len(arrangements), 1)
    cols = max(1, min(6, math.ceil(math.sqrt(n * 2.2))))
    rows = math.ceil(n / cols)
    top, bottom, left, width = 2.75, -1.45, -6.4, 12.8
    cell_w, cell_h = width / cols, (top - bottom) / rows
    mobs = []
    for i, value in enumerate(arrangements):
        m = primitives.arrangement(value, "neutral")
        m.scale(min(cell_w * 0.86 / m.width, cell_h * 0.74 / m.height, 1.0))
        r, c = divmod(i, cols)
        m.move_to(np.array([left + cell_w * (c + 0.5), top - cell_h * (r + 0.5), 0.0]))
        mobs.append(m)
    grid = VGroup(*mobs)
    o = Obj(
        id=result,
        type="gallery",
        value="",
        role="neutral",
        mob=grid,
        visible=True,
        attached_to="__gallery__",
    )
    stage.objs[result] = o
    stage.order.append(o)
    items = [stage.get(t) for t in targets if t in stage.objs and stage.get(t).visible]
    for it in items:
        it.visible = False
    stage.play(*(FadeOut(it.mob) for it in items), run_time=0.4)
    stage.play(
        LaggedStart(*(FadeIn(m, shift=UP * 0.15) for m in mobs), lag_ratio=0.06),
        run_time=run_time * 0.5,
    )

    bad = [m for m, ok in zip(mobs, flags) if not ok]
    good = [m for m, ok in zip(mobs, flags) if ok]
    if bad:
        # forbidden: dimmed and struck through (still readable — cancellation is never deletion)
        strikes = [
            Line(
                m.get_left() + LEFT * 0.06,
                m.get_right() + RIGHT * 0.06,
                color=T.color(role),
                stroke_width=T.STROKE["normal"],
            )
            for m in bad
        ]
        for s in strikes:
            _decor(stage, s, [result])
        stage.play(
            LaggedStart(*(m.animate.fade(0.68) for m in bad), lag_ratio=0.04),
            LaggedStart(*(Create(s) for s in strikes), lag_ratio=0.04),
            run_time=run_time * 0.25,
        )
        # the survivors are what we count
        lit = []
        for m in good:
            m.generate_target()
            primitives.recolor(m.target, "result")
            lit.append(MoveToTarget(m))
        stage.play(LaggedStart(*lit, lag_ratio=0.05), run_time=run_time * 0.15)
    shown = (
        f"… {len(arrangements)} / {total}" if total > len(arrangements) else ""
    )  # a sample is shown
    tally_tex = rf"{valid_total} / {total}" if bad else rf"{total}"
    tally = primitives.math(
        tally_tex, "result" if bad else "active", "formula"
    ).move_to(np.array([-5.2, -2.05, 0.0]))
    group = VGroup(tally)
    if shown:
        group.add(
            primitives.text(shown, "small", "secondary").next_to(tally, DOWN, buff=0.12)
        )
    _decor(stage, group, [result])
    stage.play(FadeIn(group, shift=UP * 0.1), run_time=run_time * 0.15)
    stage.last_result = result
