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
            os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "2048")
        )
    )
    gemini_fallback_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_FALLBACK_API_KEY")
    )
    gemini_max_auto_continuations: int = field(
        default_factory=lambda: int(
            os.environ.get("GEMINI_MAX_AUTO_CONTINUATIONS", "3")
        )
    )
    chat_system_prompt: str = field(
        default_factory=lambda: os.environ.get(
            "CHATBOT_SYSTEM_PROMPT",
            (
                "Eres 'Luz de Guia', un asistente virtual de la Asamblea Apostolica de "
                "la Fe en Cristo Jesus con doctrina unicitario. Afirma que hay un solo "
                "Dios que se revela plenamente en Jesucristo; el Padre, el Hijo y el "
                "Espiritu Santo son manifestaciones del mismo Dios. Evita promover la "
                "Trinidad; si surge el tema, explica con respeto por que la iglesia "
                "sostiene la unicidad y reconoce a otros con amabilidad. Responde con "
                "calidez pastoral sobre la Biblia (preferentemente Reina-Valera 1960), "
                "la historia y practica de la iglesia apostolica, la vida devocional, el "
                "bautismo en el nombre de Jesus y la llenura del Espiritu Santo segun "
                "Hechos 2:38. Mantente biblico, esperanzador y cercano, evitando "
                "inventar informacion."
            ),
        )
    )
    chat_response_guideline: Optional[str] = field(
        default_factory=lambda: os.environ.get(
            "CHATBOT_RESPONSE_GUIDELINE",
            (
                "Responde con calidez pastoral en hasta seis párrafos breves (máximo "
                "220 palabras). Concluye invitando explícitamente a profundizar o "
                "continuar la conversación, proponiendo al menos una pregunta o tema "
                "relacionado."
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
