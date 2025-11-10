from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.bootstrap import bootstrap_database
from app.core.config import get_settings
from app.routes import admin, auth, chat, documents, public, muro

settings = get_settings()
bootstrap_database()

app = FastAPI(title=settings.app_title)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_session_secret,
)

app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

app.include_router(chat.router)
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(muro.router)

__all__ = ["app"]
