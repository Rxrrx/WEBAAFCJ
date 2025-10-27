from typing import List, Sequence, Tuple

from sqlalchemy import case

from app import models


def document_ordering_clause():
    """SQL fragments that prioritize custom order before recency."""
    has_no_order = case(
        (models.Document.display_order.is_(None), 1),
        else_=0,
    )
    return (
        has_no_order,
        models.Document.display_order.asc(),
        models.Document.uploaded_at.desc(),
    )


def sort_documents(documents: Sequence[models.Document]) -> List[models.Document]:
    """Client-side equivalent of document_ordering_clause."""

    def sort_key(document: models.Document) -> Tuple[int, int, float]:
        has_order = 0 if document.display_order is not None else 1
        order_value = document.display_order if document.display_order is not None else 0
        uploaded_at = document.uploaded_at.timestamp() if document.uploaded_at else 0.0
        return (has_order, order_value, -uploaded_at)

    return sorted(documents, key=sort_key)


__all__ = ["document_ordering_clause", "sort_documents"]
