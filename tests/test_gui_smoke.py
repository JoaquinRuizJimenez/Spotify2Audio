"""Humo de la ventana real. Necesita pantalla: se activa con S2A_GUI_TESTS=1 (en Linux, vía xvfb-run)."""
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("S2A_GUI_TESTS") != "1", reason="define S2A_GUI_TESTS=1 para probar la ventana")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from tkinter import messagebox
    shown = []
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, _n=name, **k: shown.append((_n, a)))
    from tests.test_gui_logic import FakeClient, FakePipeline
    from spotify2audio.gui.app import App
    from spotify2audio.gui.controller import Controller
    FakePipeline.behavior = "ok"
    a = App(Controller(client_factory=FakeClient, pipeline_factory=FakePipeline))
    a.shown = shown
    yield a
    try:
        a.destroy()
    except Exception:
        pass


def pump(app, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("condición no alcanzada")


def test_full_flow(app, tmp_path):
    app.url_entry.insert(0, "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    app.dir_entry.delete(0, "end")
    app.dir_entry.insert(0, str(tmp_path / "out"))
    app._on_load()
    pump(app, lambda: app.playlist is not None)
    assert len(app.tree.get_children()) == 2 and app.start_btn._ae_enabled
    app._on_start()
    assert app.running and not app.start_btn._ae_enabled and app.cancel_btn._ae_enabled
    pump(app, lambda: not app.running)
    assert app.start_btn._ae_enabled and not app.cancel_btn._ae_enabled
    assert app.tree.set("0", "state") == "Completada" and app.shown and app.shown[-1][0] == "showinfo"


def test_validation_blocks_start(app):
    from spotify2audio.gui.controller import LOADED
    from tests.test_gui_logic import trk
    from spotify2audio.models.playlist import Playlist
    app._h_loaded(Playlist("p", "L", "o", tracks=[trk(0)]))
    app.dir_entry.delete(0, "end")
    app._on_start()
    assert not app.running and app.shown[-1][0] == "showwarning"


def test_wav_disables_bitrate(app):
    app.fmt_var.set("wav"); app._update_format_dependent()
    assert app.bitrate_menu.cget("state") == "disabled"
    app.fmt_var.set("mp3"); app._update_format_dependent()
    assert app.bitrate_menu.cget("state") == "normal"
