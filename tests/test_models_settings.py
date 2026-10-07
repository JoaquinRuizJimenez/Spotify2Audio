import json

import pytest

from spotify2audio.config.settings import Settings
from spotify2audio.core.errors import ConfigError
from spotify2audio.models.options import JobOptions, NormalizeMode, OutputFormat
from spotify2audio.models.results import JobSummary, TrackResult, TrackStatus
from spotify2audio.models.track import Track


def make_track(**kw):
    base = dict(spotify_id="1", title="T", artists=("A", "B"), album="Al")
    base.update(kw)
    return Track(**base)


def test_track_properties():
    t = make_track(duration_ms=215000)
    assert t.primary_artist == "A"
    assert t.artist_display == "A, B"
    assert t.folder_artist == "A"
    assert t.duration_s == 215.0
    assert make_track(album_artist="VA").folder_artist == "VA"


def test_job_options_validation(tmp_path):
    with pytest.raises(ConfigError):
        JobOptions(output_dir=tmp_path, bitrate_kbps=100)
    with pytest.raises(ConfigError):
        JobOptions(output_dir=tmp_path, output_format=OutputFormat.WAV, normalize=NormalizeMode.REPLAYGAIN)
    assert JobOptions(output_dir=str(tmp_path)).output_dir == tmp_path


def test_settings_roundtrip_and_bad_values(tmp_path):
    f = tmp_path / "s.json"
    s = Settings(output_dir=str(tmp_path), output_format="wav", normalize="none")
    s.save(f)
    assert Settings.load(f).output_format == "wav"
    f.write_text(json.dumps({"output_format": "ogg", "bitrate_kbps": 999, "desconocido": 1}))
    opts = Settings.load(f).to_job_options()
    assert opts.output_format is OutputFormat.MP3 and opts.bitrate_kbps == 320
    f.write_text("{no es json")
    assert Settings.load(f).bitrate_kbps == 320


def test_summary():
    s = JobSummary()
    s.add(TrackResult(make_track(), TrackStatus.OK))
    s.add(TrackResult(make_track(), TrackStatus.FAILED, error="sin match"))
    assert (s.ok, s.failed) == (1, 1)
    assert "sin match" in s.failed_report()
