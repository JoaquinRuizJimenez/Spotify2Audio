"""Ruta final de cada pista: [Destino]/[Artista]/[Álbum]/01 - Título.ext"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterable

from ..models.options import JobOptions
from ..models.track import Track
from ..utils.sanitize import sanitize_component, track_filename

MAX_PATH_LEN = 240      # margen bajo el límite clásico de 260 de Windows


class Organizer:
    def __init__(self, options: JobOptions, multi_disc_albums: set[tuple[str, str]] | None = None) -> None:
        self.options = options
        self.multi_disc_albums = multi_disc_albums or set()
        self._claimed: dict[Path, str] = {}
        self._lock = threading.Lock()

    @classmethod
    def for_playlist(cls, options: JobOptions, tracks: Iterable[Track]) -> "Organizer":
        """Detecta álbumes multidisco para numerar '2-01 - ...' de forma coherente."""
        multi = {(t.folder_artist, t.album) for t in tracks if t.disc_number > 1}
        return cls(options, multi)

    def target_path(self, track: Track) -> Path:
        """Ruta única y válida; reserva el nombre para evitar colisiones entre pistas distintas."""
        base = self._fit(track)
        with self._lock:
            path, n = base, 2
            while self._claimed.get(path, track.spotify_id) != track.spotify_id:   # ocupada por otra pista
                path = base.with_name(f"{base.stem} ({n}){base.suffix}")
                n += 1
            self._claimed[path] = track.spotify_id
        return path

    def exists(self, track: Track) -> bool:
        p = self.target_path(track)
        return p.exists() and p.stat().st_size > 0

    # ---- internos -----------------------------------------------------------
    def _build(self, t: Track, max_len: int) -> Path:
        ext = self.options.output_format.extension
        root = self.options.output_dir
        if not self.options.create_folders:
            name = sanitize_component(f"{t.primary_artist} - {t.title}", max_len=max_len, fallback="Untitled")
            return root / f"{name}.{ext}"
        multi = (t.folder_artist, t.album) in self.multi_disc_albums or t.disc_number > 1
        number = t.track_number or t.playlist_position or 1
        return (root
                / sanitize_component(t.folder_artist, max_len, "Unknown Artist")
                / sanitize_component(t.album, max_len, "Unknown Album")
                / track_filename(number, t.title, ext, t.disc_number, multi, max_len))

    def _fit(self, t: Track) -> Path:
        for max_len in (100, 80, 60, 45, 30, 20):
            path = self._build(t, max_len)
            if len(str(path)) <= MAX_PATH_LEN:
                return path
        return path
