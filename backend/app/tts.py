"""Server-side prompt audio.

The runner used to speak prompts with the browser's Web Speech API. That is a
stand-in that fails quietly: Chrome parks the engine once a microphone is open,
voice availability varies by machine, and there is no way to verify it from the
server. This synthesises the prompt to a real audio file the browser just plays
-- deterministic, verifiable, and independent of the client's speech engine.

The engine here is the platform's own `say` (macOS), converted to compact AAC
with `afconvert`. Both ship with the OS, so nothing new is installed for local
and UAT use. On a host without them -- a Linux production box -- `synthesize`
returns None and the caller falls back to the browser voice, so audio still
works, just less reliably, until a Linux engine is wired in. That fallback is
the reason this never raises.

Output is cached by (text, voice) so a passage is generated once and served to
every candidate and every replay from memory.
"""
from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

# Accent -> a natural, female-where-available system voice. Falls back to the
# system default if the named voice is not installed.
_VOICE = {"indian": "Tara", "us": "Samantha", "uk": "Daniel"}

# Bounds so a malformed prompt can neither hang the synthesiser nor be used to
# run the tool on megabytes of text.
_MAX_CHARS = 1200
_TIMEOUT_S = 20

# Generated audio, keyed by a hash of the exact text and voice. Small: a whole
# SVAR bank is a few dozen short clips.
_cache: dict[str, bytes] = {}
_disk = Path(tempfile.gettempdir()) / "commiq_tts"

# A committed bank of pre-rendered clips, shipped with the app. This is what
# makes audio work on a host that cannot synthesise (Linux production, which
# has no `say`): the fixed prompt banks are rendered once, here, and served
# from disk everywhere. Populate it with `python -m app.prerender_audio`.
_prerendered = Path(__file__).resolve().parent / "prompt_audio"


def _available() -> bool:
    return bool(shutil.which("say") and shutil.which("afconvert"))


def _key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()


def synthesize(text: str, accent: str = "indian") -> bytes | None:
    """AAC/m4a bytes for the prompt, or None if this host cannot synthesise.

    Never raises: any failure degrades to the browser-voice fallback.
    """
    text = (text or "").strip()
    if not text or len(text) > _MAX_CHARS:
        return None
    voice = _VOICE.get(accent, _VOICE["indian"])
    key = _key(text, voice)

    if key in _cache:
        return _cache[key]
    # The shipped bank first: this is the path that works on a host without the
    # synthesis tools, so it is checked before deciding we cannot synthesise.
    shipped = _prerendered / f"{key}.m4a"
    if shipped.exists():
        data = shipped.read_bytes()
        _cache[key] = data
        return data
    disk = _disk / f"{key}.m4a"
    if disk.exists():
        data = disk.read_bytes()
        _cache[key] = data
        return data

    # Nothing pre-rendered and no live engine: fall back to the browser voice.
    if not _available():
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "p.aiff"
            m4a = Path(tmp) / "p.m4a"
            # text is passed as an argv element, never through a shell.
            subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                           check=True, timeout=_TIMEOUT_S,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["afconvert", str(aiff), str(m4a),
                            "-d", "aac", "-f", "m4af", "-b", "48000"],
                           check=True, timeout=_TIMEOUT_S,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            data = m4a.read_bytes()
    except (subprocess.SubprocessError, OSError):
        return None

    if not data:
        return None
    _cache[key] = data
    try:
        _disk.mkdir(parents=True, exist_ok=True)
        disk.write_bytes(data)
    except OSError:
        pass  # memory cache is enough; disk is only a cross-restart optimisation
    return data


def data_uri(text: str, accent: str = "indian") -> str | None:
    """A `data:` URL the browser can play directly, or None to fall back."""
    data = synthesize(text, accent)
    if not data:
        return None
    return "data:audio/mp4;base64," + base64.b64encode(data).decode("ascii")


def render_to_bank(text: str, accent: str = "indian") -> bool:
    """Generate one clip and store it in the committed, shipped bank.

    For the offline pre-render step only (`python -m app.prerender_audio`), run
    on a host that can synthesise. Once committed, that clip serves everywhere,
    including hosts that cannot synthesise.
    """
    data = synthesize(text, accent)
    if not data:
        return False
    voice = _VOICE.get(accent, _VOICE["indian"])
    dest = _prerendered / f"{_key(text, voice)}.m4a"
    try:
        _prerendered.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except OSError:
        return False
