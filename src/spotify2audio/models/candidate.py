from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    """Resultado de búsqueda en YouTube / YouTube Music para una pista."""

    video_id: str
    title: str
    channel: str = ""
    duration_s: float | None = None
    source: str = "youtube"          # "ytmusic" | "youtube"
    score: float = 0.0
    notes: list[str] = field(default_factory=list)   # explicación de la puntuación (depuración)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"
