from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "library.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Ensure the data directory exists so SQLite can create the file.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Yield a database session and ensure it is cleaned up."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
