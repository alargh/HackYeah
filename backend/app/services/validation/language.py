"""Text hygiene for everything shown or spoken: detects corrupted words the LLM sometimes emits
(e.g. "Sp3jrzmy", "Wysokoőć", "krawędŹ") and turns leftover maths symbols into speakable words."""

from __future__ import annotations

import re
import unicodedata

ALPHABETS: dict[str, str] = {
    "pl": "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "de": "äöüßÄÖÜ",
    "fr": "àâæçéèêëîïôœùûüÿÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ",
    "es": "áéíñóúüÁÉÍÑÓÚÜ",
    "en": "",
}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_DIGIT_INSIDE = re.compile(r"[^\W\d_]\d+[^\W\d_]", re.UNICODE)  # letter-digit-letter: "Sp3jrzmy", "dw3ch"


def garbled_words(text: str, language: str) -> list[str]:
    """Words that look corrupted for the given language (returns at most 8, deduplicated)."""
    allowed = set(ALPHABETS.get(language, ""))
    bad: list[str] = []
    for word in _WORD.findall(text):
        if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
            if _DIGIT_INSIDE.search(word) and not re.fullmatch(r"[A-Za-z]{1,2}\d+[A-Za-z]?", word):
                bad.append(word)  # "x2", "A1", "a2b" style symbols are fine
                continue
        letters = [c for c in word if c.isalpha()]
        foreign = [c for c in letters if not c.isascii() and c not in allowed and unicodedata.category(c).startswith("L")]
        if foreign and language in ALPHABETS:
            bad.append(word)
            continue
        # an uppercase diacritic in the middle of a lowercase word: "krawędŹ", "leŹąca"
        if len(word) > 2 and word[1:].lower() != word[1:] and word[1:] != word[1:].upper():
            mid = word[1:]
            if any(c.isupper() and not c.isascii() for c in mid):
                bad.append(word)
    out: list[str] = []
    for w in bad:
        if w not in out:
            out.append(w)
    return out[:8]


def check_texts(texts: dict[str, str], language: str, target: str, scope=None, curriculum: bool = False):
    """ValidationResult (validator 'language') for a set of {location: text}: corrupted words and, with
    `curriculum`, terms from outside the high-school curriculum."""
    from app.schemas.validation import ValidationIssue, ValidationResult

    issues = []
    if curriculum:
        from app.services.validation.curriculum import check_curriculum

        issues.extend(check_curriculum(texts, scope, target).issues)
    for loc, text in texts.items():
        words = garbled_words(text or "", language)
        if words:
            issues.append(
                ValidationIssue(
                    code="GARBLED_TEXT",
                    message=f"corrupted words {words}: rewrite them with correct {language} spelling and diacritics "
                    "(no digits or foreign letters inside words)",
                    location=loc,
                )
            )
    return ValidationResult.build("language", target, issues)


# ---------------------------------------------------------------------------- speakable text for TTS

_SPOKEN = {
    "pl": [
        (r"√\s*\(([^)]+)\)", r" pierwiastek z \1 "), (r"√\s*", " pierwiastek z "), (r"π", " pi "),
        (r"²", " do kwadratu"), (r"³", " do sześcianu"), (r"\s*[·×]\s*", " razy "), (r"\s*≈\s*", " w przybliżeniu "),
        (r"\s*≠\s*", " jest różne od "), (r"\s*≤\s*", " jest mniejsze lub równe "), (r"\s*≥\s*", " jest większe lub równe "),
        (r"(?<=\d)\s*=\s*(?=\d)", " równa się "), (r"\s*°", " stopni"), (r"\s*%", " procent"),
    ],
    "en": [
        (r"√\s*\(([^)]+)\)", r" the square root of \1 "), (r"√\s*", " the square root of "), (r"π", " pi "),
        (r"²", " squared"), (r"³", " cubed"), (r"\s*[·×]\s*", " times "), (r"\s*≈\s*", " approximately "),
        (r"\s*≠\s*", " is not equal to "), (r"\s*≤\s*", " is at most "), (r"\s*≥\s*", " is at least "),
        (r"(?<=\d)\s*=\s*(?=\d)", " equals "), (r"\s*°", " degrees"), (r"\s*%", " percent"),
    ],
}


LETTER_OPEN, LETTER_CLOSE = "\u27ea", "\u27eb"  # marks a symbol to be spelled: «H» -> the letter H
NUM_OPEN, NUM_CLOSE = "\u27e6", "\u27e7"  # marks a cardinal number: Polish TTS reads "wynosi 6." as "szóstą"

# Polish names of letters, for engines without SSML (and to undo phonetic spellings written by the LLM)
PL_LETTERS = {
    "a": "a", "b": "be", "c": "ce", "d": "de", "e": "e", "f": "ef", "g": "gie", "h": "ha", "i": "i", "j": "jot",
    "k": "ka", "l": "el", "m": "em", "n": "en", "o": "o", "p": "pe", "q": "ku", "r": "er", "s": "es", "t": "te",
    "u": "u", "v": "fau", "w": "wu", "x": "iks", "y": "igrek", "z": "zet",
}
# One-letter Polish words: lowercase they are words, never variables.
_PL_ONE_LETTER_WORDS = set("aiouwz")
# Phonetic letter names the LLM sometimes writes for variables; "ha" is read as "hektary" by TTS engines.
_PL_SPELLED = {"ha": "H", "fau": "V"}


def _mark_letters_pl(s: str) -> str:
    def single(m: re.Match) -> str:
        ch, start = m.group(0), m.start()
        before = s[:start].rstrip()
        sentence_start = not before or before[-1] in ".!?:"
        if ch.islower() and ch in _PL_ONE_LETTER_WORDS:
            return ch
        if ch.isupper() and ch.lower() in _PL_ONE_LETTER_WORDS and sentence_start:
            return ch
        return f"{LETTER_OPEN}{ch}{LETTER_CLOSE}"

    s = re.sub(r"(?<![\w'’])[A-Za-z](?![\w'’])", single, s)
    for word, letter in _PL_SPELLED.items():
        s = re.sub(rf"(?<![\w]){word}(?![\w])", f"{LETTER_OPEN}{letter}{LETTER_CLOSE}", s, flags=re.IGNORECASE)
    return s


def letters_as_words(text: str, language: str) -> str:
    """For TTS engines without SSML: «H» -> "ha", number marks removed."""
    names = PL_LETTERS if language == "pl" else {}
    text = re.sub(f"{NUM_OPEN}([^{NUM_CLOSE}]*){NUM_CLOSE}", r"\1", text)
    return re.sub(f"{LETTER_OPEN}(.){LETTER_CLOSE}", lambda m: names.get(m.group(1).lower(), m.group(1)), text)


def spoken(text: str, language: str) -> str:
    """Leftover symbols -> words, LaTeX remnants removed, spacing normalised (captions keep the original).
    In Polish, single-letter variables are marked «X» so the voice spells them ("ha", not "hektary")."""
    s = re.sub(r"\\[a-zA-Z]+", " ", text)  # stray LaTeX commands
    s = s.replace("{", "").replace("}", "").replace("$", "")
    for pattern, repl in _SPOKEN.get(language, _SPOKEN["en"]):
        s = re.sub(pattern, repl, s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if language == "pl":
        s = re.sub(r"(?<!\d)(?<!\d,)(\d+)\s*/\s*(\d+)(?!\d|,\d)", r"\1 przez \2", s)  # "3/2" is read as a date
        s = re.sub(r"(?<!\d)(?<!\d,)(\d+)(?=\.(\s|$))", rf"{NUM_OPEN}\1{NUM_CLOSE}", s)  # "6." would be ordinal
        s = _mark_letters_pl(s)
    return s
