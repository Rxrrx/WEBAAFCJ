import logging
from collections import defaultdict
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

import requests
from fastapi import HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger("app.chatbot")


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
    message: str,
    max_output_tokens: int,
) -> str:
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": message}],
            }
        ],
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
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

    raise GeminiAPIError("La respuesta de Gemini no contiene texto utilizable.")


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
            return _call_gemini_raw(
                api_key=api_key,
                base_endpoint=settings.gemini_api_base,
                version=version,
                model=model,
                system_prompt=system_prompt,
                message=message,
                max_output_tokens=settings.gemini_max_output_tokens,
            )
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
