"""The Tier-1 engine, on real speech.

The fixtures in ``tests/fixtures`` are Windows TTS renderings of known
sentences: real speech signal, known ground truth. They are not a substitute
for accented human speech — no synthetic voice is — but they are enough to
prove the pipeline recovers words, times them, and scores accuracy against a
reference rather than against itself.

Skipped rather than failed where the model is unavailable: the Tier-0 fallback
is the supported configuration on a host without the weights, and a red suite
would be reporting the wrong thing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.engine.audio import decode_wav, resample_to
from app.engine.contracts.types import TranscriptResult, VADResult, WordTiming

FIXTURES = Path(__file__).parent / "fixtures"

SPOKEN = {
    "meeting": "The meeting was postponed to next Tuesday.",
    "results": "The results will be announced on Friday afternoon.",
    "practice": "Regular practice makes a noticeable difference in fluency.",
}

pytestmark = pytest.mark.skipif(
    not (FIXTURES / "meeting.wav").exists(),
    reason="speech fixtures not generated on this host",
)


def samples_for(name: str) -> np.ndarray:
    wave = decode_wav((FIXTURES / f"{name}.wav").read_bytes())
    return resample_to(wave, 16000).samples.astype(np.float32)


@pytest.fixture(scope="module")
def asr():
    try:
        from app.engine.providers.tier1.asr import FasterWhisperASR
        from app.engine.providers.tier1.model import get_model
        get_model()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Tier-1 model unavailable: {exc}")
    return FasterWhisperASR()


@pytest.fixture(scope="module")
def vad():
    from app.engine.providers.tier1.vad import SileroVAD
    return SileroVAD()


# -- transcription ---------------------------------------------------------

@pytest.mark.parametrize("name", list(SPOKEN))
def test_speech_is_transcribed_to_the_words_that_were_spoken(asr, name):
    from app.engine.providers.tier1.accuracy import normalise

    result = asr.analyse(samples_for(name))
    heard = normalise(result.text)
    expected = normalise(SPOKEN[name])

    assert heard == expected, f"heard {result.text!r}"
    assert result.confidence > 0.5


def test_every_word_carries_a_timestamp(asr):
    result = asr.analyse(samples_for("meeting"))
    assert result.words
    assert len(result.words) == len(SPOKEN["meeting"].split())
    for word in result.words:
        assert 0 <= word.start_ms < word.end_ms
        assert 0.0 <= word.confidence <= 1.0
    # Monotonic — the listen-back scrubber depends on it.
    starts = [w.start_ms for w in result.words]
    assert starts == sorted(starts)


def test_silence_transcribes_to_nothing_rather_than_hallucinating(asr):
    """Whisper will invent text in silence if it is allowed to. It is not."""
    from app.engine.providers.tier1.accuracy import normalise
    quiet = np.random.default_rng(2).normal(0, 0.0004, 16000 * 4).astype(np.float32)
    result = asr.analyse(quiet)
    assert len(normalise(result.text)) <= 3, f"hallucinated: {result.text!r}"


def test_the_reference_is_never_fed_to_the_model(asr):
    """Priming whisper with the answer would make every scripted score a
    measurement of our own prompt. The hint is accepted and ignored."""
    honest = asr.analyse(samples_for("meeting"))

    import asyncio

    from app.engine.contracts.types import AudioRef
    from app.storage import get_storage, recording_key

    key = recording_key("hinttest", "attempt", "response", "wav")
    get_storage().put(key, (FIXTURES / "meeting.wav").read_bytes(), "audio/wav")
    try:
        hinted = asyncio.run(asr.transcribe(
            AudioRef(storage_key=key),
            hint_text="Pineapples orbit the quiet mountain on Thursday.",
        ))
        assert "pineapple" not in hinted.text.lower()
        assert "mountain" not in hinted.text.lower()
        assert hinted.text.strip() == honest.text.strip()
    finally:
        get_storage().delete(key)


# -- voice activity --------------------------------------------------------

def test_silero_finds_the_speech(vad):
    result = vad.analyse(samples_for("practice"), prompt_end_ms=0)
    assert result.segments
    assert result.speech_ms > 1000
    assert result.onset_ms is not None


def test_silero_finds_no_speech_in_a_quiet_room(vad):
    quiet = np.random.default_rng(5).normal(0, 0.0004, 16000 * 3).astype(np.float32)
    result = vad.analyse(quiet, prompt_end_ms=0)
    assert result.speech_ms == 0
    assert result.onset_ms is None


# -- accuracy --------------------------------------------------------------

def test_a_correct_repeat_scores_near_the_top(asr):
    from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy

    transcript = asr.analyse(samples_for("meeting"))
    result = ReferenceMatchAccuracy().analyse(
        transcript, SPOKEN["meeting"], "repeat_sentence")

    assert result.accuracy == 1.0
    assert result.score >= 78
    assert result.word_errors == []
    assert result.confidence > 0.5


def test_a_wrong_repeat_is_marked_down_and_says_which_words(asr):
    from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy

    transcript = asr.analyse(samples_for("meeting"))
    result = ReferenceMatchAccuracy().analyse(
        transcript, "The lecture was cancelled on Monday morning.", "repeat_sentence")

    assert result.accuracy < 0.6
    assert result.word_errors
    kinds = {e["kind"] for e in result.word_errors}
    assert kinds & {"substitution", "deletion", "insertion"}


def test_an_open_response_has_no_reference_to_score_against():
    from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy

    result = ReferenceMatchAccuracy().analyse(
        TranscriptResult(text="I think teamwork matters a great deal."),
        "", "open_response")
    assert result.confidence == 0.0


def test_saying_nothing_is_a_deletion_of_everything():
    from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy

    result = ReferenceMatchAccuracy().analyse(
        TranscriptResult(text=""), "The meeting was postponed.", "repeat_sentence")
    assert result.accuracy == 0.0
    assert all(e["kind"] == "deletion" for e in result.word_errors)


# -- disfluency ------------------------------------------------------------

def words(pairs) -> TranscriptResult:
    timings = [WordTiming(word=w, start_ms=i * 400, end_ms=i * 400 + 300,
                          confidence=0.9)
               for i, w in enumerate(pairs)]
    return TranscriptResult(text=" ".join(pairs), words=timings, confidence=0.9)


def test_fillers_are_found_and_cost_something():
    from app.engine.providers.tier1.disfluency import TranscriptDisfluency

    clean = TranscriptDisfluency().analyse(
        words("the meeting was postponed to next tuesday morning".split()),
        VADResult())
    messy = TranscriptDisfluency().analyse(
        words("um the uh meeting was um postponed to er next tuesday".split()),
        VADResult())

    assert messy.filler_count >= 4
    assert messy.score < clean.score


def test_an_immediate_repeat_is_a_stumble_and_a_delayed_one_is_a_restart():
    """Long enough to be judged at all — below the minimum the provider
    reports no opinion rather than a floor score."""
    from app.engine.providers.tier1.disfluency import TranscriptDisfluency

    tail = "meeting started late because the room was locked".split()

    def timeline(gap_ms: int) -> list[WordTiming]:
        words = [WordTiming("the", 0, 200, 0.9),
                 WordTiming("the", 200 + gap_ms, 400 + gap_ms, 0.9)]
        cursor = 450 + gap_ms
        for word in tail:
            words.append(WordTiming(word, cursor, cursor + 300, 0.9))
            cursor += 350
        return words

    stumble = timeline(20)
    restart = timeline(1000)
    text = "the the " + " ".join(tail)

    a = TranscriptDisfluency().analyse(
        TranscriptResult(text=text, words=stumble), VADResult())
    b = TranscriptDisfluency().analyse(
        TranscriptResult(text=text, words=restart), VADResult())

    assert {e["type"] for e in a.events} == {"repetition"}
    assert {e["type"] for e in b.events} == {"false_start"}
    assert a.confidence > 0 and b.confidence > 0


def test_ordinary_speech_is_not_flagged_as_disfluent():
    """Marking normal speech as a defect is how a diagnostic loses trust."""
    from app.engine.providers.tier1.disfluency import TranscriptDisfluency

    result = TranscriptDisfluency().analyse(
        words(("our team decided to review the design once more before the "
               "client meeting on friday").split()),
        VADResult())
    assert result.events == []
    assert result.score >= 75


# -- normalisation ---------------------------------------------------------

def test_digits_and_number_words_are_the_same_word():
    """Whisper writes "9" where the student said "nine". Counting that as a
    substitution marks someone down for the recogniser's formatting habit."""
    from app.engine.providers.tier1.accuracy import (ReferenceMatchAccuracy,
                                                     normalise)

    assert normalise("begins at 9 in the morning") == normalise("begins at nine in the morning")
    assert normalise("21 students") == ["twenty", "one", "students"]

    result = ReferenceMatchAccuracy().analyse(
        TranscriptResult(text="The training session begins at 9 in the morning.",
                         words=[WordTiming(w, i * 300, i * 300 + 250, 0.9)
                                for i, w in enumerate(
                                    "The training session begins at 9 in the morning".split())]),
        "The training session begins at nine in the morning.", "read_aloud")

    assert result.accuracy == 1.0
    assert result.word_errors == []


def test_a_number_too_large_to_spell_is_left_alone():
    from app.engine.providers.tier1.accuracy import normalise
    assert normalise("the year 2026") == ["the", "year", "2026"]


# -- pronunciation ---------------------------------------------------------

@pytest.fixture(scope="module")
def gop():
    try:
        from app.engine.providers.tier1.pronunciation import Wav2VecGOP
        Wav2VecGOP().analyse(samples_for("meeting"), SPOKEN["meeting"])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pronunciation model unavailable: {exc}")
    from app.engine.providers.tier1.pronunciation import Wav2VecGOP
    return Wav2VecGOP()


def test_clear_speech_scores_well_on_every_word(gop):
    result = gop.analyse(samples_for("practice"), SPOKEN["practice"])
    assert result.score >= 70
    assert result.confidence > 0
    assert len(result.phonemes) == len(SPOKEN["practice"].split())
    assert result.mispronounced_words == []


def test_the_last_word_is_not_penalised_for_being_last(gop):
    """CTC alignment needs frames for the final unit. Without an edge pad a
    recording that stops the instant the speaker does scores its last word at
    the floor — which would mislabel almost every timed answer."""
    for name, reference in SPOKEN.items():
        result = gop.analyse(samples_for(name), reference)
        last = result.phonemes[-1]
        assert last["score"] >= 60, f"{name}: {last}"


def test_a_word_that_was_not_said_is_flagged(gop):
    """The audio says one sentence; the target claims another."""
    result = gop.analyse(samples_for("meeting"),
                         "Regular practice makes a noticeable difference.")
    assert result.score < 40
    assert result.mispronounced_words


def test_noise_is_reported_with_low_confidence_not_a_low_score(gop):
    """An unusable recording is our problem to report, not the student's fault
    to be scored on."""
    noise = np.random.default_rng(3).normal(0, 0.01, 16000 * 3).astype(np.float32)
    result = gop.analyse(noise, "The meeting was postponed to next Tuesday.")
    assert result.confidence < 0.4


def test_every_word_carries_a_timestamp_inside_the_recording(gop):
    """The pad is added before alignment and subtracted back out, so the
    listen-back can jump to a word without landing in padding."""
    samples = samples_for("results")
    duration_ms = int(1000 * samples.size / 16000)
    result = gop.analyse(samples, SPOKEN["results"])
    for word in result.phonemes:
        assert 0 <= word["start_ms"] < word["end_ms"] <= duration_ms + 50, word


def test_digits_and_number_words_align_the_same(gop):
    """Reuses the accuracy provider's normalisation, so a reference reading
    "nine" and one reading "9" produce the same target sequence."""
    from app.engine.providers.tier1.pronunciation import _tokenisable
    assert _tokenisable("begins at 9") == _tokenisable("begins at nine")


def test_an_empty_reference_scores_nothing_rather_than_guessing(gop):
    result = gop.analyse(samples_for("meeting"), "")
    assert result.confidence == 0.0
