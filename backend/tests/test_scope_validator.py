from app.schemas import FollowupPlan, NarrationIR, SceneIR, ScopeIR, SolutionIR
from app.services.validation import ScopeValidator
from app.services.validation.concepts import normalize_concept
from tests.fixtures import LESSON_IR, SCOPE_IR_OPEN, SCOPE_IR_RESTRICTED, narration_for, solution_ir

V = ScopeValidator()
RESTRICTED = ScopeIR.model_validate(SCOPE_IR_RESTRICTED)


def test_normalization_synonyms():
    assert normalize_concept("Permutations") == "permutation"
    assert normalize_concept("Rule of product") == "multiplication_rule"
    assert normalize_concept("Inclusion–Exclusion principle") == "inclusion_exclusion"
    assert normalize_concept("silnia") == "factorial"


def test_in_scope_solution_passes():
    r = V.validate_solution(SolutionIR.model_validate(solution_ir()), RESTRICTED)
    assert r.passed, r.feedback()


def test_forbidden_method_tag_is_rejected():
    sol = solution_ir(method="inclusion_exclusion")
    r = V.validate_solution(SolutionIR.model_validate(sol), RESTRICTED)
    assert not r.passed
    assert any(i.code == "SCOPE_FORBIDDEN" for i in r.errors)


def test_not_allowed_concept_in_restricted_scope():
    r = V.validate_solution(SolutionIR.model_validate(solution_ir(extra_concepts=["binomial_coefficient"])), RESTRICTED)
    assert not r.passed
    assert any("binomial_coefficient" in i.message for i in r.errors)


def test_forbidden_concept_mentioned_in_prose():
    sol = solution_ir()
    sol["steps"][4]["explanation"] = "By the inclusion-exclusion principle we subtract."
    r = V.validate_solution(SolutionIR.model_validate(sol), RESTRICTED)
    assert any(i.code == "SCOPE_MENTION" for i in r.errors)


def test_polish_mention_detected_in_narration():
    n = NarrationIR.model_validate(narration_for("scene_2", "Użyjemy zasady włączeń i wyłączeń."))
    r = V.validate_narration(n, RESTRICTED)
    assert not r.passed


def test_open_scope_allows_everything_not_forbidden():
    open_scope = ScopeIR.model_validate(SCOPE_IR_OPEN)
    r = V.validate_solution(SolutionIR.model_validate(solution_ir(method="inclusion_exclusion")), open_scope)
    assert r.passed


def test_scene_scope_validation():
    scene = SceneIR.model_validate({**LESSON_IR["scenes"][0], "concepts": ["generating_function"]})
    assert not V.validate_scene(scene, RESTRICTED).passed
    assert V.validate_scene(SceneIR.model_validate(LESSON_IR["scenes"][0]), RESTRICTED).passed


def test_followup_summary_mentions_are_warnings_tags_are_errors():
    from tests.fixtures import followup_plan_for

    plan = followup_plan_for("")
    plan["answer_summary"] = "That would need inclusion-exclusion, which is outside your scope."
    r = V.validate_followup(FollowupPlan.model_validate(plan), RESTRICTED)
    assert r.passed and r.issues
    plan["concepts_used"] = ["inclusion_exclusion"]
    assert not V.validate_followup(FollowupPlan.model_validate(plan), RESTRICTED).passed
