"""Credenciales de Spotify: variables de entorno/.env primero, keyring después."""
from __future__ import annotations

import os

from dotenv import load_dotenv

from ..core.errors import SpotifyError

_SERVICE = "Spotify2Audio"


def load_credentials() -> tuple[str, str]:
    load_dotenv()
    cid = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if cid and secret:
        return cid, secret
    try:
        import keyring
        cid = keyring.get_password(_SERVICE, "client_id") or ""
        secret = keyring.get_password(_SERVICE, "client_secret") or ""
    except Exception:  # keyring ausente o sin backend
        pass
    if not (cid and secret):
        raise SpotifyError("Faltan credenciales de Spotify (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET).")
    return cid, secret


def save_credentials(client_id: str, client_secret: str) -> None:
    import keyring
    keyring.set_password(_SERVICE, "client_id", client_id.strip())
    keyring.set_password(_SERVICE, "client_secret", client_secret.strip())
