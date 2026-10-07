"""Prueba por consola: python -m spotify2audio.cli <URL> [--limit N]"""
from __future__ import annotations

import argparse

from dataclasses import replace
from pathlib import Path

from .config.settings import Settings
from .core.errors import AppError
from .models.options import NormalizeMode, OutputFormat
from .services.audio_processor import AudioProcessor
from .services.cover_fetcher import CoverFetcher
from .services.organizer import Organizer
from .services.tagger import Tagger
from .services.downloader import Downloader
from .services.matcher import YouTubeSearcher
from .services.spotify_client import SpotifyClient
from .utils.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lee una playlist de Spotify y muestra sus pistas.")
    parser.add_argument("url", help="URL, URI o ID de la playlist")
    parser.add_argument("--limit", type=int, default=15, help="pistas a mostrar (0 = todas)")
    parser.add_argument("--match", type=int, default=0, metavar="N",
                        help="busca en YouTube las N primeras pistas y muestra los candidatos (no descarga)")
    parser.add_argument("--download", type=int, default=0, metavar="N",
                        help="descarga el audio crudo de las N primeras pistas")
    parser.add_argument("--process", type=int, default=0, metavar="N",
                        help="descarga + convierte + normaliza + etiqueta + organiza las N primeras pistas")
    parser.add_argument("--format", choices=[f.value for f in OutputFormat], help="mp3 | m4a | wav")
    parser.add_argument("--normalize", choices=[n.value for n in NormalizeMode], help="none | loudnorm | replaygain")
    parser.add_argument("--out", default="_test_downloads", help="carpeta de salida")
    args = parser.parse_args(argv)

    setup_logging()
    try:
        playlist = SpotifyClient().get_playlist(
            args.url, progress=lambda done, total: print(f"  leyendo pistas... {done}/{total}", end="\r"))
    except AppError as exc:
        print(f"\nERROR: {exc}")
        return 1

    print(f"\nPlaylist : {playlist.name}  (de {playlist.owner})")
    print(f"Pistas   : {len(playlist)} descargables, {len(playlist.skipped)} omitidas")
    print(f"Portada  : {playlist.cover_url or '-'}\n")
    shown = playlist.tracks if args.limit == 0 else playlist.tracks[:args.limit]
    for t in shown:
        mins, secs = divmod(int(t.duration_s), 60)
        print(f"{t.playlist_position:>3}. {t} | {t.album} ({t.year or '?'}) "
              f"[pista {t.track_number}] {mins}:{secs:02d}")
    if len(shown) < len(playlist):
        print(f"... y {len(playlist) - len(shown)} más (usa --limit 0 para verlas todas)")
    for line in playlist.skipped[:10]:
        print("omitida:", line)

    if args.match:
        _run_match(playlist.tracks[:args.match])
    if args.download:
        _run_download(playlist.tracks[:args.download], Path(args.out))
    if args.process:
        opts = Settings.load().to_job_options()
        opts = replace(opts, output_dir=Path(args.out),
                       output_format=OutputFormat(args.format) if args.format else opts.output_format,
                       normalize=NormalizeMode(args.normalize) if args.normalize else opts.normalize)
        _run_process(playlist, playlist.tracks[:args.process], opts)
    return 0


def _run_process(playlist, tracks, opts) -> None:
    """Cadena completa de una pista. En la Fase 5 se sustituye por core/pipeline.py."""
    downloader, processor = Downloader(), AudioProcessor()
    covers, tagger = CoverFetcher(), Tagger()
    organizer = Organizer.for_playlist(opts, playlist.tracks)
    work = opts.output_dir / ".work"
    print(f"\n=== Procesando a {opts.output_dir.resolve()} ({opts.output_format.value}, "
          f"{opts.bitrate_kbps} kbps, normalización: {opts.normalize.value}) ===")
    for t in tracks:
        print(f"\n> {t}")
        try:
            final = organizer.target_path(t)
            if opts.skip_existing and final.exists():
                print(f"   omitida (ya existe): {final.name}")
                continue
            raw = downloader.download_track(t, work)
            res = processor.convert(raw.path, final, opts, duration_s=t.duration_s,
                                    on_progress=lambda f: print(f"   convirtiendo {f:4.0%}", end="\r"))
            cover = covers.fetch(t.cover_url)
            rg = None
            if opts.normalize is NormalizeMode.REPLAYGAIN and res.loudness:
                rg = (res.loudness.replaygain_gain_db, res.loudness.replaygain_peak)
            tagger.write(final, t, opts.output_format, cover, rg)
            raw.path.unlink(missing_ok=True)
            vol = f", volumen original {res.loudness.input_i:.1f} LUFS" if res.loudness else ""
            cov = f", portada {cover.width}x{cover.height}" if cover else ", SIN portada"
            print(f"   OK -> {final.relative_to(opts.output_dir)}{vol}{cov}")
        except AppError as exc:
            print(f"   FALLO: {exc}")


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
            res = downloader.download_track(
                t, out, on_progress=lambda f: print(f"   {f:4.0%}", end="\r"))
            print(f"   OK -> {res.path.name} ({res.duration_s or '?'}s, puntuación {res.candidate.score:.2f})")
        except AppError as exc:
            print(f"   FALLO: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
