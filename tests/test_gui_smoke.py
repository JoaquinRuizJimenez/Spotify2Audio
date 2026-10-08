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
    from spotify2audio.services.device_sync import Drive
    usb, ipod = tmp_path / "usb", tmp_path / "ipod"
    usb.mkdir(); ipod.mkdir()
    drives = [Drive(usb, "MP3", "FAT32", 16 * 10**9, 12 * 10**9), Drive(ipod, "IPOD", "FAT32", 8 * 10**9, 4 * 10**9, "ipod_stock")]
    a = App(Controller(client_factory=FakeClient, pipeline_factory=FakePipeline), drive_lister=lambda: drives)
    a.shown, a.asked = shown, []
    monkeypatch.setattr(messagebox, "askyesno", lambda *x, **k: a.asked.append(x) or False)
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


def load(app, tmp_path):
    from spotify2audio.models.playlist import Playlist
    from tests.test_gui_logic import trk
    app._h_loaded(Playlist("p", "L", "o", tracks=[trk(0)]))
    app.dir_entry.delete(0, "end")
    app.dir_entry.insert(0, str(tmp_path / "out"))


def test_device_selection_sets_job_option(app, tmp_path):
    from tests.test_gui_logic import FakePipeline
    load(app, tmp_path)
    assert str(app.device_menu.cget("state")) == "disabled"            # casilla desmarcada
    app.device_var.set(True); app._on_device_toggle()
    assert str(app.device_menu.cget("state")) == "normal"
    assert app._selected_drive().mountpoint == tmp_path / "usb"
    app._on_start()
    pump(app, lambda: not app.running)
    assert FakePipeline.last_options.device_path == tmp_path / "usb" / "Music"


def test_stock_ipod_asks_before_starting(app, tmp_path):
    load(app, tmp_path)
    app.device_var.set(True); app._on_device_toggle()
    app.device_choice.set(app._drives[1].display)
    app._on_start()                                                      # el usuario responde «No»
    assert not app.running and app.asked and "firmware original" in app.asked[0][1]


def test_no_drives_message_and_refresh(app, tmp_path):
    app._drive_lister = lambda: []
    app.device_var.set(True); app._on_refresh_drives()
    assert "No se detectó" in app.device_choice.get() and app._selected_drive() is None
    assert str(app.device_menu.cget("state")) == "disabled"


def test_missing_credentials_opens_dialog_and_retries(app, tmp_path):
    from spotify2audio.core.errors import MissingCredentialsError
    opened = []
    app._on_credentials = lambda reason=None: opened.append(reason)
    app.controller._client_factory = lambda: (_ for _ in ()).throw(MissingCredentialsError("faltan"))
    app.url_entry.insert(0, "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    app._on_load()
    pump(app, lambda: bool(opened))
    assert "claves" in opened[0] and app.load_btn._ae_enabled


def test_credentials_dialog_saves(app):
    from spotify2audio.gui.credentials_dialog import CredentialsDialog
    saved, after = [], []
    dlg = CredentialsDialog(app, on_saved=lambda: after.append(1), saver=lambda a, b: saved.append((a, b)) or "un archivo de prueba")
    app.update()
    dlg.id_entry.insert(0, "a" * 32); dlg.secret_entry.insert(0, "b" * 32)
    dlg._save()
    assert saved == [("a" * 32, "b" * 32)] and after == [1]
    assert app.shown[-1][0] == "showinfo" and "un archivo de prueba" in app.shown[-1][1][1]
