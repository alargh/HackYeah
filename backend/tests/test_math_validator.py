import pytest
import sympy

from app.schemas import EnumerationSpec, GraphSpec, ProblemIR, SolutionIR
from app.services.validation import MathValidator
from app.services.validation import expressions as ex
from app.services.validation.independent import count_arrangements, evaluate_graph
from tests.fixtures import PROBLEM_IR, solution_ir


@pytest.mark.parametrize(
    "text,value",
    [
        ("5! - 2*4!", 72),
        ("factorial(5) - 2*factorial(4)", 72),
        ("5! − 2·4!", 72),
        ("2 * 4! = 48", 48),
        ("binomial(5,2)", 10),
        ("C(5,2) * P(3,2)", 60),
        ("2^3", 8),
    ],
)
def test_expression_evaluation(text, value):
    assert ex.evaluate(text) == value


def test_unknown_names_are_symbols_so_wrong_references_are_caught():
    # A typo'd step name stays symbolic and can never equal a claimed number.
    value = ex.evaluate(
        "totl - forbidden",
        {"total": sympy.Integer(120), "forbidden": sympy.Integer(48)},
    )
    assert value.free_symbols and not ex.equal(value, sympy.Integer(72))


def test_expression_with_step_names():
    assert (
        ex.evaluate(
            "total - forbidden",
            {"total": sympy.Integer(120), "forbidden": sympy.Integer(48)},
        )
        == 72
    )


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('id')",
        "().__class__",
        "open('x')",
        "lambda: 1",
        "x.y",
        "factorial(100000)",
        "100000!",
    ],
)
def test_expression_parser_rejects_unsafe_or_unknown(text):
    with pytest.raises(ex.ExpressionError):
        ex.evaluate(text)


def test_permutation_example_brute_force_is_72():
    spec = EnumerationSpec.model_validate(PROBLEM_IR["enumeration_spec"])
    assert count_arrangements(spec) == 72


def test_enumeration_other_constraints():
    spec = EnumerationSpec(
        items=list("ABC"),
        constraints=[{"type": "at_position", "items": ["A"], "position": 1}],
    )
    assert count_arrangements(spec) == 2
    spec = EnumerationSpec(
        items=list("ABCD"), constraints=[{"type": "adjacent", "items": ["A", "B"]}]
    )
    assert count_arrangements(spec) == 12


def test_valid_solution_passes_and_reports_72():
    result = MathValidator().validate(
        ProblemIR.model_validate(PROBLEM_IR), SolutionIR.model_validate(solution_ir())
    )
    assert result.passed, result.feedback()
    assert result.details["final_evaluated"] == "72"
    assert result.details["evaluated_steps"]["step_4"] == "48"
    assert result.details["independent_checks"][0] == {
        "method": "brute_force_enumeration",
        "value": "72",
        "matches": True,
    }


def test_wrong_claim_is_rejected():
    result = MathValidator().validate(
        ProblemIR.model_validate(PROBLEM_IR),
        SolutionIR.model_validate(solution_ir("70")),
    )
    assert not result.passed
    codes = {i.code for i in result.errors}
    assert {"STEP_MISMATCH", "FINAL_MISMATCH"} <= codes


def test_consistent_but_wrong_solution_caught_by_brute_force():
    # Model forgets the factor 2: arithmetic is self-consistent but the answer is wrong.
    sol = solution_ir("96")
    sol["steps"][2].update(expression="1", claimed_value="1")
    sol["steps"][3].update(claimed_value="24")
    sol["final_result"].update(expression="5! - 4!", value="96")
    sol["verification"]["checks"] = []
    result = MathValidator().validate(
        ProblemIR.model_validate(PROBLEM_IR), SolutionIR.model_validate(sol)
    )
    assert not result.passed
    assert any(i.code == "INDEPENDENT_MISMATCH" for i in result.errors)


def test_missing_step_reasoning_is_rejected():
    sol = solution_ir()
    sol["steps"][1]["why_valid"] = ""
    result = MathValidator().validate(
        ProblemIR.model_validate(PROBLEM_IR), SolutionIR.model_validate(sol)
    )
    assert "MISSING_REASONING" in {i.code for i in result.errors}


def test_unexplained_named_result_shortcut_is_rejected():
    sol = solution_ir()
    sol["steps"][1]["method"] = "named_theorem"
    sol["steps"][1]["explanation"] = "Z twierdzenia wynika ten wynik."
    sol["steps"][1]["why_valid"] = "Twierdzenie daje ten wynik."
    result = MathValidator().validate(
        ProblemIR.model_validate(PROBLEM_IR), SolutionIR.model_validate(sol)
    )
    assert "NAMED_THEOREM_SHORTCUT" in {i.code for i in result.errors}


def test_graph_spec_with_networkx():
    spec = GraphSpec(
        nodes=["a", "b", "c", "d"],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
            {"source": "a", "target": "d"},
        ],
        query="number_of_spanning_trees",
    )
    assert evaluate_graph(spec) == "4"
    spec2 = spec.model_copy(
        update={"query": "shortest_path_length", "source": "a", "target": "c"}
    )
    assert evaluate_graph(spec2) == "2"
