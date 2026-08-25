"""Tier 1 — common-error detection (ENG-10).

Not a grammar model. A high-precision rule set aimed at the specific errors
this population actually makes and a recruiter actually notices: preposition
choice after certain verbs, agreement with "each" and "one of", uncountable
nouns pluralised, redundant pairs, and the present-perfect/past-simple
boundary. It finds a fraction of what a real GEC model would and it names
itself accordingly, because a "grammar score" that misses half the errors is
only useful if nobody mistakes it for a complete one.

**It does not flag Indian English.** "Prepone", "do the needful", "kindly
revert", "out of station", "cousin brother", "passed out of college" — these
are dialect features of a legitimate variety with hundreds of millions of
speakers, not mistakes. Marking them down would be the accent-erasure this
product exists to refuse, wearing a grammar costume. The exclusion list below
is as load-bearing as the error list, and the tests cover it.

Precision over recall, deliberately. A false positive teaches a student
something untrue about their own English; a miss just leaves them where they
were.
"""
from __future__ import annotations

import re

from app.engine.contracts.types import GrammarResult, ProviderMeta

SCALE_MIN = 20.0
SCALE_MAX = 80.0

# Errors that are unambiguous in any variety of English. Each entry is
# (pattern, error type, what to say instead, severity 1-3).
RULES: list[tuple[str, str, str, int]] = [
    # -- verb + preposition ------------------------------------------------
    (r"\bdiscuss(?:ed|ing|es)?\s+about\b", "preposition",
     "'discuss' takes a direct object: discuss the issue, not discuss about it", 2),
    (r"\b(?:emphasi[sz]e[ds]?|emphasi[sz]ing)\s+on\b", "preposition",
     "'emphasise' takes a direct object: emphasise the point", 2),
    (r"\bcope\s+up\s+with\b", "redundancy",
     "'cope with' — the 'up' is not needed", 1),
    (r"\breach(?:ed|es|ing)?\s+to\s+(?:the\s+)?(?:office|station|college|home)\b",
     "preposition", "'reach the office', without 'to'", 1),

    # -- redundant pairs ---------------------------------------------------
    (r"\brevert\s+back\b", "redundancy",
     "'revert' already means to go back — and it does not mean 'reply'", 2),
    (r"\breturn(?:ed|ing|s)?\s+back\b", "redundancy",
     "'return' already means to come back", 1),
    (r"\brepeat(?:ed|ing|s)?\s+again\b", "redundancy",
     "'repeat' already means again", 1),
    (r"\bthe\s+reason\s+is\s+because\b", "redundancy",
     "'the reason is that', or just 'because'", 2),
    (r"\bmore\s+(?:better|taller|faster|easier|bigger|smaller|higher|lower|"
     r"stronger|older|younger|richer|cheaper|simpler)\b", "double_comparative",
     "the word is already comparative — drop 'more'", 2),
    (r"\bmost\s+(?:best|worst|easiest|biggest|highest)\b", "double_superlative",
     "the word is already superlative — drop 'most'", 2),

    # -- agreement ---------------------------------------------------------
    (r"\b(?:each|every|either|neither)\s+(?:of\s+(?:the\s+)?\w+\s+)?(?:have|are|were|do)\b",
     "agreement", "'each', 'every', 'either' and 'neither' take a singular verb", 3),
    (r"\bone\s+of\s+(?:my|the|our|his|her|their)\s+\w+?(?<!s)\b(?=\s+(?:is|was|has))",
     "agreement", "'one of' takes a plural noun: one of my friends", 2),
    (r"\bone\s+of\s+(?:my|the|our|his|her|their)\s+\w+s\s+(?:are|were|have)\b",
     "agreement", "'one of' takes a singular verb: one of my friends is", 3),

    # -- uncountable nouns -------------------------------------------------
    (r"\b(?:informations|equipments|furnitures|advices|luggages|softwares|"
     r"feedbacks|homeworks|staffs|evidences)\b", "uncountable",
     "this noun has no plural in English", 2),

    # -- tense -------------------------------------------------------------
    (r"\bdid\s+not\s+(?:went|came|saw|took|gave|made|got|said|knew|found)\b",
     "tense", "after 'did' the verb stays in its base form: did not go", 3),
    (r"\bdidn'?t\s+(?:went|came|saw|took|gave|made|got|said|knew|found)\b",
     "tense", "after 'didn't' the verb stays in its base form", 3),
    (r"\b(?:am|is|are|was|were)\s+\w+ing\s+(?:here|there|with\s+\w+)?\s*since\s+"
     r"(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
     r"(?:year|month|week|day|hour)s?\b", "tense",
     "a period uses 'for': I have been working here for two years", 3),
    (r"\bsince\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
     r"(?:year|month|week|day|hour)s?\b", "preposition",
     "'since' takes a starting point; a length of time takes 'for'", 2),
    (r"\bcould\s+able\s+to\b", "modal",
     "'was able to' or 'could' — not both", 2),

    # -- possession --------------------------------------------------------
    (r"\b(?:i\s+am|he\s+is|she\s+is|they\s+are|we\s+are)\s+having\s+"
     r"(?:a\s+|an\s+|two\s+|three\s+|some\s+)?"
     r"(?:brother|sister|car|house|doubt|question|idea|problem)s?\b",
     "stative_verb",
     "'have' for possession is not used in the continuous: I have two brothers", 2),
]

# Indian English, not error. Nothing in this list is ever flagged, and the
# list exists so that a later contributor adding a rule has to walk past it.
DIALECT_FEATURES = [
    "prepone", "do the needful", "kindly revert", "out of station",
    "cousin brother", "cousin sister", "passed out", "batchmate",
    "co-brother", "updation", "airdash", "eve teasing", "hotel",
    "years back", "same to same", "good name",
]

COMPILED = [(re.compile(pattern, re.IGNORECASE), kind, advice, severity)
            for pattern, kind, advice, severity in RULES]

# Fewer words than this is not a grammar sample.
MIN_WORDS_TO_JUDGE = 6


class CommonErrorGrammar:
    """Capability: ``grammar``."""

    contract_version = "1.0"
    provider_key = "common_error_rules"
    version = "0.1.0"

    # Surfaced in the report so a student knows what the number covers. A
    # partial check presented as a complete one is the failure mode here.
    coverage_note = ("Checks a set of high-frequency error patterns, not every "
                     "possible mistake. A clean result means none of those "
                     "patterns appeared.")

    async def analyse(self, transcript: str, *, task_type: str = "") -> GrammarResult:
        return self.check(transcript, task_type)

    def check(self, transcript: str, task_type: str = "") -> GrammarResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        text = (transcript or "").strip()
        words = text.split()
        if len(words) < MIN_WORDS_TO_JUDGE:
            # Too short to say anything about — reported as no opinion rather
            # than a floor score, which would mark down a correct one-word
            # answer for being short.
            return GrammarResult(score=SCALE_MIN, errors=[], confidence=0.0,
                                 meta=meta)

        errors: list[dict] = []
        for pattern, kind, advice, severity in COMPILED:
            for match in pattern.finditer(text):
                span = match.group(0)
                if _is_dialect(text, match.start(), match.end()):
                    continue
                errors.append({
                    "type": kind,
                    "span": span,
                    "suggestion": advice,
                    "severity": severity,
                    "start": match.start(),
                })

        # Weighted by severity and by length: one slip in forty words is not
        # the same as one in eight.
        weight = sum(e["severity"] for e in errors)
        per_hundred = 100.0 * weight / len(words)
        penalty = min(1.0, per_hundred / 12.0)
        score = SCALE_MAX - penalty * (SCALE_MAX - SCALE_MIN)

        return GrammarResult(
            score=round(score, 1),
            errors=sorted(errors, key=lambda e: e["start"])[:20],
            # Modest on purpose. This is a rule set, not a model: a clean
            # result means none of these patterns appeared, not that the
            # grammar was correct.
            confidence=0.5,
            meta=meta,
        )


def _is_dialect(text: str, start: int, end: int) -> bool:
    """True if the match sits inside a legitimate Indian English expression."""
    window = text[max(0, start - 20):min(len(text), end + 20)].lower()
    return any(feature in window for feature in DIALECT_FEATURES)
