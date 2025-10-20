from typing import Optional

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
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.database import get_db
from app.dependencies import (
    get_current_user,
    redirect_response,
    require_superuser,
)

router = APIRouter(tags=["documentos"])
settings = get_settings()


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


@router.post("/upload")
async def upload_file(
    request: Request,
    category_id: int = Form(...),
    subcategory_id: Optional[int] = Form(None),
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

    content = await file.read()

    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío.",
        )

    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo excede el límite de {settings.max_file_size_mb} MB.",
        )

    if file.content_type not in settings.allowed_upload_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de archivo no soportado.",
        )

    document = models.Document(
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        category_id=category.id,
        subcategory_id=subcategory.id if subcategory else None,
    )
    db.add(document)
    db.commit()

    referer = request.headers.get("referer")
    if referer and "/admin/upload" in referer:
        return redirect_response(request.url_for("admin_upload"))
    return redirect_response(request.url_for("read_home"))


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
    headers = {"Content-Disposition": f'inline; filename="{document.filename}"'}
    return StreamingResponse(
        iter([document.content]),
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
    headers = {"Content-Disposition": f'attachment; filename="{document.filename}"'}
    return StreamingResponse(
        iter([document.content]),
        media_type=document.content_type,
        headers=headers,
    )
