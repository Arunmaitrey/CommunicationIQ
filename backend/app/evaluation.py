"""How each format combines what was measured into what it reports.

The engine measures one thing per response: pronunciation, accuracy, fluency,
latency, disfluency, grammar, content. What differs between assessments is not
the measuring, it is the *bookkeeping* -- which tasks count towards which
sub-score, and how those sub-scores combine into an overall. A Versant-style
report says "Sentence Mastery", and that is not a rename of our accuracy
measure: it is accuracy and grammar taken from Repeat Sentence, Short Answer
and Sentence Build only, and deliberately not from Read Aloud, because reading
a sentence off a screen demonstrates nothing about sentence mastery.

That mapping is what this module holds, and it is the whole difference between
"we show four numbers with vendor-ish labels" and "we compute the sub-scores
the way the report you are preparing for computes them".

**Where this sits relative to the frozen engine.** Entirely outside it. Every
value consumed here was produced by the frozen pipeline and is unchanged; this
only decides which of them to average, and in what proportion. The internal
composite stays the headline on the report and stays comparable across
formats. Nothing in this file can move a dimension score, and
the frozen baseline is unaffected -- which is the only reason it could be
written during a data-collection freeze at all. (That baseline is now
``validation-baseline-v4``: v2 was re-cut when provider fallback and unscored
reporting were fixed, both error-handling changes that leave every scored
value identical, and v3 when Sentence Build became a construction score and
completeness became a weighted dimension -- which do change scored values,
which is why they arrived together behind one re-cut.)

**What is documented and what is not.**

*Documented*, from the published descriptions of these tests: the sub-score
names, and which task types contribute to each. This is the part that makes
the model faithful, and it is the part most worth getting right.

*Published for Versant only*: the relative weighting of the four sub-scores in
the overall.

*Not published anywhere, and therefore ours*: every internal measure standing
in for a sub-score, and the SVAR/SpeechX weightings, which are equal here
because we have nothing better and inventing a hierarchy would be worse than
admitting we do not know one.

*Not reproduced, and not reproducible from public information*: the actual
scoring algorithms. No claim is made that a number here matches a number the
real test would give. That claim needs a concordance study.

**If you have the official technical manuals, correct this table.** It is
deliberately one table, in one file, with the source of every row named.
"""
from __future__ import annotations

from dataclasses import dataclass


# Which dimensions each task type actually yields.
#
# Not every measure applies to every task, and the pipeline is right to
# withhold the ones that do not: there is no grammar to judge in a two-word
# answer, and no pronunciation score for speech whose words were never
# scripted. The consequence for this module is sharper than it looks -- a
# sub-score drawing on a dimension its tasks never emit can never be reported,
# and the student is told their attempt was too thin when the truth is that
# the format was built wrong.
#
# Mirrored here rather than imported so this module stays off the scoring
# path. ``test_evaluation.py`` checks it against what the engine emits.
DIMENSIONS_BY_TASK: dict[str, frozenset[str]] = {
    # A chosen grammar transformation: the only thing it measures is whether
    # the candidate produced the right voice. Grammar, and nothing spoken.
    "voice_change": frozenset({"grammar"}),
    "read_aloud": frozenset({"accuracy", "completeness", "disfluency",
                             "fluency", "latency", "pronunciation"}),
    "repeat_sentence": frozenset({"accuracy", "completeness", "disfluency",
                                  "fluency", "latency", "pronunciation"}),
    # Hear a gapped/flawed sentence, say the whole correct one. Scored like
    # Repeat Sentence -- the target is scripted -- and the grammar signal is
    # carried by accuracy: the target IS the grammatical sentence.
    "spoken_completion": frozenset({"accuracy", "completeness", "disfluency",
                                    "fluency", "latency", "pronunciation"}),
    "spoken_correction": frozenset({"accuracy", "completeness", "disfluency",
                                    "fluency", "latency", "pronunciation"}),
"sentence_build": frozenset({"accuracy", "completeness", "construction",
                                 "disfluency", "fluency", "grammar", "latency",
                                 "pronunciation"}),
    "short_answer": frozenset({"content", "disfluency", "fluency", "latency"}),
"story_retell": frozenset({"accuracy", "completeness", "content", "disfluency",
                                "fluency", "grammar", "latency"}),
    "open_response": frozenset({"completeness", "disfluency", "fluency",
                                "grammar", "latency"}),
    # Spoken answers to something heard. Delivery is measured exactly as it is
    # for any other spontaneous speech; `content` is the answer being right,
    # and it is added above the frozen path (see app/spoken_content.py)
    # because the pipeline's content gate names three task types and predates
    # these two. No `accuracy` and no `pronunciation`: the reference text is
    # the question, not a target utterance.
    "conversation_question": frozenset({"completeness", "content",
                                        "disfluency", "fluency", "grammar",
                                        "latency"}),
    "passage_question": frozenset({"completeness", "content", "disfluency",
                                   "fluency", "grammar", "latency"}),
    # -- answered by choosing or typing, scored in the router --------------
    #
    # These never reach the speech engine, so their dimensions are whatever
    # the marking function writes. Listed here for the same reason the
    # speaking ones are: this table is what `_unscored_reasons` compares
    # against, and a task type missing from it can produce nothing and be
    # reported as complete.
    "listening_comprehension": frozenset({"comprehension"}),
    "reading_comprehension": frozenset({"comprehension"}),
    # Not comprehension. Every wrong reply here is a correct English
    # sentence, so what is being measured is whether the candidate can tell
    # a reply that works from one that lands badly.
    "response_selection": frozenset({"appropriacy"}),
    "vocabulary_in_context": frozenset({"vocabulary"}),
    # Heard once, typed back: one right answer, measured as word accuracy.
    "dictation": frozenset({"accuracy"}),
    # One word into a gap. Grammar rather than vocabulary because the bank is
    # connectives, prepositions and agreement.
    "sentence_completion": frozenset({"grammar"}),
    "email_writing": frozenset({"content", "grammar", "vocabulary"}),
    # What was retained, and whether it came back as English. No lexical
    # range: the words are the author's.
    "passage_reconstruction": frozenset({"content", "grammar"}),
    # Timed typing: copy a given text. Measures speed (WPM) and accuracy.
    "typing": frozenset({"accuracy", "fluency"}),
}


@dataclass(frozen=True)
class SubScoreModel:
    """One sub-score a format reports, and how it is assembled."""

    label: str
    # Only responses of these task types count. An empty set means every task
    # type contributes, which is a fallback rather than a design.
    task_types: frozenset[str]
    # Our measures standing in for it, averaged. Order is not significant.
    dimensions: tuple[str, ...]
    # Share of the format's overall, before renormalising over what was
    # actually measured.
    weight: float
    # What the real test says this sub-score is about. Shown to the student,
    # so it is written for them and not for us.
    means: str


@dataclass(frozen=True)
class ScoringModel:
    """A format's whole bookkeeping."""

    subscores: tuple[SubScoreModel, ...]
    # Where the structure came from, and how far to trust the weighting.
    structure_source: str
    weights_published: bool


# --------------------------------------------------------------------------
# Versant-style
# --------------------------------------------------------------------------
#
# The most fully documented of the three. Four sub-scores, and the published
# description is specific about which tasks feed each -- notably that Read
# Aloud contributes to Fluency and Pronunciation but not to Sentence Mastery,
# and that the open-ended task is not part of the automatic score at all.

VERSANT = ScoringModel(
    structure_source=(
        "Sub-score names, the task types feeding each, and the relative "
        "weighting follow the published description of the Versant English "
        "Test. The measures standing in for each sub-score are ours, and so "
        "is the placement of Conversation and Passage Questions -- the "
        "published description predates our having them, and a section that "
        "fed no sub-score would be minutes of work counting for nothing."
    ),
    weights_published=True,
    subscores=(
        SubScoreModel(
            label="Sentence Mastery",
            # Not Read Aloud: reading a sentence you can see demonstrates
            # nothing about holding and producing sentence structure.
            task_types=frozenset({"repeat_sentence", "short_answer",
                                  "sentence_build"}),
            dimensions=("accuracy", "grammar"),
            weight=0.30,
            means=("Whether you can hold a whole sentence and produce it "
                   "correctly -- word order, tense, agreement."),
        ),
        SubScoreModel(
            label="Vocabulary",
            task_types=frozenset({"short_answer", "story_retell",
                                  "conversation_question", "passage_question"}),
            dimensions=("content", "accuracy"),
            weight=0.30,
            means=("Whether you know and can retrieve the right words in "
                   "context, without a prompt to read from."),
        ),
        SubScoreModel(
            label="Fluency",
            task_types=frozenset({"read_aloud", "repeat_sentence",
                                  "sentence_build", "story_retell",
                                  "conversation_question", "passage_question",
                                  "open_response"}),
            dimensions=("fluency", "latency", "disfluency"),
            weight=0.20,
            means=("The rhythm, phrasing and pacing of your speech -- how it "
                   "flows, not what it contains."),
        ),
        SubScoreModel(
            label="Pronunciation",
            task_types=frozenset({"read_aloud", "repeat_sentence",
                                  "sentence_build"}),
            dimensions=("pronunciation",),
            weight=0.20,
            means=("How clearly your consonants, vowels and stress come "
                   "across on speech whose words are already known."),
        ),
    ),
)


# --------------------------------------------------------------------------
# SVAR-style
# --------------------------------------------------------------------------
#
# Sub-score names are from the published description. The weighting is not
# published, so the four are equal -- an invented hierarchy would be a worse
# answer than an admitted absence of one.

SVAR = ScoringModel(
    # Said for the student, not for us. The four-section configuration this
    # simulation imitates can feed four of SVAR's six published competency
    # names from its own sections; Spoken English Understanding and Vocabulary
    # have no section behind them here and are omitted rather than faked.
    structure_source=(
        "This simulation measures the communication skills supported by this "
        "four-section format. It does not reproduce every competency "
        "available in other SVAR assessment configurations. Sub-score names "
        "follow SVAR's published competencies; the task mapping and the "
        "measures behind each are ours."
    ),
    weights_published=False,
    subscores=(
        SubScoreModel(
            label="Pronunciation",
            task_types=frozenset({"read_aloud", "repeat_sentence"}),
            dimensions=("pronunciation",),
            weight=0.25,
            means="How clearly individual words come across.",
        ),
        SubScoreModel(
            label="Fluency",
            task_types=frozenset({"read_aloud", "repeat_sentence",
                                  "open_response"}),
            dimensions=("fluency", "disfluency", "latency"),
            weight=0.25,
            means="Whether your speech flows, or stalls and restarts.",
        ),
        SubScoreModel(
            label="Active Listening",
            # Did what you heard once actually go in? The listen & answer
            # section answers that directly; Repeat answers it indirectly,
            # by whether the words survived. Reading aloud proves nothing
            # here and is excluded.
            task_types=frozenset({"listening_comprehension",
                                  "repeat_sentence"}),
            dimensions=("comprehension", "accuracy"),
            weight=0.25,
            means=("Whether you took in what you heard once -- the part of a "
                   "call that goes wrong first."),
        ),
        SubScoreModel(
            label="Grammar",
            # The grammar round (28 typed blanks in four categories plus 6
            # chosen voice changes -- 34 of the format's 67 items) is where
            # this format's grammar signal mostly comes from, plus the
            # grammar of composed speech on the topic.
            task_types=frozenset({"sentence_completion", "voice_change",
                                  "open_response"}),
            dimensions=("grammar",),
            weight=0.25,
            means="Sentence construction, in the grammar rounds and in your own speech.",
        ),
    ),
)


# --------------------------------------------------------------------------
# SpeechX-style
# --------------------------------------------------------------------------

SPEECHX = ScoringModel(
    structure_source=(
        "Sub-score names follow the published description of a SpeechX-style "
        "assessment. The task mapping and the measures behind each are ours, "
        "and the weighting is equal because none is published."
    ),
    weights_published=False,
    subscores=(
        SubScoreModel(
            label="Pronunciation",
            task_types=frozenset({"read_aloud", "repeat_sentence"}),
            dimensions=("pronunciation",),
            weight=0.25,
            means="How clearly individual words come across.",
        ),
        SubScoreModel(
            label="Fluency",
            task_types=frozenset({"read_aloud", "repeat_sentence",
                                  "open_response"}),
            dimensions=("fluency", "latency", "disfluency"),
            weight=0.25,
            means="Whether your speech flows, or stalls and restarts.",
        ),
        # No Vocabulary sub-score. The researched A-D format has no section
        # yielding a content measure (open responses yield fluency/grammar,
        # not content) -- and a sub-score the format cannot supply is a number
        # invented for the report. Four honest sub-scores instead of five with
        # a hollow one.
        SubScoreModel(
            label="Grammar",
            # The grammar round is answered by typing (fill the blanks) and
            # choosing (active/passive), which is where this format's grammar
            # signal actually comes from -- so those sections feed here, not
            # only the spoken tasks.
            task_types=frozenset({"open_response", "short_answer",
                                  "sentence_completion", "voice_change"}),
            dimensions=("grammar",),
            weight=0.25,
            means="Sentence construction, from both the grammar round and your speech.",
        ),
        SubScoreModel(
            label="Comprehension",
            # The passage round: whether what was heard once was understood.
            task_types=frozenset({"listening_comprehension"}),
            dimensions=("comprehension",),
            weight=0.25,
            means="Whether you understood the passages you heard.",
        ),
    ),
)


MODELS: dict[str, ScoringModel] = {
    "versant_style_speaking_listening": VERSANT,
    "svar_full_simulation": SVAR,
    "speechx_style_full": SPEECHX,
    # The two four-skill templates deliberately have no entry. Their report is
    # the per-skill rollup in ``app/sections.py``, measured from sections that
    # belong to those skills. Publishing vendor sub-scores as well would put
    # two different numbers labelled Listening on the same page, and the
    # weaker of the two -- a speaking dimension grouped under the word -- is
    # the one a student would read first.
}

# A sub-score built from one response is not a measurement of anything, it is
# that one response wearing a category name. Two is the floor for reporting.
MIN_RESPONSES_PER_SUBSCORE = 2

# And an overall assembled from a single surviving sub-score is just that
# sub-score relabelled.
MIN_SUBSCORES_FOR_OVERALL = 2


@dataclass(frozen=True)
class SubScoreResult:
    label: str
    value: float
    weight: float
    means: str
    # What it was actually built from, so the report can show its working.
    task_types: tuple[str, ...]
    dimensions: tuple[str, ...]
    responses: int


@dataclass(frozen=True)
class FormatResult:
    overall: float | None
    subscores: tuple[SubScoreResult, ...]
    # Sub-scores the attempt could not support, and why. Shown rather than
    # hidden: a Versant-style attempt with no Story Retell cannot report
    # Vocabulary, and silently dropping it would make the overall look like
    # the same measurement as a full one.
    missing: dict[str, str]
    structure_source: str
    weights_published: bool


def evaluate(code: str, responses: list[dict]) -> FormatResult | None:
    """Assemble a format's sub-scores and overall from per-response scores.

    ``responses`` is a list of dicts carrying at least ``task_type`` and a
    ``scores`` mapping -- the shape the report already builds. Returns None for
    a format with no model, which includes every company round and anything a
    tenant admin authored.
    """
    model = MODELS.get(code)
    if model is None:
        return None

    scored: list[SubScoreResult] = []
    missing: dict[str, str] = {}

    for sub in model.subscores:
        values: list[float] = []
        used_tasks: set[str] = set()
        counted = 0

        for response in responses:
            task_type = response.get("task_type", "")
            if sub.task_types and task_type not in sub.task_types:
                continue
            scores = response.get("scores") or {}
            present = [scores[d] for d in sub.dimensions if d in scores]
            if not present:
                continue
            values.append(sum(present) / len(present))
            used_tasks.add(task_type)
            counted += 1

        if counted < MIN_RESPONSES_PER_SUBSCORE:
            wanted = ", ".join(sorted(sub.task_types)) or "any task"
            missing[sub.label] = (
                f"needs at least {MIN_RESPONSES_PER_SUBSCORE} scored "
                f"responses from {wanted}; this attempt had {counted}"
            )
            continue

        scored.append(SubScoreResult(
            label=sub.label,
            value=round(sum(values) / len(values), 1),
            weight=sub.weight,
            means=sub.means,
            task_types=tuple(sorted(used_tasks)),
            dimensions=sub.dimensions,
            responses=counted,
        ))

    overall = None
    if len(scored) >= MIN_SUBSCORES_FOR_OVERALL:
        total = sum(s.weight for s in scored)
        if total > 0:
            # Renormalised over the sub-scores that survived, which is what
            # makes a partial attempt's overall comparable in kind -- though
            # ``missing`` is what makes it comparable in fact.
            overall = round(
                sum(s.value * s.weight for s in scored) / total, 1)

    return FormatResult(
        overall=overall,
        subscores=tuple(scored),
        missing=missing,
        structure_source=model.structure_source,
        weights_published=model.weights_published,
    )


def unreportable(code: str, sections: list[tuple[str, int]]) -> dict[str, str]:
    """Sub-scores this format could never report, given its own sections.

    ``sections`` is (task_type, item_count) pairs. A sub-score is unreportable
    when the sections cannot supply ``MIN_RESPONSES_PER_SUBSCORE`` responses
    that yield at least one of its dimensions.

    This is a design check, not a runtime one. A format advertising a
    sub-score it is structurally incapable of producing is broken, and the
    place to find that out is a failing test, not a student's report.
    """
    model = MODELS.get(code)
    if model is None:
        return {}

    problems: dict[str, str] = {}
    for sub in model.subscores:
        usable = 0
        for task_type, count in sections:
            if sub.task_types and task_type not in sub.task_types:
                continue
            if not (DIMENSIONS_BY_TASK.get(task_type, frozenset())
                    & set(sub.dimensions)):
                continue
            usable += count
        if usable < MIN_RESPONSES_PER_SUBSCORE:
            problems[sub.label] = (
                f"needs {MIN_RESPONSES_PER_SUBSCORE} responses yielding "
                f"{'/'.join(sub.dimensions)} from "
                f"{', '.join(sorted(sub.task_types))}; the format supplies "
                f"{usable}"
            )
    return problems
