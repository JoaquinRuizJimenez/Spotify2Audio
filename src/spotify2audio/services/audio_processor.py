"""Conversión y normalización de volumen con FFmpeg (EBU R128, dos pasadas)."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.cancellation import CancellationToken
from ..core.errors import CancelledError, ProcessingError
from ..models.options import JobOptions, NormalizeMode, OutputFormat
from ..utils.ffmpeg_check import ensure_ffmpeg

log = logging.getLogger(__name__)

TARGET_LUFS = -14.0      # volumen objetivo (similar a Spotify)
TARGET_TP = -1.5         # pico real máximo (margen para la codificación con pérdida)
TARGET_LRA = 11.0
RG_REFERENCE_LUFS = -18.0
SAMPLE_RATE = 44100      # CD / iPod
_NOWINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

ProgressCb = Callable[[float], None]
_JSON_RE = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


@dataclass
class Loudness:
    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float

    @property
    def replaygain_gain_db(self) -> float:
        return RG_REFERENCE_LUFS - self.input_i

    @property
    def replaygain_peak(self) -> float:
        return 10 ** (self.input_tp / 20)


@dataclass
class ProcessResult:
    path: Path
    loudness: Loudness | None = None     # medición del original
    normalized: bool = False


def _parse_loudness(stderr: str) -> Loudness | None:
    matches = _JSON_RE.findall(stderr)
    if not matches:
        return None
    try:
        d = json.loads(matches[-1])
        vals = [float(d[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")]
    except (ValueError, KeyError):
        return None
    if not all(math.isfinite(v) for v in vals):      # pista en silencio: "-inf"
        return None
    return Loudness(*vals)


class AudioProcessor:
    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg = ffmpeg_path or ensure_ffmpeg()[0]

    # ------------------------------------------------------------------ API
    def convert(self, src: Path, dst: Path, options: JobOptions, duration_s: float | None = None,
                on_progress: ProgressCb | None = None,
                cancel: CancellationToken | None = None) -> ProcessResult:
        src, dst = Path(src), Path(dst)
        if not src.exists():
            raise ProcessingError(f"No existe el archivo de entrada: {src}")
        if cancel:
            cancel.raise_if_cancelled()
        dst.parent.mkdir(parents=True, exist_ok=True)

        loudness: Loudness | None = None
        af: str | None = None
        split = 0.0
        if options.normalize is not NormalizeMode.NONE:
            split = 0.3
            loudness = self._measure(src, duration_s, self._scaled(on_progress, 0.0, split), cancel)
            if loudness is None:
                log.warning("No se pudo medir el volumen de %s; se convierte sin normalizar", src.name)
            elif options.normalize is NormalizeMode.LOUDNORM:
                af = self._loudnorm_filter(loudness)

        tmp = dst.with_name(f"{dst.stem}.tmp{dst.suffix}")
        try:
            self._run(self._encode_cmd(src, tmp, options, af), duration_s,
                      self._scaled(on_progress, split, 1.0), cancel)
            os.replace(tmp, dst)
        finally:
            tmp.unlink(missing_ok=True)
        return ProcessResult(path=dst, loudness=loudness, normalized=af is not None)

    def measure(self, path: Path) -> Loudness | None:
        """Mide un archivo (útil para verificar el resultado)."""
        return self._measure(Path(path), None, None, None)

    # -------------------------------------------------------------- comandos
    @staticmethod
    def _scaled(cb: ProgressCb | None, lo: float, hi: float) -> ProgressCb | None:
        if cb is None:
            return None
        return lambda f: cb(lo + (hi - lo) * max(0.0, min(f, 1.0)))

    def _base(self) -> list[str]:
        return [self.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
                "-progress", "pipe:1"]

    def _measure(self, src: Path, duration_s, on_progress, cancel) -> Loudness | None:
        af = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
        cmd = self._base() + ["-i", str(src), "-vn", "-af", af, "-f", "null", "-"]
        return _parse_loudness(self._run(cmd, duration_s, on_progress, cancel))

    @staticmethod
    def _loudnorm_filter(m: Loudness) -> str:
        return (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
                f"measured_I={m.input_i}:measured_TP={m.input_tp}:measured_LRA={m.input_lra}:"
                f"measured_thresh={m.input_thresh}:offset={m.target_offset}:linear=true")

    def _encode_cmd(self, src: Path, dst: Path, o: JobOptions, af: str | None) -> list[str]:
        cmd = self._base() + ["-y", "-i", str(src), "-vn", "-map", "0:a:0", "-map_metadata", "-1"]
        if af:
            cmd += ["-af", af]            # loudnorm sube internamente a 192 kHz; -ar lo devuelve a 44.1
        cmd += ["-ar", str(SAMPLE_RATE), "-ac", "2"]
        if o.output_format is OutputFormat.MP3:
            cmd += ["-c:a", "libmp3lame", "-b:a", f"{o.bitrate_kbps}k"]
        elif o.output_format is OutputFormat.M4A:
            cmd += ["-c:a", "aac", "-b:a", f"{o.bitrate_kbps}k"]
        else:
            cmd += ["-c:a", "pcm_s16le"]  # CD: 16 bit / 44.1 kHz estéreo
        return cmd + [str(dst)]

    # -------------------------------------------------------------- ejecución
    def _run(self, cmd: list[str], duration_s: float | None, on_progress: ProgressCb | None,
             cancel: CancellationToken | None) -> str:
        """Ejecuta FFmpeg, informa del progreso y devuelve stderr."""
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True,
                                    encoding="utf-8", errors="replace", creationflags=_NOWINDOW)
            try:
                for line in proc.stdout:        # type: ignore[union-attr]
                    if cancel and cancel.is_cancelled:
                        raise CancelledError("Conversión cancelada.")
                    if on_progress and duration_s and line.startswith(("out_time_us=", "out_time_ms=")):
                        try:   # ambas claves van en microsegundos
                            on_progress(int(line.split("=", 1)[1]) / 1_000_000 / duration_s)
                        except ValueError:
                            pass                # "N/A" al inicio
                rc = proc.wait()
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            err.seek(0)
            stderr = err.read().decode("utf-8", errors="replace")
        if rc != 0:
            tail = " | ".join(l for l in stderr.strip().splitlines()[-4:])
            raise ProcessingError(f"FFmpeg falló (código {rc}): {tail}")
        if on_progress:
            on_progress(1.0)
        return stderr
