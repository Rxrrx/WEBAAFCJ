from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, selectinload

from app import models
from app.core.config import get_settings
from app.core.templating import templates
from app.database import get_db
from app.dependencies import (
    get_current_user,
    redirect_response,
    template_context,
)

router = APIRouter(tags=["páginas"])
settings = get_settings()


@router.get("/")
async def read_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    recent_documents = (
        db.query(models.Document)
        .options(
            selectinload(models.Document.category),
            selectinload(models.Document.subcategory),
        )
        .order_by(models.Document.uploaded_at.desc())
        .limit(6)
        .all()
    )

    sermon_category = (
        db.query(models.Category)
        .filter(models.Category.name.ilike(settings.sermon_category_name))
        .first()
    )
    sermon_document = None
    if sermon_category:
        sermon_document = (
            db.query(models.Document)
            .options(
                selectinload(models.Document.category),
                selectinload(models.Document.subcategory),
            )
            .filter(models.Document.category_id == sermon_category.id)
            .order_by(models.Document.uploaded_at.desc())
            .first()
        )

    return templates.TemplateResponse(
        "index.html",
        template_context(
            request,
            current_user,
            documents=recent_documents,
            max_file_size=settings.max_file_size_mb,
            allowed_types=settings.allowed_upload_types,
            sermon_document=sermon_document,
            sermon_category_name=settings.sermon_category_name,
            church_address=settings.church_address,
        ),
    )


@router.get("/library")
async def library_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user),
):
    categories = (
        db.query(models.Category)
        .options(
            selectinload(models.Category.subcategories).selectinload(
                models.SubCategory.documents
            ).selectinload(models.Document.category),
            selectinload(models.Category.subcategories).selectinload(
                models.SubCategory.documents
            ).selectinload(models.Document.subcategory),
            selectinload(models.Category.documents).selectinload(
                models.Document.category
            ),
            selectinload(models.Category.documents).selectinload(
                models.Document.subcategory
            ),
        )
        .order_by(models.Category.name)
        .all()
    )
    category_groups: List[Dict[str, object]] = []
    for category in categories:
        subcollections: List[Dict[str, object]] = []
        for subcategory in sorted(
            category.subcategories, key=lambda s: s.name.lower()
        ):
            docs = sorted(
                subcategory.documents,
                key=lambda d: d.uploaded_at,
                reverse=True,
            )
            if docs:
                subcollections.append(
                    {"subcategory": subcategory, "documents": docs}
                )
        standalone_docs = sorted(
            [
                document
                for document in category.documents
                if document.subcategory_id is None
            ],
            key=lambda d: d.uploaded_at,
            reverse=True,
        )
        if subcollections or standalone_docs:
            total_docs = len(standalone_docs) + sum(
                len(item["documents"]) for item in subcollections
            )
            category_groups.append(
                {
                    "category": category,
                    "subcategories": subcollections,
                    "documents": standalone_docs,
                    "total_documents": total_docs,
                }
            )

    uncategorized = (
        db.query(models.Document)
        .options(
            selectinload(models.Document.category),
            selectinload(models.Document.subcategory),
        )
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


@router.get("/profile")
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
            ),
            selectinload(models.DocumentDownload.document).selectinload(
                models.Document.subcategory
            ),
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
            "subcategory_name": entry.document.subcategory.name
            if entry.document.subcategory
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
