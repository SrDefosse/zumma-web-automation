"""Normalizacion de texto y de nombres de archivo."""

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def clean_text(raw: str | None) -> str:
    """Colapsa espacios y normaliza unicode. Devuelve "" si la entrada es vacia."""
    if not raw:
        return ""
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFC", raw)).strip()


def safe_filename(raw: str, max_length: int = 60) -> str:
    """Convierte texto arbitrario en un segmento de nombre de archivo seguro.

    El nombre viene de la pagina scrapeada, asi que es entrada no confiable: sin esto,
    un producto llamado "../../etc/passwd" escribiria fuera del directorio de imagenes.
    """
    ascii_only = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    slug = _UNSAFE_FILENAME_RE.sub("-", ascii_only).strip("-._")
    return slug[:max_length] or "producto"
