"""The trailing-silence threshold, and what the evidence for it has to be.

``TRAILING_SILENCE_MS = 1800`` is a guess whose own comment admits it. The
analysis it will be replaced by has one property worth defending above all
others: it must not be able to declare a threshold safe on evidence that
cannot show it is unsafe. A corpus of one-word answers has no internal pauses,
so every threshold looks perfect on it -- and that is exactly the corpus this
product currently has.
"""
from __future__ import annotations

from app import silence
from app.silence import Recording


def _recording(segments, duration_ms=30_000, task="open_response"):
    return Recording(response_id="r", task_type=task, duration_ms=duration_ms,
                     segments=[{"start_ms": a, "end_ms": b}
                               for a, b in segments])


def test_a_pause_with_speech_after_it_is_evidence_of_being_cut_off():
    """The whole method, in one assertion.

    A candidate who paused for two seconds and then carried on had not
    finished, and no rating panel is needed to establish that -- their own
    recording says so.
    """
    thinking = _recording([(0, 3000), (5000, 9000)])  # a 2s gap, then more

    assert silence.would_interrupt(thinking, 1800)
    assert not silence.would_interrupt(thinking, 2500)


def test_trailing_silence_is_not_counted_as_an_interruption():
    """Silence at the end is what the threshold is *for*.

    Counting it as evidence of somebody being cut off would report every
    threshold as catastrophic and the analysis would be useless.
    """
    finished = _recording([(0, 5000)], duration_ms=30_000)

    assert silence.internal_gaps(finished.segments) == []
    assert not silence.would_interrupt(finished, 800)
    assert silence.trailing_silence_ms(finished) == 25_000


def test_a_corpus_with_no_internal_pauses_reports_no_evidence():
    """The trap this analysis exists to avoid falling into.

    Short scripted answers have nothing between them to measure. Averaging
    them in would show a 0% interruption rate at every threshold and read as
    proof that 800 ms is safe, when in truth nothing was tested.
    """
    corpus = [_recording([(0, 2000)]) for _ in range(50)]

    verdicts = silence.sweep(corpus)
    assert all(v.informative == 0 for v in verdicts), (
        "recordings with no internal gap were counted as evidence")
    assert silence.recommend(verdicts) is None, (
        "a threshold was recommended on evidence that could not contradict it")


def test_the_saving_is_reported_alongside_the_risk():
    """Both halves, because a threshold nobody reaches is also a failure.

    Adaptive advancement exists because an SVAR-style round runs eighteen
    minutes against a fifteen minute target. A report that showed only the
    interruption rate would recommend three seconds every time and leave the
    round exactly as long as it was.
    """
    corpus = [_recording([(0, 5000), (7000, 10_000)], duration_ms=30_000)
              for _ in range(10)]

    verdicts = {v.threshold_ms: v for v in silence.sweep(corpus)}

    # 20s of trailing silence each; a lower threshold trims more of it.
    assert verdicts[800].saved_ms > verdicts[3000].saved_ms
    assert verdicts[800].saved_ms == 10 * (20_000 - 800)


def test_the_recommendation_is_the_lowest_safe_threshold_not_the_safest():
    """Past the point where interruptions are rare, a higher threshold only
    spends the candidate's time."""
    # Gaps of 1.0s: anything at or below 1000 cuts every one of them off.
    corpus = [_recording([(0, 3000), (4000, 8000)], duration_ms=30_000)
              for _ in range(100)]

    verdicts = silence.sweep(corpus)
    pick = silence.recommend(verdicts)

    assert pick is not None
    assert pick.threshold_ms == 1200, (
        f"picked {pick.threshold_ms}, which is not the lowest threshold that "
        f"clears the bar")


def test_no_threshold_clears_the_bar_when_people_pause_a_lot():
    """A real answer, and the one that would keep the feature switched off.

    If candidates habitually pause for three seconds mid-answer, there is no
    threshold that both saves time and leaves them alone, and the honest
    output says so rather than picking the least bad number.
    """
    corpus = [_recording([(0, 3000), (7000, 11_000)], duration_ms=30_000)
              for _ in range(100)]

    assert silence.recommend(silence.sweep(corpus)) is None


def test_gaps_are_read_in_time_order_not_storage_order():
    """VAD output is ordered today. Depending on that silently is how an
    analysis starts producing negative gaps after somebody changes a query."""
    jumbled = Recording(response_id="r", task_type="open_response",
                        duration_ms=30_000,
                        segments=[{"start_ms": 5000, "end_ms": 9000},
                                  {"start_ms": 0, "end_ms": 3000}])

    assert silence.internal_gaps(jumbled.segments) == [2000]


def test_a_recording_with_no_segments_at_all_does_not_crash_the_sweep():
    """Silence, a dead microphone, a Tier 0 attempt with no VAD output. All
    real, and none of them should take the analysis down with them."""
    verdicts = silence.sweep([_recording([]), _recording([(0, 4000)])])

    assert verdicts
    assert all(v.informative == 0 for v in verdicts)


def test_the_current_guess_is_among_the_thresholds_reported():
    """Whatever the data says, it has to say it about the number in use --
    otherwise the report cannot tell anybody whether 1800 was wrong."""
    from app.silence import CANDIDATE_THRESHOLDS_MS

    assert 1800 in CANDIDATE_THRESHOLDS_MS
    assert min(CANDIDATE_THRESHOLDS_MS) < 1800 < max(CANDIDATE_THRESHOLDS_MS), (
        "the sweep must be able to say the guess is too high *or* too low")


def test_a_corpus_of_generated_audio_is_refused_rather_than_answered():
    """The failure this module exists to avoid, in the shape I did not expect.

    Run against the real estate, this analysis returned a confident 2500 ms on
    618 recordings. It was rubbish: 551 of the 664 gaps were exactly 2272 ms,
    because they came from the synthetic audio the test fixtures generate. One
    hardcoded pause length wearing a sample size.

    The informative-count guard did not catch it -- there was plenty of
    evidence, it just was not evidence of anything. Human speech does not
    repeat a gap to the millisecond.
    """
    fixture = [_recording([(0, 3000), (3000 + 2272, 9000)])
               for _ in range(300)]

    fake, why = silence.looks_synthetic(fixture)
    assert fake
    assert "2272" in why and "generated" in why


def test_speech_that_actually_varies_is_accepted():
    """The guard has to let real data through, or it is just an off switch."""
    varied = [_recording([(0, 3000), (3000 + 900 + i * 7, 9000)])
              for i in range(120)]

    fake, _ = silence.looks_synthetic(varied)
    assert not fake, "a corpus with no repeated gap length was called fake"


def test_an_empty_corpus_is_not_called_synthetic():
    """Nothing to measure is a different answer from measuring the wrong
    thing, and the report says each of them differently."""
    fake, why = silence.looks_synthetic([_recording([(0, 4000)])])
    assert not fake and not why
