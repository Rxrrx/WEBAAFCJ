import os
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError  # <-- agregado

from . import models
from .database import Base, SessionLocal, engine, get_db
from .security import get_password_hash, verify_password

Base.metadata.create_all(bind=engine)


def ensure_schema() -> None:
    """Compat: sólo ejecuta el PRAGMA/ALTER para SQLite; en otros motores no hace nada."""
    if engine.url.get_backend_name() != "sqlite":
        return
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(documents)")]
        if "category_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN category_id INTEGER REFERENCES categories(id)"
            )


ensure_schema()
app = FastAPI(title="Biblioteca de Documentos")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SESSION_SECRET", "dev-secret-key-change-me"),
)

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

SUPERUSER_EMAIL = os.environ.get("SUPERUSER_EMAIL", "super@biblioteca.local")
SUPERUSER_PASSWORD = os.environ.get("SUPERUSER_PASSWORD", "SuperUsuario123!")
SUPERUSER_NAME = os.environ.get("SUPERUSER_NAME", "Super Usuario")

ALLOWED_TYPES: List[str] = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
]

MAX_FILE_SIZE_MB = 25


def ensure_default_superuser() -> None:
    db = SessionLocal()
    try:
        existing = (
            db.query(models.User)
            .filter(models.User.email == SUPERUSER_EMAIL)
            .first()
        )
        if existing is None:
            superuser = models.User(
                email=SUPERUSER_EMAIL,
                full_name=SUPERUSER_NAME,
                hashed_password=get_password_hash(SUPERUSER_PASSWORD),
                is_superuser=True,
            )
            db.add(superuser)
            db.commit()
    finally:
        db.close()


ensure_default_superuser()


def _fetch_document(db: Session, document_id: int) -> models.Document:
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado.",
        )
    return document


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[models.User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_superuser(
    current_user: Optional[models.User] = Depends(get_current_user),
) -> models.User:
    if current_user is None or not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el superusuario puede realizar esta accion.",
        )
    return current_user


def redirect_response(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def template_context(
    request: Request, current_user: Optional[models.User], **kwargs
):
    context = {
        "request": request,
        "current_user": current_user,
        "current_year": datetime.utcnow().year,
    }
    context.update(kwargs)
    return context


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El asistente no esta disponible por falta de configuracion.",
        )
    cached_client: Optional[OpenAI] = getattr(app.state, "openai_client", None)
    cached_key: Optional[str] = getattr(app.state, "openai_client_key", None)
    if cached_client is None or cached_key != api_key:
        cached_client = OpenAI(api_key=api_key)
        app.state.openai_client = cached_client
        app.state.openai_client_key = api_key
    return cached_client


@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_assistant(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El mensaje no puede estar vacio.",
        )

    client = get_openai_client()
    model_name = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    system_prompt = (
        "Eres 'Luz de Guía', un asistente virtual respetuoso de la Asamblea "
        "Apostólica de la Fe en Cristo Jesús. Respondes únicamente preguntas "
        "relacionadas con la Biblia, la fe cristiana evangélica y la vida devocional. "
        "Cuando recibas preguntas fuera de ese ámbito ofrece, de manera amable, "
        "continuar la conversación sobre temas bíblicos o de fe, sin reprender ni "
        "inventar información. Utiliza un tono pastoral, cálido y breve."
    )

    try:
        response = await run_in_threadpool(
            client.responses.create,
            model=model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_output_tokens=400,
        )
    except Exception as exc:  # pragma: no cover - red externo
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo obtener una respuesta del asistente en este momento.",
        ) from exc

    answer = (getattr(response, "output_text", "") or "").strip()
    if not answer:
        answer = (
            "Lo siento, en este momento no pude generar una respuesta. "
            "Intenta nuevamente en unos instantes."
        )
    return ChatResponse(reply=answer)


@app.get("/")
async def read_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    recent_documents = (
        db.query(models.Document)
        .options(selectinload(models.Document.category))
        .order_by(models.Document.uploaded_at.desc())
        .limit(6)
        .all()
    )
    return templates.TemplateResponse(
        "index.html",
        template_context(
            request,
            current_user,
            documents=recent_documents,
            max_file_size=MAX_FILE_SIZE_MB,
            allowed_types=ALLOWED_TYPES,
        ),
    )


@app.get("/library")
async def library_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    categories = (
        db.query(models.Category)
        .options(selectinload(models.Category.documents))
        .order_by(models.Category.name)
        .all()
    )
    category_groups: List[Dict[str, object]] = []
    for category in categories:
        docs = sorted(
            category.documents, key=lambda d: d.uploaded_at, reverse=True
        )
        if docs:
            category_groups.append({"category": category, "documents": docs})

    uncategorized = (
        db.query(models.Document)
        .options(selectinload(models.Document.category))
        .filter(models.Document.category_id.is_(None))
        .order_by(models.Document.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "library.html",
        template_context(
            request,
            current_user,
            category_groups=category_groups,
            uncategorized_documents=uncategorized,
        ),
    )


@app.get("/register")
async def register_form(
    request: Request,
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user:
        return redirect_response(request.url_for("read_home"))
    return templates.TemplateResponse(
        "register.html",
        template_context(
            request, current_user, errors=None, values={}
        ),
    )


@app.post("/register")
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

    errors = []
    values = {
        "full_name": full_name.strip(),
        "email": _normalize_email(email),
    }

    if password != confirm_password:
        errors.append("Las contrasenas no coinciden.")

    if len(password) < 8:
        errors.append("La contrasena debe tener al menos 8 caracteres.")

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
                request, current_user, errors=errors, values=values
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


@app.get("/login")
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


@app.post("/login")
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

    errors = []
    values = {"email": _normalize_email(email), "next": next or ""}

    user = (
        db.query(models.User)
        .filter(models.User.email == values["email"])
        .first()
    )
    if not user or not verify_password(password, user.hashed_password):
        errors.append("Credenciales invalidas.")
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request, current_user, errors=errors, values=values
            ),
        )

    request.session["user_id"] = user.id
    redirect_target = values["next"] or request.url_for("read_home")
    return redirect_response(redirect_target)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return redirect_response(request.url_for("read_home"))


@app.post("/upload")
async def upload_file(
    request: Request,
    category_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_superuser),
):
    category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La categoria seleccionada no existe.",
        )

    content = await file.read()

    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo esta vacio.",
        )

    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo excede el limite de {MAX_FILE_SIZE_MB} MB.",
        )

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de archivo no soportado.",
        )

    document = models.Document(
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        category_id=category.id,
    )
    db.add(document)
    db.commit()

    referer = request.headers.get("referer")
    if referer and "/admin/upload" in referer:
        return redirect_response(request.url_for("admin_upload"))
    return redirect_response(request.url_for("read_home"))


@app.get("/admin/upload")
async def admin_upload(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    documents = (
        db.query(models.Document)
        .options(selectinload(models.Document.category))
        .order_by(models.Document.uploaded_at.desc())
        .limit(10)
        .all()
    )
    categories = (
        db.query(models.Category)
        .order_by(models.Category.name)
        .all()
    )
    return templates.TemplateResponse(
        "admin_upload.html",
        template_context(
            request,
            current_user,
            documents=documents,
            max_file_size=MAX_FILE_SIZE_MB,
            allowed_types=ALLOWED_TYPES,
            categories=categories,
        ),
    )


@app.get("/profile")
async def profile_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    if current_user is None:
        login_url = request.url_for("login_form")
        return redirect_response(f"{login_url}?next={request.url.path}")

    history_entries = (
        db.query(models.DocumentDownload)
        .options(
            selectinload(models.DocumentDownload.document).selectinload(
                models.Document.category
            )
        )
        .filter(models.DocumentDownload.user_id == current_user.id)
        .order_by(models.DocumentDownload.downloaded_at.desc())
        .limit(20)
        .all()
    )
    history = [
        {
            "id": entry.id,
            "document_id": entry.document_id,
            "filename": entry.document.filename,
            "content_type": entry.document.content_type,
            "downloaded_at": entry.downloaded_at,
            "category_name": entry.document.category.name
            if entry.document.category
            else None,
        }
        for entry in history_entries
    ]

    return templates.TemplateResponse(
        "profile.html",
        template_context(
            request,
            current_user,
            history=history,
        ),
    )


def _render_admin_categories(
    request: Request,
    db: Session,
    current_user: models.User,
    message: Optional[str] = None,
    errors: Optional[List[str]] = None,
):
    categories = (
        db.query(models.Category)
        .order_by(models.Category.name)
        .all()
    )
    return templates.TemplateResponse(
        "admin_categories.html",
        template_context(
            request,
            current_user,
            categories=categories,
            message=message,
            errors=errors or [],
        ),
    )


@app.get("/admin/categories")
async def admin_categories_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    message = request.query_params.get("msg")
    err = request.query_params.get("err")
    errors = [err] if err else None
    return _render_admin_categories(
        request, db=db, current_user=current_user, message=message, errors=errors
    )


@app.post("/admin/categories")
async def admin_categories_create(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    cleaned = name.strip()
    errors: List[str] = []

    if not cleaned:
        errors.append("El nombre de la categoria no puede estar vacio.")

    exists = (
        db.query(models.Category)
        .filter(models.Category.name.ilike(cleaned))
        .first()
    )
    if exists:
        errors.append("Ya existe una categoria con ese nombre.")

    if errors:
        return _render_admin_categories(
            request, db=db, current_user=current_user, errors=errors
        )

    category = models.Category(name=cleaned)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["No se pudo crear la categoria (posible duplicado o error de base de datos)."],
        )

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Categoria%20creada"
    )


@app.post("/admin/categories/{category_id}/delete")
async def admin_categories_delete(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    category = (
        db.query(models.Category)
        .options(selectinload(models.Category.documents))
        .filter(models.Category.id == category_id)
        .first()
    )
    if category is None:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["La categoria solicitada no existe."],
        )

    document_ids = [doc.id for doc in category.documents]

    if document_ids:
        db.query(models.DocumentDownload).filter(
            models.DocumentDownload.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        count = db.query(models.Document).filter(
            models.Document.id.in_(document_ids)
        ).delete(synchronize_session=False)
        db.commit()
        # Refresh category documents association after deletion.
        category = (
            db.query(models.Category)
            .options(selectinload(models.Category.documents))
            .filter(models.Category.id == category_id)
            .first()
        )

    db.delete(category)
    db.commit()

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Categoria%20eliminada"
    )


@app.post("/documents/{document_id}/delete")
async def delete_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_superuser),
):
    document = _fetch_document(db, document_id)
    db.query(models.DocumentDownload).filter(
        models.DocumentDownload.document_id == document.id
    ).delete(synchronize_session=False)
    db.delete(document)
    db.commit()

    referer = request.headers.get("referer")
    target = referer or request.url_for("library_view")
    return redirect_response(target)


@app.get("/documents/{document_id}/view")
async def view_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = _fetch_document(db, document_id)
    headers = {"Content-Disposition": f'inline; filename="{document.filename}"'}
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers=headers,
    )


@app.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    document = _fetch_document(db, document_id)
    if current_user is not None:
        download_entry = models.DocumentDownload(
            user_id=current_user.id, document_id=document.id
        )
        db.add(download_entry)
        db.commit()
    headers = {"Content-Disposition": f'attachment; filename="{document.filename}"'}
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers=headers,
    )
