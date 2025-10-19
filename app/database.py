# app/database.py
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Por defecto (desarrollo local) usamos SQLite en data/library.db
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "library.db"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Local: asegura carpeta y arma URL de SQLite
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"

# Para SQLite necesitamos este connect_arg; en Postgres/MySQL no.
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# pool_pre_ping evita conexiones muertas en DBs remotas
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Yield de sesión y cleanup garantizado."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
