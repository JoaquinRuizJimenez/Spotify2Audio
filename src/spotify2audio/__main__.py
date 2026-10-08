"""Punto de entrada: abre la interfaz gráfica. `--check` comprueba el entorno (FFmpeg, Deno, credenciales)."""
from __future__ import annotations

import logging

from .config.credentials import load_credentials
from .config.settings import Settings
from .core.errors import AppError
from .utils.ffmpeg_check import ensure_ffmpeg, ffmpeg_version
from .utils.logging_setup import setup_logging
from .utils.ytdlp_env import check_js_runtime, prepare_environment


def check_environment() -> int:
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

    runtime, msg = check_js_runtime()
    (log.info if runtime == "deno" else log.warning)("JS runtime: %s", msg)

    settings = Settings.load()
    log.info("Carpeta de salida: %s", settings.output_dir)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    import sys
    prepare_environment()
    args = sys.argv[1:] if argv is None else argv
    if "--check" in args:
        return check_environment()
    from .gui.app import run_gui
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
