"""Audience level: Polish high school (liceum), extended matura (matura rozszerzona).

The learner is assumed to know only the school curriculum. Terms from outside it (university mathematics,
jargon such as "antypodyczne") must not appear unless the learner put them in their scope; the generator
is told to use a school-level word or to explain the idea in everyday language instead.
"""

from __future__ import annotations

import re

from app.schemas.validation import ValidationIssue, ValidationResult

AUDIENCE = (
    "Polish high school (liceum), extended matura level (matura rozszerzona, podstawa programowa). "
    "Use only notions taught at school; never university terms or jargon."
)

# term (regex, matched case-insensitively at a word start) -> school-level alternative to suggest
OUT_OF_CURRICULUM: dict[str, str] = {
    r"antypod": "punkty leżące na końcach tej samej średnicy (punkty symetryczne względem środka kuli)",
    r"antipod": "points at the two ends of one diameter",
    r"zależn\w* liniow|niezależn\w* liniow|linear(ly)? (in)?dependen": "opisz to geometrycznie (np. trzy wektory leżą w jednej płaszczyźnie)",
    r"iloczyn\w* wektorow|cross product": "opisz kierunek prostopadły słowami albo użyj trygonometrii",
    r"iloczyn\w* skalarn|dot product|scalar product": "użyj twierdzenia cosinusów albo długości i kątów",
    r"wyznacznik|determinant": "rozwiąż układ równań metodą podstawiania",
    r"macierz(y|ą|e|ach|ami|om)?(?!\w)|matrix|matrices": "zapisz układ równań",
    r"jakobian|jacobian": "rachunek bez zmiany zmiennych",
    r"całk(a|i|ę|ą|om|ami|ach)(?!\w)|całkowan|integral": "pole / objętość z wzorów szkolnych albo granica sum",
    r"kąt\w* bryłow|solid angle|steradian": "porównaj pola na powierzchni kuli",
    r"miar\w* lebesgue|lebesgue": "pole albo długość",
    r"rozmaitoś|manifold": "powierzchnia",
    r"homeomorf|izomorf|homomorf|isomorph|homeomorph": "opisz kształt słowami",
    r"geodezyjn|geodesic": "najkrótsza droga po powierzchni",
    r"sympleks|simplex": "trójkąt / czworościan",
    r"otoczk\w* wypuk|convex hull": "najmniejszy wielokąt / wielościan zawierający punkty",
    r"hiperpłaszczyzn|hyperplane": "płaszczyzna",
    r"rzut\w* stereograficzn|stereographic": "opisz rzut słowami",
    r"współrzędn\w* sferyczn|współrzędn\w* biegunow|spherical coordinates|polar coordinates": "współrzędne kartezjańskie albo kąty w trójkącie",
    r"funkcj\w* tworząc|generating function": "rozumowanie krok po kroku na małych przypadkach",
    r"wartoś\w* oczekiwan|expected value|expectation": "średnia ważona wyników",
    r"wariancj|variance": "miara rozrzutu wyjaśniona słowami",
    r"rozkład\w* jednostajn\w* na sferze|uniform distribution on the sphere": "każde miejsce na powierzchni jest tak samo prawdopodobne",
    r"przestrzeń\w* metryczn|metric space": "odległość",
    r"liczb\w* zespolon|complex number": "liczby rzeczywiste",
    r"indukcj\w* pozaskończon|transfinite": "indukcja matematyczna",
}
_COMPILED = [(re.compile(rf"(?<!\w){k}", re.IGNORECASE), k, v) for k, v in OUT_OF_CURRICULUM.items()]


def out_of_curriculum(text: str) -> list[tuple[str, str]]:
    """[(matched word, school-level alternative)] for terms outside the school curriculum."""
    found: list[tuple[str, str]] = []
    for rx, _, alt in _COMPILED:
        m = rx.search(text or "")
        if m:
            end = m.end()
            while end < len(text) and text[end].isalpha():
                end += 1
            found.append((text[m.start() : end], alt))
    return found


def allowed_by_scope(scope, word: str) -> bool:
    """The learner may opt in (e.g. scope "we know vectors and the dot product")."""
    if scope is None:
        return False
    own = " ".join([scope.user_scope_text or "", *scope.allowed_concepts, *scope.allowed_methods, *scope.required_concepts]).lower()
    stem = word.lower()[:6]
    return bool(own) and stem in own.replace("_", " ")


def check_curriculum(texts: dict[str, str], scope, target: str) -> ValidationResult:
    issues = []
    for loc, text in texts.items():
        for word, alt in out_of_curriculum(text):
            if allowed_by_scope(scope, word):
                continue
            issues.append(
                ValidationIssue(
                    code="OUT_OF_CURRICULUM",
                    message=(
                        f"'{word}' is not a high-school (matura rozszerzona) term; the learner does not know it. "
                        f"Do not use it: {alt}"
                    ),
                    location=loc,
                )
            )
    return ValidationResult.build("curriculum", target, issues)
