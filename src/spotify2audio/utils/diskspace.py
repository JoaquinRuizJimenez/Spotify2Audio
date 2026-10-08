from __future__ import annotations

import shutil
from pathlib import Path


def nearest_existing(path: Path) -> Path:
    path = Path(path).resolve()
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(nearest_existing(path)).free
