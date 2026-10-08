"""Punto de entrada del ejecutable (PyInstaller)."""
import os
import sys

# Sin consola (exe "windowed") stdout/stderr son None y algunas librerías fallarían al escribir.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

from spotify2audio.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
