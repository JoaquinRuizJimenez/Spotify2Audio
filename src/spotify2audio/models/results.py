from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .track import Track


class TrackStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"     # ya existía
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TrackResult:
    track: Track
    status: TrackStatus
    output_path: Path | None = None
    matched_url: str | None = None
    error: str | None = None


@dataclass
class SyncResult:
    """Resultado de copiar al dispositivo."""

    target: Path
    copied: int = 0
    skipped: int = 0                    # ya estaban en el dispositivo con el mismo tamaño
    failed: list[tuple[str, str]] = field(default_factory=list)    # (archivo, motivo)
    bytes_copied: int = 0
    cancelled: bool = False
    aborted: str | None = None          # motivo si se detuvo antes de terminar

    def __str__(self) -> str:
        text = f"{self.copied} copiadas, {self.skipped} ya estaban"
        return text + (f", {len(self.failed)} fallidas" if self.failed else "")


@dataclass
class JobSummary:
    playlist_name: str = ""
    results: list[TrackResult] = field(default_factory=list)
    m3u_path: Path | None = None
    sync: SyncResult | None = None
    sync_error: str | None = None

    def add(self, result: TrackResult) -> None:
        self.results.append(result)

    def _count(self, status: TrackStatus) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def ok(self) -> int:
        return self._count(TrackStatus.OK)

    @property
    def skipped(self) -> int:
        return self._count(TrackStatus.SKIPPED)

    @property
    def failed(self) -> int:
        return self._count(TrackStatus.FAILED)

    @property
    def cancelled(self) -> int:
        return self._count(TrackStatus.CANCELLED)

    @property
    def failed_results(self) -> list[TrackResult]:
        return [r for r in self.results if r.status is TrackStatus.FAILED]

    def failed_report(self) -> str:
        """Texto para failed_tracks.txt."""
        return "\n".join(f"{r.track} | {r.error or 'error desconocido'}" for r in self.failed_results)

    def __str__(self) -> str:
        extra = f", {self.cancelled} canceladas" if self.cancelled else ""
        return f"{self.ok} correctas, {self.skipped} omitidas, {self.failed} fallidas{extra} de {len(self.results)}"
