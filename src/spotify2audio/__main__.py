"""Fase 1: comprobación del entorno. La GUI se conectará aquí en la Fase 6."""
from __future__ import annotations

import logging

from .config.credentials import load_credentials
from .config.settings import Settings
from .core.errors import AppError
from .utils.ffmpeg_check import ensure_ffmpeg, ffmpeg_version
from .utils.logging_setup import setup_logging


def main() -> int:
    setup_logging()
    log = logging.getLogger("spotify2audio")
    ok = True

    try:
        ffmpeg, _ = ensure_ffmpeg()
        log.info("FFmpeg OK: %s", ffmpeg_version(ffmpeg))
    except AppError as exc:
        log.error("%s", exc)
        ok = False

    try:
        load_credentials()
        log.info("Credenciales de Spotify OK")
    except AppError as exc:
        log.error("%s", exc)
        ok = False

    settings = Settings.load()
    log.info("Carpeta de salida: %s", settings.output_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
