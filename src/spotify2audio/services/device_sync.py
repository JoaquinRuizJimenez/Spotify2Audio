"""Detección de unidades extraíbles y copia segura de las canciones al dispositivo.

Copia a un archivo '.part' y lo renombra al terminar (nunca queda un MP3 a medias si se desconecta el USB),
omite lo que ya está con el mismo tamaño, comprueba el espacio antes de empezar y se puede cancelar.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psutil

from ..core.cancellation import CancellationToken
from ..core.errors import CancelledError, DeviceError
from ..models.results import SyncResult
from ..utils.diskspace import free_bytes

log = logging.getLogger(__name__)
SUBFOLDER = "Music"                  # carpeta dentro del dispositivo (Rockbox y casi todos los reproductores la usan)
KIND_USB, KIND_ROCKBOX, KIND_IPOD_STOCK = "usb", "rockbox", "ipod_stock"
_KIND_TEXT = {KIND_USB: "", KIND_ROCKBOX: " · iPod con Rockbox", KIND_IPOD_STOCK: " · iPod (firmware original)"}
_UNIX_REMOVABLE = ("/media/", "/run/media/", "/Volumes/", "/mnt/")

IPOD_STOCK_WARNING = (
    "Este iPod usa el firmware original de Apple. Ese firmware solo muestra la música que está registrada "
    "en su base de datos, así que los archivos copiados directamente NO aparecerán en el menú del iPod.\n\n"
    "Opciones: instalar Rockbox en el iPod, o añadir la carpeta de destino a iTunes / la app Música de Apple "
    "y sincronizar desde ahí.\n\n¿Copiar los archivos de todos modos?")
EJECT_REMINDER = "Antes de desconectarla, expulsa la unidad desde «Quitar hardware de forma segura»."


# ---------------------------------------------------------------------------- unidades
@dataclass(frozen=True)
class Drive:
    mountpoint: Path
    label: str
    fstype: str
    total: int
    free: int
    kind: str = KIND_USB

    @property
    def target(self) -> Path:
        return self.mountpoint / SUBFOLDER

    @property
    def display(self) -> str:
        return f"{self.mountpoint}  {self.label or 'Sin nombre'}{_KIND_TEXT.get(self.kind, '')}  ({self.free / 1e9:.1f} GB libres)"

    @property
    def warning(self) -> str | None:
        return IPOD_STOCK_WARNING if self.kind == KIND_IPOD_STOCK else None


def classify_drive(mount: Path) -> str:
    try:
        if (mount / ".rockbox").is_dir():
            return KIND_ROCKBOX
        if (mount / "iPod_Control").is_dir():
            return KIND_IPOD_STOCK
    except OSError:
        pass
    return KIND_USB


def volume_label(mount: Path) -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            if ctypes.windll.kernel32.GetVolumeInformationW(str(mount), buf, 261, None, None, None, None, 0):
                return buf.value
        except Exception:  # noqa: BLE001
            pass
        return ""
    return mount.name


def list_drives(include_fixed: bool = False, _psutil=psutil) -> list[Drive]:
    """Unidades extraíbles montadas (USB, tarjetas, reproductores). `include_fixed` añade discos externos/fijos."""
    system = (os.environ.get("SystemDrive", "C:") + "\\").upper() if sys.platform == "win32" else "/"
    drives: list[Drive] = []
    for part in _psutil.disk_partitions(all=False):
        opts, mount = (part.opts or "").lower(), part.mountpoint
        if not part.fstype or "cdrom" in opts or "ro" in opts.split(","):      # sin medio, CD o solo lectura
            continue
        if sys.platform == "win32":
            removable = "removable" in opts
            if mount.upper() == system:
                continue
        else:
            removable = mount.startswith(_UNIX_REMOVABLE)
            if mount == system:
                continue
        if not (removable or include_fixed):
            continue
        try:
            usage = _psutil.disk_usage(mount)
        except OSError:                                  # lector de tarjetas vacío, unidad sin medio...
            continue
        if usage.total <= 0:
            continue
        # TODO fix path so test passes in both Linux and Windows (rn only passes on linux)
        path = Path(mount)

        drives.append(Drive(path, volume_label(path), part.fstype, usage.total, usage.free, classify_drive(path)))
    return sorted(drives, key=lambda d: str(d.mountpoint))


# ------------------------------------------------------------------------------ copia
ProgressCb = Callable[[int, int, str], None]       # (hechos, total, archivo actual)


class DeviceSync:
    def __init__(self, chunk_size: int = 1 << 20, max_consecutive_failures: int = 3) -> None:
        self.chunk_size, self.max_failures = chunk_size, max_consecutive_failures

    def sync(self, files: list[Path], source_root: Path, target_root: Path,
             on_progress: ProgressCb | None = None, cancel: CancellationToken | None = None) -> SyncResult:
        """Copia `files` conservando su ruta relativa a `source_root` bajo `target_root`."""
        result = SyncResult(target=Path(target_root))
        items: list[tuple[Path, Path, int]] = []
        for f in files:
            f = Path(f)
            try:
                size = f.stat().st_size
            except OSError:
                result.failed.append((f.name, "el archivo de origen ya no existe"))
                continue
            try:
                rel = f.relative_to(source_root)
            except ValueError:
                rel = Path(f.name)
            items.append((f, Path(target_root) / rel, size))

        todo = [(f, d, s) for f, d, s in items if not (d.exists() and d.stat().st_size == s)]
        result.skipped = len(items) - len(todo)
        self._prepare_target(Path(target_root), sum(s for _, _, s in todo))

        total, done, consecutive = len(items), result.skipped, 0
        for src, dst, size in todo:
            if cancel and cancel.is_cancelled:
                result.cancelled = True
                break
            if on_progress:
                on_progress(done, total, src.name)
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                self._copy_file(src, dst, cancel)
                result.copied += 1
                result.bytes_copied += size
                consecutive = 0
            except CancelledError:
                result.cancelled = True
                break
            except OSError as exc:
                log.warning("No se pudo copiar %s: %s", src.name, exc)
                result.failed.append((src.name, str(exc)))
                consecutive += 1
                if consecutive >= self.max_failures:
                    result.aborted = "El dispositivo dejó de responder (¿se desconectó o está lleno?)."
                    break
            done += 1
        if on_progress:
            on_progress(done, total, "")
        return result

    @staticmethod
    def _prepare_target(target: Path, needed: int) -> None:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DeviceError(f"No se puede escribir en el dispositivo (¿desconectado o protegido contra escritura?): {exc}") from exc
        free = free_bytes(target)
        if needed * 1.02 + (1 << 20) > free:
            raise DeviceError(f"Espacio insuficiente en el dispositivo: se necesitan ~{needed / 1e6:.0f} MB "
                              f"y hay {free / 1e6:.0f} MB libres.")

    def _copy_file(self, src: Path, dst: Path, cancel: CancellationToken | None) -> None:
        tmp = dst.with_name(dst.name + ".part")
        try:
            with open(src, "rb") as fin, open(tmp, "wb") as fout:
                while chunk := fin.read(self.chunk_size):
                    if cancel and cancel.is_cancelled:
                        raise CancelledError("Copia cancelada.")
                    fout.write(chunk)
                fout.flush()
                os.fsync(fout.fileno())                  # que los datos lleguen al dispositivo antes del renombrado
            os.replace(tmp, dst)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
