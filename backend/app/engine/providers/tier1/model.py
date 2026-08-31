"""Process-wide Faster Whisper model used by the lightweight speech engine."""
from __future__ import annotations

import logging
import os
import threading
import time

from app.config import settings

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()


def get_model():
    """Load the configured model once and reuse it for every response."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        started = time.perf_counter()
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads or (os.cpu_count() or 4),
        )
        log.info("loaded whisper model %s in %.1fs",
                 settings.whisper_model, time.perf_counter() - started)
        return _model


def warm() -> None:
    try:
        get_model()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not warm Faster Whisper (%s); transcript-based "
                    "measures will remain unscored", exc)


def is_loaded() -> bool:
    return _model is not None


def reset() -> None:
    global _model
    with _lock:
        _model = None
