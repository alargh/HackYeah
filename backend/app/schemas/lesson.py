"""LessonIR, SceneIR and the ConceptLedger."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.problem import IRModel


class LedgerEntry(IRModel):
    symbol: str = Field(description="Symbol or notation, e.g. 'A', '[AB]', '5!'")
    meaning: str = Field(description="What the symbol means in THIS lesson, e.g. 'person A'")
    kind: Literal["object", "quantity", "expression", "concept", "notation"] = "object"
    introduced_in: str = Field(description="scene_id of the scene that first introduces it")
    value: str | None = Field(default=None, description="Numeric value if it is a quantity, e.g. '120'")


class ConceptLedger(IRModel):
    entries: list[LedgerEntry] = Field(default_factory=list)

    def get(self, symbol: str) -> LedgerEntry | None:
        for entry in self.entries:
            if entry.symbol == symbol:
                return entry
        return None

    def symbols(self) -> set[str]:
        return {e.symbol for e in self.entries}


class VisualObject(IRModel):
    id: str = Field(description="snake_case id used by visual events")
    kind: Literal["text", "math", "shape", "group", "arrow", "highlight", "other"] = "text"
    content: str = Field(description="Text / LaTeX / short description of the object")
    ledger_symbol: str | None = Field(default=None, description="Ledger symbol it depicts, if any")


class MathematicalState(IRModel):
    known_facts: list[str] = Field(default_factory=list, description="Facts established by the end of the scene")
    current_expression: str | None = None
    current_value: str | None = None


class SceneIR(IRModel):
    scene_id: str = Field(description="e.g. scene_1")
    title: str
    learning_goal: str = Field(description="ONE primary pedagogical purpose")
    concepts: list[str] = Field(default_factory=list)
    solution_steps: list[str] = Field(default_factory=list, description="SolutionIR step ids covered")
    introduces: list[str] = Field(default_factory=list, description="Ledger symbols first introduced here")
    uses: list[str] = Field(default_factory=list, description="Ledger symbols used here")
    mathematical_state: MathematicalState = Field(default_factory=MathematicalState)
    visual_objects: list[VisualObject] = Field(default_factory=list)
    narration_plan: list[str] = Field(default_factory=list, description="Ordered talking points")
    visual_plan: list[str] = Field(default_factory=list, description="Ordered high-level visual beats")
    duration_estimate: float = Field(default=20.0, description="Seconds")
    dependencies: list[str] = Field(default_factory=list, description="scene_ids this scene builds on")


class LessonIR(IRModel):
    title: str
    summary: str = ""
    learning_objectives: list[str]
    prerequisites: list[str] = Field(default_factory=list)
    concept_ledger: ConceptLedger
    scenes: list[SceneIR]
