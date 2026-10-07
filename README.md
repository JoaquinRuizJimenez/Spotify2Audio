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
3. **Deno** (yt-dlp lo necesita para YouTube desde nov-2025):
   ```powershell
   winget install DenoLand.Deno
   ```
4. Entorno virtual y dependencias:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install -e .
   ```
   Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
5. **Credenciales de Spotify** (https://developer.spotify.com/dashboard):
   - El dueño de la app necesita **Spotify Premium** (requisito de Spotify desde feb-2026).
   - Crea la app con *Web API* y en **Redirect URIs** añade exactamente `http://127.0.0.1:8888/callback`.
   - En *User Management* añade el email de tu cuenta de Spotify.
   - Copia `.env.example` a `.env` y rellena Client ID y Secret.
   - Solo se pueden leer playlists **tuyas o colaborativas** (restricción de Spotify en Development Mode).
6. Comprueba el entorno:
   ```powershell
   python -m spotify2audio
   pytest
   ```

## Probar con tu playlist

```powershell
python -m spotify2audio.cli "https://open.spotify.com/playlist/TU_ID"
```
La primera vez se abre el navegador para autorizar la app; el token queda guardado.

## Probar búsqueda y descarga (Fase 3)

```powershell
# Solo buscar candidatos para las 5 primeras pistas (no descarga):
python -m spotify2audio.cli "URL" --limit 0 --match 5
# Descargar el audio crudo de las 3 primeras a ./_test_downloads:
python -m spotify2audio.cli "URL" --download 3
```

## Probar la cadena completa (Fase 4)

```powershell
# 2 pistas a MP3 320 kbps con normalización de volumen:
python -m spotify2audio.cli "URL" --limit 0 --process 2 --out .\prueba_mp3
# Mismo contenido en M4A, o WAV para CD:
python -m spotify2audio.cli "URL" --limit 0 --process 2 --format m4a --out .\prueba_m4a
python -m spotify2audio.cli "URL" --limit 0 --process 2 --format wav --out .\prueba_cd
# Sin normalizar / solo etiquetas ReplayGain:
python -m spotify2audio.cli "URL" --limit 0 --process 2 --normalize none
```
Resultado: `Destino/Artista/Álbum/01 - Título.ext`, con etiquetas y portada incrustadas.
Si repites el comando, las pistas ya existentes se omiten.
