# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller (modo carpeta: arranca más rápido y da menos falsos positivos de antivirus que --onefile).
Ejecutar con:  python scripts/build_exe.py
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

datas, binaries, hiddenimports = [], [], []
for package in ("customtkinter", "yt_dlp", "yt_dlp_ejs", "certifi"):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # paquete opcional ausente
        print(f"[spec] aviso: no se pudo recoger {package}: {exc}")

hiddenimports += ["keyring.backends.Windows", "keyring.backends.fail", "keyring.backends.null",
                  "PIL._tkinter_finder"]

# Herramientas externas incluidas junto a la aplicación (se buscan en bin/)
for tool in ("ffmpeg", "ffprobe", "deno"):
    path = ROOT / "bin" / f"{tool}{EXE_SUFFIX}"
    if path.is_file():
        binaries.append((str(path), "."))
    else:
        print(f"[spec] aviso: falta {path.name}: no se incluirá")

icon = ROOT / "assets" / "app.ico"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "numpy", "matplotlib", "scipy", "pandas", "IPython", "tkinter.test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Spotify2Audio",
    console=False,
    icon=str(icon) if icon.is_file() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Spotify2Audio", upx=False)
