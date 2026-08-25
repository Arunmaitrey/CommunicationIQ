"""TCS and Infosys are practice rounds on reported patterns, and say so.

Their supplied research documents state, respectively, that TCS does not
publish a separate spoken round (the mock screens are illustrative) and
that the Infosys guide deliberately avoids fixed timings or counts. The
copy must never present either as an official, fixed employer assessment.
"""
from __future__ import annotations

from app import formats

TCS = formats.BY_CODE["company_round_tcs"]
INFY = formats.BY_CODE["company_round_infosys"]


def _copy(b):
    return " ".join([b.name, b.description, b.provenance, *b.what_to_expect]).lower()


def test_tcs_is_positioned_as_practice_on_a_reported_pattern():
    assert TCS.name == "TCS-family Communication Practice"
    assert "preparation simulation" in TCS.description
    assert "does not publish a separate spoken round" in TCS.provenance
    assert "our own configuration" in TCS.provenance
    text = _copy(TCS)
    for bad in ("the tcs ion", "ion-style communication assessment", "official", "the tcs assessment",
                "exact", "actual tcs"):
        assert bad not in text, bad


def test_infosys_is_positioned_as_practice_with_variable_configuration():
    assert INFY.name == "Infosys-style Communication Practice"
    assert "preparation simulation" in INFY.description
    assert "exact employer configuration may vary" in INFY.provenance
    assert "does not state fixed timings or question counts" in INFY.provenance
    text = _copy(INFY)
    for bad in ("the infosys communication assessment", "official", "mirroring the tcs", "seven-section test"):
        assert bad not in text, bad


def test_structures_were_not_changed_by_the_repositioning():
    assert [(s.task_type, s.item_count, s.prep_seconds, s.response_seconds) for s in TCS.sections] == [
        ("short_answer", 4, 0, 20), ("read_aloud", 4, 5, 20), ("conversation_question", 3, 0, 40),
        ("repeat_sentence", 4, 0, 15), ("spoken_completion", 4, 0, 15), ("spoken_correction", 4, 0, 15),
        ("open_response", 1, 30, 60)]
    assert [(s.task_type, s.item_count) for s in INFY.sections] == [
        ("short_answer", 4), ("read_aloud", 4), ("conversation_question", 3), ("repeat_sentence", 4),
        ("spoken_completion", 4), ("spoken_correction", 4), ("open_response", 1)]
