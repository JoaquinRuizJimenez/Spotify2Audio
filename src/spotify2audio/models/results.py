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
class JobSummary:
    playlist_name: str = ""
    results: list[TrackResult] = field(default_factory=list)

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
    def failed_results(self) -> list[TrackResult]:
        return [r for r in self.results if r.status is TrackStatus.FAILED]

    def failed_report(self) -> str:
        """Texto para failed_tracks.txt."""
        return "\n".join(f"{r.track} | {r.error or 'error desconocido'}" for r in self.failed_results)

    def __str__(self) -> str:
        return f"{self.ok} correctas, {self.skipped} omitidas, {self.failed} fallidas de {len(self.results)}"
