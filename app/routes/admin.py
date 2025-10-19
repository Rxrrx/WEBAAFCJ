from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.core.config import get_settings
from app.core.templating import templates
from app.database import get_db
from app.dependencies import (
    redirect_response,
    require_superuser,
    template_context,
)

router = APIRouter(tags=["administración"])
settings = get_settings()


@router.get("/admin/upload")
async def admin_upload(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    documents = (
        db.query(models.Document)
        .options(
            selectinload(models.Document.category),
            selectinload(models.Document.subcategory),
        )
        .order_by(models.Document.uploaded_at.desc())
        .limit(10)
        .all()
    )
    categories = (
        db.query(models.Category)
        .options(selectinload(models.Category.subcategories))
        .order_by(models.Category.display_order.asc(), models.Category.name.asc())
        .all()
    )
    category_options = [
        {
            "id": category.id,
            "name": category.name,
            "subcategories": [
                {"id": sub.id, "name": sub.name}
                for sub in sorted(
                    category.subcategories,
                    key=lambda item: (item.display_order, item.name.lower()),
                )
            ],
        }
        for category in categories
    ]
    return templates.TemplateResponse(
        "admin_upload.html",
        template_context(
            request,
            current_user,
            documents=documents,
            max_file_size=settings.max_file_size_mb,
            allowed_types=settings.allowed_upload_types,
            categories=categories,
            category_options=category_options,
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
        .options(
            selectinload(models.Category.subcategories).selectinload(
                models.SubCategory.documents
            ),
            selectinload(models.Category.documents),
        )
        .order_by(models.Category.display_order.asc(), models.Category.name.asc())
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


@router.get("/admin/categories")
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


@router.post("/admin/categories")
async def admin_categories_create(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    cleaned = name.strip()
    errors: List[str] = []

    if not cleaned:
        errors.append("El nombre de la categoría no puede estar vacío.")

    exists = (
        db.query(models.Category)
        .filter(models.Category.name.ilike(cleaned))
        .first()
    )
    if exists:
        errors.append("Ya existe una categoría con ese nombre.")

    if errors:
        return _render_admin_categories(
            request, db=db, current_user=current_user, errors=errors
        )

    max_order = db.query(func.max(models.Category.display_order)).scalar() or 0
    category = models.Category(name=cleaned, display_order=max_order + 1)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["No se pudo crear la categoría (posible duplicado o error de base de datos)."],
        )

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Categoría%20creada"
    )


@router.post("/admin/categories/{category_id}/subcategories")
async def admin_subcategory_create(
    request: Request,
    category_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )
    if category is None:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["La categoría solicitada no existe."],
        )

    cleaned = name.strip()
    if not cleaned:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["El nombre no puede estar vacío."],
        )

    max_order = (
        db.query(func.max(models.SubCategory.display_order))
        .filter(models.SubCategory.category_id == category.id)
        .scalar()
        or 0
    )
    subcategory = models.SubCategory(
        name=cleaned,
        category_id=category.id,
        display_order=max_order + 1,
    )
    db.add(subcategory)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["No se pudo crear la subcategoría (posible duplicado o error de base de datos)."],
        )

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Subcategoría%20creada"
    )


@router.post("/admin/categories/{category_id}/move")
async def admin_category_move(
    request: Request,
    category_id: int,
    direction: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )
    if category is None:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["La categoría solicitada no existe."],
        )

    normalized = (direction or "").lower()
    if normalized not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Dirección inválida para el orden.")

    if normalized == "up":
        neighbor = (
            db.query(models.Category)
            .filter(models.Category.display_order < category.display_order)
            .order_by(models.Category.display_order.desc())
            .first()
        )
    else:
        neighbor = (
            db.query(models.Category)
            .filter(models.Category.display_order > category.display_order)
            .order_by(models.Category.display_order.asc())
            .first()
        )

    if neighbor:
        category.display_order, neighbor.display_order = (
            neighbor.display_order,
            category.display_order,
        )
        db.commit()

    return redirect_response(request.url_for("admin_categories_view"))


@router.post("/admin/subcategories/{subcategory_id}/move")
async def admin_subcategory_move(
    request: Request,
    subcategory_id: int,
    direction: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    subcategory = (
        db.query(models.SubCategory)
        .filter(models.SubCategory.id == subcategory_id)
        .first()
    )
    if subcategory is None:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["La subcategoría solicitada no existe."],
        )

    normalized = (direction or "").lower()
    if normalized not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Dirección inválida para el orden.")

    query = db.query(models.SubCategory).filter(
        models.SubCategory.category_id == subcategory.category_id
    )

    if normalized == "up":
        neighbor = (
            query.filter(models.SubCategory.display_order < subcategory.display_order)
            .order_by(models.SubCategory.display_order.desc())
            .first()
        )
    else:
        neighbor = (
            query.filter(models.SubCategory.display_order > subcategory.display_order)
            .order_by(models.SubCategory.display_order.asc())
            .first()
        )

    if neighbor:
        subcategory.display_order, neighbor.display_order = (
            neighbor.display_order,
            subcategory.display_order,
        )
        db.commit()

    return redirect_response(request.url_for("admin_categories_view"))


@router.post("/admin/categories/{category_id}/delete")
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
            errors=["La categoría solicitada no existe."],
        )

    document_ids = [doc.id for doc in category.documents]

    if document_ids:
        db.query(models.DocumentDownload).filter(
            models.DocumentDownload.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        db.query(models.Document).filter(
            models.Document.id.in_(document_ids)
        ).delete(synchronize_session=False)
        db.commit()
        category = (
            db.query(models.Category)
            .options(selectinload(models.Category.documents))
            .filter(models.Category.id == category_id)
            .first()
        )

    if category:
        db.delete(category)
        db.commit()

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Categoría%20eliminada"
    )


@router.post("/admin/subcategories/{subcategory_id}/delete")
async def admin_subcategory_delete(
    request: Request,
    subcategory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superuser),
):
    subcategory = (
        db.query(models.SubCategory)
        .options(selectinload(models.SubCategory.documents))
        .filter(models.SubCategory.id == subcategory_id)
        .first()
    )
    if subcategory is None:
        return _render_admin_categories(
            request,
            db=db,
            current_user=current_user,
            errors=["La subcategoría solicitada no existe."],
        )

    document_ids = [doc.id for doc in subcategory.documents]
    if document_ids:
        db.query(models.DocumentDownload).filter(
            models.DocumentDownload.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        db.query(models.Document).filter(
            models.Document.id.in_(document_ids)
        ).delete(synchronize_session=False)
        db.commit()

    db.delete(subcategory)
    db.commit()

    return redirect_response(
        f"{request.url_for('admin_categories_view')}?msg=Subcategoría%20eliminada"
    )
