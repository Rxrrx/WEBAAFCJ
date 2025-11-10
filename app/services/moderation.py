import re
import unicodedata
from typing import Optional, Tuple


_LEETSPEAK = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in normalized if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", without_marks)


def _normalize(text: str) -> str:
    lowered = text.lower().translate(_LEETSPEAK)
    lowered = _strip_accents(lowered)
    # collapse repeated separators and spaces
    lowered = re.sub(r"[\s\W_]+", " ", lowered).strip()
    return lowered


# Minimal list focused on Spanish profanities and slurs.
# Intentionally small to avoid over-blocking; can be expanded if needed.
_BANNED_TERMS = {
    # Common insults/offensive words (Spanish)
    "puta",
    "puto",
    "mierda",
    "imbecil",
    "imbécil",
    "estupido",
    "estúpido",
    "pendejo",
    "cabron",
    "cabrón",
    "conchetumare",
    "qlo",
    "qliao",
    "ctm",
    "maricon",
    "maricón",
    "culiao",
    "culiado",
    "weon",
    "weón",
    "huevon",
    "huevón",
    "coño",
    "coño",
    "cagar",
    "cagado",
    "cagada",
}


def moderate_text(text: str) -> Tuple[bool, Optional[str]]:
    """
    Returns (ok, offending_term). ok=False when content should be rejected.
    Applies simple normalization to catch common obfuscations.
    """
    if not text:
        return False, None

    normalized = _normalize(text)

    # Check word by word against banned list
    tokens = normalized.split()
    for token in tokens:
        if token in _BANNED_TERMS:
            return False, token

    # Also detect repeated-letter obfuscations like p.u.t.a
    squashed = normalized.replace(" ", "")
    for term in _BANNED_TERMS:
        pattern = ".*".join(map(re.escape, term))
        if re.search(pattern, squashed):
            return False, term

    return True, None


__all__ = ["moderate_text"]

