"""VisualPlanValidator: manifest conformance + deterministic visual-quality rules for semantic visual plans.

Thresholds and severities come from the `quality` section of services/visuals/manifest.yaml.
"""

from __future__ import annotations

import re

from app.schemas.generation import NarrationIR, VisualPlan
from app.schemas.lesson import SceneIR
from app.schemas.validation import ValidationIssue, ValidationResult
from app.services.validation.geometry_checks import check_3d
from app.services.validation.language import check_texts
from app.services.visuals.grammar import CASE_OPERATIONS, MATH_OPERATIONS, is_text_only
from app.services.visuals.manifest import Manifest, get_manifest

NAME = "visual"

ALLOWED_TEX_COMMANDS = frozenset(
    """cdot times div frac dfrac tfrac left right le leq ge geq neq ne ldots cdots dots quad qquad binom sum prod
    sqrt pm mp to rightarrow Rightarrow implies iff in notin cup cap setminus emptyset mid vert lvert rvert
    overline underbrace overbrace text mathrm mathbf infty equiv approx displaystyle cdotp lbrace rbrace
    alpha beta gamma delta epsilon theta lambda mu pi sigma phi omega Delta Sigma Pi Omega
    sin cos tan cot arctan arcsin arccos circ perp parallel angle measuredangle triangle
    vec overrightarrow overleftrightarrow hat widehat bar log ln lim max min sqrt cong sim degree prime
    varphi varepsilon rho tau eta xi kappa nu chi psi zeta Gamma Lambda Phi Psi Theta Xi
    mathbb mathcal operatorname boxed underline square blacksquare forall exists subset subseteq""".split()
)
_TEX_CMD = re.compile(r"\\([A-Za-z]+)")
_STYLE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bcolou?r\s*[=:]|\bfont\s*[=:]|\bfont-family\b", re.IGNORECASE)

# operation → (min targets, max targets or None, min results, needs a value per result)
ARITY: dict[str, tuple[int, int | None, int, bool]] = {
    "create": (1, None, 0, False),
    "remove": (1, None, 0, False),
    "highlight": (1, None, 0, False),
    "merge": (2, None, 1, False),
    "split": (1, 1, 2, True),
    "branch": (1, 1, 2, True),
    "transform": (1, 4, 1, True),  # several formulas may combine into one (4! = 24, 2! = 2 -> 24 * 2 = 48)
    "morph": (1, 1, 1, False),
    "connect": (2, 2, 0, False),
    "grow": (1, None, 0, False),
    "compare": (2, None, 0, False),
    "count": (1, None, 0, False),
    "fill_slots": (1, None, 0, False),
    "partition": (1, 1, 1, False),
    "traverse": (2, None, 0, False),
    "emphasize_result": (1, None, 0, False),
    "focus": (1, None, 0, False),
    "unfocus": (0, None, 0, False),
    "enumerate": (2, 8, 0, False),
    "measure": (1, 1, 0, False),
    "flatten": (1, 1, 0, False),
    "revolve": (2, 2, 1, False),
}
GRAPH_TEMPLATES = {"graph_build", "graph_traversal", "highlight_path"}
_GEOMETRY_WORDS = ("geometr", "planimetr", "stereometr", "solid", "polygon", "triangle", "hexagon", "polyhedr", "revolution", "prism", "pyramid", "cube",
                   "cylinder", "cone", "sphere", "frustum", "walec", "stożek", "kula", "bryła", "graniastosłup", "ostrosłup", "sześcian")


def is_geometry_problem(problem) -> bool:
    if problem is None:
        return False
    if getattr(problem, "geometry_spec", None) is not None:
        return True
    text = " ".join([problem.domain, problem.subdomain, problem.problem_type]).lower()
    return any(w in text for w in _GEOMETRY_WORDS)


class VisualPlanValidator:
    def __init__(self, manifest: Manifest | None = None):
        self.m = manifest or get_manifest()

    def _rule(self, name: str):
        return self.m.rule(name)

    def _issue(self, issues: list, rule: str, code: str, message: str, location: str | None = None) -> None:
        issues.append(ValidationIssue(code=code, message=message, severity=self._rule(rule).severity, location=location))

    def validate(
        self,
        plan: VisualPlan,
        scene: SceneIR | None = None,
        narration: NarrationIR | None = None,
        retrieved: list[str] | None = None,
        problem=None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        err = lambda code, msg, loc=None: issues.append(ValidationIssue(code=code, message=msg, location=loc))  # noqa: E731
        warn = lambda code, msg, loc=None: issues.append(ValidationIssue(code=code, message=msg, severity="warning", location=loc))  # noqa: E731

        # ---------------------------------------------------------------- manifest conformance
        for tid in plan.template_ids:
            if self.m.template(tid) is None:
                err("UNKNOWN_TEMPLATE", f"template '{tid}' is not in the visual library")
            elif retrieved is not None and tid not in retrieved:
                warn("TEMPLATE_NOT_RETRIEVED", f"template '{tid}' was not among the retrieved capabilities")
        if len(plan.secondary_templates) > 2:
            warn("TOO_MANY_TEMPLATES", "use at most 2 secondary templates")
        allowed_ops = self.m.allowed_operations(plan.template_ids)
        allowed_types = {"label", "formula"}
        for tid in plan.template_ids:
            t = self.m.template(tid)
            if t:
                allowed_types.update(t.object_types)

        types: dict[str, str] = {}
        solid_vertices: list[str] = []
        for o in plan.objects:
            if o.type in ("solid", "figure"):
                try:
                    from app.services.visuals.runtime.tutorly_visuals import geometry as geo

                    solid_vertices = list(geo.build_solid(o.value, o.params, o.members or None).vertices)
                except Exception:  # reported by the 3D checks
                    solid_vertices = list(o.members)
        for o in plan.objects:
            if o.id in types:
                err("DUPLICATE_OBJECT", f"object id '{o.id}' is declared twice")
            types[o.id] = o.type
            if o.type not in allowed_types:
                err("UNSUPPORTED_OBJECT_TYPE", f"object '{o.id}' of type '{o.type}' is not used by templates {plan.template_ids}")
            if _STYLE.search(o.value):
                err("ARBITRARY_STYLE", f"object '{o.id}' specifies a colour/font; use an emphasis role instead")
            if o.type == "formula":
                self._check_tex(o.value, o.id, issues)
            if o.type == "label" and len(o.value) > self._rule("max_label_chars").value:
                self._issue(issues, "max_label_chars", "LABEL_TOO_LONG", f"label '{o.id}' has {len(o.value)} characters", o.id)
        for v in solid_vertices:  # every vertex of the solid is an addressable point
            types.setdefault(v, "point")
        for o in plan.objects:
            if o.type == "edge" and (len(o.members) != 2 or any(types.get(m) != "node" for m in o.members)):
                err("BAD_EDGE", f"edge '{o.id}' must connect exactly two declared nodes")
            if o.type == "node" and o.parent and types.get(o.parent) != "node":
                err("BAD_PARENT", f"node '{o.id}' has unknown parent '{o.parent}'")

        # ---------------------------------------------------------------- beats and operations
        on_stage: set[str] = set()
        produced: dict[str, str] = {}
        layout = plan.layout
        ops_used: list[str] = []
        text_run = max_text_run = text_beats = camera_moves = 0
        last_highlight: dict[str, int] = {}
        repeated = 0
        emphasis_seen = False
        known = lambda i: i in types or i in produced  # noqa: E731

        for bi, beat in enumerate(plan.beats):
            loc = beat.id
            layout = beat.layout or layout
            if not beat.purpose.strip() or beat.purpose.strip().lower() in {"decoration", "decorative", "transition", "effect"}:
                err("DECORATIVE_BEAT", "every beat needs a mathematical purpose", loc)
            if len(beat.actions) < self._rule("min_actions_per_beat").value:
                self._issue(issues, "min_actions_per_beat", "EMPTY_BEAT", "beat has no visual action", loc)
            if beat.camera is not None and not (bi == 0 and beat.camera == "wide_establishing"):
                camera_moves += 1
            if is_text_only(beat.actions, {**types, **produced}) and beat.actions:
                text_beats += 1
                text_run += 1
                max_text_run = max(max_text_run, text_run)
            else:
                text_run = 0

            for a in beat.actions:
                op = a.operation
                ops_used.append(op)
                if op not in allowed_ops:
                    err("UNSUPPORTED_OPERATION", f"'{op}' is not supported by templates {plan.template_ids}", loc)
                lo, hi, min_res, needs_vals = ARITY[op]
                if len(a.targets) < lo or (hi is not None and len(a.targets) > hi):
                    err("BAD_ARITY", f"'{op}' needs {lo}{'' if hi == lo else '+' if hi is None else f'-{hi}'} target(s)", loc)
                if len(a.results) < min_res:
                    err("MISSING_RESULT", f"'{op}' must name {min_res}+ result object(s)", loc)
                if needs_vals and len(a.values) < len(a.results):
                    err("MISSING_VALUES", f"'{op}' needs a value for every result", loc)
                if op == "measure" and not a.values:
                    err("MISSING_VALUES", "'measure' needs the value to write (values = [LaTeX])", loc)
                if op == "enumerate" and any(types.get(t) != "item" for t in a.targets):
                    err("BAD_TARGET_TYPE", "enumerate arranges items", loc)
                for v in a.values:
                    if _STYLE.search(v):
                        err("ARBITRARY_STYLE", "values must not specify colours/fonts", loc)
                if op == "transform":
                    for v in a.values:
                        self._check_tex(v, loc, issues)
                if op in ("highlight", "emphasize_result") or (a.emphasis not in (None, "neutral")):
                    emphasis_seen = True
                if op in CASE_OPERATIONS and layout not in ("split_view", "tree_layout") and self._rule("require_spatial_separation_for_cases").value:
                    self._issue(issues, "require_spatial_separation_for_cases", "CASES_NOT_SEPARATED",
                                f"'{op}' needs layout split_view or tree_layout (current: {layout})", loc)
                if op == "fill_slots" and any(types.get(t) != "slot" for t in a.targets):
                    err("BAD_TARGET_TYPE", "fill_slots targets must be slots", loc)
                if op == "partition" and any(types.get(t) != "region" for t in a.targets):
                    err("BAD_TARGET_TYPE", "partition targets must be regions", loc)
                if op == "traverse" and any(types.get(t) != "node" for t in a.targets):
                    err("BAD_TARGET_TYPE", "traverse targets must be nodes", loc)

                # targets must exist and (except for create/compare) already be on stage
                for t in a.targets:
                    if not known(t):
                        err("UNKNOWN_TARGET", f"'{op}' targets unknown object '{t}'", loc)
                    elif op in ("create", "grow"):  # both bring objects on stage
                        if t in on_stage:
                            warn("ALREADY_ON_STAGE", f"'{t}' is created twice", loc)
                    elif op not in ("compare",) and t not in on_stage:
                        err("NOT_ON_STAGE", f"'{op}' acts on '{t}' before it is created", loc)
                if op == "highlight":
                    for t in a.targets:
                        if last_highlight.get(t) == bi - 1:
                            repeated += 1
                        last_highlight[t] = bi
                if op == "morph":
                    for r in a.results:
                        if r not in types:
                            err("UNKNOWN_TARGET", f"morph result '{r}' must be a declared object", loc)
                else:
                    for r in a.results:
                        # A declared object may make its first appearance as a result; an object that is
                        # already on stage (or produced before) may not be produced again.
                        if r in on_stage or r in produced:
                            err("RESULT_EXISTS", f"result '{r}' already exists; results must be new ids", loc)
                        if r in types:
                            continue
                        produced[r] = {"merge": "block", "split": "arrangement", "branch": "arrangement",
                                       "transform": "formula", "partition": "region",
                                       "connect": "segment" if solid_vertices else "edge",
                                       "enumerate": "gallery", "flatten": "panel",
                                       "revolve": "solid"}.get(op, "formula")

                # stage bookkeeping
                if op in ("create", "grow", "compare"):
                    on_stage.update(a.targets)
                    if any(types.get(t) in ("solid", "figure") for t in a.targets):
                        on_stage.update(solid_vertices)
                if op == "enumerate":
                    on_stage.difference_update(a.targets)  # the items become the gallery
                if op == "remove":
                    on_stage.difference_update(a.targets)
                if op == "transform":
                    on_stage.difference_update(a.targets)
                if op == "morph":
                    on_stage.difference_update(a.targets[:1])
                on_stage.update(a.results)

        # ---------------------------------------------------------------- quality rules
        visual_objects = [i for i, t in {**types, **produced}.items() if t not in ("label", "formula")]
        r = self._rule("min_visual_objects")
        if len(visual_objects) < r.value:
            options = [
                f"{t.id} ({', '.join(x for x in t.object_types if x not in ('label', 'formula'))})"
                for t in (self.m.template(i) for i in (retrieved or [t.id for t in self.m.templates]))
                if t and any(x not in ("label", "formula") for x in t.object_types)
            ]
            self._issue(issues, "min_visual_objects", "TOO_FEW_VISUAL_OBJECTS",
                        f"only {len(visual_objects)} visual (non-text) object(s); show the mathematics as objects, not just "
                        f"formulas. Available: {'; '.join(options[:6])}")
        r = self._rule("max_consecutive_text_beats")
        if max_text_run > r.value:
            self._issue(issues, "max_consecutive_text_beats", "CONSECUTIVE_TEXT_BEATS",
                        f"{max_text_run} consecutive beats only show text/formulas")
        if plan.beats and text_beats / len(plan.beats) > self._rule("max_text_beat_ratio").value:
            self._issue(issues, "max_text_beat_ratio", "TOO_MUCH_TEXT", f"{text_beats}/{len(plan.beats)} beats are text-only")
        label_chars = sum(len(o.value) for o in plan.objects if o.type == "label")
        if label_chars > self._rule("max_total_label_chars").value:
            self._issue(issues, "max_total_label_chars", "TOO_MUCH_STATIC_TEXT", f"{label_chars} characters of labels")
        if camera_moves > self._rule("max_camera_moves").value:
            self._issue(issues, "max_camera_moves", "TOO_MANY_CAMERA_MOVES", f"{camera_moves} camera moves")
        if repeated > self._rule("max_repeated_highlights").value:
            self._issue(issues, "max_repeated_highlights", "REPEATED_HIGHLIGHTS", "the same object is highlighted beat after beat")
        if (
            self._rule("require_math_operation_for_steps").value
            and scene is not None
            and scene.solution_steps
            and not set(ops_used) & MATH_OPERATIONS
        ):
            self._issue(issues, "require_math_operation_for_steps", "NO_MATH_VISUAL",
                        f"scene covers solution steps {scene.solution_steps} but no beat shows a mathematical operation")
        if self._rule("require_emphasis").value and plan.beats and not emphasis_seen:
            self._issue(issues, "require_emphasis", "NO_EMPHASIS", "no object is ever emphasised (highlight / emphasize_result)")
        formulas_created = [i for i, t in types.items() if t == "formula"]
        if self._rule("prefer_transform_for_formulas").value and len(formulas_created) >= 2 and not {"transform", "morph"} & set(ops_used):
            self._issue(issues, "prefer_transform_for_formulas", "FORMULAS_NOT_TRANSFORMED",
                        "several formulas appear but none is transformed into the next")
        graphy = set(plan.template_ids) & GRAPH_TEMPLATES or any(t == "node" for t in types.values())
        if self._rule("require_graph_state_change").value and graphy and not {"traverse", "connect", "branch", "grow", "highlight"} & set(ops_used):
            self._issue(issues, "require_graph_state_change", "STATIC_GRAPH", "graph reasoning must visibly change the graph state")
        if len(plan.beats) > self._rule("max_beats").value:
            self._issue(issues, "max_beats", "TOO_MANY_BEATS", f"{len(plan.beats)} beats")

        # ---------------------------------------------------------------- on-screen text
        if problem is not None:
            texts = {o.id: o.value for o in plan.objects if o.type in ("label", "item", "arrangement", "region", "node")}
            issues.extend(check_texts(texts, problem.language, "labels").issues)

        # ---------------------------------------------------------------- geometry
        check_3d(plan, self.m.quality, issues)
        if (
            self._rule("require_figure_for_geometry").value
            and is_geometry_problem(problem)
            and not any(o.type in ("solid", "figure") for o in plan.objects)
        ):
            self._issue(issues, "require_figure_for_geometry", "GEOMETRY_WITHOUT_FIGURE",
                        "this is a geometry problem: draw the actual figure or solid (object type 'figure' or 'solid'); "
                        "items, nodes and regions cannot stand in for geometric shapes")

        # ---------------------------------------------------------------- narration sync
        if narration is not None:
            beat_ids = {b.id for b in plan.beats}
            missing = [s.visual_event for s in narration.segments if s.visual_event not in beat_ids]
            if missing:
                warn("NARRATION_NOT_VISUALIZED", f"no beat for narration events: {', '.join(missing)}")

        return ValidationResult.build(NAME, f"visual:{plan.scene_id}", issues, ops=sorted(set(ops_used)))

    def _check_tex(self, tex: str, loc: str, issues: list) -> None:
        if not tex.isascii():
            issues.append(ValidationIssue(code="FORMULA_NOT_ASCII", message=f"formula {tex!r} must be ASCII LaTeX (use labels for words)", location=loc))
        bad = sorted({c for c in _TEX_CMD.findall(tex) if c not in ALLOWED_TEX_COMMANDS})
        if bad:
            issues.append(ValidationIssue(code="UNSUPPORTED_TEX", message=f"LaTeX commands not allowed: {', '.join(bad)}", location=loc))
        if tex.count("{") != tex.count("}"):
            issues.append(ValidationIssue(code="UNBALANCED_TEX", message=f"unbalanced braces in {tex!r}", location=loc))
