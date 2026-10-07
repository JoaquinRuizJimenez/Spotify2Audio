"""Orquestador del trabajo completo: playlist -> archivos etiquetados y organizados.

Garantías:
  * Un fallo en una pista (de cualquier tipo) NUNCA detiene el resto.
  * Los archivos a medias se eliminan: lo que existe en disco está completo y etiquetado.
  * Relanzar la misma playlist solo procesa lo que falta (skip_existing).
  * Cancelable en cualquier momento (CancellationToken / Ctrl+C en el CLI).
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ..config.paths import cache_dir
from ..models.options import JobOptions, NormalizeMode, OutputFormat
from ..models.playlist import Playlist
from ..models.results import JobSummary, TrackResult, TrackStatus
from ..models.track import Track
from ..services.audio_processor import SAMPLE_RATE, AudioProcessor
from ..services.cover_fetcher import CoverFetcher
from ..services.downloader import Downloader
from ..services.organizer import Organizer
from ..services.tagger import Tagger
from ..utils.sanitize import sanitize_component
from .cancellation import CancellationToken
from .errors import AppError, CancelledError, DeviceError
from .events import (EventCallback, JobFinished, JobStarted, Stage, TrackFinished, TrackProgress,
                     TrackStarted)

log = logging.getLogger(__name__)
FAILED_FILE = "failed_tracks.txt"
_OVERHEAD_PER_TRACK = 600_000        # portada + etiquetas, en bytes


def estimate_size_bytes(tracks: list[Track], options: JobOptions) -> int:
    if options.output_format is OutputFormat.WAV:
        rate = SAMPLE_RATE * 2 * 2                    # 44.1 kHz, 16 bit, estéreo
    else:
        rate = options.bitrate_kbps * 1000 / 8
    return int(sum(t.duration_s * rate * 1.05 + _OVERHEAD_PER_TRACK for t in tracks))


def _nearest_existing(path: Path) -> Path:
    path = path.resolve()
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


class Pipeline:
    def __init__(self, options: JobOptions, *, downloader=None, processor=None, covers=None, tagger=None,
                 on_event: EventCallback | None = None, work_root: Path | None = None,
                 write_reports: bool = True) -> None:
        self.options = options
        self.downloader = downloader or Downloader()
        self.processor = processor or AudioProcessor()       # falla aquí (rápido) si falta FFmpeg
        self.covers = covers or CoverFetcher()
        self.tagger = tagger or Tagger()
        self.on_event = on_event
        self.work_root = Path(work_root) if work_root else cache_dir() / "work"
        self.write_reports = write_reports
        self._lock = threading.Lock()
        self._done = 0

    # ------------------------------------------------------------------ API
    def run(self, playlist: Playlist, cancel: CancellationToken | None = None) -> JobSummary:
        cancel = cancel or CancellationToken()
        o, tracks = self.options, playlist.tracks
        o.output_dir.mkdir(parents=True, exist_ok=True)

        # rutas en orden de playlist: la numeración de colisiones "(2)" es determinista
        organizer = Organizer.for_playlist(o, tracks)
        targets = [organizer.target_path(t) for t in tracks]
        seen: set[str] = set()
        duplicate = []
        for t in tracks:
            duplicate.append(t.spotify_id in seen)
            seen.add(t.spotify_id)

        self._check_disk_space(tracks, targets, duplicate)
        self.work_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="job_", dir=self.work_root))
        self._done = 0
        self._emit(JobStarted(playlist.name, len(tracks)))
        log.info("Iniciando «%s»: %d pistas, formato %s, %d hilo(s)",
                 playlist.name, len(tracks), o.output_format.value, o.max_workers)

        try:
            with ThreadPoolExecutor(max_workers=o.max_workers, thread_name_prefix="s2a") as pool:
                futures = [pool.submit(self._task, i, t, targets[i], duplicate[i], len(tracks), work, cancel)
                           for i, t in enumerate(tracks)]
                try:
                    results = [f.result() for f in futures]
                except KeyboardInterrupt:           # Ctrl+C: cancelar limpiamente y recoger lo hecho
                    log.warning("Interrumpido por el usuario; cancelando...")
                    cancel.cancel()
                    results = [f.result() for f in futures]
        finally:
            shutil.rmtree(work, ignore_errors=True)

        summary = JobSummary(playlist_name=playlist.name, results=results)
        if self.write_reports:
            self._write_reports(playlist, summary, cancelled=cancel.is_cancelled)
        log.info("Terminado: %s", summary)
        self._emit(JobFinished(summary))
        return summary

    # ------------------------------------------------------------- por pista
    def _task(self, index: int, track: Track, final: Path, duplicate: bool, total: int,
              work: Path, cancel: CancellationToken) -> TrackResult:
        self._emit(TrackStarted(index, total, track))
        result = self._execute(index, track, final, duplicate, work, cancel)
        with self._lock:
            self._done += 1
            done = self._done
        self._emit(TrackFinished(index, total, result, done))
        return result

    def _execute(self, index: int, track: Track, final: Path, duplicate: bool,
                 work: Path, cancel: CancellationToken) -> TrackResult:
        o = self.options
        if duplicate:
            return TrackResult(track, TrackStatus.SKIPPED, output_path=final, error="duplicada en la playlist")
        if cancel.is_cancelled:
            return TrackResult(track, TrackStatus.CANCELLED)
        if o.skip_existing and final.exists() and final.stat().st_size > 0:
            return TrackResult(track, TrackStatus.SKIPPED, output_path=final)

        converted = False
        try:
            self._progress(index, track, Stage.SEARCHING, 0.02)
            raw = self.downloader.download_track(
                track, work, cancel=cancel,
                on_progress=self._stage_cb(index, track, Stage.DOWNLOADING, 0.05, 0.55))
            res = self.processor.convert(
                raw.path, final, o, duration_s=track.duration_s, cancel=cancel,
                on_progress=self._stage_cb(index, track, Stage.CONVERTING, 0.60, 0.35))
            converted = True
            self._progress(index, track, Stage.TAGGING, 0.95)
            cover = self.covers.fetch(track.cover_url)
            gain = None
            if o.normalize is NormalizeMode.REPLAYGAIN and res.loudness:
                gain = (res.loudness.replaygain_gain_db, res.loudness.replaygain_peak)
            self.tagger.write(final, track, o.output_format, cover, gain)
            return TrackResult(track, TrackStatus.OK, output_path=final, matched_url=raw.candidate.url)
        except CancelledError:
            self._discard(final, converted)
            return TrackResult(track, TrackStatus.CANCELLED)
        except AppError as exc:
            self._discard(final, converted)
            log.warning("Falló %s: %s", track, exc)
            return TrackResult(track, TrackStatus.FAILED, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - una pista nunca debe tumbar el trabajo
            self._discard(final, converted)
            log.exception("Error inesperado en %s", track)
            return TrackResult(track, TrackStatus.FAILED, error=f"Error inesperado: {type(exc).__name__}: {exc}")
        finally:
            for leftover in work.glob(f"{track.spotify_id}_*"):
                leftover.unlink(missing_ok=True)

    @staticmethod
    def _discard(final: Path, converted: bool) -> None:
        """Si la conversión terminó pero la pista no se completó, no dejamos un archivo sin etiquetar."""
        if converted:
            final.unlink(missing_ok=True)

    # ------------------------------------------------------------ utilidades
    def _emit(self, event) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:  # noqa: BLE001 - un fallo de la GUI no debe afectar a las descargas
                log.exception("Error en el callback de eventos")

    def _progress(self, index: int, track: Track, stage: Stage, fraction: float) -> None:
        self._emit(TrackProgress(index, track, stage, min(fraction, 1.0)))

    def _stage_cb(self, index: int, track: Track, stage: Stage, base: float, span: float):
        last = [-1.0]

        def cb(f: float) -> None:
            if f - last[0] >= 0.02 or f >= 1.0:       # limita la frecuencia de eventos
                last[0] = f
                self._progress(index, track, stage, base + span * f)
        return cb

    def _check_disk_space(self, tracks: list[Track], targets: list[Path], duplicate: list[bool]) -> None:
        pending = [t for t, p, d in zip(tracks, targets, duplicate)
                   if not d and not (self.options.skip_existing and p.exists() and p.stat().st_size > 0)]
        needed = estimate_size_bytes(pending, self.options)
        free = shutil.disk_usage(_nearest_existing(self.options.output_dir)).free
        if needed * 1.1 > free:
            raise DeviceError(f"Espacio insuficiente en el destino: se necesitan ~{needed / 1e6:.0f} MB "
                              f"y hay {free / 1e6:.0f} MB libres.")

    # --------------------------------------------------------------- informes
    def _write_reports(self, playlist: Playlist, summary: JobSummary, cancelled: bool) -> None:
        out = self.options.output_dir
        try:
            failed = out / FAILED_FILE
            if summary.failed:
                header = (f"# Pistas fallidas de «{playlist.name}» - {datetime.now():%Y-%m-%d %H:%M}\n"
                          "# Vuelve a ejecutar la misma playlist: solo se reintentan estas "
                          "(las ya descargadas se omiten).\n")
                lines = [f"{r.track} | {r.error or 'error desconocido'} | "
                         f"https://open.spotify.com/track/{r.track.spotify_id}" for r in summary.failed_results]
                failed.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
            elif not cancelled:
                failed.unlink(missing_ok=True)       # reintento exitoso: elimina el informe viejo

            done = [r for r in summary.results
                    if r.status in (TrackStatus.OK, TrackStatus.SKIPPED) and r.output_path and r.output_path.exists()]
            if done:
                m3u = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]
                for r in done:
                    m3u.append(f"#EXTINF:{int(r.track.duration_s)},{r.track}")
                    m3u.append(r.output_path.relative_to(out).as_posix())
                name = sanitize_component(playlist.name, fallback="playlist")
                (out / f"{name}.m3u8").write_text("\n".join(m3u) + "\n", encoding="utf-8")
        except OSError as exc:
            log.warning("No se pudieron escribir los informes: %s", exc)
