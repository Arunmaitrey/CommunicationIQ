"""Freezing the engine for a validation study.

A study measures one specific version of the scorer. If the scoring code
changes while recordings are being collected and rated, the resulting
correlation describes an engine that no longer exists — and the failure mode
is not an honest mistake, it is the seductive one:

    collect data → tweak a threshold → collect more → rerun → keep the run
    that looked best

That is how a validation study becomes a search for a number you like. The
defence is mechanical rather than procedural: hash the scoring path, stamp the
hash onto every score, and refuse to emit a calibration when the engine that
produced the study data is not the engine in front of you.

A tag in version control records *intent* to freeze. This records *fact* —
it notices a changed constant that nobody remembered to mention.

What counts as the scoring path is deliberately narrow: the modules whose
output a score depends on. Routers, migrations and the UI can change freely
during a study; a threshold in the fluency provider cannot.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Everything a score depends on. Adding a scoring module here is part of
# writing one — a provider absent from this list can drift through a study
# unnoticed, which is the whole thing this file exists to prevent.
SCORING_PATH = [
    "app/engine/audio.py",
    "app/engine/pipeline.py",
    "app/engine/calibration.py",
    "app/engine/registry.py",
    "app/engine/contracts/types.py",
    "app/engine/contracts/speech.py",
    "app/engine/contracts/language.py",
    "app/engine/providers/tier0/vad.py",
    "app/engine/providers/tier0/fluency.py",
    "app/engine/providers/tier1/model.py",
    "app/engine/providers/tier1/asr.py",
    "app/engine/providers/tier1/vad.py",
    "app/engine/providers/tier1/accuracy.py",
    "app/engine/providers/tier1/disfluency.py",
    "app/engine/providers/tier1/grammar.py",
    "app/engine/providers/tier1/relevance.py",
    "app/engine/providers/tier1/pronunciation.py",
    "app/engine/psychometrics/bkt.py",
    "app/readiness.py",
]

FREEZE_DIR = BACKEND_ROOT / "validation_baselines"


@dataclass
class Baseline:
    name: str
    engine_hash: str
    created_at: str
    files: dict[str, str] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    note: str = ""


def _hash_file(path: Path) -> str:
    # Normalised line endings, so a checkout on another platform is not a
    # spurious drift.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fingerprint() -> tuple[str, dict[str, str], dict[str, str]]:
    """Hash the scoring path and the models it calls."""
    files: dict[str, str] = {}
    for relative in SCORING_PATH:
        path = BACKEND_ROOT / relative
        files[relative] = _hash_file(path) if path.exists() else "MISSING"

    # The model weights matter as much as the code around them: swapping
    # small.en for base.en changes every transcript and therefore every score.
    from app.engine.providers.tier1.pronunciation import MODEL_NAME as GOP_MODEL

    models = {"asr": settings.whisper_model,
              "asr_compute": settings.whisper_compute_type,
              "pronunciation": GOP_MODEL}

    combined = json.dumps({"files": files, "models": models}, sort_keys=True)
    engine_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
    return engine_hash, files, models


def current_hash() -> str:
    return fingerprint()[0]


def freeze(name: str, note: str = "") -> Baseline:
    """Record the engine as it stands, under a name a study can refer to."""
    engine_hash, files, models = fingerprint()
    baseline = Baseline(
        name=name, engine_hash=engine_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
        files=files, models=models, note=note,
    )
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    (FREEZE_DIR / f"{name}.json").write_text(
        json.dumps(asdict(baseline), indent=2), encoding="utf-8")
    return baseline


def load(name: str) -> Baseline | None:
    path = FREEZE_DIR / f"{name}.json"
    if not path.exists():
        return None
    return Baseline(**json.loads(path.read_text(encoding="utf-8")))


def drift(name: str) -> list[str]:
    """What has changed since this baseline. Empty means the engine matches.

    Returns human-readable lines rather than a boolean, because "it drifted"
    is not actionable and "the fluency provider changed" is.
    """
    baseline = load(name)
    if baseline is None:
        return [f"no baseline named {name!r} — nothing was frozen"]

    engine_hash, files, models = fingerprint()
    if engine_hash == baseline.engine_hash:
        return []

    changes: list[str] = []
    for relative, digest in baseline.files.items():
        now = files.get(relative, "MISSING")
        if now != digest:
            changes.append(f"{relative} changed since the baseline was frozen")
    for key, value in baseline.models.items():
        if models.get(key) != value:
            changes.append(f"model {key}: study used {value!r}, "
                           f"now {models.get(key)!r}")
    for relative in files:
        if relative not in baseline.files:
            changes.append(f"{relative} is new since the baseline")

    return changes or ["the engine fingerprint changed but no file differs — "
                       "check the scoring path list in app/engine/freeze.py"]


def matches(name: str) -> bool:
    return not drift(name)
