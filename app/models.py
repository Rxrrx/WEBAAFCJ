from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    documents = relationship("Document", back_populates="category")
    subcategories = relationship(
        "SubCategory",
        back_populates="category",
        cascade="all, delete-orphan",
    )


class SubCategory(Base):
    __tablename__ = "subcategories"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_subcategory_category_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    display_order = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    category = relationship("Category", back_populates="subcategories")
    documents = relationship("Document", back_populates="subcategory")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    content = Column(LargeBinary, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    storage_backend = Column(String(32), nullable=True, index=True)
    storage_key = Column(String(512), nullable=True, unique=True)
    storage_url = Column(String(2048), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    display_order = Column(Integer, nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    category = relationship("Category", back_populates="documents")
    subcategory = relationship("SubCategory", back_populates="documents")
    downloads = relationship("DocumentDownload", back_populates="document")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    downloads = relationship("DocumentDownload", back_populates="user")


class DocumentDownload(Base):
    __tablename__ = "document_downloads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    downloaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="downloads")
    document = relationship("Document", back_populates="downloads")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(32), nullable=True, index=True)
    content = Column(String(4000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")
    replies = relationship(
        "PostReply",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostReply.created_at.asc()",
    )


class PostReply(Base):
    __tablename__ = "post_replies"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(String(4000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    post = relationship("Post", back_populates="replies")
    user = relationship("User")
