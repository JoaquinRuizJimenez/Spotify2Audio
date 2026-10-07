from __future__ import annotations

import threading

from .errors import CancelledError


class CancellationToken:
    """Token compartido entre la GUI (que cancela) y los servicios (que comprueban)."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("Operación cancelada por el usuario.")
