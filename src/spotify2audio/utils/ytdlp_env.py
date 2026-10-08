"""yt-dlp necesita un runtime de JavaScript (Deno recomendado) para YouTube desde nov-2025."""
from __future__ import annotations

import shutil


def check_js_runtime() -> tuple[str | None, str]:
    """Devuelve (runtime_encontrado | None, mensaje)."""
    if shutil.which("deno"):
        return "deno", "Deno encontrado"
    for other in ("node", "bun"):
        if shutil.which(other):
            return other, (f"Se encontró {other}, pero yt-dlp solo activa Deno por defecto. "
                           "Instala Deno: winget install DenoLand.Deno")
    return None, ("No hay runtime de JavaScript: las descargas de YouTube pueden fallar. "
                  "Instala Deno: winget install DenoLand.Deno (y reabre la terminal)")
