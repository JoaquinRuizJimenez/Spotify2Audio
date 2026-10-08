import collections
import os
import sys
import types
from pathlib import Path

import pytest

from spotify2audio.core.cancellation import CancellationToken
from spotify2audio.core.errors import DeviceError
from spotify2audio.services import device_sync as ds
from spotify2audio.services.device_sync import (KIND_IPOD_STOCK, KIND_ROCKBOX, KIND_USB, Drive, DeviceSync,
                                                classify_drive, list_drives)

Part = collections.namedtuple("Part", "device mountpoint fstype opts")
Usage = collections.namedtuple("Usage", "total used free")


class FakePsutil:
    def __init__(self, parts, usage):
        self.parts, self.usage = parts, usage

    def disk_partitions(self, all=False):
        return self.parts

    def disk_usage(self, mount):
        u = self.usage[mount]
        if isinstance(u, Exception):
            raise u
        return u


# ---- detección de unidades -----------------------------------------------------------------
def test_list_drives_windows(monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    monkeypatch.setenv("SystemDrive", "C:")
    G = 10**9
    fake = FakePsutil(
        [Part("C:\\", "C:\\", "NTFS", "rw,fixed"), Part("D:\\", "D:\\", "NTFS", "rw,fixed"),
         Part("E:\\", "E:\\", "FAT32", "rw,removable"), Part("F:\\", "F:\\", "CDFS", "ro,cdrom"),
         Part("G:\\", "G:\\", "FAT32", "rw,removable"), Part("H:\\", "H:\\", "exFAT", "rw,removable"),
         Part("I:\\", "I:\\", "", "rw,removable")],
        {"C:\\": Usage(500 * G, 0, 100 * G), "D:\\": Usage(900 * G, 0, 800 * G), "E:\\": Usage(16 * G, 0, 12 * G),
         "G:\\": OSError("sin medio"), "H:\\": Usage(0, 0, 0)})
    found = list_drives(_psutil=fake)
    assert [str(d.mountpoint) for d in found] == ["E:\\"]
    assert found[0].free == 12 * G and found[0].fstype == "FAT32"
    assert [str(d.mountpoint) for d in list_drives(include_fixed=True, _psutil=fake)] == ["D:\\", "E:\\"]


def test_list_drives_unix(monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "linux")
    fake = FakePsutil([Part("/dev/sda1", "/", "ext4", "rw"), Part("/dev/sda2", "/boot", "ext4", "rw"),
                       Part("/dev/sdb1", "/media/ana/IPOD", "vfat", "rw"),
                       Part("/dev/sdc1", "/media/ana/SOLOLECTURA", "vfat", "ro,nosuid")],
                      {"/media/ana/IPOD": Usage(10**10, 0, 5 * 10**9), "/media/ana/SOLOLECTURA": Usage(10**10, 0, 0)})
    assert [str(d.mountpoint) for d in list_drives(_psutil=fake)] == ["/media/ana/IPOD"]


def test_classify_and_display(tmp_path):
    assert classify_drive(tmp_path) == KIND_USB
    (tmp_path / ".rockbox").mkdir()
    assert classify_drive(tmp_path) == KIND_ROCKBOX
    other = tmp_path / "stock"
    (other / "iPod_Control").mkdir(parents=True)
    assert classify_drive(other) == KIND_IPOD_STOCK
    d = Drive(other, "MI IPOD", "FAT32", 10**10, 5 * 10**9, KIND_IPOD_STOCK)
    assert "MI IPOD" in d.display and "firmware original" in d.display and "5.0 GB" in d.display
    assert d.warning and "Rockbox" in d.warning and d.target == other / "Music"
    assert Drive(other, "", "FAT32", 1, 1).warning is None and "Sin nombre" in Drive(other, "", "FAT32", 1, 1).display


# ---- copia -----------------------------------------------------------------------------------------
@pytest.fixture
def library(tmp_path):
    root = tmp_path / "local"
    files = []
    for rel, n in (("Band/Disc/01 - A.mp3", 300), ("Band/Disc/02 - B.mp3", 500), ("Other/Single/01 - C.mp3", 200)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * n)
        files.append(p)
    m3u = root / "lista.m3u8"
    m3u.write_text("#EXTM3U\n")
    return root, files + [m3u]


def test_copy_keeps_structure_and_is_idempotent(library, tmp_path):
    root, files = library
    dev = tmp_path / "USB" / "Music"
    seen = []
    r = DeviceSync().sync(files, root, dev, on_progress=lambda d, t, n: seen.append((d, t, n)))
    assert (r.copied, r.skipped, r.failed) == (4, 0, []) and r.bytes_copied == 1000 + len("#EXTM3U\n")
    assert (dev / "Band" / "Disc" / "02 - B.mp3").read_bytes() == b"x" * 500 and (dev / "lista.m3u8").exists()
    assert not list(dev.rglob("*.part"))
    assert seen[-1] == (4, 4, "") and seen[0][0] == 0 and all(t == 4 for _, t, _ in seen)
    again = DeviceSync().sync(files, root, dev)
    assert (again.copied, again.skipped) == (0, 4)
    files[0].write_bytes(b"y" * 999)                                   # cambia de tamaño -> se vuelve a copiar
    third = DeviceSync().sync(files, root, dev)
    assert (third.copied, third.skipped) == (1, 3) and (dev / "Band/Disc/01 - A.mp3").stat().st_size == 999


def test_not_enough_space(library, tmp_path, monkeypatch):
    root, files = library
    monkeypatch.setattr(ds, "free_bytes", lambda p: 1000)
    with pytest.raises(DeviceError, match="Espacio insuficiente"):
        DeviceSync().sync(files, root, tmp_path / "dev")


def test_unwritable_target(library, tmp_path):
    root, files = library
    blocker = tmp_path / "archivo"
    blocker.write_text("no soy una carpeta")
    with pytest.raises(DeviceError, match="No se puede escribir"):
        DeviceSync().sync(files, root, blocker / "Music")


def test_cancel_between_files(library, tmp_path):
    root, files = library
    token = CancellationToken()
    r = DeviceSync().sync(files, root, tmp_path / "dev", cancel=token,
                          on_progress=lambda d, t, n: token.cancel() if d == 1 else None)
    assert r.cancelled and r.copied == 1 and not list((tmp_path / "dev").rglob("*.part"))


def test_cancel_in_the_middle_of_a_file_leaves_nothing(library, tmp_path):
    root, files = library

    class Flip:
        def __init__(self): self.n = 0
        @property
        def is_cancelled(self):
            self.n += 1
            return self.n > 3                  # cancela durante la copia del primer archivo

    r = DeviceSync(chunk_size=50).sync(files[:1], root, tmp_path / "dev", cancel=Flip())
    assert r.cancelled and r.copied == 0
    assert not [p for p in (tmp_path / "dev").rglob("*") if p.is_file()]          # ni destino ni .part


def test_failures_are_collected_and_unplugging_aborts(library, tmp_path, monkeypatch):
    root, files = library
    (files[1]).unlink()                                                  # origen desaparecido
    r = DeviceSync().sync(files, root, tmp_path / "d1")
    assert r.copied == 3 and len(r.failed) == 1 and "02 - B" in r.failed[0][0] and "origen" in r.failed[0][1]

    def boom(self, src, dst, cancel):
        raise OSError(5, "Error de E/S")
    monkeypatch.setattr(DeviceSync, "_copy_file", boom)
    many = []
    for i in range(6):
        p = root / f"t{i}.mp3"
        p.write_bytes(b"z" * 10)
        many.append(p)
    r2 = DeviceSync().sync(many, root, tmp_path / "d2")
    assert r2.aborted and len(r2.failed) == 3 and r2.copied == 0           # se detiene tras 3 fallos seguidos
