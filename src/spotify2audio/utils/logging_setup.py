from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from ..config.paths import log_dir

_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO, extra_handlers: list[logging.Handler] | None = None) -> None:
    """Consola + archivo rotativo. `extra_handlers` permite enganchar la GUI más adelante."""
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:       # evita duplicados si se llama dos veces
        return
    formatter = logging.Formatter(_FMT)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(log_dir() / "spotify2audio.log", maxBytes=1_000_000,
                            backupCount=3, encoding="utf-8"),
        *(extra_handlers or []),
    ]
    for h in handlers:
        h.setFormatter(formatter)
        root.addHandler(h)
