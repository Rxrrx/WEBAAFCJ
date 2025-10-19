from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app import models
from app.core.templating import templates
from app.database import get_db
from app.dependencies import (
    get_current_user,
    redirect_response,
    template_context,
)
from app.security import get_password_hash, verify_password
from app.utils import normalize_email

router = APIRouter(tags=["autenticación"])


@router.get("/register")
async def register_form(
    request: Request,
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user:
        return redirect_response(request.url_for("read_home"))
    return templates.TemplateResponse(
        "register.html",
        template_context(request, current_user, errors=None, values={}),
    )


@router.post("/register")
async def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user:
        return redirect_response(request.url_for("read_home"))

    errors: List[str] = []
    values = {
        "full_name": full_name.strip(),
        "email": normalize_email(email),
    }

    if password != confirm_password:
        errors.append("Las contraseñas no coinciden.")

    if len(password) < 8:
        errors.append("La contraseña debe tener al menos 8 caracteres.")

    existing = (
        db.query(models.User)
        .filter(models.User.email == values["email"])
        .first()
    )
    if existing:
        errors.append("Ya existe una cuenta con ese correo.")

    if errors:
        return templates.TemplateResponse(
            "register.html",
            template_context(
                request,
                current_user,
                errors=errors,
                values=values,
            ),
        )

    new_user = models.User(
        full_name=values["full_name"],
        email=values["email"],
        hashed_password=get_password_hash(password),
        is_superuser=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    request.session["user_id"] = new_user.id
    return redirect_response(request.url_for("read_home"))


@router.get("/login")
async def login_form(
    request: Request,
    current_user: Optional[models.User] = Depends(get_current_user),
    next: Optional[str] = None,
):
    if current_user:
        return redirect_response(request.url_for("read_home"))
    return templates.TemplateResponse(
        "login.html",
        template_context(
            request,
            current_user,
            errors=None,
            values={"next": next or ""},
        ),
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user:
        return redirect_response(request.url_for("read_home"))

    errors: List[str] = []
    values = {"email": normalize_email(email), "next": next or ""}

    user = (
        db.query(models.User)
        .filter(models.User.email == values["email"])
        .first()
    )
    if not user or not verify_password(password, user.hashed_password):
        errors.append("Credenciales inválidas.")
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                current_user,
                errors=errors,
                values=values,
            ),
        )

    request.session["user_id"] = user.id
    redirect_target = values["next"] or request.url_for("read_home")
    return redirect_response(redirect_target)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return redirect_response(request.url_for("read_home"))
