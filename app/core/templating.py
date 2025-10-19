from fastapi.templating import Jinja2Templates

from .config import get_settings

settings = get_settings()
templates = Jinja2Templates(directory=settings.templates_dir)

__all__ = ["templates"]
