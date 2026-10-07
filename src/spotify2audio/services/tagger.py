"""Etiquetas y carátula: ID3v2.3 (MP3/WAV, máxima compatibilidad con iPod) y atoms MP4 (M4A)."""
from __future__ import annotations

import logging
from pathlib import Path

from mutagen.id3 import (APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, TXXX,
                         ID3NoHeaderError)
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.wave import WAVE

from ..core.errors import TaggingError
from ..models.options import OutputFormat
from ..models.track import Track
from .cover_fetcher import CoverImage

log = logging.getLogger(__name__)
_UTF16 = 1   # ID3v2.3 solo admite Latin-1 y UTF-16


class Tagger:
    def __init__(self, tag_wav: bool = False) -> None:
        """tag_wav: los grabadores de CD ignoran las etiquetas; actívalo solo si lo necesitas."""
        self.tag_wav = tag_wav

    def write(self, path: Path, track: Track, fmt: OutputFormat, cover: CoverImage | None = None,
              replaygain: tuple[float, float] | None = None) -> None:
        """replaygain = (ganancia_dB, pico_lineal) o None."""
        path = Path(path)
        try:
            if fmt is OutputFormat.MP3:
                tags = ID3()
                self._fill_id3(tags, track, cover, replaygain)
                tags.save(path, v1=0, v2_version=3)
            elif fmt is OutputFormat.M4A:
                self._write_mp4(path, track, cover, replaygain)
            elif self.tag_wav:
                audio = WAVE(path)
                audio.delete()
                audio.add_tags()
                self._fill_id3(audio.tags, track, cover, replaygain)
                audio.save()
        except TaggingError:
            raise
        except Exception as exc:  # noqa: BLE001 - mutagen lanza varios tipos
            raise TaggingError(f"No se pudieron escribir las etiquetas en {path.name}: {exc}") from exc

    # ---- ID3 ---------------------------------------------------------------
    @staticmethod
    def _fill_id3(tags: ID3, t: Track, cover: CoverImage | None, rg) -> None:
        tags.add(TIT2(encoding=_UTF16, text=t.title))
        tags.add(TPE1(encoding=_UTF16, text=t.artist_display))
        tags.add(TPE2(encoding=_UTF16, text=t.folder_artist))     # agrupa el álbum en el reproductor
        tags.add(TALB(encoding=_UTF16, text=t.album))
        total = f"/{t.total_tracks}" if t.total_tracks else ""
        tags.add(TRCK(encoding=_UTF16, text=f"{t.track_number}{total}"))
        tags.add(TPOS(encoding=_UTF16, text=str(t.disc_number)))
        if t.year:
            tags.add(TDRC(encoding=_UTF16, text=str(t.year)))
        if t.isrc:
            tags.add(TSRC(encoding=_UTF16, text=t.isrc))
        if rg:
            tags.add(TXXX(encoding=_UTF16, desc="REPLAYGAIN_TRACK_GAIN", text=f"{rg[0]:+.2f} dB"))
            tags.add(TXXX(encoding=_UTF16, desc="REPLAYGAIN_TRACK_PEAK", text=f"{rg[1]:.6f}"))
        if cover:
            tags.add(APIC(encoding=0, mime=cover.mime, type=3, desc="Cover", data=cover.data))

    # ---- MP4 ---------------------------------------------------------------
    @staticmethod
    def _write_mp4(path: Path, t: Track, cover: CoverImage | None, rg) -> None:
        audio = MP4(path)
        audio.delete()
        tags = audio.tags if audio.tags is not None else audio.add_tags() or audio.tags
        tags["\xa9nam"] = [t.title]
        tags["\xa9ART"] = [t.artist_display]
        tags["aART"] = [t.folder_artist]
        tags["\xa9alb"] = [t.album]
        tags["trkn"] = [(t.track_number, t.total_tracks or 0)]
        tags["disk"] = [(t.disc_number, 0)]
        if t.year:
            tags["\xa9day"] = [str(t.year)]
        if t.explicit:
            tags["rtng"] = [1]
        if t.isrc:
            tags["----:com.apple.iTunes:ISRC"] = [MP4FreeForm(t.isrc.encode())]
        if rg:
            tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN"] = [MP4FreeForm(f"{rg[0]:+.2f} dB".encode())]
            tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK"] = [MP4FreeForm(f"{rg[1]:.6f}".encode())]
        if cover:
            tags["covr"] = [MP4Cover(cover.data, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
