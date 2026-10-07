"""Localiza FFmpeg: carpeta empaquetada/bin del proyecto primero, PATH después."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ..core.errors import DependencyMissingError

_EXE = ".exe" if sys.platform == "win32" else ""
_INSTALL_HINT = (
    "FFmpeg no encontrado. En Windows: `winget install Gyan.FFmpeg` y reabre la terminal, "
    "o copia ffmpeg.exe y ffprobe.exe en la carpeta bin/ del proyecto."
)


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):                      # PyInstaller
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        dirs.append(Path(sys.executable).parent)
    dirs.append(Path(__file__).resolve().parents[3] / "bin")  # raíz del proyecto/bin
    return dirs


def find_tool(name: str = "ffmpeg") -> str | None:
    for d in _candidate_dirs():
        p = d / f"{name}{_EXE}"
        if p.is_file():
            return str(p)
    return shutil.which(name)


def ensure_ffmpeg() -> tuple[str, str]:
    """Devuelve (ruta_ffmpeg, ruta_ffprobe) o lanza DependencyMissingError."""
    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        raise DependencyMissingError(_INSTALL_HINT)
    return ffmpeg, ffprobe


def ffmpeg_version(ffmpeg_path: str) -> str:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # sin ventana de consola
    out = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True,
                         timeout=10, creationflags=flags)
    return out.stdout.splitlines()[0] if out.stdout else "desconocida"
