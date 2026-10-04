"""Math validation beyond counting: complex numbers, analysis functions, symbolic results (e.g. the DFT)."""

import pytest
import sympy

from app.schemas import ProblemIR, SolutionIR
from app.services.validation import MathValidator
from app.services.validation import expressions as ex
from tests.fixtures import PROBLEM_IR

DFT = "Sum(x(n)*exp(-2*I*pi*k*n/N), (n, 0, N-1))"


@pytest.mark.parametrize(
    "text,value",
    [
        ("1 * E**(-2*I*pi*1*0/2) + 1 * E**(-2*I*pi*1*1/2)", 0),  # DFT of [1, 1], k = 1
        ("1 * E**(-2*I*pi*0*0/2) + 1 * E**(-2*I*pi*0*1/2)", 2),  # k = 0
        ("exp(I*pi)", -1),
        ("cos(pi/3) + I*sin(0)", sympy.Rational(1, 2)),
        ("Sum(k, (k, 1, 10))", 55),
        ("log(E**3)", 3),
    ],
)
def test_complex_and_analytic_expressions(text, value):
    assert ex.equal(ex.evaluate(text), sympy.sympify(value))


def test_symbolic_expressions_are_compared_symbolically():
    a = ex.evaluate(DFT)
    assert a.free_symbols and ex.equal(a, ex.evaluate(DFT))
    assert ex.equal(ex.evaluate("(a + b)**2"), ex.evaluate("a**2 + 2*a*b + b**2"))
    assert not ex.equal(ex.evaluate("(a + b)**2"), ex.evaluate("a**2 + b**2"))
    with pytest.raises(ex.ExpressionError):
        ex.evaluate("N + 1", numeric=True)


@pytest.mark.parametrize(
    "text",
    ["lambda x: x", "x if y else z", "__import__", "_private", "Symbol + 1", "a_really_long_identifier_name_that_goes_on"],
)
def test_unsafe_identifiers_rejected(text):
    with pytest.raises(ex.ExpressionError):
        ex.parse_safe(text)


def test_sympy_namespace_is_not_reachable():
    # In SymPy's full namespace `preview` runs LaTeX and `plot` opens a window; here they are inert functions.
    expr = ex.parse_safe("preview(x) + plot(x) + open(x)")
    funcs = expr.atoms(sympy.Function)
    assert len(funcs) == 3 and all(f.func.__class__.__name__ == "UndefinedFunction" for f in funcs)


def _dft_problem(answer_type: str) -> ProblemIR:
    return ProblemIR.model_validate({
        **PROBLEM_IR,
        "original_text": "Explain the discrete Fourier transform",
        "domain": "analysis",
        "subdomain": "fourier_analysis",
        "problem_type": "concept_explanation",
        "enumeration_spec": None,
        "constraints": [],
        "goal": {"kind": "other", "description": "explain the DFT", "target_quantity": "DFT", "answer_type": answer_type},
    })


def _dft_solution(final_expr: str, final_value: str) -> SolutionIR:
    return SolutionIR.model_validate({
        "selected_method": "definition",
        "steps": [
            {"id": "s1", "goal": "definition", "method": "definition", "expression": DFT, "explanation": "X_k", "why_valid": "it follows from the previous step",
             "concepts_used": ["dft"]},
            {"id": "s2", "goal": "X_0 for [1,1]", "method": "substitution",
             "expression": "1*E**(-2*I*pi*0*0/2) + 1*E**(-2*I*pi*0*1/2)", "result_name": "x0", "claimed_value": "2",
             "explanation": "k=0", "why_valid": "it follows from the previous step", "concepts_used": ["dft"]},
            {"id": "s3", "goal": "X_1 for [1,1]", "method": "substitution",
             "expression": "1*E**(-2*I*pi*1*0/2) + 1*E**(-2*I*pi*1*1/2)", "result_name": "x1", "claimed_value": "0",
             "explanation": "k=1", "why_valid": "it follows from the previous step", "concepts_used": ["dft"]},
        ],
        "final_result": {"expression": final_expr, "value": final_value, "statement": "DFT"},
        "verification": {"strategy": "inverse DFT",
                         "checks": [{"description": "inverse", "expression": "(x0 + x1)/2", "expected_value": "1"}]},
    })


def test_conceptual_dft_lesson_is_verified():
    r = MathValidator().validate(_dft_problem("expression"), _dft_solution(DFT, DFT))
    assert r.passed, r.feedback()
    assert r.details["evaluated_steps"]["s2"] == "2" and r.details["evaluated_steps"]["s3"] == "0"


def test_wrong_complex_arithmetic_is_still_caught():
    sol = _dft_solution("x0", "2")
    sol.steps[2].claimed_value = "2"  # e^{-i pi} + 1 is 0, not 2
    r = MathValidator().validate(_dft_problem("expression"), sol)
    assert "STEP_MISMATCH" in {i.code for i in r.errors}


def test_numeric_goal_with_symbolic_answer_is_rejected():
    sol = _dft_solution("Sum(x(n), (n, 0, N-1))", "Sum(x(n), (n, 0, N-1))")
    r = MathValidator().validate(_dft_problem("integer"), sol)
    assert "FINAL_NOT_NUMERIC" in {i.code for i in r.errors}


def test_unparseable_step_no_longer_kills_the_lesson():
    sol = _dft_solution(DFT, DFT)
    sol.steps[0].expression = "sum over n of x"  # prose, not SymPy
    r = MathValidator().validate(_dft_problem("expression"), sol)
    assert r.passed and "EXPR_UNPARSEABLE" in {i.code for i in r.issues}
