"""Estado del formulario (sin dependencias de Tk): validación y conversión a opciones del pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config.settings import Settings
from ..core.errors import ConfigError
from ..models.options import VALID_BITRATES, JobOptions, NormalizeMode, OutputFormat
from ..services.device_sync import SUBFOLDER

NORMALIZE_LABELS = {
    "loudnorm": "Normalizar volumen (recomendado)",
    "replaygain": "Solo etiquetas ReplayGain",
    "none": "Sin normalizar",
}
BITRATE_LABELS = [f"{b} kbps" for b in sorted(VALID_BITRATES, reverse=True)]
WORKER_CHOICES = ["1", "2", "3", "4"]


def _digits(text: str, default: int) -> int:
    found = re.sub(r"\D", "", str(text))
    return int(found) if found else default


@dataclass
class FormState:
    url: str = ""
    output_dir: str = ""
    output_format: str = OutputFormat.MP3.value
    bitrate: str = "320 kbps"
    normalize: str = NormalizeMode.LOUDNORM.value
    create_folders: bool = True
    skip_existing: bool = True
    workers: str = "1"
    copy_to_device: bool = False
    device: str = ""             # punto de montaje, p. ej. E:\\

    @classmethod
    def from_settings(cls, s: Settings) -> "FormState":
        return cls(url=s.last_url, output_dir=s.output_dir, output_format=s.output_format,
                   bitrate=f"{s.bitrate_kbps} kbps", normalize=s.normalize,
                   create_folders=s.create_folders, skip_existing=s.skip_existing, workers=str(s.max_workers),
                   copy_to_device=s.copy_to_device, device=s.last_device)

    def to_settings(self) -> Settings:
        return Settings(
            output_dir=self.output_dir.strip(), output_format=self.output_format,
            bitrate_kbps=_digits(self.bitrate, 320), normalize=self.normalize,
            create_folders=self.create_folders, skip_existing=self.skip_existing,
            max_workers=min(max(_digits(self.workers, 1), 1), 8), last_url=self.url.strip(),
            copy_to_device=self.copy_to_device, last_device=self.device)

    def to_job_options(self) -> JobOptions:
        try:
            return JobOptions(
                output_dir=Path(self.output_dir.strip()),
                output_format=OutputFormat(self.output_format),
                bitrate_kbps=_digits(self.bitrate, 320),
                normalize=NormalizeMode(self.normalize),
                create_folders=self.create_folders, skip_existing=self.skip_existing,
                max_workers=_digits(self.workers, 1),
                device_path=Path(self.device) / SUBFOLDER if self.copy_to_device and self.device else None)
        except ValueError as exc:                      # valores de enum inválidos
            raise ConfigError(str(exc)) from exc

    def validate(self) -> list[str]:
        """Lista de problemas en lenguaje claro; vacía si todo está bien para iniciar."""
        problems: list[str] = []
        if not self.output_dir.strip():
            problems.append("Elige una carpeta de destino.")
        elif Path(self.output_dir.strip()).is_file():
            problems.append("La carpeta de destino es un archivo, no una carpeta.")
        if self.copy_to_device:
            if not self.device:
                problems.append("Elige el dispositivo al que copiar (o desmarca la copia).")
            elif not Path(self.device).exists():
                problems.append(f"El dispositivo {self.device} ya no está conectado. Pulsa «Actualizar».")
        try:
            self.to_job_options()
        except ConfigError as exc:
            problems.append(str(exc))
        return problems
