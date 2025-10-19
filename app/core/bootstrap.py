import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app import models
from app.database import Base, SessionLocal, engine
from app.security import get_password_hash

from .config import Settings, get_settings

logger = logging.getLogger("app.bootstrap")


def _ensure_table_columns() -> None:
    """Ajusta columnas opcionales en tablas existentes."""
    backend = engine.url.get_backend_name()
    with engine.begin() as connection:
        if backend == "sqlite":
            columns = [
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(documents)"
                )
            ]
            if "category_id" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN category_id INTEGER REFERENCES categories(id)"
                )
            if "subcategory_id" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN subcategory_id INTEGER REFERENCES subcategories(id)"
                )
        else:
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS subcategory_id INTEGER REFERENCES subcategories(id)"
            )


def ensure_default_superuser(settings: Optional[Settings] = None) -> None:
    """Crea un superusuario por defecto si aún no existe."""
    settings = settings or get_settings()
    db = SessionLocal()
    try:
        exists = (
            db.query(models.User)
            .filter(models.User.email == settings.superuser_email)
            .first()
        )
        if exists:
            return

        superuser = models.User(
            email=settings.superuser_email,
            full_name=settings.superuser_name,
            hashed_password=get_password_hash(settings.superuser_password),
            is_superuser=True,
        )
        db.add(superuser)
        try:
            db.commit()
            logger.info("Superusuario por defecto creado: %s", superuser.email)
        except IntegrityError:
            db.rollback()
            logger.warning(
                "No se pudo crear el superusuario por defecto; es posible que otra instancia lo haya creado."
            )
    finally:
        db.close()


def bootstrap_database() -> None:
    """Inicializa la base de datos y sincroniza esquemas auxiliares."""
    Base.metadata.create_all(bind=engine)
    _ensure_table_columns()
    ensure_default_superuser()


__all__ = ["bootstrap_database", "ensure_default_superuser"]
