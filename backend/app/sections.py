"""Section results, and the four-skill rollup they make possible.

Two jobs, both above the frozen scoring path so no engine hash moves.

**Store what each section produced.** Section scores were recomputed from the
per-response rows on every read. That is fine until the scorer changes, at
which point a report a student was shown last month quietly becomes a
different report. Writing the number down is what makes a result
*reproducible* rather than merely recomputable, and it is what a re-mark can
be compared against.

**Roll sections up by skill.** An attempt with a speaking section and a
listening section has two skill scores, not one blended number over
dimensions that came from different kinds of task. Averaging a pronunciation
score with a listening-comprehension score produces a figure that describes
nothing.

The rules carried over from everywhere else in this codebase:

* a skill with no measured section is **absent**, never zero;
* an unmeasured thing says why;
* nothing here decides a score — the per-response dimensions are already
  final when this runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SCORER_VERSION = "1.0.0"

# Which skill each task type belongs to. Explicit rather than inferred: a new
# task type must be classified deliberately, because landing in the wrong
# skill silently corrupts a rollup and nothing would fail.
SKILL_OF_TASK: dict[str, str] = {
    # Speaking — the candidate talks and audio is scored.
    "read_aloud": "speaking",
    "repeat_sentence": "speaking",
    # Hear a gapped/flawed sentence, say the whole correct one aloud. The
    # spoken E/F sections of the researched company rounds -- speaking tasks
    # by design: producing the sentence is the assessment.
    "spoken_completion": "speaking",
    "spoken_correction": "speaking",
    "sentence_build": "speaking",
    "short_answer": "speaking",
    "story_retell": "speaking",
    "open_response": "speaking",
    "conversation_question": "speaking",
    "passage_question": "speaking",
    # Listening — the candidate answers about something heard.
    "listening_comprehension": "listening",
    "dictation": "listening",
    "response_selection": "listening",
    # Reading — text in, no speaking.
    "reading_comprehension": "reading",
    "vocabulary_in_context": "reading",
    # Vocabulary standalone questions (MCQ about word meaning).
    "vocabulary": "reading",
    # Grammar MCQ questions.
    "grammar": "reading",
    # Writing.
    "email": "writing",
    "email_writing": "writing",
    # Listening comprehension from audio passages.
    "audio_comprehension": "listening",
    "sentence_completion": "writing",
    "passage_reconstruction": "writing",
    # Timed typing: speed and accuracy on a given text.
    "typing": "writing",
    # Read word lists aloud (Cognizant Q11-15): isolated words, word-clarity scoring.
    "read_words": "speaking",
    # Grammar transformation, read and chosen (not composed), so it sits
    # under reading for the four-skill rollup; its grammar signal is carried
    # by DIMENSIONS_BY_TASK, which feeds the Grammar sub-score.
    "voice_change": "reading",
}

SKILLS = ("speaking", "listening", "reading", "writing")

# How the candidate answers. The runner dispatches on this, which is what
# lets one attempt lifecycle carry a speaking section and a listening section
# without a second engine.
#
#   speak   record audio, upload, ASR, align, score      (the frozen path)
#   select  choose from options after a stimulus         (listening, reading)
#   write   type into an editor                          (writing)
#
# Anything not listed records audio, because that is what every task type did
# before the other two modes existed.
RESPONSE_MODE: dict[str, str] = {
    "listening_comprehension": "select",
    "response_selection": "select",
    "reading_comprehension": "select",
    "vocabulary_in_context": "select",
    # Vocabulary and Grammar are MCQ - select from options.
    "vocabulary": "select",
    "grammar": "select",
    # Listening comprehension from audio - select from options.
    "audio_comprehension": "select",
    # Writing tasks.
    "email": "write",
    "dictation": "write",
    "email_writing": "write",
    "sentence_completion": "write",
    "passage_reconstruction": "write",
    "typing": "write",
    # A sentence and four rewrites, chosen — like vocabulary_in_context, no audio.
    "voice_change": "select",
    # Hear a gapped/flawed sentence, say the whole correct one aloud.
    "spoken_completion": "speak",
    "spoken_correction": "speak",
    # Read word lists aloud (Cognizant Q11-15): records audio like read_aloud.
    "read_words": "speak",
}


def mode_of(task_type: str) -> str:
    """How a candidate answers this task type."""
    return RESPONSE_MODE.get(task_type, "speak")


# Where a section's items come from.
#
# Deliberately separate from the response mode. The first version keyed the
# source off the mode -- spoken items from the task bank, everything else
# from the quiz bank -- which held right up until Dictation: it is answered by
# typing, and its material is the spoken-sentence bank. Two different
# questions had been collapsed into one.
#
#   ("task", task_type)      TaskItem rows of that type
#   ("quiz", category)       QuizItem rows of that category, whole passages
#   ("writing_prompt", kind) WritingPrompt rows; "" means any composing kind
ITEM_SOURCE: dict[str, tuple[str, str]] = {
    "listening_comprehension": ("quiz", "audio_comprehension"),
    # Its own category, not the comprehension bank. A comprehension question
    # asks what a passage said; this asks which reply fits, and every wrong
    # option is a correct English sentence. Sharing a category would let the
    # selector serve one as the other.
    "response_selection": ("quiz", "response_selection"),
    "reading_comprehension": ("quiz", "reading_comprehension"),
    # One word inside one sentence. Standalone, like sentence completion, and
    # for the same reason: there is no passage to have understood.
    "vocabulary_in_context": ("quiz", "vocabulary_in_context"),
    # Vocabulary questions (standalone, not passage-based)
    "vocabulary": ("quiz", "vocabulary"),
    # Grammar questions
    "grammar": ("quiz", "grammar"),
    # Speaking questions (short answer style)
    "speaking": ("quiz", "speaking"),
    # Heard once and typed back. The sentences are the Repeat Sentence bank:
    # same material, different channel, so the bank is shared rather than
    # duplicated and drifting.
    "dictation": ("task", "repeat_sentence"),
    # Writing tasks - draw from WritingPrompt bank
    "email": ("writing_prompt", "email"),
    "email_writing": ("writing_prompt", "email"),
    # One typed word into a gap. Its own quiz category rather than a writing
    # prompt: the item is a sentence with a hole, not a task to compose.
    "sentence_completion": ("quiz", "sentence_completion"),
    # Change a sentence between active and passive, choosing the correct
    # rewrite. Its own category: a grammar transformation, not a reply choice.
    "voice_change": ("quiz", "voice_change"),
    # Hear a gapped/flawed sentence, say the whole correct one aloud.
    # Uses the task bank (same as repeat_sentence for audio source).
    "spoken_completion": ("task", "spoken_completion"),
    "spoken_correction": ("task", "spoken_correction"),
    # Read a short passage, lose it, write it back. Same table as the other
    # writing tasks -- a passage with the ideas it contains written down is
    # exactly the shape WritingPrompt already stores -- but its own kind,
    # because it is not a task to compose and must never be served as one.
    "passage_reconstruction": ("writing_prompt", "reconstruction"),
    # Timed typing: copy a given text. Its own quiz category.
    "typing": ("quiz", "typing"),
    # Read word lists aloud (Cognizant Q11-15): uses the task bank like read_aloud.
    "read_words": ("task", "read_words"),
    # Listening comprehension - uses QuizItem bank
    "audio_comprehension": ("quiz", "audio_comprehension"),
    # Open response / speaking tasks - draw from TaskItem
    "open_response": ("task", "open_response"),
}

# WritingPrompt kinds that ask the candidate to compose something new.
#
# The writing selector took every published prompt, which was correct while
# every prompt was a composition task. A reconstruction passage lives in the
# same table and is not one: served to an Email Writing section it would ask a
# candidate to compose a reply to a passage about printer maintenance, and
# served the other way an email prompt would be flashed for twenty seconds and
# taken away. A new kind must be classified here deliberately -- the same rule
# as a new task type and the maps above.
COMPOSING_KINDS = frozenset({"email", "report", "essay", "summary", "complaint"})

# Read for a fixed time, then taken away. The seconds are per item, not per
# section: forty words and sixty words do not need the same clock.
RECONSTRUCTION_KIND = "reconstruction"


def prompt_kinds_for(key: str) -> frozenset[str]:
    """Which WritingPrompt kinds a section may draw on."""
    return frozenset({key}) if key else COMPOSING_KINDS


def source_of(task_type: str) -> tuple[str, str]:
    """Which bank a section's items come from, and the key within it."""
    return ITEM_SOURCE.get(task_type, ("task", task_type))


# Quiz categories whose items must be drawn a whole passage at a time.
#
# Comprehension is measured over a passage, so four questions about one
# announcement is one listening event and half a passage is a worse measure
# than one passage fewer. That is true of comprehension and of nothing else.
#
# Sentence completion is standalone: eighteen separate gaps, each meaningful
# on its own. Treating it as grouped -- which is what happened, because every
# item shares an empty passage id -- made the selector see one indivisible
# block of eighteen and conclude it could serve none of a four-item section.
PASSAGE_GROUPED = frozenset({"audio_comprehension", "reading_comprehension"})


def groups_by_passage(category: str) -> bool:
    """Whether this quiz category is drawn whole passages at a time."""
    return category in PASSAGE_GROUPED


# Task types whose *played* audio is the reference answer rather than the
# visible prompt.
#
# Read Aloud shows its sentence and plays nothing. Repeat Sentence plays the
# sentence the candidate must reproduce. Dictation plays the sentence they
# must type -- it borrows the Repeat Sentence bank, where the words live in
# `reference_text` and `prompt_text` is empty, so a task type missing from
# this set is served silence.
#
# Here rather than in the router because it is a property of the task type,
# and the router already learned that lesson twice today with the item source
# and the publish guard.
#
# Conversation Question and Passage Question join it for the same mechanical
# reason -- their exchange and question live in `reference_text` -- and it is
# worth saying why that is safe. Membership here decides only what is
# *played*. What is *scored against* the reference is decided separately, by
# the accuracy provider's own SCRIPTED_TASKS, and neither of these is in it:
# the reference is the question, and scoring an answer for word-accuracy
# against the question it answers would be a number about nothing. Story
# Retell already relies on that separation.
SPEAKS_REFERENCE = frozenset({"repeat_sentence", "story_retell", "dictation",
                              "conversation_question", "passage_question"})


def speaks_reference(task_type: str) -> bool:
    """Whether the played prompt is the reference text, not the prompt text."""
    return task_type in SPEAKS_REFERENCE


def skill_of(task_type: str) -> str:
    """The skill a task type belongs to.

    Unknown types fall back to speaking, which is what every task type was
    before the other three existed — but the caller should classify it in
    SKILL_OF_TASK rather than rely on this.
    """
    return SKILL_OF_TASK.get(task_type, "speaking")


@dataclass
class SectionScore:
    section_id: str
    position: int
    title: str
    task_type: str
    skill: str
    score: float | None
    dimensions: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None
    weight: float = 1.0
    items_total: int = 0
    items_answered: int = 0
    unscored_reason: str = ""


@dataclass
class SkillScore:
    skill: str
    score: float | None
    section_count: int
    # Sections that contributed nothing, named so the gap is visible.
    unscored_sections: list[str] = field(default_factory=list)
    note: str = ""


def score_section(*, section_id: str, position: int, title: str,
                  task_type: str, responses: list[dict],
                  weight: float = 1.0) -> SectionScore:
    """Turn a section's per-response scores into one section result.

    ``responses`` is a list of ``{"scores": {dimension: value}, "skipped":
    bool}`` — exactly what the result endpoint already builds. The section
    score is the mean of the per-response means, so a section with one
    richly-scored response and one thinly-scored one is not dominated by
    whichever happened to produce more dimensions.
    """
    answered = [r for r in responses if not r.get("skipped")]
    scored = [r for r in answered if r.get("scores")]

    pooled: dict[str, list[float]] = {}
    for row in scored:
        for dimension, value in (row.get("scores") or {}).items():
            pooled.setdefault(dimension, []).append(float(value))
    dimensions = {d: round(sum(v) / len(v), 1) for d, v in pooled.items() if v}

    score: float | None = None
    reason = ""
    if not answered:
        reason = "No answers were given in this section."
    elif not scored:
        reason = ("Answers were given but nothing could be scored. The "
                  "recordings are stored.")
    else:
        per_response = [sum(r["scores"].values()) / len(r["scores"])
                        for r in scored if r.get("scores")]
        if per_response:
            score = round(sum(per_response) / len(per_response), 1)

    return SectionScore(
        section_id=section_id, position=position, title=title,
        task_type=task_type, skill=skill_of(task_type),
        score=score, dimensions=dimensions,
        # Confidence is how much of the section actually scored. A section
        # where one of six responses produced anything is not a firm reading.
        confidence=(round(len(scored) / len(answered), 2) if answered else None),
        weight=weight, items_total=len(responses), items_answered=len(answered),
        unscored_reason=reason,
    )


def roll_up(sections: list[SectionScore]) -> dict[str, SkillScore]:
    """One score per skill, weighted within the skill.

    Only skills with at least one scored section appear. A four-skill report
    that shows Writing as zero because the assessment contained no writing is
    describing a candidate who failed something they were never asked to do.
    """
    out: dict[str, SkillScore] = {}

    for skill in SKILLS:
        mine = [s for s in sections if s.skill == skill]
        if not mine:
            continue

        scored = [s for s in mine if s.score is not None]
        unscored = [s.title for s in mine if s.score is None]

        score: float | None = None
        if scored:
            total_weight = sum(max(0.0, s.weight) for s in scored) or float(len(scored))
            if any(s.weight > 0 for s in scored):
                score = round(
                    sum(s.score * max(0.0, s.weight) for s in scored) / total_weight, 1)
            else:
                score = round(sum(s.score for s in scored) / len(scored), 1)

        note = ""
        if unscored and scored:
            note = (f"{len(unscored)} of {len(mine)} sections could not be "
                    f"scored, so this is based on the rest.")
        elif unscored:
            note = "Nothing in this skill could be scored."

        out[skill] = SkillScore(skill=skill, score=score, section_count=len(mine),
                                unscored_sections=unscored, note=note)

    return out


# --------------------------------------------------------------------------
# Whole-passage selection
# --------------------------------------------------------------------------

def fill_from_passages(sizes: dict[str, int], target: int) -> list[str]:
    """Choose whole passages that come as close to ``target`` as possible.

    Comprehension is measured over a whole passage, so questions are taken
    passage by passage: four questions about one announcement is one listening
    event, and half a passage is a worse measure than one passage fewer.

    The obvious implementation -- walk the shuffled passages and take each one
    that still fits -- is wrong in a way that hides. Given passages of two and
    three questions and a section asking for three, drawing the two first
    leaves no room for a three, so the candidate gets two questions when three
    were available. It only misfires when the small passage happens to come
    first, which made it roughly a one-in-six failure and invisible to a test
    that ran the path once.

    So: search for a combination that reaches the target, and settle for the
    best under it only when nothing reaches it. Caller shuffles first; ties
    are broken by that order, so a retake is not the identical test.
    """
    order = list(sizes)
    best: list[str] = []
    best_total = 0

    def search(index: int, picked: list[str], total: int) -> bool:
        """Returns True once an exact fill is found, to stop the search."""
        nonlocal best, best_total
        if total > target:
            return False
        if total > best_total:
            best, best_total = list(picked), total
        if total == target:
            return True
        for n in range(index, len(order)):
            picked.append(order[n])
            if search(n + 1, picked, total + sizes[order[n]]):
                return True
            picked.pop()
        return False

    search(0, [], 0)
    return best
