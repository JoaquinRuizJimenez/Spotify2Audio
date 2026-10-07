import collections
from pathlib import Path

import pytest

from spotify2audio.core.cancellation import CancellationToken
from spotify2audio.core.errors import CancelledError, ConfigError, DeviceError, DownloadError, MatchNotFoundError, TaggingError
from spotify2audio.core.events import JobFinished, JobStarted, Stage, TrackFinished, TrackProgress, TrackStarted
from spotify2audio.core.pipeline import FAILED_FILE, Pipeline, estimate_size_bytes
from spotify2audio.models.candidate import Candidate
from spotify2audio.models.options import JobOptions, NormalizeMode, OutputFormat
from spotify2audio.models.playlist import Playlist
from spotify2audio.models.results import TrackStatus
from spotify2audio.models.track import Track
from spotify2audio.services.audio_processor import Loudness, ProcessResult
from spotify2audio.services.downloader import DownloadedAudio


def make_tracks(n=4, dur=200):
    return [Track(spotify_id=f"id{i}", title=f"Song {i}", artists=("Band",), album="Disc", album_artist="Band",
                  track_number=i + 1, duration_ms=dur * 1000, cover_url="http://c") for i in range(n)]


class FakeDownloader:
    def __init__(self, errors=None, cancel_on=None, token=None):
        self.errors, self.cancel_on, self.token, self.calls = errors or {}, cancel_on, token, []

    def download_track(self, track, work_dir, on_progress=None, cancel=None):
        self.calls.append(track.spotify_id)
        if cancel:
            cancel.raise_if_cancelled()
        if track.spotify_id == self.cancel_on:
            self.token.cancel()
            raise CancelledError("x")
        err = self.errors.get(track.spotify_id)
        if err:
            (work_dir).mkdir(parents=True, exist_ok=True)
            (work_dir / f"{track.spotify_id}_partial.webm").write_bytes(b"x")    # resto que debe limpiarse
            raise err
        work_dir.mkdir(parents=True, exist_ok=True)
        p = work_dir / f"{track.spotify_id}_vid.webm"
        p.write_bytes(b"raw")
        for f in (0.1, 0.5, 1.0):
            on_progress and on_progress(f)
        return DownloadedAudio(p, Candidate("v" * 11, "t"), track.duration_s)


class FakeProcessor:
    def __init__(self, loud=None):
        self.loud = loud

    def convert(self, src, dst, options, duration_s=None, on_progress=None, cancel=None):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"audio")
        on_progress and on_progress(1.0)
        return ProcessResult(dst, self.loud, False)


class FakeCovers:
    def fetch(self, url):
        return None


class FakeTagger:
    def __init__(self, fail_for=None, boom_for=None):
        self.fail_for, self.boom_for, self.written = fail_for, boom_for, []

    def write(self, path, track, fmt, cover=None, replaygain=None):
        if track.spotify_id == self.fail_for:
            raise TaggingError("etiqueta rota")
        if track.spotify_id == self.boom_for:
            raise RuntimeError("bug raro")
        self.written.append((track.spotify_id, replaygain))


def build(tmp_path, tracks=None, downloader=None, tagger=None, events=None, processor=None, **opt):
    options = JobOptions(output_dir=tmp_path / "out", **opt)
    pl = Playlist("p", "Mi Lista", tracks=tracks if tracks is not None else make_tracks())
    pipe = Pipeline(options, downloader=downloader or FakeDownloader(), processor=processor or FakeProcessor(),
                    covers=FakeCovers(), tagger=tagger or FakeTagger(),
                    on_event=events.append if events is not None else None, work_root=tmp_path / "work")
    return pipe, pl, options


def test_all_ok_events_and_reports(tmp_path):
    ev = []
    pipe, pl, o = build(tmp_path, events=ev)
    s = pipe.run(pl)
    assert (s.ok, s.failed, s.skipped) == (4, 0, 0)
    assert all((o.output_dir / "Band" / "Disc" / f"0{i} - Song {i - 1}.mp3").exists() for i in range(1, 5))
    assert isinstance(ev[0], JobStarted) and isinstance(ev[-1], JobFinished)
    assert sum(isinstance(e, TrackStarted) for e in ev) == 4
    fin = [e for e in ev if isinstance(e, TrackFinished)]
    assert [e.completed for e in fin] == [1, 2, 3, 4]
    stages = {e.stage for e in ev if isinstance(e, TrackProgress)}
    assert {Stage.SEARCHING, Stage.DOWNLOADING, Stage.CONVERTING, Stage.TAGGING} <= stages
    assert all(0 <= e.fraction <= 1 for e in ev if isinstance(e, TrackProgress))
    m3u = (o.output_dir / "Mi Lista.m3u8").read_text(encoding="utf-8").splitlines()
    assert m3u[0] == "#EXTM3U" and "Band/Disc/01 - Song 0.mp3" in m3u
    assert not (o.output_dir / FAILED_FILE).exists()
    assert not list((tmp_path / "work").iterdir())                    # carpeta de trabajo limpia


def test_failures_do_not_stop_the_rest(tmp_path):
    dl = FakeDownloader(errors={"id1": MatchNotFoundError("sin match"), "id2": RuntimeError("crash")})
    pipe, pl, o = build(tmp_path, downloader=dl)
    s = pipe.run(pl)
    assert (s.ok, s.failed) == (2, 2)
    assert [r.status for r in s.results] == [TrackStatus.OK, TrackStatus.FAILED, TrackStatus.FAILED, TrackStatus.OK]
    assert "sin match" in s.results[1].error and "RuntimeError" in s.results[2].error
    report = (o.output_dir / FAILED_FILE).read_text(encoding="utf-8")
    assert "Band - Song 1 | sin match | https://open.spotify.com/track/id1" in report and "Song 2" in report
    assert not list((tmp_path / "work").iterdir())


@pytest.mark.parametrize("kind", ["fail_for", "boom_for"])
def test_tagging_failure_leaves_no_untagged_file(tmp_path, kind):
    pipe, pl, o = build(tmp_path, tagger=FakeTagger(**{kind: "id0"}))
    s = pipe.run(pl)
    assert s.results[0].status is TrackStatus.FAILED
    assert not (o.output_dir / "Band" / "Disc" / "01 - Song 0.mp3").exists()
    assert s.ok == 3


def test_rerun_only_retries_failed(tmp_path):
    pipe, pl, o = build(tmp_path, downloader=FakeDownloader(errors={"id1": DownloadError("red")}))
    assert pipe.run(pl).failed == 1 and (o.output_dir / FAILED_FILE).exists()
    dl2 = FakeDownloader()
    pipe2, _, _ = build(tmp_path, downloader=dl2)
    s = pipe2.run(pl)
    assert dl2.calls == ["id1"]                                       # solo la que faltaba
    assert (s.ok, s.skipped, s.failed) == (1, 3, 0)
    assert not (o.output_dir / FAILED_FILE).exists()                  # informe viejo eliminado


def test_no_skip_redoes_everything(tmp_path):
    build(tmp_path)[0].run(build(tmp_path)[1])
    dl = FakeDownloader()
    pipe, pl, _ = build(tmp_path, downloader=dl, skip_existing=False)
    pipe.run(pl)
    assert len(dl.calls) == 4


def test_duplicate_tracks_downloaded_once(tmp_path):
    t = make_tracks(2)
    dl = FakeDownloader()
    pipe, pl, _ = build(tmp_path, tracks=[t[0], t[1], t[0]], downloader=dl)
    s = pipe.run(pl)
    assert dl.calls.count("id0") == 1
    assert [r.status for r in s.results] == [TrackStatus.OK, TrackStatus.OK, TrackStatus.SKIPPED]
    assert s.results[2].error == "duplicada en la playlist"


def test_cancel_midway(tmp_path):
    token = CancellationToken()
    dl = FakeDownloader(cancel_on="id1", token=token)
    pipe, pl, o = build(tmp_path, downloader=dl)
    s = pipe.run(pl, cancel=token)
    assert [r.status for r in s.results] == [TrackStatus.OK] + [TrackStatus.CANCELLED] * 3
    assert s.failed == 0 and s.cancelled == 3 and "canceladas" in str(s)
    assert not list((tmp_path / "work").iterdir())
    assert not (o.output_dir / FAILED_FILE).exists()


def test_cancelled_run_keeps_previous_failed_report(tmp_path):
    pipe, pl, o = build(tmp_path, downloader=FakeDownloader(errors={"id0": DownloadError("x")}))
    pipe.run(pl)
    token = CancellationToken()
    token.cancel()
    build(tmp_path)[0].run(pl, cancel=token)
    assert (o.output_dir / FAILED_FILE).exists()                      # una cancelación no borra el informe


def test_parallel_workers_keep_order_and_unique_paths(tmp_path):
    tracks = make_tracks(12)
    tracks[5] = Track("other", "Song 4", ("Band",), "Disc", album_artist="Band", track_number=5, duration_ms=200000)
    pipe, pl, o = build(tmp_path, tracks=tracks, max_workers=4)
    s = pipe.run(pl)
    assert s.ok == 12 and [r.track.spotify_id for r in s.results] == [t.spotify_id for t in tracks]
    paths = [r.output_path for r in s.results]
    assert len(set(paths)) == 12 and all(p.exists() for p in paths)


def test_replaygain_reaches_tagger(tmp_path):
    tg = FakeTagger()
    loud = Loudness(-24.0, -3.0, 5.0, -34.0, 0.0)
    pipe, pl, _ = build(tmp_path, tagger=tg, processor=FakeProcessor(loud), normalize=NormalizeMode.REPLAYGAIN)
    pipe.run(pl)
    gain, peak = tg.written[0][1]
    assert gain == pytest.approx(6.0) and peak == pytest.approx(10 ** (-3 / 20))


def test_event_callback_errors_are_isolated(tmp_path):
    def bad(_):
        raise ValueError("GUI rota")
    options = JobOptions(output_dir=tmp_path / "out")
    pipe = Pipeline(options, downloader=FakeDownloader(), processor=FakeProcessor(), covers=FakeCovers(),
                    tagger=FakeTagger(), on_event=bad, work_root=tmp_path / "w")
    assert pipe.run(Playlist("p", "L", tracks=make_tracks(2))).ok == 2


def test_insufficient_disk_space(tmp_path, monkeypatch):
    import collections
    import spotify2audio.core.pipeline as mod
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(mod.shutil, "disk_usage", lambda p: usage(10**9, 10**9 - 1000, 1000))
    pipe, pl, _ = build(tmp_path)
    with pytest.raises(DeviceError, match="Espacio insuficiente"):
        pipe.run(pl)


def test_estimate_size():
    t = make_tracks(1, dur=60)
    mp3 = estimate_size_bytes(t, JobOptions(output_dir=Path("."), bitrate_kbps=320))
    wav = estimate_size_bytes(t, JobOptions(output_dir=Path("."), output_format=OutputFormat.WAV))
    assert 2.4e6 < mp3 < 3.5e6 and 10e6 < wav < 12.5e6


def test_missing_ffmpeg_fails_fast(tmp_path, monkeypatch):
    from spotify2audio.core.errors import DependencyMissingError
    import spotify2audio.services.audio_processor as ap
    monkeypatch.setattr(ap, "ensure_ffmpeg", lambda: (_ for _ in ()).throw(DependencyMissingError("sin ffmpeg")))
    with pytest.raises(DependencyMissingError):
        Pipeline(JobOptions(output_dir=tmp_path), downloader=FakeDownloader(), covers=FakeCovers(), tagger=FakeTagger())
