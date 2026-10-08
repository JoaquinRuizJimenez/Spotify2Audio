import os
import sys
import types
from pathlib import Path

import pytest

import spotify2audio.config.credentials as cred
from spotify2audio.core.errors import MissingCredentialsError

KEYS = ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")


class FakeKeyring(types.ModuleType):
    def __init__(self, working=True, null=False):
        super().__init__("keyring")
        self.store, self.working, self.null = {}, working, null

    def set_password(self, service, user, value):
        if not self.working:
            raise RuntimeError("sin backend")
        if not self.null:
            self.store[(service, user)] = value

    def get_password(self, service, user):
        if not self.working:
            raise RuntimeError("sin backend")
        return self.store.get((service, user))


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(cred, "config_dir", lambda: cfg)
    monkeypatch.chdir(tmp_path)
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    yield cfg
    for k in KEYS:                      # load_dotenv/save escriben en os.environ fuera de monkeypatch
        os.environ.pop(k, None)


def use_keyring(monkeypatch, **kw):
    kr = FakeKeyring(**kw)
    monkeypatch.setitem(sys.modules, "keyring", kr)
    return kr


def test_missing_raises_specific_error(env, monkeypatch):
    use_keyring(monkeypatch)
    with pytest.raises(MissingCredentialsError):
        cred.load_credentials()


def test_from_environment(env, monkeypatch):
    use_keyring(monkeypatch)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", " abc ")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "def")
    assert cred.load_credentials() == ("abc", "def")


def test_from_config_dir_env_file(env, monkeypatch):
    use_keyring(monkeypatch)
    (env / ".env").write_text("SPOTIFY_CLIENT_ID=zzz\nSPOTIFY_CLIENT_SECRET=yyy\n")
    assert cred.load_credentials() == ("zzz", "yyy")


def test_from_cwd_env_file(env, monkeypatch, tmp_path):
    use_keyring(monkeypatch)
    (tmp_path / ".env").write_text("SPOTIFY_CLIENT_ID=c1\nSPOTIFY_CLIENT_SECRET=c2\n")
    assert cred.load_credentials() == ("c1", "c2")


def test_save_to_keyring_then_load(env, monkeypatch):
    kr = use_keyring(monkeypatch)
    (env / cred.TOKEN_CACHE).write_text("{}")
    where = cred.save_credentials(" id1 ", " sec1 ")
    assert "credenciales" in where or "llavero" in where
    assert kr.store[("Spotify2Audio", "client_id")] == "id1"
    assert not (env / cred.TOKEN_CACHE).exists()                   # token viejo invalidado
    for k in KEYS:
        os.environ.pop(k)
    assert cred.load_credentials() == ("id1", "sec1")               # ahora desde keyring


@pytest.mark.parametrize("kw", [dict(working=False), dict(null=True)])
def test_save_falls_back_to_env_file(env, monkeypatch, kw):
    use_keyring(monkeypatch, **kw)
    where = cred.save_credentials("id2", "sec2")
    assert Path(where) == env / ".env"
    assert "SPOTIFY_CLIENT_ID=id2" in (env / ".env").read_text()
    for k in KEYS:
        os.environ.pop(k)
    assert cred.load_credentials() == ("id2", "sec2")
