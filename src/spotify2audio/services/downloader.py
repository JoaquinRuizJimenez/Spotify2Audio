"""Descarga el audio crudo con yt-dlp. La conversión a MP3/M4A/WAV la hace AudioProcessor."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpError

from ..core.cancellation import CancellationToken
from ..core.errors import CancelledError, DownloadError
from ..models.candidate import Candidate
from ..models.track import Track
from ..utils.ffmpeg_check import find_tool
from .matcher import DURATION_MAX_S, YouTubeSearcher

log = logging.getLogger(__name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

ProgressCb = Callable[[float], None]   # fracción 0..1


@dataclass
class DownloadedAudio:
    path: Path
    candidate: Candidate
    duration_s: float | None


def _short_error(exc: Exception) -> str:
    msg = _ANSI.sub("", str(exc)).replace("ERROR: ", "").strip()
    low = msg.lower()
    if "not a bot" in low or "sign in to confirm" in low:
        msg += " [YouTube pide verificación; actualiza yt-dlp con `pip install -U yt-dlp`]"
    elif "challenge" in low or "javascript runtime" in low or "n function" in low:
        msg += " [instala Deno: winget install DenoLand.Deno]"
    return msg[:300]


def verify_duration(track: Track, actual_s: float | None) -> None:
    """Comprueba la duración real descargada frente a la de Spotify."""
    if actual_s and track.duration_ms and abs(actual_s - track.duration_s) > DURATION_MAX_S:
        raise DownloadError(
            f"duración real {actual_s:.0f}s no coincide con la esperada {track.duration_s:.0f}s")


class Downloader:
    def __init__(self, searcher: YouTubeSearcher | None = None, max_candidates: int = 3) -> None:
        self.searcher = searcher or YouTubeSearcher()
        self.max_candidates = max_candidates

    # ---- API pública -------------------------------------------------------
    def download_track(self, track: Track, work_dir: Path, on_progress: ProgressCb | None = None,
                       cancel: CancellationToken | None = None) -> DownloadedAudio:
        """Busca candidatos y prueba los mejores hasta que uno se descargue y verifique."""
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        candidates = self.searcher.find_candidates(track)        # MatchNotFoundError / DownloadError
        errors: list[str] = []
        for cand in candidates[: self.max_candidates]:
            if cancel:
                cancel.raise_if_cancelled()
            log.info("Probando %s (puntuación %.2f, %s)", cand.url, cand.score, cand.title)
            try:
                return self._download_one(cand, track, work_dir, on_progress, cancel)
            except CancelledError:
                self._cleanup(work_dir, track, cand)
                raise
            except DownloadError as exc:
                errors.append(f"{cand.video_id}: {exc}")
                log.warning("Candidato descartado: %s", errors[-1])
                self._cleanup(work_dir, track, cand)
        raise DownloadError("No se pudo descargar ningún candidato. " + " | ".join(errors))

    # ---- internos ------------------------------------------------------------
    def _ydl_opts(self, track: Track, work_dir: Path, hook: Callable) -> dict:
        opts: dict = {
            "format": "bestaudio/best",
            "outtmpl": str(work_dir / f"{track.spotify_id}_%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 20,
            "progress_hooks": [hook],
            "windowsfilenames": True,
        }
        ffmpeg = find_tool("ffmpeg")
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
        return opts

    def _download_one(self, cand: Candidate, track: Track, work_dir: Path,
                      on_progress: ProgressCb | None, cancel: CancellationToken | None) -> DownloadedAudio:
        def hook(d: dict) -> None:
            if cancel and cancel.is_cancelled:
                raise CancelledError("Descarga cancelada.")
            if on_progress and d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))
            elif on_progress and d.get("status") == "finished":
                on_progress(1.0)

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts(track, work_dir, hook)) as ydl:
                info = ydl.extract_info(cand.url, download=True)
                downloads = (info or {}).get("requested_downloads") or []
                path = Path(downloads[0]["filepath"]) if downloads else Path(ydl.prepare_filename(info))
        except CancelledError:
            raise
        except YtDlpError as exc:
            if cancel and cancel.is_cancelled:
                raise CancelledError("Descarga cancelada.") from exc
            raise DownloadError(_short_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            if cancel and cancel.is_cancelled:
                raise CancelledError("Descarga cancelada.") from exc
            raise DownloadError(_short_error(exc)) from exc

        if not path.exists():
            raise DownloadError("yt-dlp terminó pero no se encontró el archivo descargado")
        duration = info.get("duration")
        try:
            verify_duration(track, duration)
        except DownloadError:
            path.unlink(missing_ok=True)
            raise
        return DownloadedAudio(path=path, candidate=cand, duration_s=duration)

    @staticmethod
    def _cleanup(work_dir: Path, track: Track, cand: Candidate) -> None:
        for f in work_dir.glob(f"{track.spotify_id}_{cand.video_id}.*"):
            try:
                f.unlink()
            except OSError:
                pass
