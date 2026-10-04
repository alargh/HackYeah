"""Deterministic repairs of common VisualPlan slips, applied before validation.

Each fix keeps the plan's meaning (it never invents mathematics); it only removes the need for another
LLM round trip for mechanical mistakes:
  * an operation uses an object before it was created  -> create it right before (same beat);
  * an operation that takes at most N targets got more  -> split it into several actions;
  * too many camera moves                               -> keep the first ones, drop the rest;
  * a solid without its dimensions                       -> symbolic dimensions (a=a, h=h);
  * a 3D formula without its source                      -> the segment/angle/section shown just before it.
"""

from __future__ import annotations

from app.schemas.generation import VisualActionSpec, VisualPlan
from app.services.visuals.runtime.tutorly_visuals import geometry as geo

_NO_CREATE = {"create", "grow", "compare"}


def autofix(plan: VisualPlan, arity: dict, max_camera_moves: int) -> tuple[VisualPlan, list[str]]:
    plan = plan.model_copy(deep=True)
    notes: list[str] = []
    for o in plan.objects:  # "tetrahedron" without params -> symbolic edge a (drawn with a = 1)
        if o.type in ("solid", "figure") and o.value in geo.REQUIRED_PARAMS:
            have = {p.split("=", 1)[0].strip() for p in o.params if "=" in p}
            missing = [k for k in geo.REQUIRED_PARAMS[o.value] if k not in have]
            if missing and not (o.value == "pyramid_triangular" and "a" in have):
                o.params = [*o.params, *(f"{k}={k}" for k in missing if k != "n")]
                notes.append(f"{o.id}: symbolic {missing}")
    _guess_formula_sources(plan, notes)
    declared = {o.id for o in plan.objects}
    types = {o.id: o.type for o in plan.objects}
    seen: set[str] = set()
    for beat in plan.beats:
        actions: list[VisualActionSpec] = []
        for a in beat.actions:
            if a.operation == "revolve" and len(a.targets) >= 2:  # [axis, figure] -> [figure, axis]
                kinds = [types.get(t) for t in a.targets[:2]]
                if kinds == ["segment", "figure"]:
                    a.targets = [a.targets[1], a.targets[0], *a.targets[2:]]
                    notes.append(f"{beat.id}: revolve targets reordered to [figure, axis]")
            lo, hi, min_res, _ = arity.get(a.operation, (0, None, 0, False))
            parts = [a]
            if hi is not None and len(a.targets) > hi and not a.results and not a.values:
                parts = [a.model_copy(update={"targets": a.targets[i : i + hi]}) for i in range(0, len(a.targets), hi)]
                notes.append(f"{beat.id}: split '{a.operation}' over {len(a.targets)} targets")
            for p in parts:
                if p.operation not in _NO_CREATE:
                    missing = [t for t in p.targets if t in declared and t not in seen]
                    if missing:
                        actions.append(VisualActionSpec(operation="create", targets=missing))
                        seen.update(missing)
                        notes.append(f"{beat.id}: created {missing} before '{p.operation}'")
                if p.operation in ("create", "grow"):
                    seen.update(p.targets)
                seen.update(p.results)
                actions.append(p)
        beat.actions = actions
    moves = 0
    for bi, beat in enumerate(plan.beats):
        if beat.camera is not None and not (bi == 0 and beat.camera == "wide_establishing"):
            moves += 1
            if moves > max_camera_moves and beat.camera not in ("orbit", "orbit_stop"):
                notes.append(f"{beat.id}: dropped camera '{beat.camera}'")
                beat.camera = None
    return plan, notes


def prune(plan: VisualPlan, issues) -> tuple[VisualPlan, list[str]] | None:
    """Last resort before hand-written fallback code: drop the objects the validator rejected (bad points,
    unknown placements, impossible solids) and every action that uses them, keep everything else. A smaller
    correct picture drawn by the engine beats a complete one drawn at random."""
    ids = {o.id for o in plan.objects}
    bad = {i.location for i in issues if i.severity == "error" and i.location in ids}
    if not bad:
        return None
    plan = plan.model_copy(deep=True)
    notes = [f"dropped {sorted(bad)}"]
    # objects that depend on dropped ones (a point on a dropped point, a segment through it) go too
    changed = True
    while changed:
        changed = False
        for o in plan.objects:
            if o.id not in bad and (set(o.members) & bad or o.parent in bad or any(p.split("=", 1)[-1] in bad for p in o.params)):
                bad.add(o.id)
                changed = True
    plan.objects = [o for o in plan.objects if o.id not in bad]
    survivors = [o.id for o in plan.objects if o.type not in ("formula", "label")]
    for beat in plan.beats:
        kept = []
        for a in beat.actions:
            if set(a.results) & bad:
                continue
            targets = [t for t in a.targets if t not in bad]
            if len(targets) != len(a.targets) and not targets:
                continue
            kept.append(a.model_copy(update={"targets": targets}))
        if not kept and survivors:  # keep the narration in sync: look at what is still there
            kept = [VisualActionSpec(operation="highlight", targets=[survivors[0]])]
        beat.actions = kept
    return plan, notes


def _guess_formula_sources(plan: VisualPlan, notes: list[str]) -> None:
    """3D scenes: a formula without `parent` is attributed to the geometric object (segment, angle, section,
    flattened section) shown most recently before it. With nothing shown yet it stays empty, and the
    validator asks for the construction to be drawn first."""
    if plan.layout != "space_3d":
        return
    objs = {o.id: o for o in plan.objects}
    recent: list[str] = []
    for beat in plan.beats:
        for a in beat.actions:
            for t in a.targets:
                o = objs.get(t)
                if o is not None and o.type == "formula" and not o.parent and a.operation in ("create", "grow") and recent:
                    o.parent = recent[-1]
                    notes.append(f"{o.id}: source {recent[-1]}")
            if a.operation in ("create", "grow", "measure", "highlight", "focus"):
                recent += [t for t in a.targets if objs.get(t) is not None and objs[t].type in ("segment", "plane", "angle")]
            if a.operation in ("connect", "flatten"):
                recent += list(a.results)
