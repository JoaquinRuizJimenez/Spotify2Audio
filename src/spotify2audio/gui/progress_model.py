"""Traduce los eventos del pipeline a textos y progreso global (sin Tk, fácil de probar)."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.events import TrackFinished, TrackProgress
from ..models.results import TrackResult, TrackStatus

MAX_REASON = 70


@dataclass(frozen=True)
class RowState:
    text: str
    tag: str        # queued | active | ok | failed | skipped | cancelled


QUEUED = RowState("En cola", "queued")
ACTIVE = RowState("Iniciando…", "active")


def row_for_progress(ev: TrackProgress) -> RowState:
    return RowState(f"{ev.stage.value} {ev.fraction:.0%}", "active")


def row_for_result(result: TrackResult) -> RowState:
    status = result.status
    if status is TrackStatus.OK:
        return RowState("Completada", "ok")
    if status is TrackStatus.SKIPPED:
        return RowState("Duplicada" if result.error else "Ya existía", "skipped")
    if status is TrackStatus.CANCELLED:
        return RowState("Cancelada", "cancelled")
    reason = (result.error or "error desconocido").replace("\n", " ")
    if len(reason) > MAX_REASON:
        reason = reason[:MAX_REASON - 1] + "…"
    return RowState(f"Error: {reason}", "failed")


class ProgressTracker:
    """Progreso global = pistas terminadas + fracción de las que están en curso."""

    def __init__(self, total: int) -> None:
        self.total = max(total, 0)
        self.completed = 0
        self._partial: dict[int, float] = {}

    def on_progress(self, ev: TrackProgress) -> None:
        self._partial[ev.index] = ev.fraction

    def on_finished(self, ev: TrackFinished) -> None:
        self._partial.pop(ev.index, None)
        self.completed = max(self.completed, ev.completed)

    @property
    def fraction(self) -> float:
        if not self.total:
            return 0.0
        return min((self.completed + sum(self._partial.values())) / self.total, 1.0)

    @property
    def label(self) -> str:
        return f"{self.completed} de {self.total}"
