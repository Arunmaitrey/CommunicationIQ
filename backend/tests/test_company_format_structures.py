"""The six researched formats, pinned section by section.

The research decks are the product requirement; these tests are that
requirement written down. A drift in section order, task types, counts or
one-shot behaviour is a product change and must show up here as a failure --
not slip through as a quiet edit to a blueprint.
"""
from __future__ import annotations

from app import formats

# (task_type, item_count, prompt_plays_allowed) per section, in order.
EXPECTED: dict[str, list[tuple[str, int, int]]] = {
    # TCS iON-family A-G. E/F are SPOKEN grammar (hear the gapped/flawed
    # sentence, say the whole correct one aloud) -- the acceptance review
    # rejected the typed substitution: the channel is part of the assessment.
    "company_round_tcs": [
        ("short_answer", 4, 1),
        ("read_aloud", 4, 0),
        ("conversation_question", 3, 1),
        ("repeat_sentence", 4, 1),
        ("spoken_completion", 4, 1),
        ("spoken_correction", 4, 1),
        ("open_response", 1, 0),
    ],
    "company_round_infosys": [
        ("short_answer", 4, 1),
        ("read_aloud", 4, 0),
        ("conversation_question", 3, 1),
        ("repeat_sentence", 4, 1),
        ("spoken_completion", 4, 1),
        ("spoken_correction", 4, 1),
        ("open_response", 1, 0),
    ],
    # Wipro: the SHL A-G set plus the listening-comprehension round the demo
    # deck shows at the end.
    "company_round_wipro": [
        ("short_answer", 3, 1),
        ("read_aloud", 4, 0),
        ("conversation_question", 3, 1),
        ("repeat_sentence", 4, 1),
        ("spoken_completion", 4, 1),
        ("spoken_correction", 4, 1),
        ("open_response", 1, 0),
        ("listening_comprehension", 3, 1),
    ],
    # Cognizant: four-part A-D, SVAR-shaped, including the researched
    # isolated-word-list reading (its own reserved difficulty band).
    "company_round_cognizant": [
        ("read_aloud", 8, 0),
        ("read_aloud", 3, 0),
        ("repeat_sentence", 8, 1),
        ("open_response", 3, 0),
        ("sentence_completion", 5, 0),
        ("voice_change", 3, 0),
        ("listening_comprehension", 6, 1),
    ],
    # Versant: the canonical spoken six parts A-F.
    "versant_style_speaking_listening": [
        ("read_aloud", 6, 0),
        ("repeat_sentence", 8, 1),
        ("short_answer", 6, 1),
        ("sentence_build", 4, 0),
        ("story_retell", 3, 1),
        ("open_response", 2, 1),
    ],
    # SpeechX (Mercer | Mettl), rebuilt to the supplied screens 2026-08-23:
    # A 18 (10 read + 8 heard, split inferred), B 3, C 34 (8/8/6/6 typed +
    # 6 chosen, distribution inferred), D 12 questions over 4 clips whose
    # numbered clip screens make the source's 16.
    "speechx_style_full": [
        ("read_aloud", 10, 0),
        ("repeat_sentence", 8, 1),
        ("open_response", 3, 0),
        ("sentence_completion", 8, 0),
        ("sentence_completion", 8, 0),
        ("sentence_completion", 6, 0),
        ("sentence_completion", 6, 0),
        ("voice_change", 6, 0),
        ("listening_comprehension", 12, 1),
    ],
}

# Which presentation family each format belongs to. The skin the runner wears
# follows the style (with the documented Cognizant company override).
EXPECTED_STYLE = {
    "company_round_tcs": "company_round",
    "company_round_infosys": "company_round",
    "company_round_wipro": "company_round",
    "company_round_cognizant": "company_round",
    "versant_style_speaking_listening": "versant_style",
    "speechx_style_full": "speechx_style",
}


def test_the_six_formats_match_their_researched_structures():
    for code, want in EXPECTED.items():
        blueprint = formats.BY_CODE[code]
        got = [(s.task_type, s.item_count, s.prompt_plays_allowed)
               for s in blueprint.sections]
        assert got == want, f"{code} drifted from the researched structure"


def test_the_six_formats_carry_their_presentation_style():
    for code, style in EXPECTED_STYLE.items():
        assert formats.BY_CODE[code].style == style, code


def test_versant_speaking_prep_and_windows():
    """The distinctions the research is explicit about: story retelling is 30
    seconds after one hearing; open questions give 40 seconds; questions want
    a short answer window, not an essay."""
    v = formats.BY_CODE["versant_style_speaking_listening"]
    by_task = {s.task_type: s for s in v.sections}
    assert by_task["story_retell"].response_seconds == 30
    assert by_task["open_response"].response_seconds == 40
    assert by_task["short_answer"].response_seconds <= 15


def test_speak_on_topic_sections_give_thinking_time():
    """Cognizant B and SpeechX B are prepared speaking: think, then record."""
    for code in ("company_round_cognizant", "speechx_style_full"):
        b = formats.BY_CODE[code]
        topic = next(s for s in b.sections if s.task_type == "open_response")
        assert topic.prep_seconds == 30, code
        assert topic.response_seconds == 60, code
