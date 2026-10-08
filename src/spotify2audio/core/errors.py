"""Jerarquía de excepciones propias. El pipeline captura AppError por pista."""
from __future__ import annotations


class AppError(Exception):
    """Base de todos los errores controlados de la aplicación."""


class ConfigError(AppError):
    """Configuración u opciones inválidas."""


class DependencyMissingError(AppError):
    """Falta un programa externo (p. ej. FFmpeg)."""


class SpotifyError(AppError):
    """Error con Spotify (URL inválida, credenciales, playlist no accesible)."""


class InvalidSpotifyUrlError(SpotifyError):
    pass


class MissingCredentialsError(SpotifyError):
    """No hay Client ID / Secret de Spotify configurados."""


class MatchNotFoundError(AppError):
    """No se encontró un candidato aceptable en YouTube."""


class DownloadError(AppError):
    pass


class ProcessingError(AppError):
    """Fallo de FFmpeg al convertir o normalizar."""


class TaggingError(AppError):
    pass


class DeviceError(AppError):
    """Fallo al detectar o copiar a una unidad externa."""


class CancelledError(AppError):
    """El usuario canceló el trabajo."""
