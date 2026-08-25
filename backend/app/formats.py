"""What a test *looks* like, as distinct from how it is measured.

One engine, several presentations. A company round and a vendor-style
simulation put a student under different pressure -- different sections,
different clocks, a different verdict at the end -- but the measurement
underneath is the same measurement, scored by the same frozen pipeline. That
separation is deliberate and worth defending: give each format its own scoring
and you owe each format its own validation study, and the frozen baseline stops
meaning anything at all.

So this module holds three things and no arithmetic that touches a dimension
score:

* **Blueprints** -- the section composition and pacing of each round, used to
  seed profiles. Once seeded they are ordinary rows a tenant admin can edit;
  this is the starting content, not a runtime authority.
* **Presentation** -- how a result is phrased for that format. A company round
  does not report a scale, it reports a likely outcome, because that is the
  only thing the student is about to find out.
* **The honesty note** attached to both, because none of it is validated yet.

**On the naming.** These imitate the *format* of rounds run by named employers
and nothing else -- no item is taken from any real assessment (CONTENT-04), and
the company names are used descriptively to say which round a student is
practising for. No affiliation or endorsement is claimed or implied. The
``-style`` suffix is load-bearing; do not drop it in UI copy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app import evaluation

# Every company round shares this caveat, and it is not decoration. A student
# who reads "you would likely clear this" and then does not clear it has been
# misled by us, so the claim is hedged at the point it is made rather than in a
# footnote somewhere.
COMPANY_ROUND_NOTE = (
    "This is our estimate of how you would place in a round of this shape. "
    "It has not been checked against any employer's actual result, and no "
    "employer has reviewed or endorsed it. Treat the diagnosis below as the "
    "reliable part."
)


@dataclass(frozen=True)
class SectionBlueprint:
    """One section of a round: a task type and the clock it runs on."""

    title: str
    task_type: str
    item_count: int = 1
    prep_seconds: int = 0
    response_seconds: int = 30
    prompt_plays_allowed: int = 0
    instructions: str = ""
    # Optional per-section pool filter (app.selection.from_dict shape). Empty
    # means "everything published of this task type", which is what every
    # section did before. Used here so the two read-aloud sections draw from
    # different content — sentences vs paragraphs — by difficulty band.
    selection: dict = field(default_factory=dict)
    # The budget of the *lettered section* this sub-section belongs to, in
    # seconds, where the reference states one (SVAR-style: Section A 10 min,
    # C 15 min, D 10 min). Carried on every sub-section of that letter with
    # the same value; the runner takes the group's value once. Zero means no
    # section budget. Advisory-plus-stop in the runner: it never interrupts
    # an item in progress, and when it runs out the rest of the section is
    # passed over rather than answered late.
    budget_seconds: int = 0

    # Show this section's instruction line on every question screen, the way
    # the Cognizant reference does ("Task: Read the list of isolated words
    # out loud" on each numbered question). Off by default: SVAR's reference
    # shows one introduction per lettered part and nothing per question, and
    # that presentation is frozen.
    show_instruction: bool = False
    # -- section behaviour, as configuration (the SVAR-derived flags) --------
    # The runner used to key these on ``style == "svar_style"``; the SpeechX
    # rebuild is the first second format that needs them, so they are data.
    # A spoken window that only the clock or the candidate ends (no silence
    # advancement): the SVAR-style Speak on the Topic decision.
    fixed_window: bool = False
    # A Skip control that passes the item over with no response (SVAR B).
    allow_skip: bool = False
    # A control that ends the thinking time early and starts recording
    # (Mettl: "If you prefer not to use the thinking time, you can skip").
    skip_prep: bool = False
    # A typed "Okay" acknowledgement: "section" = once on the section card
    # (SVAR D, from the section instruction screen), "clip" = before each
    # clip's questions, the clip screen itself being a numbered item (Mettl
    # D: "Q.1 Listen to the given audio ... Type in 'Okay' to proceed").
    ack_gate: str = ""
    # Question numbers run through the lettered section (Q9 = first
    # paragraph, 1/34 across the grammar round) rather than per sub-section.
    continuous_numbering: bool = False
    # Show the item's speaking-point questions under the topic (SVAR B; the
    # Mettl B screen shows the bold topic only).
    show_cues: bool = False


BEHAVIOUR_FLAGS = ("fixed_window", "allow_skip", "skip_prep", "ack_gate",
                   "continuous_numbering", "show_cues", "show_instruction",
                   "budget_seconds")


def section_behaviour(code: str) -> dict[str, dict]:
    """Section title -> behaviour flags for a blueprinted profile.

    By title, like ``section_budgets``: what a seeded row and its blueprint
    share, and no new column on a frozen row. Admin-authored profiles get
    the defaults (all off), which is the engine's original behaviour."""
    blueprint = BY_CODE.get(code)
    if blueprint is None:
        return {}
    return {s.title: {f: getattr(s, f) for f in BEHAVIOUR_FLAGS} for s in blueprint.sections}


def section_budgets(code: str) -> dict[str, int]:
    """Section title -> budget seconds for a blueprinted profile.

    Looked up by title because that is what a seeded section row and its
    blueprint share; an admin-authored profile has no blueprint and no
    budgets."""
    blueprint = BY_CODE.get(code)
    if blueprint is None:
        return {}
    return {s.title: s.budget_seconds for s in blueprint.sections if s.budget_seconds}


# --------------------------------------------------------------------------
# How long a template actually takes
# --------------------------------------------------------------------------
#
# ``estimated_minutes`` was typed in by hand, and the audit caught what that
# leads to: a template advertised at eighteen minutes that runs for
# twenty-two. A student who budgets the stated time and is still answering
# when it runs out has been misinformed by us, not by their own planning.
#
# So the number is computed from the sections and a test asserts the field
# matches. Every constant below is an authoring estimate rather than a
# measurement -- they are stated here, in one place, so a wrong one is a
# visible wrong number instead of an invisible one.

# Between items: reading the next screen, the tone, settling.
TRANSITION_SECONDS = 3

# Before the first item of each section: the section card and its
# instructions. Small, and there is one per section, so a six-part format
# pays it six times.
SECTION_SECONDS = 25

# Once per attempt, before anything is answered: consent, the microphone
# check, the runner-check modal. Included because the question a student is
# asking is "how long will this take me", and it takes them this too.
SETUP_SECONDS = 90

# Nobody answers the instant the tone sounds, and nobody starts the next item
# the instant they stop talking. A flat margin on the whole run rather than a
# fiddled-with per-task number, because there is no measurement behind either
# and the flat one is at least legible.
PACING_MARGIN = 0.15

# Trailing silence after which the runner advances (the scripted-task window;
# composed speech gets a longer one client-side). Mirrors TRAILING_SILENCE_MS
# in frontend/lib/speech.ts, which is the authority; a test asserts the two
# agree. Raised from the original 1.8 s guess after the acceptance rule that a
# 2-3 second thinking pause must never end a recording -- the very case
# app/silence.py's analysis calls being cut off.
TRAILING_SILENCE_SECONDS = 3.0

# How long a played prompt runs, per item, by task type. Roughly the bank's
# own item lengths at a natural speaking rate.
PLAY_SECONDS: dict[str, int] = {
    "repeat_sentence": 6,
    "spoken_completion": 6,
    "spoken_correction": 6,
    "short_answer": 5,
    "dictation": 6,
    "story_retell": 35,
    "conversation_question": 25,
    "passage_question": 30,
    "response_selection": 8,
    "open_response": 4,
}

# Played or read once per passage, before that passage's questions. Grouped
# task types only -- everything else carries its stimulus per item.
PASSAGE_SECONDS: dict[str, int] = {
    "listening_comprehension": 45,
    "reading_comprehension": 90,
}

# How many questions a passage typically carries, so a section of six is
# costed as two passages rather than one.
QUESTIONS_PER_PASSAGE = 3

# What an untimed section actually costs per item. A section with
# ``response_seconds = 0`` is untimed by design -- which is right for reading
# and writing, and does not mean it takes no time.
ANSWER_SECONDS: dict[str, int] = {
    "listening_comprehension": 25,
    "reading_comprehension": 25,
    "response_selection": 20,
    "vocabulary_in_context": 20,
    "sentence_completion": 30,
    "dictation": 45,
    # The passage is readable for a computed window and then withdrawn; the
    # writing follows. One number covering both.
    "passage_reconstruction": 145,
    "email_writing": 600,
}


def section_seconds(section: "SectionBlueprint") -> int:
    """How long one section takes, start to finish."""
    answering = section.response_seconds or ANSWER_SECONDS.get(
        section.task_type, 30)
    per_item = section.prep_seconds + answering + TRANSITION_SECONDS
    if section.prompt_plays_allowed > 0:
        per_item += PLAY_SECONDS.get(section.task_type, 0)

    total = per_item * section.item_count
    passage = PASSAGE_SECONDS.get(section.task_type, 0)
    if passage:
        passages = -(-section.item_count // QUESTIONS_PER_PASSAGE)
        total += passage * passages
    return total


def duration_minutes(blueprint: "FormatBlueprint") -> int:
    """The whole template, door to door, rounded to the nearest minute.

    A **ceiling**, and deliberately still one after Phase 7. The runner now
    advances when a candidate stops speaking, so most sittings finish sooner
    than this -- but the number a candidate is shown has to be the one they
    can safely budget. Publishing the typical figure would make the estimate
    optimistic, which is precisely the fault the computed duration replaced: a
    template advertised at eighteen minutes that ran for twenty-two.
    """
    running = sum(section_seconds(s) + SECTION_SECONDS
                  for s in blueprint.sections)
    return round((SETUP_SECONDS + running * (1 + PACING_MARGIN)) / 60)


# What share of a response window a candidate typically fills before stopping.
#
# Measured against the runner's own loop, not guessed: with adaptive
# advancement and a 1.8-second trailing-silence window, SVAR-style comes out at
# 15 minutes for a brief speaker, 16 for a typical one and 18 -- the ceiling --
# for somebody who uses every window in full. The audit's target was 15.
#
# It is one number for every task type on purpose. A per-type table would look
# more precise and rest on the same single observation.
TYPICAL_SPEAK_SHARE = 0.55


def typical_minutes(blueprint: "FormatBlueprint") -> int:
    """How long this usually takes, now that an item can end early.

    Never published as *the* duration -- see `duration_minutes`. Useful for
    telling somebody "about sixteen minutes, up to eighteen", which is more
    informative than either number alone.
    """
    running = 0.0
    for section in blueprint.sections:
        answering = section.response_seconds or ANSWER_SECONDS.get(
            section.task_type, 30)
        if section.response_seconds > 0:
            # Adaptive advancement applies only where something is spoken
            # into a window. A written or chosen answer ends when the
            # candidate says it does, which the model already reflects.
            spoken = section.response_seconds * TYPICAL_SPEAK_SHARE
            answering = min(section.response_seconds,
                            spoken + TRAILING_SILENCE_SECONDS)
        per_item = section.prep_seconds + answering + TRANSITION_SECONDS
        if section.prompt_plays_allowed > 0:
            per_item += PLAY_SECONDS.get(section.task_type, 0)
        running += per_item * section.item_count + SECTION_SECONDS
        passage = PASSAGE_SECONDS.get(section.task_type, 0)
        if passage:
            running += passage * -(-section.item_count // QUESTIONS_PER_PASSAGE)
    return round((SETUP_SECONDS + running * (1 + PACING_MARGIN)) / 60)


# The engine's own scale. Mirrored rather than imported so this module stays
# free of the scoring path -- ``test_formats_vendor.py`` asserts the two agree,
# so a change to the engine cannot silently desynchronise the presentation.
INTERNAL_MIN = 20.0
INTERNAL_MAX = 80.0


def _fraction(internal: float) -> float:
    """Where a score sits in the internal range, as 0..1."""
    span = INTERNAL_MAX - INTERNAL_MIN
    return max(0.0, min(1.0, (internal - INTERNAL_MIN) / span))


@dataclass(frozen=True)
class ScaleBlueprint:
    """The scale a format reports on, and what its bands are called.

    The mapping from our internal 0-100 composite onto this range is linear
    and **has never been checked against a real result from the test being
    imitated**. That is a concordance study -- the same speakers sitting both
    tests -- and nothing of the sort has been run. The number is offered for
    orientation and labelled as an estimate everywhere it appears.
    """

    minimum: float
    maximum: float
    # (lower bound as a fraction of the range, label)
    bands: tuple[tuple[float, str], ...]
    # Whether a *number* on this scale can be justified at all.
    #
    # True only where the internal scale was built on this range, which is the
    # case for exactly one format: the engine's 20-80 was designed Versant-like
    # from the start, so restating a score on it is arithmetic rather than a
    # claim.
    #
    # False everywhere else, and then no number is published. Stretching our
    # 20-80 linearly onto somebody else's 0-100 asserts that our floor is their
    # floor and our ceiling is their ceiling -- a perfect concordance, which is
    # the one thing we know we have not established. It also inflates: an
    # internal 70, respectable and barely above the ready threshold, would come
    # out at 83, and an internal 77.5 at 96. A student reading "Grammar 96"
    # concludes there is nothing left to fix. The band is defensible because it
    # is ordinal; the number is not.
    anchored: bool = False

    def project(self, internal: float) -> float | None:
        """A score restated on this scale, or None when that is not honest.

        Clamped to the internal range. Returns None for an unanchored scale --
        callers publish the band instead.
        """
        if not self.anchored:
            return None
        return round(self.minimum + _fraction(internal)
                     * (self.maximum - self.minimum), 1)

    def band_for(self, internal: float) -> str:
        fraction = _fraction(internal)
        label = self.bands[0][1] if self.bands else ""
        for lower, name in self.bands:
            if fraction >= lower:
                label = name
        return label


@dataclass(frozen=True)
class SubScore:
    """One of the format's own sub-scores, and what we build it from.

    The groupings are ours. A test that reports "Sentence Mastery" is not
    reporting our accuracy and grammar measures averaged together, and saying
    so is the difference between a useful orientation and a false claim of
    equivalence.
    """

    label: str
    # Internal dimension names, averaged when more than one is present.
    from_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class FormatBlueprint:
    """A round or simulation, ready to be seeded as a profile."""

    code: str
    name: str
    style: str
    company: str
    description: str
    estimated_minutes: int
    sections: tuple[SectionBlueprint, ...]
    # What the student is told at the end. Thresholds are on the internal
    # 0-100 composite and are authoring estimates until the validation study
    # says otherwise -- which is exactly what COMPANY_ROUND_NOTE admits.
    verdict_bands: tuple[tuple[float, str, str], ...] = ()
    # Why this round is shaped the way it is. Shown on the format card, so a
    # student knows what they are walking into before they start.
    what_to_expect: tuple[str, ...] = field(default_factory=tuple)
    # Vendor-style simulations only: the scale and sub-scores this format
    # reports on. Company rounds report an outcome instead and leave both unset.
    scale: ScaleBlueprint | None = None
    subscores: tuple[SubScore, ...] = field(default_factory=tuple)
    # Parts of the real format this simulation does not contain, and where to
    # go for them instead. Shown on the format card. Being explicit is the
    # point: a student who thinks they have practised the whole test has been
    # misled by the omission.
    not_included: str = ""
    # Where the structure came from, said plainly and briefly. Vendor-style
    # simulations imitate one *configuration* of a vendor's platform, and the
    # vendor runs others; this line tells the student which one they are
    # practising without turning the card into a legal notice.
    provenance: str = ""


# The bands are shared: the rounds differ in shape and pressure, not in what
# counts as ready. A single definition also means one place to refit them when
# the study comes back.
_BANDS: tuple[tuple[float, str, str], ...] = (
    (72.0, "Likely to clear",
     "On this evidence you would probably get through a round of this shape."),
    (60.0, "Borderline",
     "Could go either way on the day. The gap below is the one to close first."),
    (45.0, "Not yet",
     "A round of this shape would probably stop you today. It is closeable, "
     "and the diagnosis below says where to start."),
    (0.0, "Well short",
     "This round is not the next thing to attempt. Work the drills first and "
     "come back to it."),
)


EXTEMPORE = SectionBlueprint(
    title="Extempore",
    task_type="open_response", item_count=1, prep_seconds=30,
    response_seconds=120, prompt_plays_allowed=1,
    instructions=("Thirty seconds to think, then two minutes to speak. Take a "
                  "position early and hold it -- wandering is what costs marks."),
)

HR_SHORT = SectionBlueprint(
    title="HR questions",
    task_type="short_answer", item_count=5, prep_seconds=0,
    response_seconds=45, prompt_plays_allowed=1,
    instructions=("Standard interview questions, one play each. Answer as you "
                  "would to a person, not as you would write it down."),
)


BLUEPRINTS: tuple[FormatBlueprint, ...] = (
    # TCS iON-style communication round: the seven-section A–G spoken-English
    # assessment described in the research deck. Fill-the-Blanks and Correct-
    # the-Sentence are grammar sections; until the spoken variants exist
    # (Phase 3) they are served as the typed/chosen grammar tasks the bank
    # already fills, which is the same grammar signal by a different channel.
    FormatBlueprint(
        # Positioning (2026-08-23): the supplied research document states
        # that TCS does not publish a separate spoken communication round
        # (the NQT lists Verbal Ability) and that its mock screens are
        # illustrative, not live screenshots. So this is a practice round
        # built on the reported seven-task pattern -- never "the TCS iON
        # assessment". Counts and timings are ours.
        code="company_round_tcs", name="TCS-family Communication Practice",
        style="company_round", company="TCS", estimated_minutes=20,
        description=("A preparation simulation of the spoken communication "
                     "round pattern reported for TCS-family hiring: short "
                     "spoken answers, reading aloud, a workplace conversation, "
                     "listen-and-repeat, spoken fill-in and correction tasks, "
                     "and a short free-speech topic."),
        provenance=("Based on reported and researched communication-round "
                    "patterns, not on a published TCS test. TCS does not "
                    "publish a separate spoken round; question counts and "
                    "timings here are our own configuration."),
        sections=(
            SectionBlueprint(
                title="Section A - Short Questions", task_type="short_answer",
                item_count=4, prep_seconds=0, response_seconds=20,
                prompt_plays_allowed=1,
                instructions=("Listen to the question once and answer in a "
                              "complete, natural sentence."),
            ),
            SectionBlueprint(
                title="Section B - Read Aloud", task_type="read_aloud",
                item_count=4, prep_seconds=5, response_seconds=20,
                selection={"difficulty_max": 1.0},
                instructions="Read the sentence on screen aloud, clearly and fluently.",
            ),
            SectionBlueprint(
                title="Section C - Conversation", task_type="conversation_question",
                item_count=3, prep_seconds=0, response_seconds=40,
                prompt_plays_allowed=1,
                # Instruction truthfulness (PM increment 2026-08-24): this
                # said "Read the workplace situation", but the situation is
                # PLAYED, once, as audio (prompt_plays_allowed=1) -- a
                # candidate who waited to read it lost the one play. The
                # wording now states the actual mechanic. Task, timing,
                # audio and counts are unchanged.
                instructions=("Listen to the workplace situation — it is "
                              "spoken and plays only once. Then respond as "
                              "you would to a colleague, in one to three "
                              "sentences."),
            ),
            SectionBlueprint(
                title="Section D - Listen & Repeat", task_type="repeat_sentence",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="Listen once and repeat the sentence exactly.",
            ),
            SectionBlueprint(
                title="Section E - Fill in the Blanks", task_type="spoken_completion",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence with one word missing, "
                              "read as 'blank'. Say the complete sentence "
                              "aloud with the missing word filled in."),
            ),
            SectionBlueprint(
                title="Section F - Correct the Sentence", task_type="spoken_correction",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence containing one error. "
                              "Say the corrected sentence aloud."),
            ),
            SectionBlueprint(
                title="Section G - Free Speech", task_type="open_response",
                item_count=1, prep_seconds=30, response_seconds=60,
                instructions=("Thirty seconds to think, then speak on the topic "
                              "for up to a minute."),
            ),
        ),
        verdict_bands=_BANDS,
        what_to_expect=(
            "Seven short spoken sections, from short answers to a free-speech topic.",
            "Heard prompts play once -- Short Questions and Listen & Repeat.",
            "The fill-in and correction tasks are spoken, not typed.",
        ),
    ),
    # Infosys: the supplied guide is a practice/research document that
    # deliberately declines to claim fixed timings or question counts, so
    # this is positioned as practice on the reported seven-task pattern.
    FormatBlueprint(
        code="company_round_infosys", name="Infosys-style Communication Practice",
        style="company_round", company="Infosys", estimated_minutes=20,
        description=("A preparation simulation of the spoken communication "
                     "round pattern reported for Infosys hiring: short spoken "
                     "answers, reading aloud, a workplace conversation, "
                     "listen-and-repeat, spoken fill-in and correction tasks, "
                     "and a free-speech topic."),
        provenance=("Based on the reference material available to us, which "
                    "does not state fixed timings or question counts; the "
                    "exact employer configuration may vary. Counts and "
                    "timings here are our own configuration."),
        sections=(
            SectionBlueprint(
                title="Section A - Short Questions", task_type="short_answer",
                item_count=4, prep_seconds=0, response_seconds=20,
                prompt_plays_allowed=1,
                instructions=("Listen to the question once and answer in one "
                              "clear, complete sentence."),
            ),
            SectionBlueprint(
                title="Section B - Read Aloud", task_type="read_aloud",
                item_count=4, prep_seconds=5, response_seconds=20,
                selection={"difficulty_max": 1.0},
                instructions="Read the sentence aloud with clear pronunciation.",
            ),
            SectionBlueprint(
                title="Section C - Conversation", task_type="conversation_question",
                item_count=3, prep_seconds=0, response_seconds=40,
                prompt_plays_allowed=1,
                instructions=("Respond naturally to the workplace situation, in "
                              "one to three sentences."),
            ),
            SectionBlueprint(
                title="Section D - Listen & Repeat", task_type="repeat_sentence",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="Listen to the sentence and repeat it exactly.",
            ),
            SectionBlueprint(
                title="Section E - Fill in the Blanks", task_type="spoken_completion",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence with one word missing, "
                              "read as 'blank'. Say the complete sentence "
                              "aloud with the missing word filled in."),
            ),
            SectionBlueprint(
                title="Section F - Correct the Sentence", task_type="spoken_correction",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence containing one error. "
                              "Say the corrected sentence aloud."),
            ),
            SectionBlueprint(
                title="Section G - Free Speech", task_type="open_response",
                item_count=1, prep_seconds=30, response_seconds=60,
                instructions="Prepare briefly, then speak on the topic for up to a minute.",
            ),
        ),
        verdict_bands=_BANDS,
        what_to_expect=(
            "Seven short spoken sections, from short answers to a free-speech topic.",
            "No visual cue on the heard prompts -- they arrive as audio, once.",
            "The fill-in and correction tasks are spoken, not typed.",
        ),
    ),
    # Wipro voice round on the SHL/SVAR platform: the seven-section A–G set from
    # the research deck, plus a short listening-comprehension round the demo
    # shows at the end.
    FormatBlueprint(
        code="company_round_wipro", name="Wipro-style Voice Round",
        style="company_round", company="Wipro", estimated_minutes=22,
        description=("An SHL/SVAR-style voice assessment: short spoken answers, "
                     "reading aloud, a conversation, listen-and-repeat, a "
                     "grammar round, a free-speech topic, and a short "
                     "listening-comprehension round."),
        sections=(
            SectionBlueprint(
                title="Section A - Short Questions", task_type="short_answer",
                item_count=3, prep_seconds=0, response_seconds=20,
                prompt_plays_allowed=1,
                instructions="Listen to the information and answer in a single sentence.",
            ),
            SectionBlueprint(
                title="Section B - Read & Speak", task_type="read_aloud",
                item_count=4, prep_seconds=5, response_seconds=20,
                selection={"difficulty_max": 1.0},
                instructions="Read the sentence shown on screen out loud.",
            ),
            SectionBlueprint(
                title="Section C - Conversation", task_type="conversation_question",
                item_count=3, prep_seconds=0, response_seconds=40,
                prompt_plays_allowed=1,
                instructions="Listen to the situation and give an appropriate spoken response.",
            ),
            SectionBlueprint(
                title="Section D - Listen & Repeat", task_type="repeat_sentence",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="Listen to the sentence (played once) and repeat it exactly.",
            ),
            SectionBlueprint(
                title="Section E - Fill in the Blanks", task_type="spoken_completion",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence with one word missing, "
                              "read as 'blank'. Say the complete sentence "
                              "aloud with the missing word filled in."),
            ),
            SectionBlueprint(
                title="Section F - Correct the Sentence", task_type="spoken_correction",
                item_count=4, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence containing one error. "
                              "Say the corrected sentence aloud."),
            ),
            SectionBlueprint(
                title="Section G - Free Speech", task_type="open_response",
                item_count=1, prep_seconds=30, response_seconds=45,
                instructions="Thirty seconds to prepare, then speak for up to forty-five.",
            ),
            SectionBlueprint(
                title="Section H - Listening Comprehension",
                task_type="listening_comprehension", item_count=3,
                prep_seconds=0, response_seconds=0, prompt_plays_allowed=1,
                instructions=("Listen to the clip once, then choose the most "
                              "suitable answer."),
            ),
        ),
        verdict_bands=_BANDS,
        what_to_expect=(
            "Eight parts, from short answers to a listening-comprehension round.",
            "Heard prompts play once and cannot be replayed.",
            "The grammar and comprehension rounds are answered by choosing.",
        ),
    ),
    # Cognizant Versant-style assessment: the four-part A–D structure from the
    # research deck -- Reading & Listening, Speaking, Grammar, Passages. Shaped
    # like SVAR, so the runner gives it the navy skin (a company-based skin
    # override; its style stays company_round so results present as a round
    # verdict, not a vendor scale); the isolated word-list items
    # (real Q11–15) fold into Reading until the read_words task exists (Phase 3).
    FormatBlueprint(
        code="company_round_cognizant",
        name="Cognizant-style Communication Assessment",
        style="company_round", company="Cognizant", estimated_minutes=28,
        description=("A four-part communication assessment: read sentences aloud "
                     "and repeat what you hear, speak on open topics, a written "
                     "grammar round, and listen-and-answer comprehension."),
        sections=(
            SectionBlueprint(
                title="Section A - Reading & Listening", task_type="read_aloud",
                item_count=8, prep_seconds=0, response_seconds=15,
                selection={"difficulty_max": 1.0},
                instructions=("Read each sentence given below out loud. You have "
                              "fifteen seconds to record each one."),
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section A - Word Lists", task_type="read_aloud",
                item_count=3, prep_seconds=0, response_seconds=15,
                # The reserved word-list difficulty band (1.2): only these
                # items sit in it, so only this section draws them.
                selection={"difficulty_min": 1.1, "difficulty_max": 1.4},
                instructions=("Read the list of isolated words out loud, "
                              "clearly, one after another."),
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section A - Listen & Repeat", task_type="repeat_sentence",
                item_count=8, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions=("Listen to the audio played, then repeat the "
                              "sentence out loud. It plays once."),
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section B - Speaking", task_type="open_response",
                item_count=3, prep_seconds=30, response_seconds=60,
                instructions=("Speak on the topic given. Thirty seconds to think, "
                              "then up to a minute to speak."),
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section C - Grammar", task_type="sentence_completion",
                item_count=5, prep_seconds=0, response_seconds=0,
                instructions=("Fill in the blank with the most appropriate word "
                              "-- articles, tenses and prepositions."),
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section C - Grammar (Voice)", task_type="voice_change",
                item_count=3, prep_seconds=0, response_seconds=0,
                instructions="Convert the sentence into the correct active/passive voice.",
                continuous_numbering=True, show_instruction=True,
            ),
            SectionBlueprint(
                title="Section D - Passages", task_type="listening_comprehension",
                item_count=6, prep_seconds=0, response_seconds=0,
                prompt_plays_allowed=1,
                instructions=("Listen to each passage once, then answer the "
                              "questions that follow."),
                continuous_numbering=True, show_instruction=True,
            ),
        ),
        verdict_bands=_BANDS,
        what_to_expect=(
            "Four parts: reading & listening, speaking, grammar, comprehension.",
            "Spoken items record once; audio plays once and cannot be paused.",
            "The grammar and comprehension rounds are answered by typing or choosing.",
        ),
    ),
    FormatBlueprint(
        code="company_round_accenture", name="Accenture-style Communication Round",
        style="company_round", company="Accenture", estimated_minutes=15,
        description=("A two-part gate: an automated speaking screen in the "
                     "shape of a vendor test, then an HR round. The longest of "
                     "the company rounds and the closest to a full simulation."),
        sections=(
            SectionBlueprint(
                title="Read Aloud", task_type="read_aloud", item_count=4,
                prep_seconds=5, response_seconds=20,
                instructions="Read each sentence aloud, clearly and at a natural pace.",
            ),
            SectionBlueprint(
                title="Repeat Sentence", task_type="repeat_sentence", item_count=4,
                prep_seconds=0, response_seconds=15, prompt_plays_allowed=1,
                instructions="You will hear each sentence once. Repeat it exactly.",
            ),
            SectionBlueprint(
                title="Sentence Build", task_type="sentence_build", item_count=3,
                prep_seconds=8, response_seconds=25,
                instructions=("Put the word groups in order and say the whole "
                              "sentence aloud."),
            ),
            HR_SHORT,
        ),
        verdict_bands=_BANDS,
        what_to_expect=(
            "The automated screen comes first and is unforgiving on timing.",
            "Repeat Sentence plays once -- there is no second chance.",
            "The HR questions are scored the same way as the rest.",
        ),
    ),
)


# --------------------------------------------------------------------------
# Vendor-style simulations
# --------------------------------------------------------------------------
#
# Format only. These imitate the section order, the timing and the one-shot
# pressure of the automated spoken-English tests used in campus hiring. No
# item is taken from any real assessment (CONTENT-04), the names are used
# descriptively to say which format is being practised, and no test provider
# is affiliated with, has reviewed, or endorses any of it.
#
# **What these deliberately leave out.** Two of the three real formats include
# multiple-choice grammar, vocabulary and listening-comprehension sections.
# The simulation runner records speech; it has no multiple-choice mode, and a
# section it cannot serve would be dropped without saying so. Rather than ship
# a simulation that is quietly shorter than the test it imitates, those
# sections are named in ``not_included`` and the student is pointed at the
# quiz engine, which is where that content actually lives.

_VENDOR_BANDS: tuple[tuple[float, str], ...] = (
    (0.00, "Beginning"),
    (0.30, "Developing"),
    (0.55, "Competent"),
    (0.75, "Strong"),
)

# Sub-scores, grouped from our internal dimensions. Same caveat every time:
# the grouping is ours, not the vendor's.
_SPEAKING_SUBSCORES: tuple[SubScore, ...] = (
    SubScore("Sentence Mastery", ("accuracy", "grammar")),
    SubScore("Vocabulary", ("content",)),
    SubScore("Fluency", ("fluency", "latency", "disfluency")),
    SubScore("Pronunciation", ("pronunciation",)),
)

# Derived from the scoring model, as SVAR's is: the hand-typed tuple named
# "Active Listening" while the model that scores the format says
# "Comprehension", and a card and a result that disagree is a trust defect.
_SPEECHX_SUBSCORES: tuple[SubScore, ...] = tuple(
    SubScore(x.label, tuple(x.dimensions)) for x in evaluation.SPEECHX.subscores
)

# SVAR names six. Five were reportable from a speaking-only format; the sixth,
# Vocabulary, had nothing behind it until Vocabulary in Context existed -- so
# the format now contains a Vocabulary in Context section and the sub-score is
# a measurement rather than a relabelled content score.
# SVAR names six. The researched A-D structure can honestly feed four of
# them from its own sections: Pronunciation (read aloud, repeat), Fluency,
# Active Listening (listen & answer, repeat) and Grammar (the two typed
# grammar rounds plus composed speech). "Spoken English Understanding" and
# "Vocabulary" have no section behind them in the real structure, and
# inventing one -- or relabelling a different measure -- would put a number
# on the report that measures something else. They are omitted, and the
# results page says so.
# One definition, not two. This tuple used to be typed by hand and drifted
# from the model that actually scores the format (Active Listening carried
# ``accuracy`` here and not there). It is now derived from ``evaluation.SVAR``
# so the card, the fallback grouping and the scorer cannot disagree.
_SVAR_SUBSCORES: tuple[SubScore, ...] = tuple(
    SubScore(s.label, tuple(s.dimensions)) for s in evaluation.SVAR.subscores
)

VENDOR_BLUEPRINTS: tuple[FormatBlueprint, ...] = (
    # ``versant_style_full`` and ``svar_style_full`` used to sit here. They
    # were the same two formats the audit calls T1 and T2, built when a
    # template could contain nothing but speaking -- so both were speaking-only
    # imitations of tests that are not. They are replaced by
    # ``TEMPLATE_BLUEPRINTS`` below rather than kept alongside: two SVAR
    # simulations in the picker, one of them missing half the test, is not a
    # choice a student can make sensibly.
    FormatBlueprint(
        # ------------------------------------------------------------------
        # Evidence basis (2026-08-23): supplied Mercer | Mettl screens
        # ("SpeechX Assessment.pdf", 10 pages). Directly evidenced: section
        # list "A 18 Questions / 10 Minutes, B 4 Questions / 10 Minutes,
        # C 34 Questions / 15 Minutes, D 16 Questions / 10 Minutes"; A
        # "18 statements/audio clips ... read and record", item "Maximum
        # Recording Time 00:15"; B "3 topics ... 1 minute each ... 30
        # seconds to think ... you can skip and start recording"; C "34
        # questions ... 15 minutes", item "fill in the blank using the
        # correct form of the verb in bracket" (typed); D "audio clips and
        # questions ... 10 minutes", clip item "Q.1 ... The next three
        # questions are based on the audio ... play this media: 1 times ...
        # Type in 'Okay' to proceed to the questions"; total clock 44:50.
        #
        # Inferred: A split 10 read / 8 heard (source gives the total only);
        # C's internal distribution 8/8/6/6 typed + 6 voice-change (the
        # source shows one verb-form item; the split follows the other
        # four-section walkthrough); D = 4 clips x (1 numbered clip screen +
        # 3 questions) = 16 numbered items, the only reading consistent with
        # "the next three questions" and a 16 count; B's "4 Questions" in
        # the overview against "3 topics" in its instructions -- 3 is used.
        # Ours: every item's wording.
        #
        # PM decision (2026-08-23): speaking-window advancement behaviour is
        # not explicitly established by the supplied source material; the
        # current implementation uses the platform's adaptive speech
        # behaviour (fixed_window stays False on every section). This is a
        # documented P2 fidelity uncertainty, not official Mercer | Mettl
        # behaviour, and the implementation is not vendor-identical.
        # ------------------------------------------------------------------
        code="speechx_style_full",
        name="SpeechX-style Communication Assessment (Mercer | Mettl)",
        style="speechx_style", company="", estimated_minutes=50,
        description=("A simulation of the four-section SpeechX (Mercer | "
                     "Mettl) communication assessment shown in our reference "
                     "material — reading & listening, speaking, grammar and "
                     "comprehension."),
        provenance=("Based on screenshots of one SpeechX (Mercer | Mettl) "
                    "assessment sitting supplied to us. Not official Mercer "
                    "or employer material; some details are our own "
                    "configuration."),
        sections=(
            SectionBlueprint(
                title="Section A1 - Read & Record (Sentence)",
                task_type="read_aloud", item_count=10,
                prep_seconds=0, response_seconds=15, budget_seconds=600,
                continuous_numbering=True,
                selection={"difficulty_max": 1.0},
                instructions=("In this section you will be presented with 18 "
                              "statements/audio clips. You will have to read "
                              "and record the statements/content of the audio "
                              "clips. Total time to complete the recordings is "
                              "10 min. All questions are mandatory."),
            ),
            SectionBlueprint(
                title="Section A2 - Listen & Record",
                task_type="repeat_sentence", item_count=8,
                prep_seconds=0, response_seconds=15, prompt_plays_allowed=1,
                budget_seconds=600, continuous_numbering=True,
                instructions=("Listen to the audio clip once and record the "
                              "sentence you heard. Maximum recording time 15 "
                              "seconds."),
            ),
            SectionBlueprint(
                title="Section B - Speak on the Topic",
                task_type="open_response", item_count=3,
                prep_seconds=30, response_seconds=60, prompt_plays_allowed=0,
                budget_seconds=600, skip_prep=True, continuous_numbering=True,
                instructions=("In this section you will be given 3 topics on "
                              "which you need to speak for 1 minute each. For "
                              "each topic you will get 30 seconds to think, "
                              "after which your response will start getting "
                              "recorded. If you prefer not to use the thinking "
                              "time, you can skip and start recording your "
                              "response. All questions are mandatory."),
            ),
            SectionBlueprint(
                title="Section C1 - Verb Forms",
                task_type="sentence_completion", item_count=8,
                prep_seconds=0, response_seconds=0, budget_seconds=900,
                continuous_numbering=True, selection={"topics": ["verb_forms"]},
                instructions=("In this section you are given 34 questions to be "
                              "completed in 15 minutes. Read the sentence and "
                              "fill in the blank using the correct form of the "
                              "verb in brackets."),
            ),
            SectionBlueprint(
                title="Section C2 - Tenses",
                task_type="sentence_completion", item_count=8,
                prep_seconds=0, response_seconds=0, budget_seconds=900,
                continuous_numbering=True, selection={"topics": ["tenses"]},
                instructions=("Fill in the blank using the appropriate tense "
                              "provided in brackets."),
            ),
            SectionBlueprint(
                title="Section C3 - Articles",
                task_type="sentence_completion", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900,
                continuous_numbering=True, selection={"topics": ["articles"]},
                instructions=("Fill in the blank using the correct article."),
            ),
            SectionBlueprint(
                title="Section C4 - Prepositions",
                task_type="sentence_completion", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900,
                continuous_numbering=True, selection={"topics": ["prepositions"]},
                instructions=("Fill in the blank with the most suitable "
                              "preposition provided in brackets."),
            ),
            SectionBlueprint(
                title="Section C5 - Change the Voice (Active/Passive)",
                task_type="voice_change", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900,
                continuous_numbering=True,
                instructions=("Change the voice of the following sentences "
                              "(active/passive) as required, choosing the "
                              "correct rewrite from the options."),
            ),
            SectionBlueprint(
                title="Section D - Listen & Answer",
                task_type="listening_comprehension", item_count=12,
                prep_seconds=0, response_seconds=0, prompt_plays_allowed=1,
                budget_seconds=600, ack_gate="clip", continuous_numbering=True,
                instructions=("In this section you will be presented with audio "
                              "clips and questions based on the audio clips. "
                              "You are given 10 minutes to complete all the "
                              "questions. You can play each clip once and "
                              "cannot pause it; the next three questions are "
                              "based on it. Type 'Okay' after each clip to "
                              "proceed to its questions."),
            ),
        ),
        what_to_expect=(
            "Four sections: reading & listening, speaking, grammar, and comprehension.",
            "Sections A, B, C and D each have their own time budget.",
            "Spoken items record once; each audio clip plays once and cannot be paused.",
        ),
        scale=ScaleBlueprint(0, 100, _VENDOR_BANDS, anchored=False),
        subscores=_SPEECHX_SUBSCORES,
        not_included=(
            "This simulation covers reading, speaking, grammar and listening "
            "comprehension. A dedicated vocabulary section is practised "
            "separately under Practice, where the vocabulary quizzes cover the "
            "same ground."
        ),
    ),
)

# --------------------------------------------------------------------------
# The four templates
# --------------------------------------------------------------------------
#
# Assembled from modules, not hard-coded: every section below names a task
# type the runner already serves and the bank already fills, which is what
# Phases 3 and 4 were for. Before them, three of these four were impossible to
# express -- a template could contain nothing but speaking.
#
# ``estimated_minutes`` on each is the computed figure, not a guess. See
# ``duration_minutes``.

_FOUR_SKILL_NOTE = (
    "This reports one score per skill rather than vendor sub-scores. The four "
    "skills are measured from their own sections, so a Listening score here "
    "is what the listening sections produced -- not a speaking dimension "
    "wearing the word Listening."
)

TEMPLATE_BLUEPRINTS: tuple[FormatBlueprint, ...] = (
    FormatBlueprint(
        # ------------------------------------------------------------------
        # Evidence basis (PM closure, 2026-08-23). Source: observed
        # third-party walkthrough evidence -- 20 frames of a YouTube
        # recording titled "Wipro WILP SVAR Assessment Questions". No
        # SHL/SVAR branding is visible in any frame; "SVAR" is the video's
        # label. Directly evidenced: Section A "18 statements or audio
        # clips", 10 minutes, mandatory; sentence items 15 s; paragraph
        # items 30 s, record once, auto-submit; listen items 15 s, once, no
        # pause, Play Audio button; Section B 3 topics, 90 s think, 60 s
        # speak, speaking points shown as questions ("just suggestions");
        # Section C 34 questions in five categories (8/8/6/6/6), 15 min,
        # typed with bracketed choices, voice change chosen from four;
        # Section D clips played once, three questions each, 10 min, a typed
        # "Okay" before the questions.
        #
        # Inferred (conservative): A1 = 8 (paragraph part starts at Q9),
        # A2 = 2 (listen part starts at Q11), A3 = 8 (18 - 8 - 2).
        #
        # Ours, because the source does not show them: the number of D
        # clips (4) and D's answer format (multiple choice); the wording of
        # every item and every speaking point; scoring.
        #
        # Never "the SVAR test", "official", "exact", "full", "delivered on
        # the SVAR platform". See test_svar_positioning.
        # ------------------------------------------------------------------
        code="svar_full_simulation",
        name="SVAR-style Communication Assessment (4-section)",
        style="svar_style", company="", estimated_minutes=54,
        description=("A simulation of an observed four-section communication "
                     "assessment — reading & listening, speaking, grammar "
                     "and comprehension."),
        provenance=("Based on a publicly available third-party walkthrough "
                    "of one assessment sitting. Not official SHL or employer "
                    "material; some details are our own configuration."),
        sections=(
            # -- Section A: Reading & Listening -- 18 items, 10 minutes ------
            SectionBlueprint(
                title="Section A1 - Read & Say Aloud (Sentence)",
                task_type="read_aloud", item_count=8,
                prep_seconds=0, response_seconds=15, budget_seconds=600, continuous_numbering=True,
                selection={"difficulty_max": 1.0},
                instructions=("In this section you will encounter 18 "
                              "statements or audio clips. Read and record "
                              "the statements or the content of the audio "
                              "clips. You have a total of 10 minutes to "
                              "complete all recordings, and every question "
                              "is mandatory."),
            ),
            SectionBlueprint(
                title="Section A2 - Read & Say Aloud (Paragraph)",
                task_type="read_aloud", item_count=2,
                prep_seconds=0, response_seconds=30, budget_seconds=600, continuous_numbering=True,
                selection={"difficulty_min": 1.5},
                instructions=("Read the given paragraph carefully and then say "
                              "the exact paragraph out loud. You have 30 "
                              "seconds; your response submits automatically."),
            ),
            SectionBlueprint(
                title="Section A3 - Listen & Say Aloud",
                task_type="repeat_sentence", item_count=8,
                prep_seconds=0, response_seconds=15, prompt_plays_allowed=1,
                budget_seconds=600, continuous_numbering=True,
                instructions=("Listen carefully to the audio recording and "
                              "repeat the sentences exactly as you hear them. "
                              "You have 15 seconds to record. You can only "
                              "listen once and cannot pause the audio."),
            ),
            # -- Section B: Speaking -- 3 topics ------------------------------
            SectionBlueprint(
                title="Section B - Speak on the Topic",
                task_type="open_response", item_count=3,
                prep_seconds=90, response_seconds=60, prompt_plays_allowed=0,
                fixed_window=True, allow_skip=True, show_cues=True,
                continuous_numbering=True,
                instructions=("In this section you will be given 3 topics on "
                              "which you have to speak for 60 seconds each. "
                              "You will have 90 seconds to think about each "
                              "topic before recording starts automatically. "
                              "Speaking points are shown as questions under "
                              "the topic; they are suggestions only, and you "
                              "may speak on other points related to the "
                              "topic."),
            ),
            # -- Section C: Grammar -- 34 questions, 15 minutes ---------------
            SectionBlueprint(
                title="Section C1 - Verb Forms",
                task_type="sentence_completion", item_count=8,
                prep_seconds=0, response_seconds=0, budget_seconds=900, continuous_numbering=True,
                selection={"topics": ["verb_forms"]},
                instructions=("In this section you will answer a total of 34 "
                              "questions in five categories: verb forms (8), "
                              "tenses (8), articles (6), prepositions (6) and "
                              "voice change (6). You have 15 minutes to "
                              "complete all the questions, and each question "
                              "is mandatory. Fill in the blank using the "
                              "correct form of the verb provided in brackets."),
            ),
            SectionBlueprint(
                title="Section C2 - Tenses",
                task_type="sentence_completion", item_count=8,
                prep_seconds=0, response_seconds=0, budget_seconds=900, continuous_numbering=True,
                selection={"topics": ["tenses"]},
                instructions=("Fill in the blank using the appropriate tense "
                              "provided in brackets."),
            ),
            SectionBlueprint(
                title="Section C3 - Articles",
                task_type="sentence_completion", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900, continuous_numbering=True,
                selection={"topics": ["articles"]},
                instructions=("Fill in the blank using the correct article to "
                              "complete the sentence appropriately."),
            ),
            SectionBlueprint(
                title="Section C4 - Prepositions",
                task_type="sentence_completion", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900, continuous_numbering=True,
                selection={"topics": ["prepositions"]},
                instructions=("Fill in the blank with the most suitable "
                              "preposition provided in brackets."),
            ),
            SectionBlueprint(
                title="Section C5 - Change the Voice (Active/Passive)",
                task_type="voice_change", item_count=6,
                prep_seconds=0, response_seconds=0, budget_seconds=900, continuous_numbering=True,
                instructions=("Change the voice of the following sentences "
                              "(active/passive) as required, choosing the "
                              "correct rewrite from the options."),
            ),
            # -- Section D: Comprehension -- 10 minutes -----------------------
            SectionBlueprint(
                title="Section D - Listen & Answer",
                task_type="listening_comprehension", item_count=12,
                prep_seconds=0, response_seconds=0, prompt_plays_allowed=1,
                budget_seconds=600, ack_gate="section", continuous_numbering=True,
                instructions=("In this section you will listen to audio clips "
                              "followed by a set of questions. You have 10 "
                              "minutes to finish all the questions. Pay close "
                              "attention to the audio, as the next three "
                              "questions will be based on it. You can only "
                              "listen to the audio once and cannot pause it."),
            ),
        ),
        what_to_expect=(
            "Four sections: reading & listening, speaking, grammar, and comprehension.",
            "Spoken items record once; audio plays once and cannot be paused.",
            "Sections A, C and D have their own time budgets; the grammar and "
            "comprehension questions are typed or chosen, not timed one by one.",
        ),
        scale=ScaleBlueprint(0, 100, _VENDOR_BANDS, anchored=False),
        subscores=_SVAR_SUBSCORES,
    ),
    FormatBlueprint(
        code="versant_style_speaking_listening",
        name="Versant-style Speaking Test",
        style="versant_style", company="", estimated_minutes=22,
        description=("The Pearson Versant-style spoken test, six parts: read on "
                     "cue, repeat what you hear, short answers, sentence builds, "
                     "story retelling, and open questions."),
        sections=(
            SectionBlueprint(
                title="Part A - Reading", task_type="read_aloud",
                item_count=6, prep_seconds=3, response_seconds=20,
                selection={"difficulty_max": 1.0},
                # Instruction truthfulness (PM increment 2026-08-24): the
                # old wording promised a spoken sentence number and an
                # end-of-window beep; this product plays neither -- the
                # sentence appears on screen and a start tone begins the
                # recording. The claim changed, not the assessment.
                instructions=("Read the sentence on screen aloud, clearly "
                              "and at a natural pace. Recording starts "
                              "after the tone."),
            ),
            SectionBlueprint(
                title="Part B - Repeat", task_type="repeat_sentence",
                item_count=8, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="You will hear each sentence once. Repeat it word-for-word.",
            ),
            SectionBlueprint(
                title="Part C - Questions", task_type="short_answer",
                item_count=6, prep_seconds=0, response_seconds=12,
                prompt_plays_allowed=1,
                instructions=("Give a simple answer to each question -- one to "
                              "four words, not a full sentence."),
            ),
            SectionBlueprint(
                title="Part D - Sentence Builds", task_type="sentence_build",
                item_count=4, prep_seconds=5, response_seconds=25,
                instructions=("Rearrange the word groups into a sentence and say "
                              "it aloud in the time provided."),
            ),
            SectionBlueprint(
                title="Part E - Story Retelling", task_type="story_retell",
                item_count=3, prep_seconds=0, response_seconds=30,
                prompt_plays_allowed=1,
                instructions=("You will hear a story once. Retell it, including "
                              "the names, the action and the ending."),
            ),
            SectionBlueprint(
                title="Part F - Open Questions", task_type="open_response",
                item_count=2, prep_seconds=0, response_seconds=40,
                prompt_plays_allowed=1,
                instructions=("You will hear a question about a familiar "
                              "situation. Speak for up to forty seconds."),
            ),
        ),
        what_to_expect=(
            "Six parts, from reading on cue to open questions.",
            "Every heard prompt plays exactly once.",
            "Story retelling and open questions want a whole answer, not a word.",
        ),
        scale=ScaleBlueprint(20, 80, _VENDOR_BANDS, anchored=True),
        subscores=_SPEAKING_SUBSCORES,
        not_included=(
            "Every part of this is listening -- you hear the prompt and speak "
            "the answer -- but the report shows one skill, Speaking, because "
            "that is what is measured: how well you answered, not whether you "
            "followed. There is no reading and no writing here at all. "
            "Versant-style 4 Skills covers all four and scores each "
            "separately."
        ),
    ),
    FormatBlueprint(
        code="versant_style_four_skills",
        name="Versant-style 4 Skills",
        style="versant_style", company="", estimated_minutes=31,
        description=("Speaking, listening, reading and writing in one sitting. "
                     "The report gives a score per skill, because a single "
                     "number over four different abilities describes none of "
                     "them."),
        sections=(
            SectionBlueprint(
                title="Part A - Repeat Sentence", task_type="repeat_sentence",
                item_count=6, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="You will hear each sentence once. Repeat it exactly.",
            ),
            SectionBlueprint(
                title="Part B - Sentence Builds", task_type="sentence_build",
                item_count=4, prep_seconds=8, response_seconds=25,
                instructions=("Put the word groups in order and say the whole "
                              "sentence aloud."),
            ),
            SectionBlueprint(
                title="Part C - Conversations", task_type="conversation_question",
                item_count=3, prep_seconds=0, response_seconds=30,
                prompt_plays_allowed=1,
                instructions=("You will hear two people talking, then a "
                              "question. Answer out loud."),
            ),
            SectionBlueprint(
                title="Part D - Dictation", task_type="dictation",
                item_count=4, prep_seconds=0, response_seconds=0,
                prompt_plays_allowed=1,
                instructions=("You will hear a sentence once. Type it exactly "
                              "as you heard it."),
            ),
            SectionBlueprint(
                title="Part E - Reading", task_type="reading_comprehension",
                item_count=3, prep_seconds=0, response_seconds=0,
                instructions=("Read the passage, then answer the questions. "
                              "There is no clock on this part."),
            ),
            SectionBlueprint(
                title="Part F - Sentence Completion",
                task_type="sentence_completion",
                item_count=6, prep_seconds=0, response_seconds=0,
                instructions=("Type the one word that fits the gap. More than "
                              "one word is often acceptable."),
            ),
            SectionBlueprint(
                title="Part G - Passage Reconstruction",
                task_type="passage_reconstruction",
                item_count=2, prep_seconds=0, response_seconds=0,
                instructions=("Read the passage. It disappears, and then you "
                              "write what it said in your own words."),
            ),
        ),
        what_to_expect=(
            "Four skills, seven parts. You will type as much as you speak.",
            "The reconstruction passages disappear - that is the point of them.",
            "One score per skill, not one score for the lot.",
        ),
        scale=ScaleBlueprint(20, 80, _VENDOR_BANDS, anchored=True),
        # No vendor sub-scores on purpose. This format's report is the
        # four-skill rollup, and publishing both would put two different
        # numbers labelled Listening on the same page.
        subscores=(),
        not_included=_FOUR_SKILL_NOTE,
    ),
    FormatBlueprint(
        code="professional_english",
        name="Professional English",
        style="professional", company="", estimated_minutes=61,
        description=("The long one: ten parts across all four skills, on "
                     "workplace material throughout. Built to be sat once and "
                     "read carefully, not repeated weekly."),
        sections=(
            SectionBlueprint(
                title="Part 1 - Read Aloud", task_type="read_aloud",
                item_count=5, prep_seconds=5, response_seconds=20,
                instructions="Read each sentence aloud, clearly and at a natural pace.",
            ),
            SectionBlueprint(
                title="Part 2 - Repeat Sentence", task_type="repeat_sentence",
                item_count=6, prep_seconds=0, response_seconds=15,
                prompt_plays_allowed=1,
                instructions="You will hear each sentence once. Repeat it exactly.",
            ),
            SectionBlueprint(
                title="Part 3 - Conversations", task_type="conversation_question",
                item_count=4, prep_seconds=0, response_seconds=30,
                prompt_plays_allowed=1,
                instructions=("You will hear two colleagues talking, then a "
                              "question. Answer out loud."),
            ),
            SectionBlueprint(
                title="Part 4 - Briefings", task_type="passage_question",
                item_count=3, prep_seconds=0, response_seconds=40,
                prompt_plays_allowed=1,
                instructions=("You will hear an announcement or a short talk "
                              "once, then a question about it."),
            ),
            SectionBlueprint(
                title="Part 5 - Speak to the Point", task_type="open_response",
                item_count=2, prep_seconds=30, response_seconds=120,
                prompt_plays_allowed=1,
                instructions=("Thirty seconds to think, then two minutes. Take "
                              "a position early and hold it."),
            ),
            SectionBlueprint(
                title="Part 6 - Listening", task_type="listening_comprehension",
                item_count=6, prep_seconds=0, response_seconds=0,
                prompt_plays_allowed=1,
                instructions=("Each passage plays once, then you answer "
                              "questions about it."),
            ),
            SectionBlueprint(
                title="Part 7 - Choose the Reply", task_type="response_selection",
                item_count=5, prep_seconds=0, response_seconds=0,
                prompt_plays_allowed=1,
                instructions=("You will hear something said to you. Choose the "
                              "reply that fits. Every option is correct "
                              "English; only one of them lands."),
            ),
            SectionBlueprint(
                title="Part 8 - Reading", task_type="reading_comprehension",
                item_count=6, prep_seconds=0, response_seconds=0,
                instructions=("Read each passage, then answer the questions. "
                              "There is no clock on this part."),
            ),
            SectionBlueprint(
                title="Part 9 - Writing", task_type="email_writing",
                item_count=2, prep_seconds=0, response_seconds=360,
                instructions=("Write the email the brief asks for. Cover every "
                              "point listed; length is not the measure."),
            ),
            SectionBlueprint(
                title="Part 10 - Passage Reconstruction",
                task_type="passage_reconstruction",
                item_count=2, prep_seconds=0, response_seconds=0,
                instructions=("Read the passage. It disappears, and then you "
                              "write what it said in your own words."),
            ),
        ),
        what_to_expect=(
            "An hour, in one sitting. Do not start it between lectures.",
            "All four skills, workplace material in every part.",
            "The writing parts are the longest and carry the most weight.",
        ),
        scale=ScaleBlueprint(20, 80, _VENDOR_BANDS, anchored=True),
        subscores=(),
        not_included=_FOUR_SKILL_NOTE,
    ),
)


# Blueprints that have been withdrawn, named rather than inferred.
#
# The seeder needs to know which seeded profiles no longer have a blueprint so
# it can retire them. The obvious rule -- "any profile whose code is not a
# blueprint code" -- is wrong and dangerous: the builder gives every
# admin-authored profile a code too, so that rule retires a tenant's own
# assessments the next time anybody runs a content release. It did, on the
# first run, to two dozen of them.
#
# So the list is explicit. Adding a name here is part of removing a blueprint,
# and nothing else is ever touched.
WITHDRAWN_CODES: frozenset[str] = frozenset({
    # Replaced by versant_style_speaking_listening and (originally)
    # svar_style_spoken_english: the same two formats, no longer
    # speaking-only imitations of tests that are not.
    "versant_style_full",
    "svar_style_full",
    # The pre-research SVAR stand-in. It carried three sections the
    # researched assessment does not have (short answer, conversation, word
    # in context) and, worse, the SVAR scoring model was keyed to it rather
    # than to svar_full_simulation -- so the real, mockup-verified simulation
    # reported no sub-scores while the stand-in did. One SVAR, the real one.
    "svar_style_spoken_english",
})


# --------------------------------------------------------------------------
# Targeted practice
# --------------------------------------------------------------------------
#
# One small profile per weakness the result page can diagnose, so "Practise
# pronunciation" starts pronunciation work -- not a generic mock. These are
# ordinary profiles through the ordinary runner and scorer: configuration,
# not a second engine. style="drill" keeps them off the assessment pickers
# (they are started from a result, by id) and out of the picker's families.
#
# Composition rules, kept deliberately simple (no invented pedagogy):
# every session is short; where a natural easy->hard order exists it is used
# (read a visible sentence before repeating a heard one; a completion before
# a correction); each session's tasks emit the dimension it claims to train,
# which the scoring table (DIMENSIONS_BY_TASK) guarantees.

def _practice(code: str, name: str, description: str,
              sections: tuple[SectionBlueprint, ...]) -> FormatBlueprint:
    return FormatBlueprint(
        code=code, name=name, style="drill", company="",
        description=description, estimated_minutes=0,  # computed below
        sections=sections,
        what_to_expect=(
            "A short practice, not a test — a few focused items.",
            "Your result compares this practice with your last assessment.",
        ),
    )


PRACTICE_BLUEPRINTS: tuple[FormatBlueprint, ...] = (
    _practice(
        "practice_pronunciation", "Pronunciation practice",
        "A few sentences to read aloud, then a few to repeat. Slow down and "
        "say every word clearly.",
        (
            SectionBlueprint(title="Read aloud", task_type="read_aloud",
                             item_count=4, prep_seconds=0, response_seconds=15,
                             selection={"difficulty_max": 1.0},
                             instructions="Read the sentence aloud, clearly."),
            SectionBlueprint(title="Repeat", task_type="repeat_sentence",
                             item_count=3, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions="Listen once and repeat it exactly."),
        )),
    _practice(
        "practice_fluency", "Fluency practice",
        "Short timed speaking. Keep going — shorter sentences beat long "
        "pauses.",
        (
            SectionBlueprint(title="Warm up", task_type="read_aloud",
                             item_count=2, prep_seconds=0, response_seconds=15,
                             selection={"difficulty_max": 1.0},
                             instructions="Read the sentence aloud at a steady pace."),
            SectionBlueprint(title="Keep talking", task_type="open_response",
                             item_count=2, prep_seconds=5, response_seconds=45,
                             instructions=("Speak on the topic for up to 45 "
                                           "seconds. Do not stop to find the "
                                           "perfect sentence — keep going.")),
        )),
    _practice(
        "practice_latency", "Response speed practice",
        "Quick questions, quick answers. Start speaking as soon as you can.",
        (
            SectionBlueprint(title="Quick answers", task_type="short_answer",
                             item_count=5, prep_seconds=0, response_seconds=12,
                             prompt_plays_allowed=1,
                             instructions=("Answer the question you hear, "
                                           "straight away.")),
        )),
    _practice(
        "practice_accuracy", "Listening accuracy practice",
        "Sentences you hear once and say back. Hold the whole sentence, then "
        "say it.",
        (
            SectionBlueprint(title="Repeat", task_type="repeat_sentence",
                             item_count=5, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions="Listen once and repeat it exactly."),
        )),
    _practice(
        "practice_grammar", "Spoken grammar practice",
        "Say the corrected or completed sentence aloud — grammar at speaking "
        "speed.",
        (
            SectionBlueprint(title="Fill the blank", task_type="spoken_completion",
                             item_count=3, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions=("You will hear a sentence with one "
                                           "word missing, read as 'blank'. Say "
                                           "the complete sentence aloud.")),
            SectionBlueprint(title="Correct it", task_type="spoken_correction",
                             item_count=3, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions=("You will hear a sentence with one "
                                           "error. Say the corrected sentence "
                                           "aloud.")),
            SectionBlueprint(title="Build it", task_type="sentence_build",
                             item_count=2, prep_seconds=5, response_seconds=25,
                             instructions=("Rearrange the word groups into one "
                                           "sentence and say it aloud.")),
        )),
    _practice(
        "practice_comprehension", "Listening practice",
        "Short clips, then questions. Each clip plays once.",
        (
            SectionBlueprint(title="Listen and answer",
                             task_type="listening_comprehension",
                             item_count=3, prep_seconds=0, response_seconds=0,
                             prompt_plays_allowed=1,
                             instructions=("Listen to the clip once, then "
                                           "choose the best answer.")),
        )),
    _practice(
        "practice_content", "Answering the question practice",
        "Heard questions and situations. Answer what was actually asked.",
        (
            SectionBlueprint(title="Respond", task_type="conversation_question",
                             item_count=2, prep_seconds=0, response_seconds=40,
                             prompt_plays_allowed=1,
                             instructions=("Listen to the situation and give "
                                           "your spoken response.")),
            SectionBlueprint(title="Quick answers", task_type="short_answer",
                             item_count=3, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions="Answer the question you hear."),
        )),
    _practice(
        "practice_completeness", "Complete answers practice",
        "Say the whole thing — a story retold, sentences said back in full.",
        (
            SectionBlueprint(title="Repeat in full", task_type="repeat_sentence",
                             item_count=3, prep_seconds=0, response_seconds=15,
                             prompt_plays_allowed=1,
                             instructions="Listen once and repeat the whole sentence."),
            SectionBlueprint(title="Retell", task_type="story_retell",
                             item_count=1, prep_seconds=0, response_seconds=30,
                             prompt_plays_allowed=1,
                             instructions=("You will hear a short story once. "
                                           "Retell it — names, action, ending.")),
        )),
    _practice(
        "practice_appropriacy", "Choosing what to say practice",
        "Hear a line, choose the reply that lands well. Every wrong option "
        "is correct English — the skill is judgement.",
        (
            SectionBlueprint(title="Pick the reply",
                             task_type="response_selection",
                             item_count=5, prep_seconds=0, response_seconds=0,
                             prompt_plays_allowed=1,
                             instructions=("Listen once, then choose the reply "
                                           "that fits best.")),
        )),
    _practice(
        "practice_vocabulary", "Vocabulary practice",
        "Which sense a word carries in the sentence it is in.",
        (
            SectionBlueprint(title="Word in context",
                             task_type="vocabulary_in_context",
                             item_count=5, prep_seconds=0, response_seconds=0,
                             instructions=("Choose what the word means in this "
                                           "sentence.")),
        )),
)

# The computed sitting length is the one shown; a practice advertised at five
# minutes that runs eight is the same lie as any other wrong estimate.
import dataclasses as _dataclasses
PRACTICE_BLUEPRINTS = tuple(
    _dataclasses.replace(b, estimated_minutes=duration_minutes(b))
    for b in PRACTICE_BLUEPRINTS
)

ALL_BLUEPRINTS: tuple[FormatBlueprint, ...] = (
    BLUEPRINTS + VENDOR_BLUEPRINTS + TEMPLATE_BLUEPRINTS)

ALL_BLUEPRINTS = ALL_BLUEPRINTS + PRACTICE_BLUEPRINTS
BY_CODE: dict[str, FormatBlueprint] = {b.code: b for b in ALL_BLUEPRINTS}


def companies() -> list[str]:
    """Every company with a seeded round, in the order they are offered."""
    seen: list[str] = []
    for b in BLUEPRINTS:
        if b.company and b.company not in seen:
            seen.append(b.company)
    return seen


ESTIMATED_SCALE_NOTE = (
    "This is our estimate of where you would sit on a test of this shape. It "
    "has not been compared against a real result from that test -- doing so "
    "needs the same people sitting both, which has not happened. The measures "
    "below are the reliable part; this number is for orientation."
)

UNANCHORED_NOTE = (
    "Shown as a band rather than a number on purpose. We have no data "
    "relating our measurements to this test's scale, so any number we printed "
    "under its name would be invented -- and stretching our range onto theirs "
    "would flatter you near the top. The band reflects the ordering we can "
    "defend; the measures below are the reliable part."
)

SUBSCORE_NOTE = (
    "Built the way this format builds them -- each sub-score comes only from "
    "the tasks that format counts towards it. The measures underneath are "
    "ours, and no number here has been checked against a real result from "
    "that test."
)


def presentation(code: str, overall: float | None,
                 dimensions: dict[str, float],
                 responses: list[dict] | None = None) -> dict | None:
    """Restate a result the way the format being imitated would report it.

    Presentation only. Every number here is a rearrangement of values the
    frozen pipeline already produced -- which tasks count towards which
    sub-score, and in what proportion, per ``app/evaluation.py``. Nothing here
    can move a measurement.

    Returns ``None`` where there is nothing honest to show: a format with no
    published scale, or an attempt that never got a composite.
    """
    blueprint = BY_CODE.get(code)
    if blueprint is None or blueprint.scale is None or overall is None:
        return None

    scale = blueprint.scale
    # None means the caller had no per-response detail to give, which is a
    # different thing from an attempt that scored nothing: the first falls
    # back to the coarse whole-attempt grouping, the second correctly reports
    # every sub-score as unsupported.
    model = (evaluation.evaluate(code, responses)
             if responses is not None else None)

    subscores: list[dict] = []
    missing: dict[str, str] = {}
    headline = overall
    structure_note = ""
    weights_published = False

    if model is not None:
        # The format's own bookkeeping: sub-scores drawn only from the tasks
        # that format counts, and an overall weighted its way.
        for sub in model.subscores:
            subscores.append({
                "label": sub.label,
                "score": scale.project(sub.value),
                "band": scale.band_for(sub.value),
                "means": sub.means,
                "from_tasks": list(sub.task_types),
                "from": list(sub.dimensions),
                "responses": sub.responses,
            })
        missing = dict(model.missing)
        structure_note = model.structure_source
        weights_published = model.weights_published
        if model.overall is not None:
            headline = model.overall
    else:
        # No model for this code -- an admin-authored profile on a vendor
        # style. Fall back to the blueprint's grouping over the whole attempt,
        # which is coarser and says so by carrying no task list.
        for sub in blueprint.subscores:
            values = [dimensions[d] for d in sub.from_dimensions
                      if d in dimensions]
            if not values:
                continue
            internal = sum(values) / len(values)
            subscores.append({
                "label": sub.label,
                "score": scale.project(internal),
                "band": scale.band_for(internal),
                "means": "",
                "from_tasks": [],
                "from": [d for d in sub.from_dimensions if d in dimensions],
                "responses": 0,
            })

    score = scale.project(headline)
    return {
        "score": score,
        "band": scale.band_for(headline),
        "scale_min": scale.minimum if score is not None else None,
        "scale_max": scale.maximum if score is not None else None,
        "subscores": subscores,
        # Sub-scores this attempt could not support. Shown, because a missing
        # Vocabulary changes what the overall means.
        "missing": missing,
        "estimated": True,
        "note": ESTIMATED_SCALE_NOTE if score is not None else UNANCHORED_NOTE,
        "subscore_note": SUBSCORE_NOTE if subscores else "",
        "structure_note": structure_note,
        "weights_published": weights_published,
    }


def verdict(style: str, score: float | None,
            bands: tuple[tuple[float, str, str], ...] = _BANDS) -> dict | None:
    """Phrase a composite as an outcome, for formats that report one.

    Returns ``None`` for anything that is not a company round, and for a score
    that was never composed -- an attempt too short to judge must not acquire a
    verdict on the way through the presentation layer.
    """
    if style != "company_round" or score is None:
        return None
    for threshold, label, detail in bands:
        if score >= threshold:
            return {"label": label, "detail": detail,
                    "estimated": True, "note": COMPANY_ROUND_NOTE}
    return None
