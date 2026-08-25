"""The Tier-0 engine, measured against audio whose properties we set.

These assert on *direction and ordering* rather than exact scores. A test that
pins fluency to 66.4 fails the first time a threshold is tuned and tells you
nothing about whether the tuning was right; a test that says hesitant speech
must score below fluent speech keeps being true for the reason we care about.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.engine.audio import (AudioDecodeError, decode_wav, signal_quality,
                              syllable_nuclei)
from app.engine.pipeline import _biggest_lever, _latency_score
from app.engine.providers.tier0.fluency import FeatureFluency
from app.engine.providers.tier0.vad import EnergyVAD
from tests.audio_fixtures import (FLUENT, HESITANT, RUSHED, clipped, noisy,
                                  silence, speech_like, to_wav)


def analyse(samples):
    wave = decode_wav(to_wav(samples))
    vad = EnergyVAD().analyse(wave, prompt_end_ms=0)
    fluency = FeatureFluency().analyse(wave, vad=vad)
    return wave, vad, fluency


# -- decoding --------------------------------------------------------------

def test_a_wav_round_trips_with_its_duration_intact():
    wave = decode_wav(to_wav(speech_like(3.0)))
    assert wave.sample_rate == 16000
    assert 2950 <= wave.duration_ms <= 3050


def test_a_non_wav_upload_is_refused_rather_than_guessed_at():
    with pytest.raises(AudioDecodeError):
        decode_wav(b"this is not audio")
    with pytest.raises(AudioDecodeError):
        decode_wav(b"")


def test_stereo_is_mixed_to_mono():
    mono = speech_like(2.0)
    stereo = np.repeat(mono, 2)
    import io
    import wave as wavemod
    buf = io.BytesIO()
    with wavemod.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    decoded = decode_wav(buf.getvalue())
    assert 1950 <= decoded.duration_ms <= 2050


# -- voice activity --------------------------------------------------------

def test_speech_onset_is_measured_not_assumed():
    _, vad, _ = analyse(speech_like(6.0, start_silence=1.5))
    assert vad.onset_ms is not None
    # Within a couple of frames of the silence we actually inserted.
    assert 1400 <= vad.onset_ms <= 1700


def test_an_internal_gap_becomes_a_pause():
    _, vad, fluency = analyse(speech_like(8.0, gaps=((3.0, 5.0),)))
    assert len(vad.segments) == 2
    assert fluency.pause_count == 1
    assert 1800 <= fluency.longest_pause_ms <= 2200


def test_a_stop_consonant_sized_gap_is_not_a_pause():
    """80 ms of closure is a consonant. Counting it as hesitation would make
    every fluent speaker look like they were stalling."""
    _, vad, fluency = analyse(speech_like(6.0, gaps=((3.0, 3.08),)))
    assert fluency.pause_count == 0


def test_silence_yields_no_speech_and_no_confidence():
    _, vad, fluency = analyse(silence())
    assert vad.segments == []
    assert vad.speech_ms == 0
    assert vad.onset_ms is None
    assert fluency.confidence == 0.0


# -- fluency ---------------------------------------------------------------

def test_hesitant_speech_scores_below_fluent_speech():
    _, _, fluent = analyse(FLUENT())
    _, _, hesitant = analyse(HESITANT())
    assert hesitant.score < fluent.score - 8


def test_rushed_speech_is_penalised_too():
    """Too fast costs a listener comprehension just as too slow does. A
    monotonic 'faster is better' rate score would reward the wrong thing."""
    _, _, fluent = analyse(FLUENT())
    _, _, rushed = analyse(RUSHED())
    assert rushed.articulation_rate > fluent.articulation_rate
    assert rushed.score < fluent.score


def test_the_syllable_rate_tracks_the_rate_we_synthesised():
    for target in (3.0, 4.5, 6.0):
        _, _, fluency = analyse(speech_like(6.0, syllables_per_sec=target))
        assert abs(fluency.articulation_rate - target) < 1.0, target


def test_a_noisy_room_lowers_confidence_not_just_the_score():
    _, _, clean = analyse(FLUENT())
    _, _, dirty = analyse(noisy())
    assert dirty.confidence < clean.confidence


# -- signal quality --------------------------------------------------------

def test_clipping_is_detected():
    assert signal_quality(decode_wav(to_wav(clipped()))).clipped


def test_a_clean_recording_is_reported_as_good():
    assert signal_quality(decode_wav(to_wav(FLUENT()))).verdict == "good"


def test_an_empty_room_is_reported_as_no_speech():
    assert signal_quality(decode_wav(to_wav(silence()))).verdict == "no_speech"


def test_syllable_nuclei_need_a_dip_between_them():
    """A sustained tone is one long sound, not forty syllables."""
    tone = 0.4 * np.sin(2 * np.pi * 140 * np.arange(16000 * 4) / 16000)
    wave = decode_wav(to_wav(tone))
    quality = signal_quality(wave)
    assert len(syllable_nuclei(wave, quality.noise_floor_dbfs + 8.0)) <= 3


# -- scoring maths ---------------------------------------------------------

def test_latency_scoring_is_monotonic_and_bounded():
    scores = [_latency_score(ms) for ms in (0, 500, 800, 1200, 2000, 3500, 9000)]
    assert scores == sorted(scores, reverse=True)
    assert max(scores) <= 80.0 and min(scores) >= 20.0


def test_the_biggest_lever_is_the_weakest_dimension():
    lever = _biggest_lever({"fluency": 40.0, "latency": 70.0})
    assert lever is not None
    assert lever["dimension"] == "fluency"
    assert lever["predicted_gain"] > 0


def test_there_is_no_lever_when_the_dimensions_are_level():
    """GAM-19: a near-miss message must be backed by a real number. Inventing
    a lever where none exists is the failure this guards."""
    assert _biggest_lever({"fluency": 58.0, "latency": 58.5}) is None


def test_a_single_dimension_offers_no_comparison():
    assert _biggest_lever({"fluency": 40.0}) is None
