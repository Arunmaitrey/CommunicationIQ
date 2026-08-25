"""Prompt-audio synthesis. Host-independent: it exercises the always-safe
behaviour (never raises, degrades to None) and, only where the platform can
synthesise, that a real clip comes back."""
from app import tts


def test_empty_text_returns_none():
    assert tts.synthesize("") is None
    assert tts.synthesize("   ") is None


def test_oversized_text_returns_none_not_a_crash():
    assert tts.synthesize("word " * 1000) is None


def test_data_uri_is_a_playable_url_or_none():
    # On a host with `say`/`afconvert` (macOS, and the UAT box) this is a real
    # AAC clip; on a host without them it is None and the runner falls back to
    # the browser voice. Both are valid -- what must never happen is a raise or
    # a malformed value.
    uri = tts.data_uri("This is a placement readiness check.", "indian")
    assert uri is None or uri.startswith("data:audio/mp4;base64,")


def test_synthesis_is_cached_when_available():
    if not tts._available():  # noqa: SLF001 -- the whole point of the test
        return
    text = "The cache should serve this the second time."
    first = tts.synthesize(text, "us")
    second = tts.synthesize(text, "us")
    assert first is not None and first == second


def test_shipped_bank_serves_without_synthesis_tools(monkeypatch):
    # A clip in the committed bank must serve even on a host that cannot
    # synthesise (Linux production). This is what makes prompt audio portable.
    text, accent = "A committed prompt clip for the portability test.", "indian"
    voice = tts._VOICE[accent]                       # noqa: SLF001
    path = tts._prerendered / f"{tts._key(text, voice)}.m4a"  # noqa: SLF001
    created = not path.exists()
    tts._prerendered.mkdir(parents=True, exist_ok=True)  # noqa: SLF001
    if created:
        path.write_bytes(b"\x00\x00\x00\x1cftypM4A ")   # enough to look like m4a
    try:
        tts._cache.clear()                            # noqa: SLF001
        monkeypatch.setattr(tts, "_available", lambda: False)
        assert tts.synthesize(text, accent) is not None, \
            "a shipped clip must serve without synthesis tools"
        assert tts.data_uri(text, accent, ).startswith("data:audio/mp4;base64,")
    finally:
        if created:
            path.unlink(missing_ok=True)
        tts._cache.clear()                            # noqa: SLF001
