"""Descarga la portada, intenta una versión de mayor resolución y la deja lista para incrustar."""
from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

from ..config.paths import cache_dir
from ..utils.retry import retry

log = logging.getLogger(__name__)

# i.scdn.co: ...b273 = 640 px (lo que da la API); ...82c1 = original sin reescalar (no documentado).
_STD_PREFIX = "ab67616d0000b273"
_HIRES_PREFIX = "ab67616d000082c1"


@dataclass(frozen=True)
class CoverImage:
    data: bytes          # JPEG baseline
    width: int
    height: int
    mime: str = "image/jpeg"


def upgrade_spotify_url(url: str) -> str:
    return url.replace(_STD_PREFIX, _HIRES_PREFIX) if _STD_PREFIX in url else url


class CoverFetcher:
    def __init__(self, max_px: int = 1000, jpeg_quality: int = 90, try_hires: bool = True,
                 cache_path: Path | None = None) -> None:
        """max_px: lado máximo incrustado. 1000 px es nítido y no hincha los archivos para iPod."""
        self.max_px, self.quality, self.try_hires = max_px, jpeg_quality, try_hires
        self.cache_path = Path(cache_path) if cache_path else cache_dir() / "covers"
        self._memory: dict[str, CoverImage | None] = {}

    def fetch(self, url: str | None) -> CoverImage | None:
        """Nunca lanza: una portada ausente no debe impedir la descarga de la canción."""
        if not url:
            return None
        if url in self._memory:
            return self._memory[url]
        cover = self._from_disk(url) or self._download(url)
        self._memory[url] = cover
        return cover

    # --- internos -----------------------------------------------------------
    @retry(attempts=3, delay=1.0, exceptions=(requests.RequestException,))
    def _get(self, url: str) -> bytes:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.content

    def _download(self, url: str) -> CoverImage | None:
        urls = [upgrade_spotify_url(url), url] if self.try_hires and upgrade_spotify_url(url) != url else [url]
        for candidate in urls:
            try:
                cover = self._process(self._get(candidate))
            except (requests.RequestException, UnidentifiedImageError, OSError) as exc:
                log.debug("Portada no disponible en %s: %s", candidate, exc)
                continue
            self._to_disk(url, cover)
            return cover
        log.warning("No se pudo obtener la portada: %s", url)
        return None

    def _process(self, raw: bytes) -> CoverImage:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if max(img.size) > self.max_px:
            img.thumbnail((self.max_px, self.max_px), Image.LANCZOS)
        buf = io.BytesIO()
        # baseline (no progresivo): los iPod y reproductores antiguos no leen JPEG progresivo
        img.save(buf, "JPEG", quality=self.quality, progressive=False, optimize=False)
        return CoverImage(buf.getvalue(), img.width, img.height)

    def _key(self, url: str) -> Path:
        return self.cache_path / f"{hashlib.sha1(url.encode()).hexdigest()}_{self.max_px}.jpg"

    def _from_disk(self, url: str) -> CoverImage | None:
        p = self._key(url)
        try:
            if p.exists():
                data = p.read_bytes()
                with Image.open(io.BytesIO(data)) as im:
                    return CoverImage(data, im.width, im.height)
        except (OSError, UnidentifiedImageError):
            pass
        return None

    def _to_disk(self, url: str, cover: CoverImage) -> None:
        try:
            self.cache_path.mkdir(parents=True, exist_ok=True)
            self._key(url).write_bytes(cover.data)
        except OSError:
            pass
