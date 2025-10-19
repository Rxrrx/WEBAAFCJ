from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.database import get_db

settings = get_settings()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[models.User]:
    """Obtiene el usuario autenticado desde la sesión."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_superuser(
    current_user: Optional[models.User] = Depends(get_current_user),
) -> models.User:
    """Valida que el usuario actual sea superusuario."""
    if current_user is None or not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el superusuario puede realizar esta acción.",
        )
    return current_user


def redirect_response(url: str) -> RedirectResponse:
    """Crea una respuesta de redirección 303."""
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def template_context(
    request: Request, current_user: Optional[models.User], **extra: Any
) -> Dict[str, Any]:
    """Contexto base compartido para templates HTML."""
    context: Dict[str, Any] = {
        "request": request,
        "current_user": current_user,
        "current_year": datetime.utcnow().year,
    }
    context.update(extra)
    return context


__all__ = [
    "get_current_user",
    "require_superuser",
    "redirect_response",
    "template_context",
]
