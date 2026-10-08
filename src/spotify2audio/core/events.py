"""Eventos que el pipeline emite; la GUI (o el CLI) los consume. Pueden llegar desde hilos de fondo."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Union

from ..models.results import JobSummary, TrackResult
from ..models.track import Track


class Stage(str, Enum):
    SEARCHING = "Buscando"
    DOWNLOADING = "Descargando"
    CONVERTING = "Convirtiendo"
    TAGGING = "Etiquetando"


@dataclass(frozen=True)
class JobStarted:
    playlist_name: str
    total: int


@dataclass(frozen=True)
class TrackStarted:
    index: int          # 0-based
    total: int
    track: Track


@dataclass(frozen=True)
class TrackProgress:
    index: int
    track: Track
    stage: Stage
    fraction: float     # progreso de ESTA pista, 0..1 (todas las etapas)


@dataclass(frozen=True)
class TrackFinished:
    index: int
    total: int
    result: TrackResult
    completed: int      # pistas ya terminadas (barra global = completed / total)


@dataclass(frozen=True)
class SyncProgress:
    done: int
    total: int
    current: str        # archivo que se está copiando ("" al terminar)


@dataclass(frozen=True)
class JobFinished:
    summary: JobSummary


Event = Union[JobStarted, TrackStarted, TrackProgress, TrackFinished, SyncProgress, JobFinished]
EventCallback = Callable[[Event], None]
