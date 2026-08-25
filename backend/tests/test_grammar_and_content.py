"""Grammar and content scoring.

The most important tests in this file are the ones asserting that something is
*not* flagged. A grammar checker aimed at Indian students that marks Indian
English as wrong is not a rough edge — it is the accent-erasure this product
exists to refuse, wearing a grammar costume.
"""
from __future__ import annotations

import pytest

from app.engine.providers.tier1.grammar import CommonErrorGrammar
from app.engine.providers.tier1.relevance import RubricRelevance, content_words

grammar = CommonErrorGrammar()
relevance = RubricRelevance()


def kinds(text: str) -> set[str]:
    return {e["type"] for e in grammar.check(text, "open_response").errors}


# -- what must be caught ---------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("I discussed about the issue with him yesterday.", "preposition"),
    ("Each of the students have submitted their work.", "agreement"),
    ("She is more taller than her younger sister.", "double_comparative"),
    ("Please revert back to me once you have checked.", "redundancy"),
    ("The reason is because the server was down all day.", "redundancy"),
    ("He did not went to the office on Monday morning.", "tense"),
    ("I am working here since two years now.", "tense"),
    ("We received many informations from the client.", "uncountable"),
    ("I am having two brothers and one sister at home.", "stative_verb"),
    ("She could able to finish the assignment on time.", "modal"),
    ("They returned back from Chennai late last night.", "redundancy"),
    ("We must cope up with the new deadline somehow.", "redundancy"),
])
def test_a_real_error_is_caught(text, kind):
    assert kind in kinds(text), f"missed {kind} in {text!r}"


def test_more_errors_cost_more():
    clean = grammar.check(
        "Our team reviewed the design before the client meeting on Friday.",
        "open_response")
    messy = grammar.check(
        "I discussed about the issue and each of them have agreed, so please "
        "revert back because the reason is because we did not went there.",
        "open_response")
    assert messy.score < clean.score
    assert len(messy.errors) >= 3


def test_the_same_error_costs_less_in_a_longer_answer():
    """One slip in forty words is not one slip in eight."""
    short = grammar.check("I discussed about the issue today.", "open_response")
    long = grammar.check(
        "In my last internship I worked with a team of six people on a "
        "reporting tool, and during the review I discussed about the issue "
        "with my manager before we agreed on the final approach together.",
        "open_response")
    assert long.score > short.score


# -- what must NOT be caught -----------------------------------------------

@pytest.mark.parametrize("text", [
    "Can we prepone the meeting to Tuesday morning?",
    "Kindly do the needful and confirm by email.",
    "My cousin brother is also appearing for the same drive.",
    "He is out of station this week, so I will handle it.",
    "I passed out of college in 2024 with a CSE degree.",
    "Please share your good name and contact number.",
    "She joined two years back as a junior developer.",
    "All my batchmates have registered for the placement drive.",
])
def test_indian_english_is_not_an_error(text):
    """A legitimate variety with hundreds of millions of speakers. Flagging it
    would be exactly the thing this product refuses to do."""
    result = grammar.check(text, "open_response")
    assert result.errors == [], f"flagged {text!r}: {result.errors}"
    assert result.score >= 75


@pytest.mark.parametrize("text", [
    "Our team reviewed the design before the client meeting on Friday.",
    "I have been working on this project for two years.",
    "One of my friends is preparing for the same interview.",
    "Neither of the candidates is available on Monday.",
    "The manager appreciated the effort of the whole department.",
    "We discussed the issue and agreed to revise the schedule.",
])
def test_correct_english_is_left_alone(text):
    result = grammar.check(text, "open_response")
    assert result.errors == [], f"false positive on {text!r}: {result.errors}"


def test_an_answer_too_short_to_judge_reports_no_opinion():
    """Three words with no errors is not evidence of good grammar — and the
    floor score must not reach the report as though it were a measurement."""
    result = grammar.check("Yes I think", "open_response")
    assert result.confidence == 0.0
    assert result.errors == []


def test_a_judgeable_answer_carries_confidence():
    result = grammar.check(
        "Our team reviewed the design before the client meeting.", "open_response")
    assert result.confidence > 0


# -- content coverage ------------------------------------------------------

STORY_POINTS = [
    "a bakery was losing customers",
    "the queue was slow",
    "she added a second billing counter",
]


def test_a_full_retell_covers_the_points():
    told = ("There was a bakery that was losing its customers because the "
            "queue at the counter was very slow, so the owner added a second "
            "billing counter.")
    result = relevance.analyse(told, {"key_points": STORY_POINTS}, "story_retell")
    assert result.coverage == 1.0
    assert all(p["covered"] for p in result.key_points)
    assert result.score >= 78


def test_a_partial_retell_scores_partially_and_says_which_points_were_missed():
    told = "A bakery was losing customers because the queue was slow."
    result = relevance.analyse(told, {"key_points": STORY_POINTS}, "story_retell")
    assert 0.5 <= result.coverage < 1.0
    missed = [p["point"] for p in result.key_points if not p["covered"]]
    assert "she added a second billing counter" in missed


def test_a_paraphrase_still_counts():
    """A student who says it in their own words has not failed the task."""
    told = ("The bakery kept losing its customers, the queue was moving slowly, "
            "and so a second counter for billing was added.")
    result = relevance.analyse(told, {"key_points": STORY_POINTS}, "story_retell")
    assert result.coverage == 1.0


def test_an_unrelated_answer_covers_nothing_and_is_flagged():
    result = relevance.analyse(
        "I like playing cricket with my friends on Sunday afternoons.",
        {"key_points": STORY_POINTS}, "story_retell")
    assert result.coverage == 0.0
    assert result.off_topic is True


def test_a_short_retell_is_reported_with_low_confidence():
    result = relevance.analyse("A bakery.", {"key_points": STORY_POINTS},
                               "story_retell")
    assert result.confidence < 0.5


# -- open response ---------------------------------------------------------

PROMPT = "Describe a skill you would like to improve this year, and why."


def test_an_open_response_is_never_given_a_content_score():
    """There is no defensible way to grade the content of an opinion. The
    result is a flag, and zero confidence keeps it out of the overall."""
    on_topic = relevance.analyse(
        "The skill I would like to improve this year is public speaking, "
        "because I get nervous when I have to present in front of a group and "
        "I want to feel confident during interviews.",
        {"prompt": PROMPT}, "open_response")
    assert on_topic.confidence == 0.0
    assert on_topic.off_topic is False


def test_an_answer_about_something_else_is_flagged():
    off = relevance.analyse(
        "Yesterday I went to the market with my mother and we bought "
        "vegetables and some fruit for the week ahead and then came home.",
        {"prompt": PROMPT}, "open_response")
    assert off.off_topic is True


def test_too_little_speech_to_judge_is_not_called_off_topic():
    result = relevance.analyse("I want to improve.", {"prompt": PROMPT},
                               "open_response")
    assert result.off_topic is False
    assert result.confidence == 0.0


def test_no_rubric_means_no_score_rather_than_a_default():
    result = relevance.analyse("Some answer text here that is long enough.",
                               {}, "story_retell")
    assert result.coverage == 0.0
    assert result.confidence == 0.0


def test_stopwords_cannot_carry_a_key_point():
    """Matching on 'the' and 'of' would make any answer cover any point."""
    assert content_words("the and of is was a an to for") == set()


# -- short answer ----------------------------------------------------------

def test_a_short_answer_is_judged_on_the_accepted_set_not_word_overlap():
    """'a key' against 'key' is 50% word accuracy and 100% correct."""
    result = relevance.analyse("A key.", {"key_points": ["key"]}, "short_answer")
    assert result.coverage == 1.0
    assert result.score == 80.0


def test_the_accepted_answers_are_alternatives_not_a_checklist():
    """The rubric for "what do you check before boarding a train?" lists
    ticket, platform and timing. Saying one of them is a correct answer, not
    a third of one."""
    result = relevance.analyse(
        "I check my ticket.",
        {"key_points": ["ticket", "platform", "timing"]}, "short_answer")
    assert result.coverage == 1.0
    assert result.score == 80.0


def test_any_accepted_phrasing_counts():
    for said in ["Autumn.", "The monsoon.", "Rainy season."]:
        result = relevance.analyse(
            said, {"key_points": ["monsoon", "autumn", "rainy", "fall"]},
            "short_answer")
        assert result.coverage == 1.0, said


def test_a_wrong_short_answer_scores_nothing():
    result = relevance.analyse("A banana.", {"key_points": ["key"]}, "short_answer")
    assert result.coverage == 0.0
    assert result.off_topic is True


def test_a_retell_still_needs_every_point():
    """The alternatives rule is Short Answer only — a retell that covers one
    point out of three has covered one point out of three."""
    result = relevance.analyse(
        "A bakery was losing customers.", {"key_points": STORY_POINTS},
        "story_retell")
    assert result.coverage < 0.5
