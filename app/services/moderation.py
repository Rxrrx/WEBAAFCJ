import re
import unicodedata
from typing import Optional, Tuple

from fastapi import HTTPException

from app.core.config import get_settings
from .gemini import get_gemini_reply


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


def _regex_for_term(term: str) -> re.Pattern:
    # Allow very small obfuscations like p.u.t.a or p u t a
    # up to 2 non-letters between letters, and anchor as a word
    pieces = [re.escape(ch) for ch in term]
    pattern = r"\b" + r"[\W_]{0,2}".join(pieces) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


_TERM_PATTERNS = {term: _regex_for_term(term) for term in _BANNED_TERMS}


def _basic_screen(text: str) -> Tuple[bool, Optional[str]]:
    normalized = _normalize(text)

    # Fast path: token match
    for token in normalized.split():
        if token in _BANNED_TERMS:
            return False, token

    # Obfuscations with minimal separators
    for term, pattern in _TERM_PATTERNS.items():
        if pattern.search(normalized):
            return False, term

    return True, None


def _ai_screen(text: str) -> Tuple[Optional[bool], Optional[str]]:
    """Try AI moderation via Gemini. Returns (decision, reason) where
    decision is True allow, False block, or None when unavailable/error.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return None, None

    system = (
        "Eres un moderador para una iglesia cristiana evangélica. "
        "Evalúa si el siguiente texto contiene insultos, groserías u ofensas. "
        "Responde solo en una línea con 'ALLOW' si se puede publicar sin problema, "
        "o 'BLOCK: <motivo breve>' si debe rechazarse. No hagas otras aclaraciones."
    )
    try:
        reply = get_gemini_reply(system, text, history=())
    except HTTPException:
        return None, None
    except Exception:
        return None, None

    normalized = reply.strip().upper()
    if normalized.startswith("ALLOW"):
        return True, None
    if normalized.startswith("BLOCK") or "RECHAZ" in normalized or "BLOQUE" in normalized:
        # Extract brief reason if present
        reason = reply.split(":", 1)[1].strip() if ":" in reply else None
        return False, reason or None
    # If unclear, don't block on AI
    return None, None


def moderate_text(text: str) -> Tuple[bool, Optional[str]]:
    """Returns (ok, reason_or_term). Prefers AI when available, and uses a
    safer basic screen to avoid falsos positivos como el mensaje de bienvenida.
    """
    if not text:
        return False, None

    ai_decision, ai_reason = _ai_screen(text)
    if ai_decision is True:
        return True, None
    if ai_decision is False:
        return False, ai_reason or "Contenido no permitido"

    # Fallback or complement with basic screen
    return _basic_screen(text)


__all__ = ["moderate_text"]
