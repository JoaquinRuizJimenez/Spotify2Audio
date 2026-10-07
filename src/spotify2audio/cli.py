"""Uso por consola.

  python -m spotify2audio.cli URL                 # solo muestra la playlist
  python -m spotify2audio.cli URL --match 5       # candidatos de YouTube (no descarga)
  python -m spotify2audio.cli URL --download 3    # audio crudo de 3 pistas
  python -m spotify2audio.cli URL --process 2     # pipeline completo, 2 primeras pistas
  python -m spotify2audio.cli URL --run           # pipeline completo, playlist entera
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .config.settings import Settings
from .core.errors import AppError
from .core.events import JobStarted, TrackFinished, TrackProgress, TrackStarted
from .core.pipeline import FAILED_FILE, Pipeline
from .models.options import NormalizeMode, OutputFormat
from .models.results import TrackStatus
from .services.downloader import Downloader
from .services.matcher import YouTubeSearcher
from .services.spotify_client import SpotifyClient
from .utils.logging_setup import setup_logging

_LABEL = {TrackStatus.OK: "OK", TrackStatus.SKIPPED: "omitida", TrackStatus.FAILED: "FALLO",
          TrackStatus.CANCELLED: "cancelada"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convierte una playlist de Spotify en archivos de audio.")
    parser.add_argument("url", help="URL, URI o ID de la playlist")
    parser.add_argument("--limit", type=int, default=15, help="pistas a listar (0 = todas)")
    parser.add_argument("--match", type=int, default=0, metavar="N", help="muestra candidatos de YouTube de N pistas")
    parser.add_argument("--download", type=int, default=0, metavar="N", help="descarga audio crudo de N pistas")
    parser.add_argument("--process", type=int, default=0, metavar="N", help="pipeline completo con las N primeras pistas")
    parser.add_argument("--run", action="store_true", help="pipeline completo con toda la playlist")
    parser.add_argument("--format", choices=[f.value for f in OutputFormat], help="mp3 | m4a | wav")
    parser.add_argument("--normalize", choices=[n.value for n in NormalizeMode], help="none | loudnorm | replaygain")
    parser.add_argument("--workers", type=int, help="pistas en paralelo (1-8)")
    parser.add_argument("--no-skip", action="store_true", help="rehacer aunque el archivo ya exista")
    parser.add_argument("--out", default="_test_downloads", help="carpeta de salida")
    args = parser.parse_args(argv)

    setup_logging()
    try:
        playlist = SpotifyClient().get_playlist(
            args.url, progress=lambda done, total: print(f"  leyendo pistas... {done}/{total}", end="\r"))
        _print_playlist(playlist, args.limit)
        if args.match:
            _run_match(playlist.tracks[:args.match])
        if args.download:
            _run_download(playlist.tracks[:args.download], Path(args.out))
        count = len(playlist) if args.run else args.process
        if count:
            return _run_pipeline(playlist, count, args)
    except AppError as exc:
        print(f"\nERROR: {exc}")
        return 1
    return 0


def _print_playlist(playlist, limit: int) -> None:
    print(f"\nPlaylist : {playlist.name}  (de {playlist.owner})")
    print(f"Pistas   : {len(playlist)} descargables, {len(playlist.skipped)} omitidas\n")
    shown = playlist.tracks if limit == 0 else playlist.tracks[:limit]
    for t in shown:
        mins, secs = divmod(int(t.duration_s), 60)
        print(f"{t.playlist_position:>3}. {t} | {t.album} ({t.year or '?'}) [pista {t.track_number}] {mins}:{secs:02d}")
    if len(shown) < len(playlist):
        print(f"... y {len(playlist) - len(shown)} más (usa --limit 0 para verlas todas)")
    for line in playlist.skipped[:10]:
        print("omitida:", line)


def _run_pipeline(playlist, count: int, args) -> int:
    settings = Settings.load()
    opts = settings.to_job_options()
    opts = replace(
        opts, output_dir=Path(args.out),
        output_format=OutputFormat(args.format) if args.format else opts.output_format,
        normalize=NormalizeMode(args.normalize) if args.normalize else opts.normalize,
        max_workers=args.workers or opts.max_workers,
        skip_existing=False if args.no_skip else opts.skip_existing)
    sub = replace(playlist, tracks=playlist.tracks[:count])
    print(f"\n=== {len(sub)} pistas -> {opts.output_dir.resolve()} ({opts.output_format.value}, "
          f"{opts.bitrate_kbps} kbps, normalización: {opts.normalize.value}, {opts.max_workers} hilo(s)) ===")
    print("(Ctrl+C cancela de forma limpia)\n")

    def on_event(ev) -> None:
        if isinstance(ev, TrackStarted):
            print(f"[{ev.index + 1}/{ev.total}] {ev.track}")
        elif isinstance(ev, TrackProgress) and opts.max_workers == 1:
            print(f"      {ev.stage.value:<12}{ev.fraction:4.0%}", end="\r")
        elif isinstance(ev, TrackFinished):
            r = ev.result
            detail = r.error or (r.output_path.relative_to(opts.output_dir).as_posix() if r.output_path else "")
            print(f"      {_LABEL[r.status]:<10} {detail}" + " " * 20)

    summary = Pipeline(opts, on_event=on_event).run(sub)      # DependencyMissingError / DeviceError -> main()
    print(f"\n=== Resumen: {summary} ===")
    if summary.failed:
        print(f"Detalle de fallos en {opts.output_dir / FAILED_FILE} (repite el comando para reintentarlas)")
    return 1 if summary.failed or summary.cancelled else 0


def _run_match(tracks) -> None:
    searcher = YouTubeSearcher()
    print("\n=== Candidatos de YouTube ===")
    for t in tracks:
        print(f"\n> {t}  [{int(t.duration_s)}s]")
        try:
            for c in searcher.find_candidates(t)[:3]:
                dur = f"{int(c.duration_s)}s" if c.duration_s else "?"
                print(f"   {c.score:.2f} | {dur:>5} | {c.source:<7} | {c.title} - {c.channel}")
                print(f"          {'; '.join(c.notes)}")
        except AppError as exc:
            print(f"   FALLO: {exc}")


def _run_download(tracks, out: Path) -> None:
    downloader = Downloader()
    print(f"\n=== Descargando a {out.resolve()} ===")
    for t in tracks:
        print(f"\n> {t}")
        try:
            res = downloader.download_track(t, out, on_progress=lambda f: print(f"   {f:4.0%}", end="\r"))
            print(f"   OK -> {res.path.name} ({res.duration_s or '?'}s, puntuación {res.candidate.score:.2f})")
        except AppError as exc:
            print(f"   FALLO: {exc}")


if __name__ == "__main__":
    sys.exit(main())
