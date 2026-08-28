"""Scoring written English: four measures, each defensible on its own.

This is the engine the Writing module needed and did not have. It is not a
neural essay scorer and it does not pretend to be one. It is four measurable
things, computed separately, each with a stated basis and a confidence, in
the same shape and on the same 20-80 scale as every other measure here.

    task response        did the writing address what was asked
    coherence            does it hold together as a piece of prose
    lexical range        how varied is the language
    grammatical accuracy the existing rule set, which already works on text
    mechanics            capitalisation, punctuation, spacing -- writing only

**What it can and cannot see.** It can see structure, variety, coverage of
the points an author wrote down, and a specific set of high-frequency errors.
It cannot see whether an argument is good, whether a claim is true, or
whether the writing is interesting. Those are the things a human marker is
for, and no amount of counting connectives approximates them. The module says
so on screen rather than letting four confident numbers imply otherwise.

**Why heuristics rather than a model.** A trained scorer would be better and
is not available: the speech models already do not fit the deployment target,
and an unvalidated language model marking student essays would be the least
defensible thing in this product. These heuristics are transparent -- every
number can be traced to something countable in the text, which means a
admin can disagree with one and see exactly why it came out that way. That
is worth more here than an extra few points of correlation nobody can audit.

**Not part of the frozen scoring path.** The validation baseline covers the
speech pipeline. Writing is new, has never been part of a study, and is kept
out of ``SCORING_PATH`` deliberately -- adding it would change the engine
hash without any study data to justify the recut.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SCALE_MIN = 20.0
SCALE_MAX = 80.0

# Below this there is not enough writing to judge. Returning a number anyway
# would be the same error as scoring three words of speech: a confident
# measurement of nothing.
MIN_WORDS_TO_SCORE = 40

# Connectives that actually signal a relationship, grouped by what they do.
# Counting "and" would reward padding; these mark structure.
CONNECTIVES = {
    "contrast": ("however", "although", "though", "whereas", "nevertheless",
                 "on the other hand", "in contrast", "but then", "even so"),
    "cause": ("because", "since", "therefore", "so that", "as a result",
              "consequently", "which means", "for this reason"),
    "addition": ("moreover", "furthermore", "in addition", "as well as",
                 "besides", "not only"),
    "sequence": ("first", "second", "finally", "then", "afterwards",
                 "to begin with", "lastly"),
    "example": ("for example", "for instance", "such as", "in particular",
                "specifically"),
    "conclusion": ("in conclusion", "to summarise", "to summarize",
                   "overall", "in short", "on balance"),
}

# Words that carry no content, excluded from the variety measure. A student
# who repeats "the" is not repeating themselves.
FUNCTION_WORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for
with from by as is are was were be been being have has had do does did will
would can could should may might must i you he she it we they me him her us
them my your his its our their there here what which who whom when where why
how all any both each few more most other some such no nor not only own same
so too very just also about into over after before again further once
""".split())


@dataclass
class Measure:
    name: str
    score: float
    # 0 when there was not enough evidence. Never a quiet zero-as-bad.
    confidence: float
    # What was counted, so a admin can disagree with the number and see why.
    basis: str
    detail: dict = field(default_factory=dict)


@dataclass
class EssayScore:
    measures: list[Measure]
    overall: float | None
    word_count: int
    # Set when the piece is too short to judge; every measure is then unscored.
    too_short: bool = False
    notes: list[str] = field(default_factory=list)


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


# Full stops that do not end a sentence. Without these the splitter breaks
# "we tested e.g. the login flow" into two, and the second half then looks
# like a sentence beginning in lower case -- a mechanics error the student
# did not make. Precision over recall applies to punctuation too.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "no.",
                  "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
                  "a.m.", "p.m.", "u.s.", "u.k.")


def _sentences(text: str) -> list[str]:
    guarded = text.strip()
    # Hide the dots inside known abbreviations, split, then restore them.
    for n, abbreviation in enumerate(_ABBREVIATIONS):
        pattern = re.compile(re.escape(abbreviation), re.IGNORECASE)
        guarded = pattern.sub(lambda m, n=n: m.group(0).replace(".", f"<{n}>"),
                              guarded)

    parts = re.split(r"[.!?]+(?:\s|$)", guarded)

    restored: list[str] = []
    for part in parts:
        for n in range(len(_ABBREVIATIONS)):
            part = part.replace(f"<{n}>", ".")
        if part.strip():
            restored.append(part.strip())
    return restored


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _band(fraction: float) -> float:
    """Map 0-1 onto the internal scale."""
    return round(SCALE_MIN + (SCALE_MAX - SCALE_MIN) * max(0.0, min(1.0, fraction)), 1)


# --------------------------------------------------------------------------
# Task response
# --------------------------------------------------------------------------

def task_response(text: str, *, key_points: list, min_words: int) -> Measure:
    """Coverage of what the prompt asked for, and enough of it.

    A key point is an instruction to the writer -- "give the new date" -- and
    a good answer does not contain those words. It says "by Tuesday". Matching
    the rubric's own vocabulary against the text therefore marked a genuinely
    complete reply as covering one point of four, which is worse than not
    scoring it at all: it tells a student their good answer was bad.

    So a point may carry ``cues``: the things that actually indicate it was
    addressed. Any one cue counts. A plain string still works and falls back
    to content-word overlap, which is right for points whose own wording is
    the thing being looked for.

    Cues are matched as substrings on a lower-cased text, so "tuesday" catches
    "Tuesday" and "by Tuesday". That is deliberately generous: this measure
    should not fail a student for phrasing, only for omission.
    """
    lowered = text.lower()
    written = set(_words(text))
    count = len(_words(text))

    hit: list[str] = []
    missed: list[str] = []
    for entry in key_points:
        if isinstance(entry, dict):
            label = str(entry.get("point", ""))
            cues = [c.lower() for c in entry.get("cues", []) if c]
        else:
            label, cues = str(entry), []

        if cues:
            covered = any(cue in lowered for cue in cues)
        else:
            terms = [w for w in _words(label) if w not in FUNCTION_WORDS]
            if not terms:
                continue
            overlap = sum(1 for w in terms if w in written)
            covered = overlap >= max(1, int(len(terms) * 0.67))

        (hit if covered else missed).append(label)

    total_points = len(hit) + len(missed)
    coverage = len(hit) / total_points if total_points else 0.0

    # Length is a gate, not a score. Writing far under the asked-for length
    # cannot have covered the task however many cues it contains; writing far
    # over it is not thereby better.
    if min_words > 0 and count < min_words:
        coverage *= max(0.3, count / min_words)

    return Measure(
        name="task_response",
        score=_band(coverage),
        confidence=0.6 if total_points else 0.0,
        basis=(f"{len(hit)} of {total_points} points the prompt asked for, "
               f"in {count} words"
               + (f" against a {min_words}-word minimum" if min_words else "")),
        detail={"covered": hit, "missing": missed, "word_count": count},
    )


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------

def coherence(text: str) -> Measure:
    """Paragraphing, connectives and sentence variety.

    Three countable things that correlate with prose holding together. None
    of them is coherence itself -- a well-paragraphed piece of nonsense scores
    well here, and the module says as much. What they do catch reliably is
    the single undifferentiated block of same-length sentences, which is the
    most common shape of weak writing in this population.
    """
    sentences = _sentences(text)
    paragraphs = _paragraphs(text)
    lowered = text.lower()

    kinds_used = sum(1 for family in CONNECTIVES.values()
                     if any(marker in lowered for marker in family))
    connective_fraction = kinds_used / len(CONNECTIVES)

    # Paragraphing: one block is poor, and a new paragraph per sentence is
    # not better than sensible grouping.
    if len(sentences) <= 3:
        paragraph_fraction = 0.5          # too short to tell
    elif len(paragraphs) == 1:
        paragraph_fraction = 0.25
    else:
        per = len(sentences) / len(paragraphs)
        paragraph_fraction = 1.0 if 2 <= per <= 6 else 0.6

    # Variety: the spread of sentence lengths, normalised. All-same-length
    # writing reads as a list however good the content.
    lengths = [len(_words(s)) for s in sentences] or [0]
    mean = sum(lengths) / len(lengths)
    if mean <= 0 or len(lengths) < 3:
        variety_fraction = 0.5
    else:
        spread = (sum((n - mean) ** 2 for n in lengths) / len(lengths)) ** 0.5
        variety_fraction = min(1.0, (spread / mean) / 0.6)

    combined = (0.4 * connective_fraction
                + 0.3 * paragraph_fraction
                + 0.3 * variety_fraction)

    return Measure(
        name="coherence",
        score=_band(combined),
        confidence=0.5 if len(sentences) >= 4 else 0.2,
        basis=(f"{len(paragraphs)} paragraph(s), {len(sentences)} sentences, "
               f"{kinds_used} of {len(CONNECTIVES)} kinds of connective"),
        detail={"paragraphs": len(paragraphs), "sentences": len(sentences),
                "connective_kinds": kinds_used,
                "mean_sentence_words": round(mean, 1)},
    )


# --------------------------------------------------------------------------
# Lexical range
# --------------------------------------------------------------------------

def lexical_range(text: str) -> Measure:
    """Variety of content words, corrected for length.

    A raw type-token ratio punishes long writing: every extra sentence drags
    it down whatever the vocabulary. The root TTR used here (types over the
    square root of tokens) is the standard correction, and it means a longer
    piece is not penalised for being longer.
    """
    content = [w for w in _words(text) if w not in FUNCTION_WORDS]
    if len(content) < 20:
        return Measure(name="lexical_range", score=SCALE_MIN, confidence=0.0,
                       basis="not enough content words to judge variety",
                       detail={"content_words": len(content)})

    types = len(set(content))
    root_ttr = types / (len(content) ** 0.5)
    # ~7.0 is unremarkable for this length of workplace prose; ~11 is varied.
    fraction = (root_ttr - 5.0) / 6.0

    counts: dict[str, int] = {}
    for word in content:
        counts[word] = counts.get(word, 0) + 1
    repeated = sorted((w for w, n in counts.items() if n >= 4),
                      key=lambda w: -counts[w])[:5]
    if repeated:
        fraction -= 0.08 * len(repeated)

    return Measure(
        name="lexical_range",
        score=_band(fraction),
        confidence=0.5,
        basis=(f"{types} different content words in {len(content)}"
               + (f"; leans on {', '.join(repeated)}" if repeated else "")),
        detail={"types": types, "tokens": len(content),
                "root_ttr": round(root_ttr, 2), "overused": repeated},
    )


# --------------------------------------------------------------------------
# Grammatical accuracy
# --------------------------------------------------------------------------

async def grammatical_accuracy(text: str) -> Measure:
    """The existing rule set, applied to writing.

    ``CommonErrorGrammar`` was built for transcribed speech and is pure
    pattern matching, so it works unchanged on typed text -- including on a
    deployment with no speech models at all. It carries its own limitations
    with it: high precision, partial recall, and it does not treat Indian
    English as an error. Both properties are inherited here on purpose.
    """
    from app.engine.providers.tier1.grammar import CommonErrorGrammar

    result = await CommonErrorGrammar().analyse(text, task_type="written")
    return Measure(
        name="grammatical_accuracy",
        score=result.score,
        confidence=result.confidence,
        basis=(f"{len(result.errors)} error pattern(s) found. Checks a set of "
               f"high-frequency mistakes, not every possible one, and never "
               f"treats Indian English as an error."),
        detail={"errors": result.errors},
    )


# --------------------------------------------------------------------------
# Mechanics
# --------------------------------------------------------------------------

def mechanics(text: str) -> Measure:
    """Capitalisation, sentence-final punctuation, spacing.

    A measure that only writing needs. ``CommonErrorGrammar`` was built for
    transcribed speech, where there is no such thing as a capital letter or a
    full stop -- the recogniser supplies both. Run against typed text it
    therefore scores an entirely lower-case, unpunctuated paragraph as
    flawless, which was the first thing the test essays exposed.

    These are the cheapest errors to fix and the most costly to leave in: a
    recruiter reading an email with no capitals forms a view before reaching
    the second line, whatever the grammar underneath is doing.

    Kept apart from grammatical accuracy rather than folded into it, because
    they are a different kind of mistake with a different remedy, and a
    student who is strong at one and weak at the other should be able to see
    that rather than get one blended number.
    """
    sentences = _sentences(text)
    if len(sentences) < 2:
        return Measure(name="mechanics", score=SCALE_MIN, confidence=0.0,
                       basis="not enough sentences to judge mechanics",
                       detail={})

    problems: list[str] = []

    unopened = [s for s in sentences if s[:1].islower()]
    if unopened:
        problems.append(f"{len(unopened)} sentence(s) do not start with a "
                        f"capital letter")

    # A trailing sentence with no terminator is normal in the split; anything
    # earlier means a full stop was genuinely missing.
    stripped = text.strip()
    if stripped and stripped[-1] not in ".!?":
        problems.append("the last sentence has no full stop")

    # Standalone "i" is the single most common written slip in this population.
    # The word boundaries are load-bearing. Without them this matches the
    # letter i inside every word containing one, so "this is fine" reports
    # three lower-case pronouns and clean writing scores as broken.
    lone_i = len(re.findall(r"\bi\b", text))
    if lone_i:
        problems.append(f"'i' written in lower case {lone_i} time(s)")

    if re.search(r"[ \t]+[,.;:!?]", text):
        problems.append("a space before a comma or full stop")
    # Comma, semicolon and colon only. A full stop followed by a letter is
    # normal in abbreviations, decimals and URLs, and flagging it would fail
    # the precision-over-recall rule the grammar rules are held to -- it
    # would teach a student that "e.g." is a mistake.
    if re.search(r"[,;:][A-Za-z]", text):
        problems.append("a missing space after punctuation")

    # Scored against the number of sentences, so one slip in twenty is not
    # treated like one slip in two.
    weight = min(1.0, (len(unopened) + lone_i) / max(1, len(sentences)))
    fraction = 1.0 - weight - (0.1 * max(0, len(problems) - 2))

    return Measure(
        name="mechanics",
        score=_band(fraction),
        confidence=0.7,
        basis=("; ".join(problems) if problems
               else "capitalisation, punctuation and spacing are clean"),
        detail={"problems": problems, "sentences": len(sentences)},
    )


# --------------------------------------------------------------------------
# The whole piece
# --------------------------------------------------------------------------

async def score_essay(text: str, *, key_points: list[str],
                      min_words: int = 0) -> EssayScore:
    """Every measure, plus an overall that is only produced when it means something."""
    count = len(_words(text))

    if count < MIN_WORDS_TO_SCORE:
        return EssayScore(
            measures=[], overall=None, word_count=count, too_short=True,
            notes=[f"{count} words is too short to judge. Below "
                   f"{MIN_WORDS_TO_SCORE} there is not enough writing for any "
                   f"of these measures to mean anything, so none of them have "
                   f"been guessed at."],
        )

    measures = [
        task_response(text, key_points=key_points, min_words=min_words),
        coherence(text),
        lexical_range(text),
        await grammatical_accuracy(text),
        mechanics(text),
    ]

    # Same rule as the speech composite: a measure with no confidence does not
    # vote, and too few voters means no overall rather than a thin one.
    usable = [m for m in measures if m.confidence > 0]
    overall = (round(sum(m.score for m in usable) / len(usable), 1)
               if len(usable) >= 3 else None)

    notes = ["These four are countable properties of the text: coverage, "
             "structure, variety and a specific set of error patterns. They "
             "do not judge whether your argument is good, whether what you "
             "wrote is true, or whether it is interesting to read."]
    if overall is None:
        notes.append("Too few measures came back to combine into an overall.")

    return EssayScore(measures=measures, overall=overall, word_count=count,
                      notes=notes)
