"""Concept name normalisation, synonyms and a small bilingual lexicon (EN/PL).

Structured tags (`concepts_used`, `method`, ...) are compared after normalisation.
The lexicon is used to detect concepts mentioned in prose that were not tagged.
"""

from __future__ import annotations

import re
import unicodedata

SYNONYMS: dict[str, str] = {
    # multiplication rule
    "rule_of_product": "multiplication_rule",
    "product_rule": "multiplication_rule",
    "multiplication_principle": "multiplication_rule",
    "fundamental_counting_principle": "multiplication_rule",
    "counting_principle": "multiplication_rule",
    "regula_mnozenia": "multiplication_rule",
    # addition rule
    "rule_of_sum": "addition_rule",
    "sum_rule": "addition_rule",
    "addition_principle": "addition_rule",
    # inclusion-exclusion
    "inclusion_exclusion_principle": "inclusion_exclusion",
    "principle_of_inclusion_exclusion": "inclusion_exclusion",
    "pie": "inclusion_exclusion",
    "zasada_wlaczen_i_wylaczen": "inclusion_exclusion",
    # complement counting
    "complementary_counting": "complement_counting",
    "complement_principle": "complement_counting",
    "counting_the_complement": "complement_counting",
    "complement": "complement_counting",
    # block / gluing
    "gluing_method": "block_method",
    "glue_method": "block_method",
    "treating_as_a_block": "block_method",
    "bundling": "block_method",
    "block": "block_method",
    "superelement": "block_method",
    # permutations / factorials
    "permutation_without_repetition": "permutation",
    "arrangement": "permutation",
    "linear_arrangement": "permutation",
    "factorial_notation": "factorial",
    "permutacja": "permutation",
    "silnia": "factorial",
    # combinations
    "binomial_coefficient": "combination",
    "kombinacja": "combination",
    "n_choose_k": "combination",
}

# Always permitted, even in a restricted scope: elementary arithmetic and plain counting.
ELEMENTARY: frozenset[str] = frozenset(
    {
        "addition",
        "subtraction",
        "multiplication",
        "division",
        "arithmetic",
        "counting",
        "direct_counting",
        "equality",
        "substitution",
        "natural_number",
        "integer",
        "set",
        "listing",
        "enumeration",
    }
)

# Phrases (lower-case, accent-folded) that reveal use of a concept in prose.
LEXICON: dict[str, tuple[str, ...]] = {
    "inclusion_exclusion": (
        "inclusion-exclusion",
        "inclusion exclusion",
        "wlaczen i wylaczen",
        "wlaczania i wylaczania",
    ),
    "combination": ("binomial coefficient", "\\binom", "symbol newtona", "kombinacj"),
    "generating_function": ("generating function", "funkcja tworzaca", "funkcji tworzacej"),
    "recursion": ("recurrence relation", "rekurencj"),
    "probability": ("probability", "prawdopodobienstw"),
    "derivative": ("derivative", "pochodna", "pochodnej"),
    "integral": ("integral", "calka", "calki"),
    "variation": ("wariacj",),
    "pigeonhole_principle": ("pigeonhole", "szufladkow"),
    "mathematical_induction": ("induction", "indukcj"),
    "burnside_lemma": ("burnside",),
}


def fold(text: str) -> str:
    """Lower-case and strip accents (ł -> l etc.) for robust matching."""
    text = text.replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def normalize_concept(name: str) -> str:
    s = fold(name).strip()
    s = re.sub(r"[\s\-–—/]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if s in SYNONYMS:
        return SYNONYMS[s]
    # crude singularisation: permutations -> permutation, factorials -> factorial
    if len(s) > 4 and s.endswith("s") and not s.endswith("ss"):
        singular = s[:-1]
        return SYNONYMS.get(singular, singular)
    return s


def normalize_all(names: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    return {normalize_concept(n) for n in names if n and n.strip()}


def mentioned_concepts(text: str, concepts: set[str]) -> set[str]:
    """Which of `concepts` are mentioned in `text` (using lexicon phrases and the concept's own words)."""
    folded = fold(text)
    found: set[str] = set()
    for concept in concepts:
        phrases = set(LEXICON.get(concept, ()))
        words = concept.replace("_", " ")
        if len(words) >= 6:
            phrases.add(words)
            phrases.add(concept.replace("_", "-"))
        if any(p in folded for p in phrases):
            found.add(concept)
    return found
