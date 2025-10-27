import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings


class StorageUnavailableError(RuntimeError):
    """Se��ala que el backend de almacenamiento no est�� configurado."""


@dataclass
class PresignedUpload:
    """Representa los datos necesarios para enviar un archivo directamente al backend."""

    url: str
    headers: Dict[str, str]
    key: str
    expires_in: int


@dataclass
class PresignedDownload:
    url: str
    expires_in: int


class StorageService:
    """Capa de abstracci��n sobre S3 u otros backends equivalentes."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = self._build_client() if settings.use_s3_storage else None

    def _build_client(self):
        if not self.settings.s3_bucket_name:
            return None
        kwargs: Dict[str, Optional[str]] = {
            "region_name": self.settings.s3_region_name,
            "endpoint_url": self.settings.s3_endpoint_url,
        }
        if self.settings.s3_access_key_id and self.settings.s3_secret_access_key:
            kwargs["aws_access_key_id"] = self.settings.s3_access_key_id
            kwargs["aws_secret_access_key"] = self.settings.s3_secret_access_key
        # Eliminar claves en None para evitar advertencias de boto3.
        clean_kwargs = {k: v for k, v in kwargs.items() if v}
        session = boto3.session.Session()
        return session.client("s3", config=Config(signature_version="s3v4"), **clean_kwargs)

    @property
    def enabled(self) -> bool:
        return self._client is not None and self.settings.use_s3_storage

    def _require_enabled(self):
        if not self.enabled:
            raise StorageUnavailableError(
                "El almacenamiento directo no est�� configurado correctamente."
            )

    def generate_object_key(self, filename: str) -> str:
        """Genera una ruta amigable manteniendo la extensi��n original."""
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", filename.strip().lower()).strip("-")
        if not safe_name:
            safe_name = "documento.pdf"
        return f"documents/{uuid4().hex}-{safe_name}"

    def create_presigned_upload(
        self, *, filename: str, content_type: str
    ) -> PresignedUpload:
        self._require_enabled()
        key = self.generate_object_key(filename)
        try:
            url = self._client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": self.settings.s3_bucket_name,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=self.settings.s3_presign_expiration_seconds,
            )
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(
                f"No se pudo generar la URL firmada: {error}"
            ) from error
        headers = {"Content-Type": content_type}
        return PresignedUpload(
            url=url,
            headers=headers,
            key=key,
            expires_in=self.settings.s3_presign_expiration_seconds,
        )

    def ensure_object_exists(self, key: str) -> bool:
        self._require_enabled()
        try:
            self._client.head_object(
                Bucket=self.settings.s3_bucket_name,
                Key=key,
            )
            return True
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey"}:
                return False
            raise

    def create_presigned_download(
        self,
        key: str,
        *,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        inline: bool = False,
    ) -> PresignedDownload:
        self._require_enabled()
        params = {
            "Bucket": self.settings.s3_bucket_name,
            "Key": key,
        }
        if filename:
            disposition = "inline" if inline else "attachment"
            safe = filename.replace('"', "")
            params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
        if content_type:
            params["ResponseContentType"] = content_type
        try:
            url = self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=self.settings.s3_presign_expiration_seconds,
            )
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(
                f"No se pudo firmar la descarga: {error}"
            ) from error
        return PresignedDownload(
            url=url,
            expires_in=self.settings.s3_presign_expiration_seconds,
        )


@lru_cache(maxsize=1)
def get_storage_service(settings: Optional[Settings] = None) -> StorageService:
    """Devuelve una instancia compartida del servicio de almacenamiento."""
    return StorageService(settings or get_settings())


__all__ = [
    "StorageService",
    "StorageUnavailableError",
    "get_storage_service",
    "PresignedUpload",
    "PresignedDownload",
]
