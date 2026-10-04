"""The semantic visual grammar: mathematical meaning → motion primitives.

    new object        → create            → appear (by object type)
    removal           → remove            → [cross_out] → disappear
    grouping          → merge             → indicate → move_adjacent → enclose (block + label) → relayout
    case analysis     → split / branch    → copies fly out into columns / child nodes with edges
    equivalent form   → transform / morph → matching-tex rewrite (several formulas may combine into one) / shape interpolation
    important choice  → highlight         → recolor (role) → indicate
    relation          → connect           → line / arc (dashed + cross when forbidden)
    growth            → grow              → lagged appear
    comparison        → compare           → split columns + divider
    counting          → count / fill_slots→ numbered indication / items occupy slots with choice counts
    sets              → partition         → sub-region carved inside a region
    walk              → traverse          → visit nodes, light the edges
    all possibilities → enumerate         → grid of concrete arrangements, forbidden ones struck (Python decides)
    a length / angle  → measure           → value label at the segment / angle (Python checks it)
    rotation          → revolve           → the figure turns about the axis while its solid of revolution grows
    a 2D sub-problem  → flatten           → the 3D polygon's true shape is laid flat beside the solid
    result            → emphasize_result  → result colour + box + flash
    spotlight         → focus / unfocus   → dim everything else / restore

Weights are relative durations; the compiler scales them to the narration length of each beat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.generation import VisualActionSpec


@dataclass
class Step:
    primitive: str
    targets: list[str]
    weight: float
    params: dict = field(default_factory=dict)


CASE_OPERATIONS = {"split", "branch", "compare"}
MATH_OPERATIONS = {
    "merge", "split", "branch", "transform", "morph", "count", "fill_slots", "partition", "compare", "traverse",
    "emphasize_result", "connect", "grow", "enumerate", "measure", "flatten", "revolve",
}
TEXT_TYPES = {"label", "formula"}


def expand(action: VisualActionSpec, object_types: dict[str, str]) -> list[Step]:
    op, t = action.operation, list(action.targets)
    res, vals = list(action.results), list(action.values)
    role = action.emphasis

    if op == "create":
        if any(object_types.get(x) in ("solid", "figure") for x in t):
            return [Step("appear", t, 2.6)]  # sweep-reveal of the wireframe / outline
        return [Step("grow" if len(t) > 3 else "appear", t, 1.4 if len(t) > 3 else 1.0)]
    if op == "enumerate":
        return [Step("enumerate", t, 3.0, {"result": res[0] if res else "gallery", "values": vals, "role": role or "forbidden"})]
    if op == "measure":
        return [Step("measure", t[:1], 0.9, {"value": vals[0] if vals else "", "role": role or "focus"})]
    if op == "revolve":
        return [Step("revolve", t[:2], 4.0, {"result": res[0] if res else "revolution", "role": role or "transformation"})]
    if op == "flatten":
        return [Step("flatten", t[:1], 2.0, {"result": res[0] if res else "panel", "role": role or "focus"})]
    if op == "remove":
        if role == "forbidden":
            return [Step("cross_out", t, 0.6), Step("disappear", t, 0.6)]
        return [Step("disappear", t, 0.6)]
    if op == "highlight":
        r = role or "focus"
        return [Step("recolor", t, 0.4, {"role": r}), Step("indicate", t, 0.6, {"role": r})]
    if op == "merge":
        return [
            Step("indicate", t, 0.6, {"role": "focus"}),
            Step("move_adjacent", t, 0.9),
            Step("enclose", t, 1.0, {"result": res[0], "value": vals[0] if vals else "", "role": role or "transformation"}),
        ]
    if op == "split":
        return [Step("spawn_copies", t[:1], 1.5, {"results": res, "values": vals, "role": role or "active"})]
    if op == "branch":
        return [Step("branch", t[:1], 1.5, {"results": res, "values": vals, "role": role or "active"})]
    if op == "transform":
        return [Step("transform_tex", t, 1.0 + 0.3 * (len(t) - 1), {"result": res[0], "value": vals[0] if vals else "", "role": role or "transformation"})]
    if op == "morph":
        return [Step("morph", t[:1], 1.0, {"result": res[0]})]
    if op == "connect":
        return [Step("connect", t[:2], 0.8, {"result": res[0] if res else None, "role": role or "active"})]
    if op == "grow":
        return [Step("grow", t, 1.4)]
    if op == "compare":
        return [Step("compare", t, 1.0)]
    if op == "count":
        return [Step("count_up", t, 0.4 * len(t) + 0.6, {"result": res[0] if res else None, "value": vals[-1] if vals else "", "role": role or "active"})]
    if op == "fill_slots":
        choices = vals[: len(t)]
        final = vals[len(t)] if len(vals) > len(t) else ""
        return [Step("fill_slots", t, 0.55 * len(t) + 0.6, {"values": choices, "result": res[0] if res else None, "value": final, "role": role or "focus"})]
    if op == "partition":
        return [Step("partition", t[:1], 1.2, {"result": res[0], "value": vals[0] if vals else "", "role": role or "forbidden"})]
    if op == "traverse":
        return [Step("traverse", t, 0.5 * len(t), {"role": role or "active"})]
    if op == "emphasize_result":
        return [Step("emphasize", t, 1.2, {"role": role or "result"})]
    if op == "focus":
        return [Step("dim_others", t, 0.6)]
    if op == "unfocus":
        return [Step("undim", t, 0.5)]
    raise ValueError(f"no grammar rule for operation '{op}'")


def is_text_only(actions: list[VisualActionSpec], object_types: dict[str, str]) -> bool:
    """A beat that only puts text/formulas on screen (no visual operation on mathematical objects)."""
    for a in actions:
        if a.operation != "create":
            return False
        if any(object_types.get(t) not in TEXT_TYPES for t in a.targets):
            return False
    return True
