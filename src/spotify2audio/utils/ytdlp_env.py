"""yt-dlp necesita un runtime de JavaScript (Deno recomendado) para YouTube desde nov-2025."""
from __future__ import annotations

import os
import shutil

from .ffmpeg_check import tool_dirs


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


def prepare_environment() -> None:
    """Antepone al PATH las carpetas con herramientas incluidas (deno/ffmpeg en el .exe o en bin/)."""
    current = os.environ.get("PATH", "")
    extra = [str(d) for d in tool_dirs() if d.is_dir() and str(d) not in current.split(os.pathsep)]
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [current])
