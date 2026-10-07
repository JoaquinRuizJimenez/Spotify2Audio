"""Nombres de archivo seguros (pensado para Windows, válido también en macOS/Linux)."""
from __future__ import annotations

import re
import unicodedata

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(name: str, max_len: int = 100, fallback: str = "Unknown") -> str:
    """Convierte un texto en un nombre válido para un archivo o carpeta."""
    name = unicodedata.normalize("NFC", name or "")
    name = _INVALID.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")            # Windows no admite punto/espacio final
    if len(name) > max_len:
        name = name[:max_len].rstrip(". ")
    if not name:
        return fallback
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name


def track_filename(track_number: int, title: str, extension: str, disc_number: int = 1,
                   multi_disc: bool = False, max_len: int = 100) -> str:
    """'01 - Título.mp3' (o '1-01 - Título.mp3' en álbumes multidisco)."""
    prefix = f"{disc_number}-{track_number:02d}" if multi_disc else f"{track_number:02d}"
    safe_title = sanitize_component(title, max_len=max_len, fallback="Untitled")
    return f"{prefix} - {safe_title}.{extension.lstrip('.')}"
