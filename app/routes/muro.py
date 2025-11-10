from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app import models
from app.core.templating import templates
from app.database import get_db
from app.dependencies import (
    get_current_user,
    redirect_response,
    template_context,
)
from app.services.moderation import moderate_text


router = APIRouter(tags=["muro"])


def _redirect_to_login(request: Request) -> RedirectResponse:
    # Preserve current path and query when redirecting to login
    path = request.url.path
    query = request.url.query
    next_target = path + (f"?{query}" if query else "")
    return redirect_response(request.url_for("login_form") + f"?next={next_target}")


@router.get("/muro")
async def muro_index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
    error: Optional[str] = None,
    tipo: Optional[str] = None,
):
    kind_filter = (tipo or "").strip().lower() or None
    if kind_filter and kind_filter not in ALLOWED_KINDS:
        kind_filter = None

    query = (
        db.query(models.Post)
        .options(
            selectinload(models.Post.user),
            selectinload(models.Post.replies).selectinload(models.PostReply.user),
        )
        .order_by(models.Post.created_at.desc())
    )
    if kind_filter:
        query = query.filter(models.Post.kind == kind_filter)
    posts = query.all()

    return templates.TemplateResponse(
        "muro.html",
        template_context(
            request,
            current_user,
            posts=posts,
            selected_kind=kind_filter,
            errors=[error] if error else None,
        ),
    )


ALLOWED_KINDS = {"pregunta", "oracion", "anuncio", "testimonio"}


@router.post("/muro/create")
async def muro_create_post(
    request: Request,
    content: str = Form(...),
    kind: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user is None:
        return _redirect_to_login(request)

    errors: List[str] = []
    value = (content or "").strip()
    if len(value) < 4:
        errors.append("El mensaje es demasiado corto.")
    if len(value) > 4000:
        errors.append("El mensaje supera el limite de 4000 caracteres.")

    kind_value = (kind or "").strip().lower()
    if kind_value and kind_value not in ALLOWED_KINDS:
        errors.append("Tipo de publicacion no valido.")

    ok, _ = moderate_text(value)
    if not ok:
        errors.append("Tu mensaje contiene lenguaje no permitido.")

    if errors:
        posts = (
            db.query(models.Post)
            .options(
                selectinload(models.Post.user),
                selectinload(models.Post.replies).selectinload(models.PostReply.user),
            )
            .order_by(models.Post.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            "muro.html",
            template_context(
                request,
                current_user,
                posts=posts,
                errors=errors,
                draft={"content": value, "kind": kind_value},
            ),
        )

    post = models.Post(user_id=current_user.id, content=value, kind=kind_value or None)
    db.add(post)
    db.commit()
    return redirect_response(request.url_for("muro_index"))


@router.post("/muro/post/{post_id}/reply")
async def muro_reply(
    request: Request,
    post_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user is None:
        return _redirect_to_login(request)

    value = (content or "").strip()
    errors: List[str] = []
    if len(value) < 2:
        errors.append("La respuesta es demasiado corta.")
    if len(value) > 4000:
        errors.append("La respuesta supera el limite de 4000 caracteres.")

    ok, _ = moderate_text(value)
    if not ok:
        errors.append("Tu respuesta contiene lenguaje no permitido.")

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post is None:
        return redirect_response(request.url_for("muro_index"))

    if errors:
        posts = (
            db.query(models.Post)
            .options(
                selectinload(models.Post.user),
                selectinload(models.Post.replies).selectinload(models.PostReply.user),
            )
            .order_by(models.Post.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            "muro.html",
            template_context(
                request,
                current_user,
                posts=posts,
                errors=errors,
            ),
        )

    reply = models.PostReply(post_id=post.id, user_id=current_user.id, content=value)
    db.add(reply)
    db.commit()
    return redirect_response(request.url_for("muro_index"))


@router.post("/muro/post/{post_id}/delete")
async def muro_delete_post(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user is None:
        return _redirect_to_login(request)

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post is None:
        return redirect_response(request.url_for("muro_index"))

    if (post.user_id != current_user.id) and (not current_user.is_superuser):
        return redirect_response(request.url_for("muro_index"))

    db.delete(post)
    db.commit()
    return redirect_response(request.url_for("muro_index"))


@router.post("/muro/reply/{reply_id}/delete")
async def muro_delete_reply(
    request: Request,
    reply_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    """Eliminar una respuesta del muro.
    Permite borrar solo al autor de la respuesta o al superusuario.
    """
    if current_user is None:
        return _redirect_to_login(request)

    reply = db.query(models.PostReply).filter(models.PostReply.id == reply_id).first()
    if reply is None:
        return redirect_response(request.url_for("muro_index"))

    if (reply.user_id != current_user.id) and (not current_user.is_superuser):
        return redirect_response(request.url_for("muro_index"))

    db.delete(reply)
    db.commit()
    return redirect_response(request.url_for("muro_index"))


__all__ = ["router", "muro_index"]
