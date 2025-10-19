from pathlib import Path
import sys

# Asegura que el paquete `app` (ubicado en la raíz del repo) esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402  (importa la app ASGI principal)

__all__ = ["app"]
