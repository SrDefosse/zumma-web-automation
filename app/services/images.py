"""Descarga y almacenamiento local de imagenes de producto."""

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.normalization import safe_filename

log = get_logger(__name__)

_ALLOWED_PREFIX = "image/"
_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_EXTENSION = ".jpg"


class ImageDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredImage:
    filename: str
    file_path: str
    content_type: str | None
    size_bytes: int


def _extension_for(content_type: str | None, url: str) -> str:
    """Extension real del archivo.

    Se deduce del Content-Type y, si falta, de la URL: forzar .jpg para todo deja los
    PNG y WEBP con una extension que miente y los clientes pueden rechazarlos.
    """
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}:
        return suffix
    return _DEFAULT_EXTENSION


def build_filename(product_name: str, url: str, content_type: str | None = None) -> str:
    """Nombre de archivo determinista y seguro: slug del producto + hash de la URL."""
    digest = hashlib.sha256(f"{product_name}|{url}".encode()).hexdigest()[:16]
    return f"{safe_filename(product_name)}-{digest}{_extension_for(content_type, url)}"


async def download_image(
    url: str, product_name: str, client: httpx.AsyncClient | None = None
) -> StoredImage:
    """Descarga una imagen a storage/images y devuelve sus metadatos.

    Lanza ImageDownloadError ante cualquier problema; el caller decide si el producto
    se guarda sin imagen o si el job falla.
    """
    if not url:
        raise ImageDownloadError("URL de imagen vacia")

    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=30)
    try:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type")
        if content_type and not content_type.lower().startswith(_ALLOWED_PREFIX):
            raise ImageDownloadError(f"Content-Type inesperado: {content_type}")
        if len(response.content) > _MAX_BYTES:
            raise ImageDownloadError(f"Imagen demasiado grande: {len(response.content)} bytes")
        if not response.content:
            raise ImageDownloadError("Respuesta vacia")

        filename = build_filename(product_name, url, content_type)
        destination = settings.images_dir / filename

        images_root = settings.images_dir.resolve()
        if not destination.resolve().is_relative_to(images_root):
            raise ImageDownloadError(f"Ruta de destino invalida: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)

        return StoredImage(
            filename=filename,
            file_path=str(destination),
            content_type=content_type,
            size_bytes=len(response.content),
        )
    except httpx.HTTPError as exc:
        raise ImageDownloadError(f"Fallo la descarga de {url}: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()


def delete_image(file_path: str) -> None:
    """Borra un archivo descargado. Usado para no dejar huerfanos si el job falla."""
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("no se pudo borrar la imagen", file_path=file_path, error=str(exc))
