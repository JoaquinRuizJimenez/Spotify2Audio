from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    """Metadatos de una pista según Spotify."""

    spotify_id: str
    title: str
    artists: tuple[str, ...]
    album: str
    album_artist: str = ""
    track_number: int = 1
    disc_number: int = 1
    total_tracks: int = 0
    year: int | None = None
    duration_ms: int = 0
    cover_url: str | None = None
    isrc: str | None = None
    explicit: bool = False
    playlist_position: int = 0  # posición 1-based dentro de la playlist

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else "Unknown Artist"

    @property
    def artist_display(self) -> str:
        return ", ".join(self.artists) if self.artists else "Unknown Artist"

    @property
    def folder_artist(self) -> str:
        """Artista usado para carpetas: el del álbum si existe (agrupa mejor)."""
        return self.album_artist or self.primary_artist

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0

    def __str__(self) -> str:
        return f"{self.artist_display} - {self.title}"
