# Spotify2Audio

Convierte playlists públicas de Spotify en archivos de audio etiquetados y organizados.

## Instalación en Windows 11

1. **Python 3.10+** (https://www.python.org, marca "Add to PATH").
2. **FFmpeg**, desde PowerShell:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   Cierra y reabre la terminal y comprueba con `ffmpeg -version`.
   Alternativa: copia `ffmpeg.exe` y `ffprobe.exe` en la carpeta `bin/` del proyecto.
3. Entorno virtual y dependencias:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install -e .
   ```
   Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
4. **Credenciales de Spotify**: crea una app en https://developer.spotify.com/dashboard
   (Redirect URI: `http://127.0.0.1:8888/callback`, aunque por ahora no se usa).
   Copia `.env.example` a `.env` y rellena Client ID y Secret.
5. Comprueba el entorno:
   ```powershell
   python -m spotify2audio
   pytest
   ```
