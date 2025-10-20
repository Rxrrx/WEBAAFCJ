import logging
import re
from dataclasses import dataclass
from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

import requests
from fastapi import HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger("app.chatbot")


@dataclass
class GeminiCallResult:
    """Representa una respuesta individual de Gemini."""

    text: str
    finish_reason: Optional[str]


_CONTINUATION_PROMPT = (
    "Continúa exactamente donde quedaste, sin repetir nada anterior. "
    "Mantén el formato y completa la idea que estaba en curso."
)

_OPEN_LIST_RE = re.compile(r"(?:^|\n)(?:[-*\u2022]|(?:\d+\.))\s+[^\n]*$")


def _normalize_finish_reason(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value.upper() if value else None


def _looks_like_truncated_markdown(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False

    if stripped.count("**") % 2:
        return True
    if stripped.count("`") % 2:
        return True
    if _OPEN_LIST_RE.search(stripped):
        return True
    if stripped.endswith(("-", "\u2022", ":", ";", ",")):
        return True

    last_line = stripped.splitlines()[-1].strip()
    if last_line and last_line[-1] not in (
        ".",
        "!",
        "?",
        "\u2026",
        ")",
        "]",
        '"',
        "\u201d",
        "'",
    ):
        if len(last_line.split()) >= 4:
            return True

    return False


def _needs_continuation(text: str, finish_reason: Optional[str]) -> bool:
    normalized_reason = _normalize_finish_reason(finish_reason)
    if normalized_reason == "MAX_TOKENS":
        return True
    if normalized_reason and normalized_reason not in {"STOP", "MAX_TOKENS"}:
        return False

    if len(text.strip()) < 80:
        return False

    return _looks_like_truncated_markdown(text)


def _initial_contents(message: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "user",
            "parts": [{"text": message}],
        }
    ]


def _continuation_contents(
    original_message: str, accumulated_response: str
) -> List[Dict[str, Any]]:
    return [
        {
            "role": "user",
            "parts": [{"text": original_message}],
        },
        {
            "role": "model",
            "parts": [{"text": accumulated_response}],
        },
        {
            "role": "user",
            "parts": [{"text": _CONTINUATION_PROMPT}],
        },
    ]


class GeminiModelNotFound(Exception):
    """Se arroja cuando el modelo solicitado no está disponible."""


class GeminiAPIError(Exception):
    """Se arroja ante respuestas inválidas de la API de Gemini."""


_ALIAS_PAIRS: Iterable[Iterable[str]] = [
    ("gemini-1.5-pro-latest", "gemini-pro-latest"),
    ("gemini-1.5-pro-latest", "gemini-2.5-pro"),
    ("gemini-1.5-pro", "gemini-pro-latest"),
    ("gemini-1.5-pro", "gemini-2.5-pro"),
    ("gemini-pro", "gemini-pro-latest"),
    ("gemini-1.0-pro", "gemini-pro-latest"),
    ("gemini-1.0-pro-latest", "gemini-pro-latest"),
    ("gemini-1.5-flash-latest", "gemini-flash-latest"),
    ("gemini-1.5-flash-latest", "gemini-2.5-flash"),
    ("gemini-1.5-flash", "gemini-flash-latest"),
    ("gemini-1.5-flash", "gemini-2.5-flash"),
    ("gemini-flash-latest", "gemini-2.5-flash"),
    ("gemini-1.5-flash-8b", "gemini-2.0-flash-lite"),
    ("gemini-1.5-flash-8b", "gemini-2.5-flash-lite"),
    ("gemini-1.5-flash-8b-latest", "gemini-2.0-flash-lite"),
    ("gemini-1.5-flash-8b-latest", "gemini-2.5-flash-lite"),
    ("gemini-2.0-flash-lite", "gemini-2.5-flash-lite"),
]

MODEL_ALIAS_GRAPH: Dict[str, set] = defaultdict(set)
for alias_a, alias_b in _ALIAS_PAIRS:
    MODEL_ALIAS_GRAPH[alias_a].add(alias_b)
    MODEL_ALIAS_GRAPH[alias_b].add(alias_a)


DEFAULT_MODEL_ORDER: List[str] = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro",
    "gemini-pro-latest",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-8b-latest",
]


def _version_candidates(version_hint: Optional[str]) -> List[str]:
    """Genera el orden de versiones a probar."""
    ordered = []
    if version_hint:
        ordered.append(version_hint.strip())
    ordered.extend(["v1beta", "v1"])

    result: List[str] = []
    seen = set()
    for version in ordered:
        if version and version not in seen:
            seen.add(version)
            result.append(version)
    return result


def _expand_aliases(name: Optional[str]) -> List[str]:
    """Devuelve el nombre y sus alias conocidos, preservando el orden."""
    if not name:
        return []

    queue: List[str] = [name]
    seen = set()
    ordered: List[str] = []

    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        for alias in MODEL_ALIAS_GRAPH.get(current, ()):
            if alias not in seen:
                queue.append(alias)
    return ordered


def _auth_headers(api_key: str, *, json: bool = False) -> Dict[str, str]:
    headers = {"x-goog-api-key": api_key}
    if json:
        headers["Content-Type"] = "application/json"
    return headers


@lru_cache(maxsize=8)
def _available_models(
    api_key: str, base_endpoint: str, version_hint: Optional[str]
) -> Dict[str, str]:
    """Lista modelos disponibles y mapea modelo -> versión a utilizar."""
    available: Dict[str, str] = {}
    for version in _version_candidates(version_hint):
        url = f"{base_endpoint}/{version}/models"
        try:
            response = requests.get(
                url, headers=_auth_headers(api_key), timeout=10
            )
        except requests.RequestException as exc:  # pragma: no cover (red)
            logger.warning(
                "No se pudo listar modelos de Gemini para la versión %s: %s",
                version,
                exc,
            )
            continue

        if not response.ok:
            logger.warning(
                "ListModels %s respondió %s: %s",
                version,
                response.status_code,
                response.text,
            )
            continue

        data = response.json()
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = item.get("name")
            if not name:
                continue
            short_name = name.split("/", 1)[1] if "/" in name else name
            available.setdefault(short_name, version)

    return available


def _build_candidate_list(
    preferred: Optional[str],
    default_model: Optional[str],
    available: Dict[str, str],
) -> List[str]:
    """Ordena modelos a probar respetando disponibilidad y alias."""
    available_names = set(available.keys())
    ordered: List[str] = []
    seen = set()

    def add_with_aliases(name: Optional[str]) -> None:
        if not name:
            return
        for candidate in _expand_aliases(name):
            if available_names and candidate not in available_names:
                continue
            if candidate in seen:
                continue
            ordered.append(candidate)
            seen.add(candidate)

    for source in (preferred, default_model):
        add_with_aliases(source)

    for fallback in DEFAULT_MODEL_ORDER:
        add_with_aliases(fallback)

    if not ordered and available_names:
        for candidate in sorted(available_names):
            if candidate not in seen:
                ordered.append(candidate)
                seen.add(candidate)

    if not ordered:
        for fallback in DEFAULT_MODEL_ORDER:
            for candidate in _expand_aliases(fallback):
                if candidate in seen:
                    continue
                ordered.append(candidate)
                seen.add(candidate)

    return ordered


def _call_gemini_raw(
    *,
    api_key: str,
    base_endpoint: str,
    version: str,
    model: str,
    system_prompt: str,
    contents: List[Dict[str, Any]],
    max_output_tokens: int,
) -> GeminiCallResult:
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
        },
    }

    url = f"{base_endpoint}/{version}/models/{model}:generateContent"

    try:
        response = requests.post(
            url,
            headers=_auth_headers(api_key, json=True),
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:  # pragma: no cover (red)
        raise GeminiAPIError(f"Error de red comunicándose con Gemini: {exc}") from exc

    if response.status_code == 404:
        raise GeminiModelNotFound(
            f"Modelo {model} no disponible ({response.status_code})."
        )
    if not response.ok:
        raise GeminiAPIError(
            f"Respuesta {response.status_code} de Gemini: {response.text}"
        )

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiAPIError("La respuesta de Gemini no contiene candidatos.")

    candidate = candidates[0] or {}
    content = candidate.get("content") or {}
    parts = content.get("parts") or []

    aggregated_parts: List[str] = []
    for part in parts:
        text = part.get("text")
        if isinstance(text, str):
            aggregated_parts.append(text)

    combined_text = "".join(aggregated_parts).strip()
    if not combined_text:
        raise GeminiAPIError(
            "La respuesta de Gemini no contiene texto utilizable."
        )

    finish_reason = candidate.get("finishReason")

    return GeminiCallResult(
        text=combined_text,
        finish_reason=finish_reason,
    )


def _compose_system_prompt(base_prompt: str, extra: Optional[str]) -> str:
    if not extra:
        return base_prompt
    base_prompt = base_prompt.rstrip()
    extra = extra.strip()
    if not base_prompt:
        return extra
    return f"{base_prompt}\n\n{extra}"


def get_gemini_reply(system_prompt: str, message: str) -> str:
    """Obtiene una respuesta del asistente Gemini con reintentos inteligentes."""
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El asistente no está disponible por falta de configuración.",
        )

    available = _available_models(
        api_key, settings.gemini_api_base, settings.gemini_api_version_hint
    )
    models = _build_candidate_list(
        settings.gemini_chat_model, settings.gemini_default_model, available
    )

    composed_system_prompt = _compose_system_prompt(
        system_prompt, settings.chat_response_guideline
    )

    if not models:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay modelos configurados para el asistente.",
        )

    last_error: Optional[Exception] = None
    version_candidates = _version_candidates(settings.gemini_api_version_hint)

    for model in models:
        version = available.get(model) or next(iter(version_candidates), "v1beta")

        try:
            contents = _initial_contents(message)
            chunks: List[str] = []

            for attempt in range(
                settings.gemini_max_auto_continuations + 1
            ):
                result = _call_gemini_raw(
                    api_key=api_key,
                    base_endpoint=settings.gemini_api_base,
                    version=version,
                    model=model,
                    system_prompt=composed_system_prompt,
                    contents=contents,
                    max_output_tokens=settings.gemini_max_output_tokens,
                )

                chunks.append(result.text)
                accumulated = "".join(chunks)

                if not _needs_continuation(accumulated, result.finish_reason):
                    return accumulated.strip()

                if attempt + 1 > settings.gemini_max_auto_continuations:
                    logger.warning(
                        (
                            "La respuesta de Gemini se truncó repetidamente "
                            "utilizando el modelo %s, incluso tras %s "
                            "continuaciones automáticas."
                        ),
                        model,
                        settings.gemini_max_auto_continuations,
                    )
                    return accumulated.strip()

                logger.debug(
                    "Solicitud de continuación automática #%s para el modelo %s "
                    "(finishReason=%s).",
                    attempt + 1,
                    model,
                    result.finish_reason,
                )
                contents = _continuation_contents(message, accumulated)
        except GeminiModelNotFound as exc:
            available.pop(model, None)
            logger.warning("Modelo Gemini %s no disponible (%s).", model, exc)
            last_error = exc
            continue
        except GeminiAPIError as exc:
            logger.warning("Fallo de Gemini con el modelo %s: %s", model, exc)
            last_error = exc
            continue

    raise HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        detail="No se pudo obtener una respuesta del asistente en este momento.",
    ) from last_error


__all__ = ["get_gemini_reply", "GeminiAPIError", "GeminiModelNotFound"]
