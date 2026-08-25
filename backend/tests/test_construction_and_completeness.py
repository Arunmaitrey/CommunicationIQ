"""Sentence Build as a construction, and completeness as its own dimension.

Both change the frozen scoring path, which is why they arrive together and
behind one re-cut of the baseline rather than as two quiet edits.

**Sentence Build.** The candidate is handed the words, jumbled, and asked to
build a sentence. Scored as ordinary word accuracy, the arrangement -- the
only thing the task measures -- barely registered, and padding the answer out
cost nothing at all.

**Completeness.** Every other dimension judges the quality of what was said.
None of them notices that a third of it never arrived: a candidate who reads
two thirds of a passage beautifully and stops has nothing wrong with their
speech, and the report used to say so.
"""
from __future__ import annotations

from app.engine.contracts.types import TranscriptResult, WordTiming
from app.engine.providers.tier1.accuracy import (COVERAGE_SHARE, ORDER_SHARE,
                                                 ReferenceMatchAccuracy,
                                                 _coverage, _lcs, normalise)

REFERENCE = "the manager approved the request yesterday"


def _said(text: str) -> TranscriptResult:
    words = [WordTiming(word=w, start_ms=i * 400, end_ms=i * 400 + 350,
                        confidence=0.9)
             for i, w in enumerate(text.split())]
    return TranscriptResult(text=text, confidence=0.9, words=words)


def _score(text: str, task_type: str = "sentence_build") -> float:
    return ReferenceMatchAccuracy().analyse(
        _said(text), REFERENCE, task_type).score


def test_the_right_sentence_scores_at_the_top():
    assert _score(REFERENCE) == 80.0


def test_saying_it_twice_no_longer_scores_as_well_as_saying_it_once():
    """The clearest thing the old scorer got wrong.

    Its denominator was the reference length alone, so extra words were free.
    A candidate who said the sentence, paused, and said it again got full
    marks for an answer that is not the sentence they were asked to build.
    """
    once = _score(REFERENCE)
    twice = _score(REFERENCE + " " + REFERENCE)
    assert twice < once - 10, (
        "padding cost only %.1f points, which is not enough to notice"
        % (once - twice))


def test_a_scramble_scores_far_below_the_sentence():
    """Using the words is not building the sentence."""
    scrambled = _score("request the approved manager yesterday the")
    assert scrambled < _score(REFERENCE) - 15


def test_the_scramble_is_reported_as_word_order_not_as_wrong_words():
    """What the candidate is told matters as much as the number.

    Aligned as substitutions, a scramble reads as though they said the wrong
    words. They did not. They said the right words, and the error is where
    they put them -- a different thing, with a different fix.
    """
    result = ReferenceMatchAccuracy().analyse(
        _said("request the approved manager yesterday the"), REFERENCE,
        "sentence_build")
    kinds = {e["kind"] for e in result.word_errors}
    assert kinds == {"word_order"}, "reported as %s" % kinds


def test_an_accepted_alternative_arrangement_scores_as_correct():
    """The bank carries none today, and the hook has to work before it can.

    Some of these sentences have a second natural arrangement. Where one is
    written down, accepting it must be a content change rather than a code
    change -- so the reading of it is tested even though nothing writes it.
    """
    alternative = "yesterday the manager approved the request"
    without = ReferenceMatchAccuracy().analyse(
        _said(alternative), REFERENCE, "sentence_build").score
    with_it = ReferenceMatchAccuracy().analyse(
        _said(alternative), REFERENCE, "sentence_build",
        alternatives=(alternative,)).score

    assert with_it == 80.0, "the accepted arrangement was still marked down"
    assert without < with_it, "the alternative made no difference at all"


def test_read_aloud_is_untouched_by_any_of_this():
    """Only Sentence Build changes. Read Aloud asks a different question --
    did the words come out -- and its scoring is not a construction test."""
    result = ReferenceMatchAccuracy().analyse(
        _said(REFERENCE), REFERENCE, "read_aloud")
    assert result.score == 80.0
    assert result.reference_words == 6
    # And it keeps the generous denominator it always had, which is right for
    # reading: a reader who repeats a word has still read the passage.
    padded = ReferenceMatchAccuracy().analyse(
        _said(REFERENCE + " " + REFERENCE), REFERENCE, "read_aloud")
    assert padded.score == 80.0


def test_the_two_halves_of_a_construction_score_are_named_and_add_up():
    assert abs(COVERAGE_SHARE + ORDER_SHARE - 1.0) < 1e-9
    assert ORDER_SHARE > COVERAGE_SHARE, (
        "order is the task -- weighting coverage higher would score a "
        "scramble above a partial sentence")


def test_coverage_counts_repeats_rather_than_distinct_words():
    """A reference with 'the' twice is not satisfied by one 'the'."""
    reference = normalise("the cat sat on the mat")
    assert _coverage(reference, normalise("the cat sat on mat")) < 1.0
    assert _coverage(reference, normalise("the cat sat on the mat")) == 1.0


def test_lcs_respects_order():
    assert _lcs(["a", "b", "c"], ["a", "b", "c"]) == 3
    assert _lcs(["a", "b", "c"], ["c", "b", "a"]) == 1


# -- completeness ---------------------------------------------------------

def test_completeness_is_weighted_and_the_weights_still_sum_to_one():
    from app.engine.pipeline import WEIGHTS

    assert "completeness" in WEIGHTS
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_the_two_mirrors_of_the_weights_match_the_engine():
    """`weighting` and `reporting` both restate WEIGHTS to stay off the frozen
    path. A re-cut that moved one and not the others would make the
    role-weighted score and the report disagree with the engine silently."""
    from app.engine.pipeline import WEIGHTS
    from app.reporting import WEIGHTS as REPORTING
    from app.weighting import ENGINE_WEIGHTS

    assert ENGINE_WEIGHTS == WEIGHTS
    assert REPORTING == WEIGHTS


class _Vad:
    def __init__(self, speech_ms: int) -> None:
        self.speech_ms = speech_ms


class _Item:
    def __init__(self, **rubric) -> None:
        self.rubric = rubric


def test_a_truncated_reading_is_incomplete_even_when_what_was_said_was_good():
    """The case completeness exists for.

    Two thirds of the passage, said perfectly. Accuracy sees only what
    arrived; fluency and pronunciation have nothing to complain about. The
    missing third has to come from somewhere.
    """
    from app.engine.pipeline import _completeness

    whole, _ = _completeness(task_type="read_aloud", item=None,
                             reference=REFERENCE, transcript=_said(REFERENCE),
                             vad=_Vad(8000))
    part, _ = _completeness(task_type="read_aloud", item=None,
                            reference=REFERENCE,
                            transcript=_said("the manager approved the"),
                            vad=_Vad(8000))
    assert whole == 1.0
    assert part is not None and part < 0.7


def test_a_short_answer_to_an_open_question_is_incomplete():
    from app.engine.pipeline import _completeness

    item = _Item(min_seconds=30)
    brief, _ = _completeness(task_type="open_response", item=item,
                             reference="", transcript=_said("not much"),
                             vad=_Vad(4000))
    full, _ = _completeness(task_type="open_response", item=item,
                            reference="", transcript=_said("plenty"),
                            vad=_Vad(31000))
    assert brief is not None and brief < 0.2
    assert full == 1.0


def test_talking_longer_never_earns_more_than_complete():
    """Otherwise the dimension rewards padding, which is the opposite of what
    it measures and exactly what a candidate would learn to do."""
    from app.engine.pipeline import _completeness

    score, _ = _completeness(task_type="open_response",
                             item=_Item(min_seconds=30), reference="",
                             transcript=_said("on and on"),
                             vad=_Vad(300_000))
    assert score == 1.0


def test_an_item_that_never_said_what_complete_means_is_not_scored_as_zero():
    """The honest refusal. Scoring silence from the bank as an incomplete
    answer fails candidates for our own missing data."""
    from app.engine.pipeline import _completeness

    score, reason = _completeness(task_type="short_answer", item=None,
                                  reference="", transcript=_said("a key"),
                                  vad=_Vad(5000))
    assert score is None
    assert reason, "unscored with no reason is what this codebase keeps fixing"


def test_completeness_has_advice_and_evidence_behind_it():
    """A new weighted dimension with no advice is a card with a blank body,
    and one with no evidence is a number nobody can check."""
    from app.reporting import ADVICE, EVIDENCE_FOR
    from app.schemas import ResponseMetrics

    assert ADVICE.get("completeness", "").strip()
    fields = set(ResponseMetrics.model_fields)
    assert set(EVIDENCE_FOR["completeness"]) <= fields
