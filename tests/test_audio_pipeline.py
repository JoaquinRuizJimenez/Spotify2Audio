"""Tests con FFmpeg real (se omiten si no está instalado)."""
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from PIL import Image

from spotify2audio.core.cancellation import CancellationToken
from spotify2audio.core.errors import CancelledError, ProcessingError
from spotify2audio.models.options import JobOptions, NormalizeMode, OutputFormat
from spotify2audio.models.track import Track
from spotify2audio.services.audio_processor import AudioProcessor
from spotify2audio.services.cover_fetcher import CoverFetcher, CoverImage
from spotify2audio.services.tagger import Tagger

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="FFmpeg no instalado")

TRACK = Track(spotify_id="s1", title="Canción ñandú", artists=("Beyoncé", "Guest"), album="Álbum",
              album_artist="Beyoncé", track_number=3, disc_number=1, total_tracks=12, year=2019,
              duration_ms=6000, isrc="USABC1234567", explicit=True)


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    return json.loads(out)


@pytest.fixture(scope="module")
def raw_audio(tmp_path_factory) -> Path:
    """Tono de 6 s en Opus/WebM, como lo entrega yt-dlp (volumen bajo a propósito)."""
    p = tmp_path_factory.mktemp("raw") / "raw.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-ac", "1", "-c:a", "libopus", str(p)], check=True)
    return p


@pytest.fixture(scope="module")
def cover() -> CoverImage:
    buf = io.BytesIO()
    Image.new("RGB", (600, 600), (200, 30, 30)).save(buf, "JPEG")
    return CoverImage(buf.getvalue(), 600, 600)


def opts(tmp_path, fmt, norm=NormalizeMode.LOUDNORM, bitrate=320):
    return JobOptions(output_dir=tmp_path, output_format=fmt, normalize=norm, bitrate_kbps=bitrate)


@pytest.mark.parametrize("fmt,codec", [(OutputFormat.MP3, "mp3"), (OutputFormat.M4A, "aac"),
                                       (OutputFormat.WAV, "pcm_s16le")])
def test_convert_formats(raw_audio, tmp_path, fmt, codec):
    dst = tmp_path / f"out.{fmt.value}"
    progress = []
    res = AudioProcessor().convert(raw_audio, dst, opts(tmp_path, fmt), duration_s=6.0, on_progress=progress.append)
    s = probe(dst)["streams"][0]
    assert s["codec_name"] == codec and s["sample_rate"] == "44100" and s["channels"] == 2
    assert res.normalized and progress[-1] == 1.0 and progress == sorted(progress)
    assert not list(tmp_path.glob("*.tmp*"))                    # sin temporales
    if fmt is OutputFormat.MP3:
        assert 300_000 <= int(s["bit_rate"]) <= 330_000
    if fmt is OutputFormat.WAV:
        assert s["bits_per_sample"] == 16


def test_loudnorm_reaches_target(raw_audio, tmp_path):
    proc = AudioProcessor()
    before = proc.measure(raw_audio)
    dst = tmp_path / "n.mp3"
    proc.convert(raw_audio, dst, opts(tmp_path, OutputFormat.MP3))
    after = proc.measure(dst)
    assert before.input_i < -18                 # el original suena bajo
    assert abs(after.input_i - (-14.0)) < 1.5   # normalizado cerca del objetivo
    assert after.input_tp <= -0.5               # sin clipping


def test_no_normalize_keeps_level(raw_audio, tmp_path):
    proc = AudioProcessor()
    dst = tmp_path / "x.wav"
    res = proc.convert(raw_audio, dst, opts(tmp_path, OutputFormat.WAV, NormalizeMode.NONE))
    assert not res.normalized and res.loudness is None
    assert abs(proc.measure(dst).input_i - proc.measure(raw_audio).input_i) < 1.0


def test_replaygain_measures_without_changing_audio(raw_audio, tmp_path):
    res = AudioProcessor().convert(raw_audio, tmp_path / "r.mp3", opts(tmp_path, OutputFormat.MP3, NormalizeMode.REPLAYGAIN))
    assert not res.normalized and res.loudness is not None
    assert res.loudness.replaygain_gain_db > 0 and 0 < res.loudness.replaygain_peak < 1


def test_errors_and_cancel(raw_audio, tmp_path):
    proc = AudioProcessor()
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"no es audio")
    with pytest.raises(ProcessingError):
        proc.convert(bad, tmp_path / "o.mp3", opts(tmp_path, OutputFormat.MP3, NormalizeMode.NONE))
    assert not (tmp_path / "o.mp3").exists() and not list(tmp_path.glob("*.tmp*"))
    with pytest.raises(ProcessingError):
        proc.convert(tmp_path / "missing.webm", tmp_path / "o.mp3", opts(tmp_path, OutputFormat.MP3))
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        proc.convert(raw_audio, tmp_path / "c.mp3", opts(tmp_path, OutputFormat.MP3), cancel=token)


def test_tag_mp3(raw_audio, tmp_path, cover):
    dst = tmp_path / "t.mp3"
    AudioProcessor().convert(raw_audio, dst, opts(tmp_path, OutputFormat.MP3, NormalizeMode.NONE))
    Tagger().write(dst, TRACK, OutputFormat.MP3, cover, replaygain=(-3.2, 0.5))
    tags = ID3(dst)
    assert tags.version == (2, 3, 0)
    assert str(tags["TIT2"]) == "Canción ñandú" and str(tags["TPE1"]) == "Beyoncé, Guest"
    assert str(tags["TPE2"]) == "Beyoncé" and str(tags["TALB"]) == "Álbum"
    assert str(tags["TRCK"]) == "3/12" and str(tags["TPOS"]) == "1" and str(tags["TSRC"]) == "USABC1234567"
    assert "2019" in str(tags.get("TDRC") or tags.get("TYER"))
    assert tags["APIC:Cover"].data == cover.data and tags["APIC:Cover"].type == 3
    assert str(tags["TXXX:REPLAYGAIN_TRACK_GAIN"]) == "-3.20 dB"
    assert dst.read_bytes()[-128:-125] != b"TAG"                # sin ID3v1
    assert probe(dst)["streams"][0]["codec_name"] == "mp3"       # sigue siendo reproducible


def test_tag_m4a(raw_audio, tmp_path, cover):
    dst = tmp_path / "t.m4a"
    AudioProcessor().convert(raw_audio, dst, opts(tmp_path, OutputFormat.M4A, NormalizeMode.NONE))
    Tagger().write(dst, TRACK, OutputFormat.M4A, cover)
    t = MP4(dst).tags
    assert t["\xa9nam"] == ["Canción ñandú"] and t["aART"] == ["Beyoncé"] and t["trkn"] == [(3, 12)]
    assert t["\xa9day"] == ["2019"] and t["rtng"] == [1] and bytes(t["covr"][0]) == cover.data


def test_tag_wav_optional(raw_audio, tmp_path, cover):
    dst = tmp_path / "t.wav"
    AudioProcessor().convert(raw_audio, dst, opts(tmp_path, OutputFormat.WAV, NormalizeMode.NONE))
    before = dst.read_bytes()
    Tagger().write(dst, TRACK, OutputFormat.WAV, cover)         # por defecto no toca los WAV
    assert dst.read_bytes() == before
    Tagger(tag_wav=True).write(dst, TRACK, OutputFormat.WAV, cover)
    assert probe(dst)["streams"][0]["codec_name"] == "pcm_s16le"
    from mutagen.wave import WAVE
    assert str(WAVE(dst).tags["TIT2"]) == "Canción ñandú"


def test_tagging_without_cover(raw_audio, tmp_path):
    dst = tmp_path / "nc.mp3"
    AudioProcessor().convert(raw_audio, dst, opts(tmp_path, OutputFormat.MP3, NormalizeMode.NONE))
    Tagger().write(dst, TRACK, OutputFormat.MP3, None)
    assert not ID3(dst).getall("APIC")


# ---- portadas (sin red) ---------------------------------------------------------------
def test_cover_processing_and_fallback(tmp_path):
    big = io.BytesIO()
    Image.new("RGB", (2400, 2400), (10, 120, 200)).save(big, "PNG")
    urls = []

    class Fake(CoverFetcher):
        def _get(self, url):
            urls.append(url)
            if "82c1" in url:                                   # la versión hi-res "no existe"
                import requests
                raise requests.HTTPError("404")
            return big.getvalue()

    cf = Fake(max_px=1000, cache_path=tmp_path / "cache")
    c = cf.fetch("https://i.scdn.co/image/ab67616d0000b273deadbeef")
    assert c and max(c.width, c.height) == 1000
    img = Image.open(io.BytesIO(c.data))
    assert img.format == "JPEG" and not img.info.get("progressive") and not img.info.get("progression")
    assert urls[0].endswith("ab67616d000082c1deadbeef") and urls[-1].endswith("ab67616d0000b273deadbeef")
    n = len(urls)
    assert cf.fetch("https://i.scdn.co/image/ab67616d0000b273deadbeef") is c and len(urls) == n   # caché memoria
    assert Fake(cache_path=tmp_path / "cache").fetch("https://i.scdn.co/image/ab67616d0000b273deadbeef")
    assert len(urls) == n                                                                         # caché disco


def test_cover_never_raises(tmp_path):
    class Broken(CoverFetcher):
        def _get(self, url):
            return b"basura"

    assert Broken(cache_path=tmp_path).fetch("https://example.com/x.jpg") is None
    assert CoverFetcher(cache_path=tmp_path).fetch(None) is None
