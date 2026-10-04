"""SolutionIR: a structured, step-by-step solution that Python can verify."""

from __future__ import annotations

from pydantic import Field

from app.schemas.problem import IRModel


class CandidateMethod(IRModel):
    name: str = Field(description="snake_case method name")
    description: str
    concepts: list[str] = Field(default_factory=list)
    in_scope: bool
    reason: str = Field(description="Why this method is (not) selected / (not) in scope")


class ReasoningStep(IRModel):
    id: str = Field(description="e.g. step_1")
    goal: str
    method: str = Field(description="snake_case method used in this step")
    expression: str | None = Field(
        default=None,
        description=(
            "SymPy-parsable expression computed in this step, e.g. 'factorial(5)', '5!', "
            "'2*factorial(4)', 'binomial(5,2)', or using result_name of earlier steps, e.g. 'total - forbidden'"
        ),
    )
    result_name: str | None = Field(
        default=None, description="snake_case name for this step's value so later steps can reference it"
    )
    claimed_value: str | None = Field(default=None, description="The value the expression evaluates to, e.g. '120'")
    explanation: str
    why_valid: str = Field(default="", description="Why this step is mathematically justified")
    concepts_used: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list, description="Ids of earlier steps")


class FinalResult(IRModel):
    expression: str = Field(description="SymPy-parsable closed form of the answer, e.g. '5! - 2*4!'")
    value: str = Field(description="Exact value, e.g. '72'")
    statement: str = Field(description="Natural-language answer in the problem's language")


class VerificationCheck(IRModel):
    description: str
    expression: str = Field(description="SymPy-parsable expression")
    expected_value: str


class VerificationInfo(IRModel):
    strategy: str = Field(description="How the answer can be verified independently")
    checks: list[VerificationCheck] = Field(default_factory=list)


class SolutionIR(IRModel):
    selected_method: str
    selected_method_concepts: list[str] = Field(default_factory=list)
    candidate_methods: list[CandidateMethod] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    steps: list[ReasoningStep]
    final_result: FinalResult
    verification: VerificationInfo
    concepts_used: list[str] = Field(default_factory=list, description="Every concept used anywhere in the solution")
    scope_notes: str = Field(default="", description="How the solution respects the scope")
