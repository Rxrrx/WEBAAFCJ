import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """Centraliza configuración leída desde variables de entorno."""

    app_title: str = field(default="Biblioteca de Documentos")
    templates_dir: str = field(
        default_factory=lambda: str(BASE_DIR / "templates")
    )
    static_dir: str = field(
        default_factory=lambda: str(BASE_DIR / "static")
    )
    app_session_secret: str = field(
        default_factory=lambda: os.environ.get(
            "APP_SESSION_SECRET", "dev-secret-key-change-me"
        )
    )
    superuser_email: str = field(
        default_factory=lambda: os.environ.get(
            "SUPERUSER_EMAIL", "super@biblioteca.local"
        )
    )
    superuser_password: str = field(
        default_factory=lambda: os.environ.get(
            "SUPERUSER_PASSWORD", "SuperUsuario123!"
        )
    )
    superuser_name: str = field(
        default_factory=lambda: os.environ.get(
            "SUPERUSER_NAME", "Super Usuario"
        )
    )
    church_address: str = field(
        default_factory=lambda: os.environ.get(
            "CHURCH_ADDRESS", "Las Ilusiones 2194, Pedro Aguirre Cerda"
        )
    )
    sermon_category_name: str = field(
        default_factory=lambda: os.environ.get(
            "SERMON_CATEGORY_NAME", "Sermones"
        )
    )
    allowed_upload_types: List[str] = field(
        default_factory=lambda: [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain",
        ]
    )
    max_file_size_mb: int = field(
        default_factory=lambda: int(os.environ.get("MAX_FILE_SIZE_MB", "25"))
    )
    gemini_api_base: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_API_BASE", "https://generativelanguage.googleapis.com"
        ).rstrip("/")
    )
    gemini_api_version_hint: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_API_VERSION")
    )
    gemini_chat_model: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_CHAT_MODEL")
    )
    gemini_default_model: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_DEFAULT_MODEL")
    )
    gemini_max_output_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "400")
        )
    )
    gemini_fallback_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_FALLBACK_API_KEY")
    )
    chat_system_prompt: str = field(
        default_factory=lambda: os.environ.get(
            "CHATBOT_SYSTEM_PROMPT",
            (
                "Eres 'Luz de Guía', un asistente virtual respetuoso de la Asamblea "
                "Apostólica de la Fe en Cristo Jesús. Respondes con calidez acerca de "
                "la Biblia, la fe cristiana evangélica, personajes y acontecimientos "
                "bíblicos o históricos relacionados, denominaciones y prácticas "
                "cristianas, música y liturgia, así como consejos devocionales y "
                "pastorales. Si la consulta se aleja por completo del ámbito espiritual, "
                "orienta de manera amable hacia un tema afín sin reprender ni inventar "
                "información. Mantén un tono pastoral, cercano y esperanzador."
            ),
        )
    )
    mapbox_token: Optional[str] = field(
        default_factory=lambda: os.environ.get("MAPBOX_TOKEN")
    )

    @property
    def gemini_api_key(self) -> Optional[str]:
        """Obtiene la API key tomando en cuenta las variantes heredadas."""
        return (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or self.gemini_fallback_api_key
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve configuración cacheada para reutilizar en todo el proyecto."""
    return Settings()


__all__ = ["Settings", "get_settings"]
