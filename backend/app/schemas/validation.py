"""Validation results and lesson status."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LessonStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    READY = "READY"  # generated + validated, not rendered yet
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RenderStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    location: str | None = None


class ValidationResult(BaseModel):
    validator: str
    target: str
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def feedback(self) -> str:
        """Human/LLM-readable summary used in repair prompts."""
        return "\n".join(f"- [{i.severity}] {i.code}: {i.message}" for i in self.issues) or "no issues"

    @classmethod
    def build(cls, validator: str, target: str, issues: list[ValidationIssue], **details: Any) -> "ValidationResult":
        return cls(
            validator=validator,
            target=target,
            passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            details=details,
        )
