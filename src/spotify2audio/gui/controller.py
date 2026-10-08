"""Puente entre la GUI (hilo principal) y el trabajo pesado (hilos de fondo) mediante una cola."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

from ..core.cancellation import CancellationToken
from ..core.errors import AppError, MissingCredentialsError
from ..core.pipeline import Pipeline
from ..models.options import JobOptions
from ..models.playlist import Playlist
from ..services.spotify_client import SpotifyClient

log = logging.getLogger(__name__)

# Tipos de mensaje que recibe la GUI
LOAD_PROGRESS, LOADED, LOAD_ERROR, EVENT, JOB_DONE, JOB_ERROR, NEED_CREDENTIALS = (
    "load_progress", "loaded", "load_error", "event", "job_done", "job_error", "need_credentials")


class Controller:
    def __init__(self, client_factory: Callable[[], Any] = SpotifyClient,
                 pipeline_factory: Callable[..., Pipeline] = Pipeline) -> None:
        self.queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._client_factory = client_factory
        self._pipeline_factory = pipeline_factory
        self._client = None                       # se reutiliza: el login de Spotify se hace una vez
        self._thread: threading.Thread | None = None
        self._cancel: CancellationToken | None = None

    # ------------------------------------------------------------------ estado
    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def drain(self, limit: int = 300) -> list[tuple[str, Any]]:
        items: list[tuple[str, Any]] = []
        while len(items) < limit:
            try:
                items.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return items

    # ----------------------------------------------------------------- acciones
    def load_playlist(self, url: str) -> bool:
        return self._launch(self._load_worker, url)

    def start(self, playlist: Playlist, options: JobOptions) -> bool:
        if self.busy:
            return False
        self._cancel = CancellationToken()
        return self._launch(self._job_worker, playlist, options, self._cancel)

    def reset_client(self) -> None:
        """Olvida el cliente de Spotify (p. ej. tras guardar credenciales nuevas)."""
        self._client = None

    def cancel(self) -> None:
        if self._cancel:
            self._cancel.cancel()

    def shutdown(self, timeout: float = 8.0) -> None:
        """Cancela y espera un poco a que los hilos terminen y limpien sus temporales."""
        self.cancel()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    # ------------------------------------------------------------------ hilos
    def _launch(self, target: Callable, *args) -> bool:
        if self.busy:
            return False
        self._thread = threading.Thread(target=target, args=args, daemon=True, name="s2a-worker")
        self._thread.start()
        return True

    def _put(self, kind: str, payload: Any = None) -> None:
        self.queue.put((kind, payload))

    def _load_worker(self, url: str) -> None:
        try:
            if self._client is None:
                self._client = self._client_factory()      # puede abrir el navegador la primera vez
            playlist = self._client.get_playlist(
                url, progress=lambda done, total: self._put(LOAD_PROGRESS, (done, total)))
            self._put(LOADED, playlist)
        except MissingCredentialsError as exc:
            self._put(NEED_CREDENTIALS, str(exc))
        except AppError as exc:
            self._put(LOAD_ERROR, str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Error inesperado al cargar la playlist")
            self._put(LOAD_ERROR, f"Error inesperado: {type(exc).__name__}: {exc}")

    def _job_worker(self, playlist: Playlist, options: JobOptions, cancel: CancellationToken) -> None:
        try:
            pipeline = self._pipeline_factory(options, on_event=lambda ev: self._put(EVENT, ev))
            summary = pipeline.run(playlist, cancel=cancel)
            self._put(JOB_DONE, summary)
        except AppError as exc:
            self._put(JOB_ERROR, str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Error inesperado en el trabajo")
            self._put(JOB_ERROR, f"Error inesperado: {type(exc).__name__}: {exc}")
