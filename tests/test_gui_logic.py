"""Lógica de la GUI sin abrir ventanas: formulario, progreso y controlador."""
import time
from pathlib import Path

import pytest

from spotify2audio.config.settings import Settings
from spotify2audio.core.errors import ConfigError, DependencyMissingError, SpotifyError
from spotify2audio.core.events import Stage, TrackFinished, TrackProgress
from spotify2audio.gui.controller import (EVENT, JOB_DONE, JOB_ERROR, LOAD_ERROR, LOAD_PROGRESS, LOADED,
                                          Controller)
from spotify2audio.gui.form_state import BITRATE_LABELS, FormState
from spotify2audio.gui.progress_model import ProgressTracker, row_for_progress, row_for_result
from spotify2audio.models.options import JobOptions, NormalizeMode, OutputFormat
from spotify2audio.models.playlist import Playlist
from spotify2audio.models.results import JobSummary, TrackResult, TrackStatus
from spotify2audio.models.track import Track


def trk(i=0):
    return Track(spotify_id=f"id{i}", title=f"Song {i}", artists=("Band",), album="Disc", duration_ms=200000)


# ---- FormState ------------------------------------------------------------------------------------
def test_form_roundtrip_with_settings(tmp_path):
    s = Settings(output_dir=str(tmp_path), output_format="m4a", bitrate_kbps=256, normalize="none",
                 create_folders=False, skip_existing=False, max_workers=3, last_url="https://x")
    f = FormState.from_settings(s)
    assert f.bitrate == "256 kbps" and f.workers == "3" and f.url == "https://x"
    back = f.to_settings()
    assert (back.output_format, back.bitrate_kbps, back.normalize, back.max_workers, back.last_url) == ("m4a", 256, "none", 3, "https://x")
    o = f.to_job_options()
    assert o.output_format is OutputFormat.M4A and o.bitrate_kbps == 256 and o.normalize is NormalizeMode.NONE
    assert not o.create_folders and not o.skip_existing and o.max_workers == 3


def test_form_validation(tmp_path):
    assert FormState(output_dir=str(tmp_path)).validate() == []
    assert any("carpeta" in p for p in FormState(output_dir="  ").validate())
    f = tmp_path / "archivo.txt"
    f.write_text("x")
    assert any("archivo" in p for p in FormState(output_dir=str(f)).validate())
    wav_rg = FormState(output_dir=str(tmp_path), output_format="wav", normalize="replaygain")
    assert any("ReplayGain" in p for p in wav_rg.validate())
    with pytest.raises(ConfigError):
        FormState(output_dir=str(tmp_path), output_format="ogg").to_job_options()


def test_form_tolerates_odd_values(tmp_path):
    f = FormState(output_dir=str(tmp_path), bitrate="basura", workers="99")
    assert f.to_settings().bitrate_kbps == 320 and f.to_settings().max_workers == 8
    assert BITRATE_LABELS[0] == "320 kbps"


# ---- progreso -----------------------------------------------------------------------------------------
def test_tracker_combines_finished_and_partial():
    t = ProgressTracker(4)
    assert t.fraction == 0 and t.label == "0 de 4"
    t.on_progress(TrackProgress(0, trk(0), Stage.DOWNLOADING, 0.5))
    t.on_progress(TrackProgress(1, trk(1), Stage.CONVERTING, 0.5))
    assert t.fraction == pytest.approx(0.25)
    t.on_finished(TrackFinished(0, 4, TrackResult(trk(0), TrackStatus.OK), 1))
    assert t.completed == 1 and t.fraction == pytest.approx((1 + 0.5) / 4) and t.label == "1 de 4"
    for i in (1, 2, 3):
        t.on_finished(TrackFinished(i, 4, TrackResult(trk(i), TrackStatus.OK), i + 1))
    assert t.fraction == 1.0
    assert ProgressTracker(0).fraction == 0.0


def test_row_texts():
    assert row_for_progress(TrackProgress(0, trk(), Stage.CONVERTING, 0.456)).text == "Convirtiendo 46%"
    assert row_for_result(TrackResult(trk(), TrackStatus.OK)).tag == "ok"
    assert row_for_result(TrackResult(trk(), TrackStatus.SKIPPED)).text == "Ya existía"
    assert row_for_result(TrackResult(trk(), TrackStatus.SKIPPED, error="duplicada")).text == "Duplicada"
    assert row_for_result(TrackResult(trk(), TrackStatus.CANCELLED)).tag == "cancelled"
    long = row_for_result(TrackResult(trk(), TrackStatus.FAILED, error="x" * 300 + "\nmás"))
    assert long.tag == "failed" and len(long.text) <= 80 and "\n" not in long.text and long.text.endswith("…")


# ---- controlador -----------------------------------------------------------------------------------------
def wait_for(ctrl, kinds, timeout=5.0):
    got, end = [], time.time() + timeout
    while time.time() < end:
        got += ctrl.drain()
        if any(k in kinds for k, _ in got):
            return got
        time.sleep(0.01)
    raise AssertionError(f"no llegó {kinds}; recibido: {got}")


class FakeClient:
    def __init__(self, error=None):
        self.error, self.calls = error, 0

    def get_playlist(self, url, progress=None):
        self.calls += 1
        if self.error:
            raise self.error
        progress and progress(2, 2)
        return Playlist("p", "Lista", tracks=[trk(0), trk(1)])


def test_load_ok_and_client_reused():
    made = []
    ctrl = Controller(client_factory=lambda: made.append(1) or FakeClient())
    assert ctrl.load_playlist("u")
    msgs = wait_for(ctrl, {LOADED})
    assert {k for k, _ in msgs} >= {LOAD_PROGRESS, LOADED}
    ctrl._thread.join()
    ctrl.load_playlist("u")
    wait_for(ctrl, {LOADED})
    assert made == [1]                                  # el login/cliente se crea una sola vez


@pytest.mark.parametrize("err,expected", [(SpotifyError("403 prohibido"), "403"), (RuntimeError("boom"), "Error inesperado")])
def test_load_errors_become_messages(err, expected):
    ctrl = Controller(client_factory=lambda: FakeClient(err))
    ctrl.load_playlist("u")
    kind, payload = wait_for(ctrl, {LOAD_ERROR})[-1]
    assert kind == LOAD_ERROR and expected in payload


class FakePipeline:
    behavior = "ok"

    def __init__(self, options, on_event=None):
        self.options, self.on_event = options, on_event

    def run(self, playlist, cancel=None):
        if FakePipeline.behavior == "dep":
            raise DependencyMissingError("sin ffmpeg")
        if FakePipeline.behavior == "bug":
            raise ValueError("bug")
        for i, t in enumerate(playlist.tracks):
            if cancel and cancel.is_cancelled:
                break
            self.on_event(TrackFinished(i, len(playlist), TrackResult(t, TrackStatus.OK), i + 1))
        return JobSummary(playlist.name, [TrackResult(t, TrackStatus.OK) for t in playlist.tracks])


def opts(tmp_path):
    return JobOptions(output_dir=tmp_path)


def test_job_events_then_done(tmp_path):
    FakePipeline.behavior = "ok"
    ctrl = Controller(pipeline_factory=FakePipeline)
    pl = Playlist("p", "L", tracks=[trk(0), trk(1)])
    assert ctrl.start(pl, opts(tmp_path))
    msgs = wait_for(ctrl, {JOB_DONE})
    kinds = [k for k, _ in msgs]
    assert kinds.count(EVENT) == 2 and kinds[-1] == JOB_DONE and msgs[-1][1].ok == 2


@pytest.mark.parametrize("behavior,expected", [("dep", "sin ffmpeg"), ("bug", "Error inesperado")])
def test_job_errors_become_messages(tmp_path, behavior, expected):
    FakePipeline.behavior = behavior
    ctrl = Controller(pipeline_factory=FakePipeline)
    ctrl.start(Playlist("p", "L", tracks=[trk(0)]), opts(tmp_path))
    kind, payload = wait_for(ctrl, {JOB_ERROR})[-1]
    assert kind == JOB_ERROR and expected in payload


def test_cannot_start_twice_and_cancel_token(tmp_path):
    import threading
    gate = threading.Event()

    class Slow(FakePipeline):
        def run(self, playlist, cancel=None):
            gate.wait(5)
            return JobSummary(playlist.name, [TrackResult(t, TrackStatus.CANCELLED if cancel.is_cancelled else TrackStatus.OK) for t in playlist.tracks])

    ctrl = Controller(pipeline_factory=Slow)
    pl = Playlist("p", "L", tracks=[trk(0)])
    assert ctrl.start(pl, opts(tmp_path)) and ctrl.busy
    assert not ctrl.start(pl, opts(tmp_path)) and not ctrl.load_playlist("u")   # ocupado
    ctrl.cancel()
    gate.set()
    summary = wait_for(ctrl, {JOB_DONE})[-1][1]
    assert summary.cancelled == 1
    ctrl.shutdown(2)
    assert not ctrl.busy
