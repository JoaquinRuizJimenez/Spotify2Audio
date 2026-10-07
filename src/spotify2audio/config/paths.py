from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_log_dir, user_music_dir

APP_NAME = "Spotify2Audio"


def config_dir() -> Path:
    p = Path(user_config_dir(APP_NAME, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = Path(user_cache_dir(APP_NAME, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = Path(user_log_dir(APP_NAME, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_file() -> Path:
    return config_dir() / "settings.json"


def default_output_dir() -> Path:
    return Path(user_music_dir() or Path.home() / "Music") / APP_NAME
