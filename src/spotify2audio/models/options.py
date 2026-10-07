from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..core.errors import ConfigError

VALID_BITRATES = (128, 192, 256, 320)


class OutputFormat(str, Enum):
    MP3 = "mp3"    # iPod / reproductores MP3
    M4A = "m4a"    # AAC, iPod / iTunes
    WAV = "wav"    # CD de audio (16-bit / 44.1 kHz estéreo)

    @property
    def extension(self) -> str:
        return self.value

    @property
    def is_lossy(self) -> bool:
        return self is not OutputFormat.WAV


class NormalizeMode(str, Enum):
    NONE = "none"
    LOUDNORM = "loudnorm"        # modifica el audio (EBU R128); funciona en todo reproductor
    REPLAYGAIN = "replaygain"    # solo etiquetas; muchos reproductores simples la ignoran


@dataclass
class JobOptions:
    output_dir: Path
    output_format: OutputFormat = OutputFormat.MP3
    bitrate_kbps: int = 320
    normalize: NormalizeMode = NormalizeMode.LOUDNORM
    create_folders: bool = True        # Artista/Álbum/...
    skip_existing: bool = True
    max_workers: int = 1
    device_path: Path | None = None    # si se indica, se copia al terminar

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.device_path is not None:
            self.device_path = Path(self.device_path)
        if self.bitrate_kbps not in VALID_BITRATES:
            raise ConfigError(f"Bitrate no válido: {self.bitrate_kbps} (usa {VALID_BITRATES})")
        if not 1 <= self.max_workers <= 8:
            raise ConfigError("max_workers debe estar entre 1 y 8")
        if self.output_format is OutputFormat.WAV and self.normalize is NormalizeMode.REPLAYGAIN:
            raise ConfigError("ReplayGain no es fiable en WAV; usa loudnorm o ninguna.")
