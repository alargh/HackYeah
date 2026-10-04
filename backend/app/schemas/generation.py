"""Per-scene generation artifacts: NarrationIR, VisualPlan, ManimCode, FollowupPlan and Voiceover."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.lesson import LedgerEntry, SceneIR
from app.schemas.problem import IRModel


class NarrationSegment(IRModel):
    id: str = Field(description="e.g. n1")
    text: str = Field(description="Spoken/displayed narration, in the problem's language")
    visual_event: str = Field(description="Id of the visual event this segment accompanies")
    concepts: list[str] = Field(default_factory=list)
    duration_estimate: float = 4.0


class NarrationIR(IRModel):
    scene_id: str
    segments: list[NarrationSegment]

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)


# Vocabulary of the semantic visual plan. These enums mirror services/visuals/manifest.yaml
# (a test keeps them in sync); the model can only pick from them, never name colours or Manim calls.
Emphasis = Literal["neutral", "secondary", "active", "focus", "forbidden", "result", "transformation"]
ObjectType = Literal[
    "item", "slot", "formula", "counter", "label", "arrangement", "region", "node", "edge",
    # geometry: 3D solid, plane figure, and their points / segments / planes / angles
    "solid", "figure", "point", "segment", "plane", "angle",
]
Operation = Literal[
    "create", "remove", "highlight", "merge", "split", "branch", "transform", "morph", "connect", "grow",
    "compare", "count", "fill_slots", "partition", "traverse", "emphasize_result", "focus", "unfocus",
    "enumerate", "measure", "flatten", "revolve",
]
Layout = Literal["center_focus", "horizontal_row", "split_view", "tree_layout", "graph_layout", "grid_layout", "space_3d"]
Camera = Literal[
    "wide_establishing", "focus_subject", "follow_transform", "split_view",
    # 3D cameras (space_3d layout)
    "three_quarter", "orbit", "top_view", "front_view",
]
SOLID_TYPES = ("solid", "figure", "point", "segment", "plane", "angle")


class VisualObjectSpec(IRModel):
    id: str = Field(description="snake_case id, unique in the scene")
    type: ObjectType
    value: str = Field(default="", description="label text / LaTeX (formula) / items separated by spaces (arrangement)")
    emphasis: Emphasis = "neutral"
    members: list[str] = Field(
        default_factory=list,
        description="edge/segment: [P, Q]; plane: polygon points; angle: [P, V, Q]; solid: vertex labels in "
        "standard order; point: [P, Q] midpoint or [A, B, C, ...] centre",
    )
    parent: str | None = Field(
        default=None,
        description="node in a tree: id of the parent node; formula in a 3D scene: id of the segment / angle / "
        "section plane / flattened section / solid the formula is read from (it lights up in the same colour)",
    )
    params: list[str] = Field(default_factory=list, description='solid dimensions ["a=4"], point division ["t=1/3"]')


class VisualActionSpec(IRModel):
    operation: Operation
    targets: list[str] = Field(default_factory=list, description="object ids the operation acts on")
    results: list[str] = Field(
        default_factory=list, description="ids of NEW objects the operation produces (merge block, split cases, transformed formula)"
    )
    values: list[str] = Field(
        default_factory=list,
        description="values for the results (block label, case arrangements 'A B', new LaTeX, slot choice counts)",
    )
    emphasis: Emphasis | None = None


class VisualBeat(IRModel):
    id: str = Field(description="EQUAL to the narration segment's visual_event id")
    purpose: str = Field(description="what this beat makes the learner see, e.g. 'show_second_order'")
    narration_segment: str | None = None
    actions: list[VisualActionSpec]
    layout: Layout | None = Field(default=None, description="layout change for this beat (e.g. split_view for cases)")
    camera: Camera | None = Field(default=None, description="camera move at the start of this beat (use sparingly)")
    duration: float = Field(default=3.0, description="seconds; the narration segment's duration")


class VisualPlan(IRModel):
    scene_id: str
    template: str = Field(description="primary template id from the visual capabilities")
    secondary_templates: list[str] = Field(default_factory=list, description="at most 2 extra template ids")
    layout: Layout
    camera: Camera = "wide_establishing"
    objects: list[VisualObjectSpec]
    beats: list[VisualBeat]

    @model_validator(mode="before")
    @classmethod
    def _legacy_events(cls, data):
        """Plans stored before the visual library used free-text `events`; read them as action-less beats
        (they fail visual validation, so such scenes keep using the Gemini-written Manim code)."""
        if isinstance(data, dict) and "events" in data and "beats" not in data:
            data = {
                "scene_id": data.get("scene_id", ""),
                "template": "spotlight",
                "layout": "center_focus",
                "objects": [],
                "beats": [{"id": e.get("id", f"e{i}"), "purpose": e.get("description", ""), "actions": []} for i, e in enumerate(data["events"])],
            }
        return data

    @property
    def events(self) -> list[VisualBeat]:  # name used by the voiceover/marker checks
        return self.beats

    @property
    def template_ids(self) -> list[str]:
        return [self.template, *self.secondary_templates]


class AnimationStep(BaseModel):
    """One deterministic motion primitive executed by the tutorly_visuals runtime."""

    beat: str
    primitive: str
    targets: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    run_time: float = 0.8


class AnimationPlan(BaseModel):
    scene_id: str
    class_name: str
    title: str
    layout: str
    steps: list[AnimationStep]
    camera: str = "wide_establishing"
    dimension: str = "2d"
    objects: list[dict] = Field(default_factory=list)
    beat_durations: dict[str, float] = Field(default_factory=dict)
    beat_layouts: dict[str, str] = Field(default_factory=dict)
    captions: dict[str, str] = Field(default_factory=dict)


class ManimCode(IRModel):
    scene_id: str
    class_name: str = Field(description="Name of the single Scene subclass")
    code: str = Field(description="Complete Python source: 'from manim import *' plus one Scene subclass")
    events_covered: list[str] = Field(default_factory=list)
    notes: str = ""


class ChatAnswer(IRModel):
    """The tutor's text answer to a question about a scene (a video is generated only on request)."""

    answer: str = Field(description="the answer, in the learner's language; short paragraphs, plain text, formulas in simple text")
    suggest_video: bool = Field(
        default=False,
        description="true when a short animated explanation would clearly help (spatial, step-by-step or visual idea)",
    )
    video_reason: str = Field(default="", description="one short sentence: what the video would show")


class FollowupPlan(IRModel):
    """The Ask Tutor's answer to a learner question: a NEW short scene that answers it as a video."""

    answer_summary: str = Field(description="1-2 sentence summary of the answer, in the learner's language")
    concepts_used: list[str] = Field(default_factory=list)
    stays_in_scope: bool = True
    scene: SceneIR = Field(description="The new follow-up scene; scene_id must equal required_scene_id")
    new_ledger_entries: list[LedgerEntry] = Field(
        default_factory=list,
        description="Symbols this follow-up introduces that are NOT already in the concept ledger",
    )


class VoiceoverSegment(BaseModel):
    id: str
    visual_event: str
    path: str
    duration: float


class Voiceover(BaseModel):
    model: str
    voice: str
    segments: list[VoiceoverSegment]

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.segments)
