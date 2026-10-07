from __future__ import annotations

from dataclasses import dataclass, field

from .track import Track


@dataclass
class Playlist:
    spotify_id: str
    name: str
    owner: str = ""
    cover_url: str | None = None
    url: str = ""
    tracks: list[Track] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # entradas no descargables (locales, podcasts, borradas)

    def __len__(self) -> int:
        return len(self.tracks)
