"""Cliente de Spotify: URL de playlist -> Playlist.

Desde feb-2026, en apps en Development Mode Spotify solo devuelve el contenido de
playlists de las que el usuario es dueño o colaborador, y exige sesión de usuario (OAuth).
Por eso se usa SpotifyOAuth. Los endpoints son /playlists/{id}/items (antes /tracks) y
cada entrada trae `item` (antes `track`); aquí se aceptan ambos nombres por robustez.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

import requests
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOauthError, SpotifyOAuth

from ..config.credentials import load_credentials
from ..config.paths import config_dir
from ..core.errors import InvalidSpotifyUrlError, SpotifyError
from ..models.playlist import Playlist
from ..models.track import Track

log = logging.getLogger(__name__)

SCOPES = "playlist-read-private playlist-read-collaborative"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
_ID = r"[A-Za-z0-9]{22}"
_PLAYLIST_RE = re.compile(rf"playlist[/:]({_ID})")
_BARE_RE = re.compile(rf"^{_ID}$")


# --------------------------------------------------------------------------- parsing
def parse_playlist_id(text: str) -> str:
    """Acepta URL (con /intl-xx/, ?si=...), URI spotify:playlist:ID o el ID suelto."""
    text = (text or "").strip()
    if not text:
        raise InvalidSpotifyUrlError("Pega la URL de una playlist de Spotify.")
    if _BARE_RE.match(text):
        return text
    match = _PLAYLIST_RE.search(text)
    if match:
        return match.group(1)
    if "spotify.link" in text or "spoti.fi" in text:
        raise InvalidSpotifyUrlError(
            "Los enlaces cortos no se admiten. Abre el enlace en el navegador y copia la URL completa.")
    raise InvalidSpotifyUrlError("Eso no parece una URL de playlist de Spotify.")


def _pick_cover(images: list[dict[str, Any]] | None) -> str | None:
    if not images:
        return None
    return max(images, key=lambda i: i.get("width") or 0).get("url")


def parse_track(entry: dict[str, Any], position: int) -> Track | None:
    """Convierte una entrada de playlist en Track; None si no es una pista descargable."""
    raw = entry.get("item") or entry.get("track")     # `item` desde feb-2026
    if not raw or raw.get("is_local") or raw.get("type", "track") != "track" or not raw.get("id"):
        return None
    album = raw.get("album") or {}
    artists = tuple(a["name"] for a in raw.get("artists") or [] if a.get("name"))
    album_artists = [a["name"] for a in album.get("artists") or [] if a.get("name")]
    release = (album.get("release_date") or "")[:4]
    return Track(
        spotify_id=raw["id"],
        title=raw.get("name") or "Untitled",
        artists=artists,
        album=album.get("name") or "Unknown Album",
        album_artist=album_artists[0] if album_artists else "",
        track_number=raw.get("track_number") or 1,
        disc_number=raw.get("disc_number") or 1,
        total_tracks=album.get("total_tracks") or 0,
        year=int(release) if release.isdigit() else None,
        duration_ms=raw.get("duration_ms") or 0,
        cover_url=_pick_cover(album.get("images")),
        isrc=(raw.get("external_ids") or {}).get("isrc"),
        explicit=bool(raw.get("explicit")),
        playlist_position=position,
    )


# --------------------------------------------------------------------------- errores
def _translate(exc: Exception) -> SpotifyError:
    if isinstance(exc, SpotifyException):
        status = exc.http_status
        if status == 401:
            return SpotifyError("Sesión de Spotify caducada o inválida. Borra spotify_token.json y reintenta.")
        if status == 403:
            return SpotifyError(
                "Spotify denegó el acceso (403). Causas habituales: la playlist no es tuya ni colaborativa "
                "(restricción de Spotify desde feb-2026), tu cuenta no está añadida a la app en el Dashboard, "
                "o el dueño de la app no tiene Premium.")
        if status == 404:
            return SpotifyError("Playlist no encontrada (404). Comprueba la URL; si es privada, inicia sesión con su dueño.")
        if status == 429:
            return SpotifyError("Spotify limitó las peticiones (429). Espera unos minutos y reintenta.")
        return SpotifyError(f"Error de Spotify ({status}): {exc.msg}")
    if isinstance(exc, SpotifyOauthError):
        return SpotifyError(f"Fallo en el inicio de sesión de Spotify: {exc}")
    if isinstance(exc, requests.exceptions.RequestException):
        return SpotifyError(f"Sin conexión con Spotify: {exc}")
    return SpotifyError(str(exc))


# --------------------------------------------------------------------------- cliente
class SpotifyClient:
    def __init__(self, sp: Any | None = None) -> None:
        """`sp` permite inyectar un cliente falso en los tests."""
        self._sp = sp or self._build()

    @staticmethod
    def _build() -> spotipy.Spotify:
        client_id, client_secret = load_credentials()
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI),
            scope=SCOPES,
            cache_path=str(config_dir() / "spotify_token.json"),
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=3)

    def get_playlist(self, url_or_id: str,
                     progress: Callable[[int, int], None] | None = None) -> Playlist:
        pid = parse_playlist_id(url_or_id)
        try:
            meta = self._sp._get(f"playlists/{pid}", fields="id,name,owner(display_name,id),images,external_urls")
            playlist = Playlist(
                spotify_id=pid,
                name=meta.get("name") or "Playlist",
                owner=(meta.get("owner") or {}).get("display_name") or (meta.get("owner") or {}).get("id", ""),
                cover_url=_pick_cover(meta.get("images")),
                url=(meta.get("external_urls") or {}).get("spotify", ""),
            )
            offset = 0
            while True:
                page = self._sp._get(f"playlists/{pid}/items", limit=100, offset=offset, additional_types="track")
                entries = page.get("items") or []
                for i, entry in enumerate(entries):
                    position = offset + i + 1
                    track = parse_track(entry, position)
                    if track:
                        playlist.tracks.append(track)
                    else:
                        playlist.skipped.append(f"#{position}: no descargable (local, podcast o eliminada)")
                offset += len(entries)
                if progress:
                    progress(offset, page.get("total") or offset)
                if not page.get("next") or not entries:
                    break
        except SpotifyError:
            raise
        except Exception as exc:  # noqa: BLE001 - se traduce a error propio
            raise _translate(exc) from exc

        if not playlist.tracks and not playlist.skipped:
            log.warning("La playlist no devolvió pistas (¿no eres dueño/colaborador?)")
        return playlist
