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
            document_columns = [
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(documents)"
                )
            ]
            if "category_id" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN category_id INTEGER REFERENCES categories(id)"
                )
            if "subcategory_id" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN subcategory_id INTEGER REFERENCES subcategories(id)"
                )
            if "file_size_bytes" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN file_size_bytes INTEGER"
                )
            if "storage_backend" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN storage_backend VARCHAR(32)"
                )
            if "storage_key" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN storage_key VARCHAR(512)"
                )
            if "storage_url" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN storage_url VARCHAR(2048)"
                )
            if "display_order" not in document_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE documents "
                    "ADD COLUMN display_order INTEGER"
                )

            category_columns = [
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(categories)"
                )
            ]
            if "display_order" not in category_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE categories "
                    "ADD COLUMN display_order INTEGER DEFAULT 0 NOT NULL"
                )

            subcategory_columns = [
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(subcategories)"
                )
            ]
            if "display_order" not in subcategory_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE subcategories "
                    "ADD COLUMN display_order INTEGER DEFAULT 0 NOT NULL"
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
            connection.exec_driver_sql(
                "ALTER TABLE categories "
                "ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0 NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE subcategories "
                "ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0 NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS storage_backend VARCHAR(32)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS storage_key VARCHAR(512)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS storage_url VARCHAR(2048)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS display_order INTEGER"
            )

        # Normaliza valores de orden cuando el campo es nuevo o está sin asignar.
        connection.exec_driver_sql(
            "UPDATE categories SET display_order = id "
            "WHERE display_order IS NULL OR display_order = 0"
        )
        connection.exec_driver_sql(
            "UPDATE subcategories SET display_order = id "
            "WHERE display_order IS NULL OR display_order = 0"
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
