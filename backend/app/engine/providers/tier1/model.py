"""The shared faster-whisper model.

Loaded once per process and reused. On this class of machine a cached load is
about two seconds and a transcription runs at roughly 0.6× real time for
``small.en`` — which is why scoring happens as each answer arrives rather than
in a batch at the end. A student answering item five is having item four
transcribed behind them; by the time they submit, the work is done.

Nothing here is warmed automatically on import. ``warm()`` is called from the
application's startup hook so the first student of the day does not pay for
the load.
"""
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
    """The process-wide WhisperModel, loading it on first use.

    Guarded by a lock: two responses can finish uploading at the same moment,
    and two threads racing to build the same model would allocate it twice.
    """
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
    """Load the model ahead of the first request. Safe to call more than once."""
    try:
        get_model()
    except Exception as exc:  # noqa: BLE001
        # A missing model must not stop the API booting: the registry falls
        # back to Tier 0, which is exactly what the fallback exists for.
        log.warning("could not warm the Tier-1 model (%s) — Tier 0 will serve", exc)


def is_loaded() -> bool:
    return _model is not None


def reset() -> None:
    """Drop the loaded model. Tests only."""
    global _model
    with _lock:
        _model = None
