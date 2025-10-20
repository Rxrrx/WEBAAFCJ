import logging
from typing import List, Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.gemini import get_gemini_reply

router = APIRouter(prefix="/api", tags=["chatbot"])
logger = logging.getLogger("app.chatbot")
settings = get_settings()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = []


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El mensaje no puede estar vacio.",
        )

    history: List[dict] = []
    for turn in payload.history:
        content = turn.content.strip()
        if not content:
            continue
        history.append({"role": turn.role, "content": content})

    history_limit = max(settings.chat_history_max_turns, 0)
    if history_limit and len(history) > history_limit:
        history = history[-history_limit:]

    try:
        answer = await run_in_threadpool(
            get_gemini_reply,
            settings.chat_system_prompt,
            message,
            tuple(history),
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - red externo
        logger.exception("Error inesperado consultando Gemini: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo obtener una respuesta del asistente en este momento.",
        ) from exc

    answer = (answer or "").strip()
    if not answer:
        answer = (
            "Lo siento, en este momento no pude generar una respuesta. "
            "Intenta nuevamente en unos instantes."
        )
    return ChatResponse(reply=answer)
