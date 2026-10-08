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

## Pipeline completo (Fase 5)

```powershell
# Playlist entera (Ctrl+C cancela de forma limpia):
python -m spotify2audio.cli "URL" --run --out "D:\Musica\MiPlaylist"
# Con 3 pistas en paralelo y WAV para CD:
python -m spotify2audio.cli "URL" --run --workers 3 --format wav --out .\cd
```
Al terminar, en la carpeta de salida:
- `failed_tracks.txt`: pistas fallidas con el motivo y su enlace de Spotify. Repite el mismo comando para reintentar solo esas.
- `<Nombre de la playlist>.m3u8`: lista de reproducción con rutas relativas, en el orden de Spotify.

## Interfaz gráfica (Fase 6)

```powershell
python -m spotify2audio          # abre la aplicación
python -m spotify2audio --check  # solo comprueba FFmpeg, Deno y credenciales
```
También puedes hacer doble clic en `Spotify2Audio.bat` (sin ventana de consola).

Flujo: pega el enlace → **Cargar** → elige formato y carpeta → **Iniciar conversión**.
Tus opciones y la última URL se guardan al cerrar. Si algo falla, el motivo aparece en la cola,
en el registro y en `failed_tracks.txt`; vuelve a pulsar *Iniciar* para reintentar solo lo que falta.

Tests de la ventana real (opcionales; abren una ventana unos segundos):
```powershell
$env:S2A_GUI_TESTS = "1"; pytest tests/test_gui_smoke.py
```

## Copiar a un dispositivo (Fase 7)

Marca **«Copiar también a un dispositivo»** y elige la unidad en la lista (pulsa *Actualizar* si la conectaste después).
Las canciones se procesan siempre en la carpeta de destino y, al terminar, se copian a `<unidad>\Music\Artista\Álbum\…`
junto con la lista `.m3u8`.

- La copia es segura: escribe en un archivo temporal y lo renombra al terminar, omite lo que ya está y comprueba el espacio.
- Solo se listan unidades **extraíbles**. Un disco duro USB que Windows trate como «fijo» no aparece: usa *Examinar…* y elígelo como carpeta de destino.
- **iPod con firmware original de Apple**: el iPod solo muestra lo que está en su base de datos, así que los archivos copiados no aparecerán en su menú.
  Opciones: instalar [Rockbox](https://www.rockbox.org), o añadir la carpeta de destino a iTunes / la app Música y sincronizar desde ahí.
- Expulsa siempre la unidad con «Quitar hardware de forma segura» antes de desconectarla.

## Credenciales de Spotify desde la aplicación

Si no hay credenciales, al pulsar *Cargar* se abre el diálogo para guardarlas (botón **Credenciales…**).
Se guardan en el Administrador de credenciales de Windows (o, si no está disponible, en un `.env` dentro de la
carpeta de configuración). También se leen de variables de entorno o de un `.env` en la carpeta actual o junto al `.exe`.

## Crear el ejecutable (.exe)

```powershell
pip install -r requirements-build.txt
python scripts/build_exe.py --fetch-tools --zip
```
`--fetch-tools` copia `ffmpeg`, `ffprobe` y `deno` desde tu PATH a `bin/` (si no, cópialos tú a mano).
El resultado queda en `dist\Spotify2Audio\` (ejecutable: `Spotify2Audio.exe`) y, con `--zip`, en un `.zip` listo para compartir.
Se genera una **carpeta** (no un único archivo): arranca más rápido y los antivirus lo marcan menos.

Notas para distribuirlo:
- Windows SmartScreen o el antivirus pueden avisar la primera vez porque el programa no está firmado digitalmente.
- Incluir FFmpeg en lo que compartas implica cumplir su licencia (las compilaciones de Gyan son GPL).
- Cada persona necesita sus propias credenciales de Spotify (cuenta Premium y ser añadida en tu Dashboard, máximo 5 usuarios en modo desarrollo).
