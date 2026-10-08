"""Crea el ejecutable:  python scripts/build_exe.py [--fetch-tools] [--zip] [--allow-missing-ffmpeg]

  --fetch-tools   copia ffmpeg, ffprobe y deno desde el PATH a bin/ si todavía no están
  --zip           comprime el resultado en dist/Spotify2Audio-<versión>-<sistema>.zip
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SUFFIX = ".exe" if sys.platform == "win32" else ""
TOOLS = {"ffmpeg": True, "ffprobe": True, "deno": False}        # nombre -> imprescindible
MIN_REAL_SIZE = 3_000_000                                         # un "shim" de winget pesa unos KB


def fetch_tools() -> None:
    (ROOT / "bin").mkdir(exist_ok=True)
    for name in TOOLS:
        dest = ROOT / "bin" / f"{name}{SUFFIX}"
        if dest.exists():
            continue
        found = shutil.which(name)
        if not found:
            print(f"  - {name}: no está en el PATH")
            continue
        shutil.copy2(Path(found).resolve(), dest)                 # resolve() sigue los enlaces de winget
        if dest.stat().st_size < MIN_REAL_SIZE:
            dest.unlink()
            print(f"  - {name}: {found} parece un acceso directo, no el programa real; cópialo a mano en bin/")
        else:
            print(f"  + {name}: copiado desde {found}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-tools", action="store_true")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--allow-missing-ffmpeg", action="store_true")
    args = ap.parse_args()

    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("Falta PyInstaller:  pip install -r requirements-build.txt")
        return 1

    from spotify2audio import __version__
    from spotify2audio.gui.aero import make_app_icon

    (ROOT / "assets").mkdir(exist_ok=True)
    print("Generando el icono…")
    make_app_icon(ROOT / "assets" / "app.ico")

    if args.fetch_tools:
        print("Buscando herramientas en el PATH…")
        fetch_tools()
    missing = [n for n, required in TOOLS.items() if required and not (ROOT / "bin" / f"{n}{SUFFIX}").is_file()]
    if missing and not args.allow_missing_ffmpeg:
        print(f"Faltan en bin/: {', '.join(m + SUFFIX for m in missing)}.\n"
              "Cópialos allí o ejecuta con --fetch-tools (o --allow-missing-ffmpeg para compilar sin ellos).")
        return 1
    if not (ROOT / "bin" / f"deno{SUFFIX}").is_file():
        print("Aviso: sin deno, quien use el programa tendrá que instalarlo aparte (winget install DenoLand.Deno).")

    print("Compilando con PyInstaller (puede tardar unos minutos)…")
    pyinstaller.run([str(ROOT / "packaging" / "spotify2audio.spec"), "--noconfirm", "--clean",
                     "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build")])

    out = ROOT / "dist" / "Spotify2Audio"
    if not out.is_dir():
        print("La compilación no generó la carpeta esperada.")
        return 1
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"\nListo: {out}  ({size:.0f} MB)\nEjecutable: {out / ('Spotify2Audio' + SUFFIX)}")
    if args.zip:
        name = f"Spotify2Audio-{__version__}-{'windows' if sys.platform == 'win32' else sys.platform}"
        archive = shutil.make_archive(str(ROOT / "dist" / name), "zip", ROOT / "dist", "Spotify2Audio")
        print(f"Comprimido: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
