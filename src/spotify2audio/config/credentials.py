"""Credenciales de Spotify. Orden de búsqueda:
variables de entorno -> .env (carpeta actual, junto al .exe o en la carpeta de configuración) -> keyring.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from ..core.errors import MissingCredentialsError
from .paths import config_dir

log = logging.getLogger(__name__)
_SERVICE = "Spotify2Audio"
TOKEN_CACHE = "spotify_token.json"


def _env_files() -> list[Path]:
    files = []
    found = find_dotenv(usecwd=True)
    if found:
        files.append(Path(found))
    if getattr(sys, "frozen", False):
        files.append(Path(sys.executable).parent / ".env")
    files.append(config_dir() / ".env")
    return files


def load_credentials() -> tuple[str, str]:
    for f in _env_files():
        if f.is_file():
            load_dotenv(f, override=False)
    cid = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if cid and secret:
        return cid, secret
    try:
        import keyring
        cid = keyring.get_password(_SERVICE, "client_id") or ""
        secret = keyring.get_password(_SERVICE, "client_secret") or ""
    except Exception:  # noqa: BLE001 - keyring ausente o sin backend
        cid = secret = ""
    if not (cid and secret):
        raise MissingCredentialsError("Faltan las credenciales de Spotify (Client ID y Client Secret).")
    return cid, secret


def save_credentials(client_id: str, client_secret: str) -> str:
    """Guarda las credenciales y devuelve dónde ('el Administrador de credenciales' o un archivo)."""
    client_id, client_secret = client_id.strip(), client_secret.strip()
    where = None
    try:
        import keyring
        keyring.set_password(_SERVICE, "client_id", client_id)
        keyring.set_password(_SERVICE, "client_secret", client_secret)
        if keyring.get_password(_SERVICE, "client_secret") == client_secret:     # comprueba que no es un backend nulo
            where = "el Administrador de credenciales de Windows" if sys.platform == "win32" else "el llavero del sistema"
    except Exception as exc:  # noqa: BLE001
        log.info("keyring no disponible (%s); se usará un archivo .env", exc)
    if where is None:
        env = config_dir() / ".env"
        env.write_text(f"SPOTIFY_CLIENT_ID={client_id}\nSPOTIFY_CLIENT_SECRET={client_secret}\n", encoding="utf-8")
        try:
            env.chmod(0o600)
        except OSError:
            pass
        where = str(env)
    os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"] = client_id, client_secret
    (config_dir() / TOKEN_CACHE).unlink(missing_ok=True)       # el token antiguo pertenece a otra app
    return where
