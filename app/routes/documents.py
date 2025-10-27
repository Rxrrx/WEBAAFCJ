from io import BytesIO
from typing import Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from urllib.parse import quote

from app import models
from app.core.config import get_settings
from app.database import get_db
from app.dependencies import (
    get_current_user,
    redirect_response,
    require_superuser,
)
from app.services.storage import (
    StorageUnavailableError,
    get_storage_service,
)

router = APIRouter(tags=["documentos"])
settings = get_settings()
storage = get_storage_service()


def _build_content_disposition(filename: str, inline: bool = False) -> str:
    disposition = 'inline' if inline else 'attachment'
    safe = quote(filename)
    return f"{disposition}; filename*=UTF-8''{safe}"


def _resolve_category_selection(
    db: Session, category_id: int, subcategory_id: Optional[int]
) -> Tuple[models.Category, Optional[models.SubCategory]]:
    category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La categoría seleccionada no existe.",
        )

    subcategory = None
    if subcategory_id:
        subcategory = (
            db.query(models.SubCategory)
            .filter(
                models.SubCategory.id == subcategory_id,
                models.SubCategory.category_id == category.id,
            )
            .first()
        )
        if subcategory is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La subcategoría seleccionada no es válida para la categoría.",
            )
    return category, subcategory


def _validate_file_metadata(content_type: str, file_size_bytes: int) -> None:
    if file_size_bytes <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío.",
        )

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo excede el límite de {settings.max_file_size_mb} MB.",
        )

    if content_type not in settings.allowed_upload_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de archivo no soportado.",
        )


class DirectUploadInitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    content_type: str = Field(..., alias="contentType")
    file_size: int = Field(..., gt=0, alias="fileSize")
    category_id: int = Field(..., alias="categoryId")
    subcategory_id: Optional[int] = Field(None, alias="subcategoryId")


class DirectUploadFinalizeRequest(DirectUploadInitRequest):
    model_config = ConfigDict(populate_by_name=True)

    storage_key: str = Field(..., alias="storageKey")


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


def _is_remote(document: models.Document) -> bool:
    return bool(document.storage_backend and document.storage_key)


@router.post("/upload")
async def upload_file(
    request: Request,
    category_id: int = Form(...),
    subcategory_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_superuser),
):
    if storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta instalación usa subidas directas. Realiza la carga desde el panel para obtener una URL firmada.",
        )

    category, subcategory = _resolve_category_selection(
        db, category_id=category_id, subcategory_id=subcategory_id
    )

    content = await file.read()
    _validate_file_metadata(file.content_type or "", len(content))

    document = models.Document(
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        file_size_bytes=len(content),
        category_id=category.id,
        subcategory_id=subcategory.id if subcategory else None,
    )
    db.add(document)
    db.commit()

    referer = request.headers.get("referer")
    if referer and "/admin/upload" in referer:
        return redirect_response(request.url_for("admin_upload"))
    return redirect_response(request.url_for("read_home"))


@router.post("/upload/direct/init")
async def init_direct_upload(
    payload: DirectUploadInitRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_superuser),
):
    if not storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El backend de almacenamiento directo no está configurado.",
        )

    category, subcategory = _resolve_category_selection(
        db, category_id=payload.category_id, subcategory_id=payload.subcategory_id
    )
    _validate_file_metadata(payload.content_type, payload.file_size)

    try:
        presigned = storage.create_presigned_upload(
            filename=payload.filename,
            content_type=payload.content_type,
        )
    except StorageUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return {
        "uploadUrl": presigned.url,
        "headers": presigned.headers,
        "storageKey": presigned.key,
        "expiresIn": presigned.expires_in,
        "categoryId": category.id,
        "subcategoryId": subcategory.id if subcategory else None,
        "maxFileSize": settings.max_file_size_mb,
    }


@router.post("/upload/direct/finalize")
async def finalize_direct_upload(
    payload: DirectUploadFinalizeRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_superuser),
):
    if not storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El backend de almacenamiento directo no está configurado.",
        )

    category, subcategory = _resolve_category_selection(
        db, category_id=payload.category_id, subcategory_id=payload.subcategory_id
    )
    _validate_file_metadata(payload.content_type, payload.file_size)

    if not payload.storage_key or not payload.storage_key.startswith("documents/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La clave del archivo no es válida.",
        )

    exists = storage.ensure_object_exists(payload.storage_key)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no se encuentra en el almacenamiento. Intenta subirlo nuevamente.",
        )

    document = models.Document(
        filename=payload.filename,
        content_type=payload.content_type,
        content=b"",
        file_size_bytes=payload.file_size,
        category_id=category.id,
        subcategory_id=subcategory.id if subcategory else None,
        storage_backend=settings.storage_backend,
        storage_key=payload.storage_key,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return {"documentId": document.id}


@router.post("/documents/{document_id}/delete")
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


@router.get("/documents/{document_id}/view")
async def view_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = _fetch_document(db, document_id)
    if _is_remote(document):
        if not storage.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El documento se encuentra en almacenamiento externo y no puede visualizarse en este entorno.",
            )
        try:
            presigned = storage.create_presigned_download(
                document.storage_key,
                filename=document.filename,
                content_type=document.content_type,
                inline=True,
            )
        except StorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return RedirectResponse(
            presigned.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    raw_content = document.content or b""
    if isinstance(raw_content, memoryview):
        raw_content = raw_content.tobytes()
    content = bytes(raw_content)
    stream = BytesIO(content)
    headers = {
        "Content-Disposition": _build_content_disposition(document.filename, inline=True),
        "Content-Length": str(len(content)),
        "Cache-Control": "no-store",
    }
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type=document.content_type,
        headers=headers,
    )


@router.get("/documents/{document_id}/download")
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
    if _is_remote(document):
        if not storage.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El documento se encuentra en almacenamiento externo y no puede descargarse en este entorno.",
            )
        try:
            presigned = storage.create_presigned_download(
                document.storage_key,
                filename=document.filename,
                content_type=document.content_type,
                inline=False,
            )
        except StorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return RedirectResponse(
            presigned.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    raw_content = document.content or b""
    if isinstance(raw_content, memoryview):
        raw_content = raw_content.tobytes()
    content = bytes(raw_content)
    stream = BytesIO(content)
    stream.seek(0)
    headers = {
        "Content-Disposition": _build_content_disposition(document.filename, inline=False),
        "Content-Length": str(len(content)),
        "Cache-Control": "no-store",
    }
    return StreamingResponse(
        stream,
        media_type=document.content_type,
        headers=headers,
    )
