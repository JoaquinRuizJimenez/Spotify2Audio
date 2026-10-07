from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from ..models.options import VALID_BITRATES, JobOptions, NormalizeMode, OutputFormat
from .paths import default_output_dir, settings_file

log = logging.getLogger(__name__)


@dataclass
class Settings:
    """Preferencias persistentes del usuario. NO contiene credenciales."""

    output_dir: str = ""
    output_format: str = OutputFormat.MP3.value
    bitrate_kbps: int = 320
    normalize: str = NormalizeMode.LOUDNORM.value
    create_folders: bool = True
    skip_existing: bool = True
    max_workers: int = 1

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(default_output_dir())

    # --- persistencia ---------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or settings_file()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except (OSError, ValueError, TypeError) as exc:
            log.warning("settings.json ilegible (%s); se usan valores por defecto", exc)
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    # --- conversión -------------------------------------------------------
    def to_job_options(self, device_path: Path | None = None) -> JobOptions:
        fmt = _enum_or_default(OutputFormat, self.output_format, OutputFormat.MP3)
        bitrate = self.bitrate_kbps if self.bitrate_kbps in VALID_BITRATES else 320
        return JobOptions(
            output_dir=Path(self.output_dir),
            output_format=fmt,
            bitrate_kbps=bitrate,
            normalize=_enum_or_default(NormalizeMode, self.normalize, NormalizeMode.LOUDNORM),
            create_folders=self.create_folders,
            skip_existing=self.skip_existing,
            max_workers=min(max(self.max_workers, 1), 8),
            device_path=device_path,
        )


def _enum_or_default(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default
