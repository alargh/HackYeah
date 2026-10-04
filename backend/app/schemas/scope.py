"""ScopeIR: the learner's allowed knowledge, compiled into structured form."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.problem import IRModel


class MethodJustification(IRModel):
    method: str = Field(description="snake_case method name")
    built_from: list[str] = Field(description="Allowed concepts this method is composed of")
    justification: str


class ScopeWarning(IRModel):
    scope_sufficient: bool
    missing_concepts: list[str] = Field(default_factory=list)
    explanation: str = ""


class ScopeIR(IRModel):
    user_scope_text: str | None = None
    mode: Literal["open", "restricted"] = Field(
        description="'open' when the user gave no scope; 'restricted' when they limited the allowed knowledge"
    )
    allowed_concepts: list[str] = Field(default_factory=list)
    forbidden_concepts: list[str] = Field(default_factory=list)
    allowed_methods: list[str] = Field(default_factory=list)
    forbidden_methods: list[str] = Field(default_factory=list)
    method_justifications: list[MethodJustification] = Field(default_factory=list)
    required_concepts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    difficulty_level: str | None = None
    scope_sufficient: bool = True
    missing_concepts: list[str] = Field(default_factory=list)
    explanation: str = ""

    @property
    def warning(self) -> ScopeWarning | None:
        if self.scope_sufficient:
            return None
        return ScopeWarning(
            scope_sufficient=False,
            missing_concepts=self.missing_concepts,
            explanation=self.explanation,
        )
