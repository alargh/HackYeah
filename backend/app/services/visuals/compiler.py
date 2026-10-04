"""Deterministic compilation: semantic VisualPlan → AnimationPlan → Manim source.

The source is a short, readable scene that drives the tutorly_visuals runtime. It keeps the
`# EVENT: <beat id>` markers, so the existing voiceover hooks and synchronisation keep working.
"""

from __future__ import annotations

import itertools
import math

from app.schemas.generation import SOLID_TYPES, AnimationPlan, AnimationStep, NarrationIR, VisualPlan
from app.schemas.problem import ProblemIR
from app.services.visuals.grammar import expand

MAX_GALLERY = 24

# Fraction of a beat's duration used for motion (the rest is reading/listening time).
MOTION_SHARE = 0.75
MIN_SCALE, MAX_SCALE = 0.6, 1.6
CAPTION_TRANSITION = 0.5


def is_3d(plan: VisualPlan) -> bool:
    return plan.layout == "space_3d" or any(o.type in SOLID_TYPES for o in plan.objects)


def gallery(labels: list[str], problem: ProblemIR | None) -> tuple[list[str], list[bool], int, int]:
    """Concrete arrangements for `enumerate`: all of them when few, otherwise an even sample.
    Validity is decided by Python from the problem's enumeration_spec constraints (never by the model)."""
    from app.services.validation.independent import _satisfies

    spec = problem.enumeration_spec if problem is not None else None
    constraints = spec.constraints if spec is not None and set(spec.items) <= set(labels) else []
    total = math.factorial(len(labels))
    if total <= MAX_GALLERY:
        chosen = list(itertools.permutations(labels))
    else:
        step = total / MAX_GALLERY
        wanted = {int(i * step) for i in range(MAX_GALLERY)}
        chosen = [p for i, p in enumerate(itertools.permutations(labels)) if i in wanted]
    if total <= 40320:
        valid_total = sum(1 for p in itertools.permutations(labels) if all(_satisfies(c, p) for c in constraints))
    else:
        valid_total = total
    flags = [all(_satisfies(c, p) for c in constraints) for p in chosen]
    return [" ".join(p) for p in chosen], flags, total, valid_total


def compile_plan(
    plan: VisualPlan, narration: NarrationIR | None, class_name: str, title: str, problem: ProblemIR | None = None
) -> AnimationPlan:
    object_types = {o.id: o.type for o in plan.objects}
    object_values = {o.id: o.value or o.id for o in plan.objects}
    segments = {s.visual_event: s for s in narration.segments} if narration else {}
    steps: list[AnimationStep] = []
    durations: dict[str, float] = {}
    captions: dict[str, str] = {}

    for beat in plan.beats:
        seg = segments.get(beat.id)
        duration = max(seg.duration_estimate if seg else beat.duration, 1.0)
        durations[beat.id] = duration
        captions[beat.id] = seg.text if seg else ""

        raw = []
        start_cams = ("wide_establishing", "split_view", "focus_subject", "three_quarter", "top_view", "front_view")
        if beat.camera in start_cams:
            first = next((a.targets[0] for a in beat.actions if a.targets), None)
            raw.append(("camera", [first] if beat.camera == "focus_subject" and first else [], 1.0, {"preset": beat.camera}))
        if beat.camera == "orbit":
            raw.append(("camera", [], 0.0, {"preset": "orbit"}))
        for action in beat.actions:
            for st in expand(action, object_types):
                params = dict(st.params)
                if st.primitive == "enumerate":
                    labels = [object_values.get(t, t) for t in st.targets]
                    arrangements, flags, total, valid_total = gallery(labels, problem)
                    params.update(arrangements=arrangements, flags=flags, total=total, valid_total=valid_total)
                    params.pop("values", None)
                raw.append((st.primitive, st.targets, st.weight, params))
        if beat.camera == "follow_transform":
            raw.append(("camera", [], 0.8, {"preset": "follow_transform"}))

        total_weight = sum(w for _, _, w, _ in raw) or 1.0
        scale = min(max((duration - CAPTION_TRANSITION) * MOTION_SHARE / total_weight, MIN_SCALE), MAX_SCALE)
        used = CAPTION_TRANSITION
        for prim, targets, weight, params in raw:
            rt = round(weight * scale, 2)
            used += rt
            steps.append(AnimationStep(beat=beat.id, primitive=prim, targets=targets, params=params, run_time=rt))
        rest = round(duration - used, 2)
        if rest > 0.1:
            steps.append(AnimationStep(beat=beat.id, primitive="wait", run_time=rest))
        if beat.camera == "orbit":
            steps.append(AnimationStep(beat=beat.id, primitive="camera", params={"preset": "orbit_stop"}, run_time=0.0))

    return AnimationPlan(
        scene_id=plan.scene_id,
        class_name=class_name,
        title=title,
        layout=plan.layout,
        steps=steps,
        beat_durations=durations,
        captions=captions,
        objects=_declaration_order([o.model_dump() for o in plan.objects]),
        dimension="3d" if is_3d(plan) else "2d",
        camera=plan.camera,
        beat_layouts={b.id: b.layout for b in plan.beats if b.layout},
    )


def _declaration_order(objects: list[dict]) -> list[dict]:
    """Solids first (they define the vertex points), then derived points, then everything else."""
    rank = {"solid": 0, "figure": 0, "point": 1}

    def key(o: dict) -> int:
        # a second solid placed at a point (params "at=P") comes with the points, in plan order
        if o["type"] == "solid" and any(str(p).replace(" ", "").startswith("at=") for p in o.get("params") or []):
            return 1
        return rank.get(o["type"], 2)

    return sorted(objects, key=key)


def _py(value) -> str:
    """Python literal for compiled code (repr is injection-safe for str/list/dict/None/float)."""
    return repr(value)


def render_source(anim: AnimationPlan) -> str:
    three_d = anim.dimension == "3d"
    stage, base = ("Stage3D", "ThreeDScene") if three_d else ("Stage", "MovingCameraScene")
    lines = [
        "from manim import *",
        f"from tutorly_visuals import {stage}",
        "",
        "",
        f"class {anim.class_name}({base}):",
        "    def construct(self):",
        f"        st = {stage}(self, title={_py(anim.title)}, layout={_py(anim.layout)}, camera={_py(anim.camera)})",
    ]
    for o in anim.objects:
        lines.append(
            f"        st.declare({_py(o['id'])}, {_py(o['type'])}, {_py(o.get('value', ''))}, "
            f"role={_py(o.get('emphasis', 'neutral'))}, members={_py(o.get('members', []))}, parent={_py(o.get('parent'))}, "
            f"params={_py(o.get('params', []))})"
        )
    current = None
    for step in anim.steps:
        if step.beat != current:
            current = step.beat
            lines.append("")
            lines.append(f"        # EVENT: {current}")
            layout = anim.beat_layouts.get(current)
            lines.append(
                f"        st.beat({_py(current)}, caption={_py(anim.captions.get(current, ''))}, layout={_py(layout)}, "
                f"duration={anim.beat_durations.get(current, 4.0)})"
            )
        if step.primitive == "wait":
            lines.append(f"        st.wait({step.run_time})")
            continue
        params = "".join(f", {k}={_py(v)}" for k, v in step.params.items())
        lines.append(f"        st.do({_py(step.primitive)}, {_py(step.targets)}, run_time={step.run_time}{params})")
    lines += ["", "        st.finish()", ""]
    return "\n".join(lines)
