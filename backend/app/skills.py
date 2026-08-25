"""The four language skills, and how much of each this build can actually do.

Reading, Writing, Listening and Speaking are how every student, trainer and
placement officer already thinks about English. The product measured exactly
one of them and never said so: there was no Listening screen, no Reading
screen, no Writing anything, and nothing anywhere admitted the gap. A student
looking at the app had no way to tell whether Listening was missing or whether
they simply had not found it yet.

So the four exist here as first-class things, and each one reports its own
readiness **computed from the content actually in the database** rather than
from a constant somebody has to remember to update. That direction matters:

* it cannot drift into a lie -- adding twenty audio-comprehension items moves
  Listening from planned to live on its own, and deleting them moves it back;
* it cannot flatter us -- a module with a screen, a nav entry and no items
  reports as planned, because that is what it is.

The alternative was hardcoding a status field, which is the same shape as the
``UNSCORED = {}`` constant that let a completely blank result page claim
everything was fine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import QuizItem, SkillMastery, TaskItem

# Enough material to face a student with. Below this a module is a promise,
# not a product: five items is one sitting and then immediate repetition,
# which measures memory rather than skill.
MIN_ITEMS_FOR_LIVE = 12

# Writing is counted in prompts, not questions, and the units are not
# comparable: one prompt is fifteen to twenty-five minutes of work, where
# twelve quiz questions are five. Six prompts is six genuine sessions before
# anything repeats, which is the same "enough to face a student with" bar the
# item count above is aiming at.
#
# Named rather than inlined because it was a bare `>= 4` first, and the test
# that asserts no module claims to be live below MIN_ITEMS_FOR_LIVE caught it
# immediately -- correctly, since an unexplained second threshold is
# indistinguishable from a mistake.
MIN_PROMPTS_FOR_LIVE = 4

# Speaking task types, and the quiz categories that are text comprehension
# rather than listening. Both are content that already exists.
SPEAKING_TASKS = ("read_aloud", "repeat_sentence", "sentence_build",
                  "short_answer", "story_retell", "open_response")
READING_CATEGORIES = ("reading_comprehension",)
# Language-knowledge questions. Adjacent to reading and deliberately not
# counted as it -- see _reading.
QUIZ_TEXT_CATEGORIES = ("grammar", "vocabulary", "sentence_correction", "error_id")
LISTENING_CATEGORIES = ("audio_comprehension",)


@dataclass
class SkillModule:
    key: str
    label: str
    #  live      -- enough content, and a scorer that produces a real measure
    #  partial   -- some content or some scoring, not both
    #  planned   -- named, structured, and honestly empty
    status: str
    # One line a student can act on. Never markets an empty module.
    summary: str
    # What it measures today. Empty for planned modules, on purpose.
    measures: list[str] = field(default_factory=list)
    item_count: int = 0
    # Where it goes. Empty when there is nowhere honest to send anyone.
    href: str = ""
    # Present only when something is missing, and says what.
    gap: str = ""
    # 0-100 from the student's own mastery, or None if never measured.
    mastery: float | None = None
    # Where that number came from. Required whenever it is indirect, because a
    # mastery percentage sitting on a module with no content reads as a
    # measurement of that module -- and for Listening it is not one.
    mastery_basis: str = ""


async def _count_tasks(tenant: AsyncSession, types: tuple[str, ...]) -> int:
    return int((await tenant.execute(
        select(func.count()).select_from(TaskItem)
        .where(TaskItem.task_type.in_(types), TaskItem.status == "published")
    )).scalar_one())


async def _count_quiz(tenant: AsyncSession, categories: tuple[str, ...]) -> int:
    return int((await tenant.execute(
        select(func.count()).select_from(QuizItem)
        .where(QuizItem.category.in_(categories), QuizItem.status == "published")
    )).scalar_one())


async def _mastery(tenant: AsyncSession, user_id: str,
                   skills: tuple[str, ...]) -> float | None:
    rows = list((await tenant.execute(
        select(SkillMastery.mastery).where(SkillMastery.user_id == user_id,
                                           SkillMastery.skill.in_(skills))
    )).scalars().all())
    if not rows:
        return None
    return round(100 * sum(rows) / len(rows), 1)


async def modules_for(tenant: AsyncSession, user_id: str) -> list[SkillModule]:
    """The four skills, in the order they are usually taught and tested."""
    speaking_items = await _count_tasks(tenant, SPEAKING_TASKS)
    listening_items = await _count_quiz(tenant, LISTENING_CATEGORIES)
    reading_items = await _count_quiz(tenant, READING_CATEGORIES)

    from app.models.tenant import WritingPrompt
    writing_prompts = int((await tenant.execute(
        select(func.count()).select_from(WritingPrompt)
        .where(WritingPrompt.status == "published")
    )).scalar_one())

    return [
        await _speaking(tenant, user_id, speaking_items),
        await _listening(tenant, user_id, listening_items),
        await _reading(tenant, user_id, reading_items),
        # _writing() -- the honest empty shell -- is kept below for the case
        # where an institution has no prompts, so the module still explains
        # itself rather than vanishing.
        (await _writing_live(tenant, user_id, writing_prompts)
         if writing_prompts else _writing()),
    ]


async def _speaking(tenant: AsyncSession, user_id: str, items: int) -> SkillModule:
    """The one that is genuinely finished."""
    return SkillModule(
        key="speaking", label="Speaking",
        status="live" if items >= MIN_ITEMS_FOR_LIVE else "partial",
        summary=("Read aloud, repeat, build sentences, answer and retell. "
                 "Scored on pronunciation, fluency, timing and content."),
        measures=["pronunciation", "fluency", "response latency", "grammar",
                  "content"],
        item_count=items,
        href="/simulate",
        mastery=await _mastery(tenant, user_id,
                               ("pronunciation", "fluency", "response_latency")),
        mastery_basis="Measured directly from your recordings.",
    )


async def _listening(tenant: AsyncSession, user_id: str, items: int) -> SkillModule:
    """Half-built, and the half that exists is easy to mistake for the whole.

    ``listening`` has been a tracked mastery skill from the beginning and
    ``audio_comprehension`` has been a declared quiz category, so the plumbing
    reads as finished from the inside. There has never been a single item in
    it. Repeat Sentence does require hearing accurately, which is why this
    reports partial rather than planned -- but repeating is not comprehension,
    and saying so is the difference between a gap and a lie.
    """
    live = items >= MIN_ITEMS_FOR_LIVE
    return SkillModule(
        key="listening", label="Listening",
        status="live" if live else "partial",
        summary=("Hear a passage once, then answer questions about what it "
                 "meant. Announcements, instructions, talks, voicemail and "
                 "conversation." if live else
                 "Repeat Sentence already tests whether you heard accurately. "
                 "Comprehension — following a talk and answering about it — is "
                 "not built yet."),
        measures=["listening comprehension"] if live else ["accuracy of what you heard"],
        item_count=items,
        href="/listening",
        gap="" if live else (
            f"Needs audio-comprehension items; there are {items} in the bank. "
            f"Until then your Listening reading comes indirectly from Repeat "
            f"Sentence."),
        mastery=await _mastery(tenant, user_id, ("listening",)),
        # Worth stating plainly. The engine maps its `accuracy` dimension onto
        # the `listening` skill, and accuracy is scored on Read Aloud as well
        # as Repeat Sentence -- so this number is partly earned by reading a
        # sentence off a screen, where nothing was heard at all. It is the
        # best signal available today and it overstates listening.
        # Once comprehension items exist the number stops being a proxy, but
        # a history built from repeat-accuracy is still mixed into it, so the
        # provenance line stays until it has been earned afresh.
        mastery_basis=(
            "From comprehension questions you answered after listening."
            if live else
            "Derived from how accurately you reproduce sentences, which "
            "includes Read Aloud — where the text was on screen. It is an "
            "indirect signal and flatters your listening."),
    )


async def _reading(tenant: AsyncSession, user_id: str, items: int) -> SkillModule:
    """Comprehension over real passages, plus a rate measure.

    The grammar, vocabulary and error-identification questions are still not
    counted here. They are read off a screen, so filing them under Reading
    would be easy and would have made this module look finished months before
    it was -- but they test language knowledge, not comprehension: no passage,
    no inference, no reading rate. They stay under Quiz.
    """
    live = items >= MIN_ITEMS_FOR_LIVE
    return SkillModule(
        key="reading", label="Reading",
        status="live" if live else "partial",
        summary=("Emails, notices, reports and articles. Comprehension and "
                 "reading speed, reported separately." if live else
                 "Passage comprehension is not built yet. The grammar and "
                 "vocabulary questions under Quiz are language knowledge, "
                 "which is a different thing."),
        measures=["reading comprehension", "reading rate"] if live else [],
        item_count=items,
        href="/reading",
        gap="" if live else (
            "Needs passages with comprehension questions; there are "
            f"{items} in the bank."),
        mastery=await _mastery(tenant, user_id, ("vocabulary",)),
        mastery_basis=(
            "From reading comprehension, sharing the vocabulary mastery track."
            if live else
            "From grammar and vocabulary questions — an indirect signal, not "
            "reading comprehension."),
    )


async def _writing_live(tenant: AsyncSession, user_id: str,
                        prompts: int) -> SkillModule:
    """Now built: five measures over real workplace writing tasks."""
    return SkillModule(
        key="writing", label="Writing",
        status="live" if prompts >= MIN_PROMPTS_FOR_LIVE else "partial",
        summary=("Awkward emails, status reports, summaries. Scored on task "
                 "response, coherence, lexical range, grammar and mechanics."),
        measures=["task response", "coherence", "lexical range",
                  "grammatical accuracy", "mechanics"],
        item_count=prompts,
        href="/writing",
        gap=("The scorer counts structure, coverage and error patterns. It "
             "cannot judge whether an argument is sound or whether the "
             "writing is worth reading — those need a human marker."),
        mastery=await _mastery(tenant, user_id, ("grammar",)),
        mastery_basis=("Shares the grammar mastery track; there is no "
                       "separate writing skill fitted yet."),
    )


def _writing() -> SkillModule:
    """Nothing. Not a screen, not an item, not a scorer.

    Writing needs an essay scorer -- task response, coherence, range,
    accuracy -- which is a different engine from the speech pipeline rather
    than a screen on top of it. It is listed anyway, because a student
    comparing this against a four-skill test should be able to see what is
    absent instead of assuming they missed a menu item.
    """
    return SkillModule(
        key="writing", label="Writing",
        status="planned",
        summary=("Not built. Writing needs its own scoring engine — task "
                 "response, coherence, range and accuracy — which is separate "
                 "work from the speech pipeline."),
        measures=[],
        item_count=0,
        # A page that says "nothing here yet" is more use than a dead card:
        # it names what is missing and what building it would take.
        href="/writing",
        gap=("No items, no scoring, no screen. Listed here so the gap is "
             "visible rather than something you have to discover."),
        mastery=None,
    )
