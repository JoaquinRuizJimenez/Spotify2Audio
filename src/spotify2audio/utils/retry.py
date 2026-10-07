from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


def retry(attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,)) -> Callable:
    """Reintenta la función con espera exponencial. Relanza la última excepción."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            wait = delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    log.warning("%s falló (%d/%d): %s. Reintentando en %.1fs",
                                func.__name__, attempt, attempts, exc, wait)
                    time.sleep(wait)
                    wait *= backoff
            raise RuntimeError("unreachable")
        return wrapper
    return decorator
