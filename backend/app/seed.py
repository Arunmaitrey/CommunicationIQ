"""Create the schema and a working demo estate.

Run with ``python -m app.seed`` (add ``--reset`` to drop and rebuild).

Two institutions are seeded, not one. A single tenant makes isolation look
fine no matter what the code does; two make the cross-tenant tests meaningful
and let anyone check by hand that St Mary's cannot see Vignan's students.

All content here is original. Profiles imitate the *format* of Versant-,
SVAR- and SpeechX-style tests — section order, timing, one-shot audio — and
never their items (CONTENT-04).
"""
from __future__ import annotations

import argparse
import asyncio
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import selectinload

from app.db import (PlatformBase, control_db, init_store,
                    platform_sessionmaker, tenant_sessionmaker)
from app.models.platform import (AuditLog, GamificationConfig, Plan,
                                 PlatformUser, ProviderConfig,
                                 ProviderRegistry, Subscription, Tenant,
                                 TenantUserDirectory)
from app.models.tenant import (Attempt, Cohort, CohortMember, ConsentRecord,
                               ListeningPassage, ReadingPassage,
                               WritingPrompt,
                               MistakeBankEntry, ProfileSection, Quest, QuizItem,
                               Response, ScoreRecord, SimulationProfile,
                               SkillMastery, StreakState, StudentFlag, TaskItem,
                               User, XPLedger)
from app import formats
from app.listening_bank import PASSAGES as LISTENING_PASSAGES
from app.listening_bank import rotated as _rotate_options
from app.reading_bank import PASSAGES as READING_PASSAGES
from app.writing_bank import PROMPTS as WRITING_PROMPTS
from app.completion_bank import ITEMS as COMPLETION_ITEMS
from app import grammar_bank
from app.voice_change_bank import ITEMS as VOICE_CHANGE_ITEMS
from app.spoken_question_bank import ITEMS as SPOKEN_QUESTIONS
from app.spoken_grammar_bank import (COMPLETIONS as SPOKEN_COMPLETIONS,
                                     CORRECTIONS as SPOKEN_CORRECTIONS,
                                     WORD_LIST_DIFFICULTY, WORD_LISTS)
from app.selection_bank import RESPONSES as RESPONSE_ITEMS
from app.selection_bank import VOCABULARY as VOCABULARY_ITEMS
from app.reconstruction_bank import PASSAGES as RECONSTRUCTIONS
from app.industry_bank import READ_ALOUD as INDUSTRY_READ_ALOUD
from app.industry_bank import SHORT_ANSWERS as INDUSTRY_SHORT_ANSWERS
from app.reading_bank import word_count as _word_count
from app.provisioning import (create_tenant_schema, drop_tenant_schema,
                             upgrade_tenant_schema)
from app.security import hash_password

DEMO_PASSWORD = "Password123!"
RNG = random.Random(20260817)

SKILLS = ["pronunciation", "fluency", "grammar", "vocabulary", "response_latency",
          "listening", "content_recall"]


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------

# The bank has to be deeper than the longest simulation, or a student who
# retakes gets the identical test back and the second score measures memory.
# A Versant-style attempt draws eight read-aloud sentences; twenty-four means
# three genuinely different sittings before anything repeats.
READ_ALOUD = [
    # Short and plain.
    "The training session begins at nine in the morning.",
    "Please submit your report before the end of the week.",
    "She explained the problem clearly to the whole team.",
    "Our office is located near the railway station.",
    "He asked three questions during the interview.",
    "The results will be announced on Friday afternoon.",
    "We should confirm the schedule with the client first.",
    "This project requires careful planning and steady effort.",
    # Medium: subordinate clauses, longer noun phrases.
    "The company announced that the new office would open in October.",
    "Before you send the file, please check the version number twice.",
    "Our supervisor suggested a shorter deadline for the second phase.",
    "The workshop covered communication, teamwork and time management.",
    "She has been working on the same module since the middle of March.",
    "Everyone in the department received the updated guidelines yesterday.",
    "The candidate arrived early and waited quietly in the reception area.",
    "We could not complete the testing because the server was unavailable.",
    # Longer, with consonant clusters and unstressed syllables that are the
    # usual trouble spots -- these are what a pronunciation measure is for.
    "The technical documentation should describe every configuration clearly.",
    "Our recruitment strategy depends on strengthening the campus partnerships.",
    "Approximately thirty applicants were shortlisted for the final discussion.",
    "The infrastructure team scheduled the maintenance for the twelfth of April.",
    "She acknowledged the difficulty but insisted the deadline was achievable.",
    "Successful collaboration requires patience, clarity and a little humility.",
    "The organisation published its quarterly results earlier than expected.",
    "Consistent practice over several weeks produces a measurable improvement.",
]


# Genuine paragraph-length read-aloud items for the SVAR Section A2. Seeded at
# a high difficulty so the section's pool filter (difficulty_min) draws these
# and only these, while Section A1 (difficulty_max) draws only the sentences
# above. Three to four sentences each — a realistic thirty-second read.
READ_ALOUD_PARAGRAPHS = [
    ("Our team spent the last quarter rebuilding the reporting system from the "
     "ground up. The old version was slow and hard to maintain, and a small "
     "change in one place often broke something in another. The new design "
     "separates the data from the display, so each part can be tested on its "
     "own, and the finance team has already found the reports easier to read."),
    ("Clear communication at work is not about long words or complicated "
     "sentences. It is about being brief and making sure the other person "
     "actually understands what you mean. Before you send an email, read it "
     "once more and ask yourself whether a busy reader would know exactly what "
     "to do next."),
    ("For many people, a support call is their first real experience of a "
     "company. A single patient, well-handled conversation can turn a "
     "frustrated customer into a loyal one. The trick is to listen fully "
     "before you respond, to explain the next steps in plain language, and to "
     "follow up when you say you will."),
]
# Repeat Sentence is a working-memory test as much as a speaking one, so the
# bank is graded by length: roughly eight words at the easy end and sixteen at
# the hard end, which is the span the real formats cover.
REPEAT_SENTENCE = [
    # ~8 words.
    "The meeting was postponed to next Tuesday.",
    "I need to finish this assignment before lunch.",
    "Our team decided to review the design once more.",
    "She left the office before the rain started.",
    "The bus to the campus leaves every twenty minutes.",
    "He forgot to attach the file to the email.",
    "Most of the students completed the exercise on time.",
    "The library stays open until eight on weekdays.",
    # ~12 words.
    "The new software update improved the response time across every module.",
    "They travelled by train because the flight had been cancelled that morning.",
    "The manager appreciated the effort of the whole department this quarter.",
    "We agreed to postpone the review until the client had responded.",
    "Regular practice over several weeks makes a noticeable difference in fluency.",
    "The report was returned because two of the figures did not match.",
    "Please confirm whether the training room will be available on Thursday.",
    "Nobody expected the second interview to last more than an hour.",
    # ~16 words, the hard end.
    "The committee decided that the revised proposal should be circulated before the end of the month.",
    "Although the deadline was extended by a week, most of the team finished the work early.",
    "She explained that the delay had been caused by a shortage of testing equipment.",
    "The new joiners were asked to complete the orientation modules before their first project meeting.",
    "Our supervisor mentioned that the schedule might change once the client confirms the requirements.",
    "If the results are published on Friday, we will have two days to prepare the response.",
    "The department has been collecting feedback from students since the beginning of the academic year.",
    "He argued that clear writing matters more than technical vocabulary in a client report.",
]

OPEN_RESPONSE = [
    "Describe a skill you would like to improve this year, and why.",
    "Talk about a time you solved a problem with a group.",
    "What would you change about the way your course is taught?",
    "Describe something you built or fixed, and what went wrong first.",
    "Is it better to be good at one thing or passable at many? Say why.",
    "Talk about a person whose work you would like to do one day.",
    "Should companies hire for skill or for attitude? Take a side.",
    "Describe the hardest thing you have had to explain to someone.",
    # The one topic the reference walkthrough shows, with its three
    # speaking-point questions exactly as displayed (observed third-party
    # walkthrough evidence, Section B, 1/3).
    "The Importance of Healthy Eating.",
]

# Speaking points under each topic, "in the form of questions" -- the shape
# the reference shows. They are suggestions the candidate may ignore, and are
# never scored against: they sit in the rubric as `cues`, not `key_points`.
# Only the Healthy Eating set is the reference's wording; the rest are ours.
TOPIC_CUES: dict[str, list[str]] = {
    "Describe a skill you would like to improve this year, and why.": [
        "Which skill is it, and where do you use it?",
        "What makes it hard for you right now?",
        "How will you practise it, and how will you know you have improved?",
    ],
    "Talk about a time you solved a problem with a group.": [
        "What was the problem, and who was in the group?",
        "What did you personally contribute?",
        "What would you do differently next time?",
    ],
    "What would you change about the way your course is taught?": [
        "What works well in your course today?",
        "What is the one change you would make first?",
        "How would that change help students like you?",
    ],
    "Describe something you built or fixed, and what went wrong first.": [
        "What did you build or fix, and why?",
        "What went wrong the first time?",
        "How did you find the cause and solve it?",
    ],
    "Is it better to be good at one thing or passable at many? Say why.": [
        "Which side do you take?",
        "Can you give an example from your own studies or work?",
        "When might the other side be right?",
    ],
    "Talk about a person whose work you would like to do one day.": [
        "Who is the person, and what do they do?",
        "What attracts you to that work?",
        "What would you need to learn to get there?",
    ],
    "Should companies hire for skill or for attitude? Take a side.": [
        "Which matters more to you, and why?",
        "Can you think of an example where one made the difference?",
        "How can a company judge attitude in an interview?",
    ],
    "Describe the hardest thing you have had to explain to someone.": [
        "What were you explaining, and to whom?",
        "Why was it difficult?",
        "What finally made it clear to them?",
    ],
    "The Importance of Healthy Eating.": [
        "Why is maintaining a healthy diet important?",
        "How do you incorporate healthy eating into your lifestyle?",
        "Can you share any personal experiences related to healthy eating?",
    ],
}


# Short Answer: a direct question with a one- or two-word answer. Scored on
# whether the answer came back, not on how many words matched — several
# phrasings are right, and the accepted set is the rubric.
SHORT_ANSWERS = [
    ("What do you use to unlock a door?", ["key"]),
    ("What season comes after summer?", ["monsoon", "autumn", "rainy", "fall"]),
    ("Where would you go to borrow a book?", ["library"]),
    ("What do you call the person who treats patients?", ["doctor", "physician"]),
    ("How many days are there in a fortnight?", ["fourteen", "14"]),
    ("What do you check before boarding a train?", ["ticket", "platform", "timing"]),
    ("What do you wear on your feet before going outside?",
     ["shoes", "sandals", "slippers", "chappals", "footwear"]),
    ("What do you call the meal you eat in the morning?", ["breakfast"]),
    ("Which part of the body do you use to hear?", ["ear", "ears"]),
    ("What do you use to write on a whiteboard?", ["marker", "pen"]),
    ("How many months are there in a year?", ["twelve", "12"]),
    ("Where do you go to catch a flight?", ["airport"]),
    ("What do you call water falling from the sky?", ["rain", "rainfall"]),
    ("Who teaches students in a college?",
     ["teacher", "professor", "lecturer", "faculty"]),
    ("What do you call the first day of the working week?", ["monday"]),
    ("What do you use to cut paper?", ["scissors", "scissor", "blade", "cutter"]),
    ("What do you call the place where you withdraw money?", ["bank", "atm"]),
    ("Which meal do you eat in the middle of the day?", ["lunch"]),
]

# Sentence Build: word groups in the wrong order, spoken back as one sentence.
# The prompt is what the student sees; the reference is the correct ordering.
SENTENCE_BUILDS = [
    ("the report / before Friday / must be submitted",
     "The report must be submitted before Friday."),
    ("asked me / the manager / to join the call",
     "The manager asked me to join the call."),
    ("very carefully / she explained / the process",
     "She explained the process very carefully."),
    ("in the morning / the training / begins at nine",
     "The training begins at nine in the morning."),
    ("we decided / after the meeting / to revise the plan",
     "After the meeting we decided to revise the plan."),
    ("the client / by email / confirmed the schedule",
     "The client confirmed the schedule by email."),
    ("the interview / was rescheduled / to Monday morning",
     "The interview was rescheduled to Monday morning."),
    ("without checking / he sent the file / the version number",
     "He sent the file without checking the version number."),
    ("every candidate / a short presentation / was asked to give",
     "Every candidate was asked to give a short presentation."),
    ("the department / new guidelines / published last week",
     "The department published new guidelines last week."),
    ("before the deadline / the team / completed the testing",
     "The team completed the testing before the deadline."),
    ("politely / she declined / the second offer",
     "She declined the second offer politely."),
    ("on the noticeboard / the results / will be displayed",
     "The results will be displayed on the noticeboard."),
    ("because of the rain / was delayed / the morning session",
     "The morning session was delayed because of the rain."),
    ("a detailed answer / the interviewer / expected",
     "The interviewer expected a detailed answer."),
    ("to the whole class / the concept / he explained",
     "He explained the concept to the whole class."),
]

# Story Retell: a short narrative heard once, retold in the student's own
# words. The key points are the rubric — coverage is measured against what a
# human author decided mattered, never against a model's opinion.
RETELL_STORIES = [
    ("A small bakery in Vijayawada was losing customers because the queue at the "
     "counter was too slow. The owner, Meera, noticed that most people were "
     "buying the same three items. She put those items in pre-packed boxes near "
     "the door and added a second billing counter. Within a month the queue had "
     "halved and her sales had gone up by a fifth.",
     ["a bakery was losing customers", "the queue was slow",
      "most people bought the same three items",
      "she pre-packed those items near the door",
      "she added a second billing counter",
      "the queue halved and sales rose"]),
    ("Arun joined a software company after finishing his degree. In his first "
     "week he found a mistake in an old report, but he was afraid to mention it "
     "because he was new. After two days he told his manager anyway. The manager "
     "thanked him, fixed the report before it reached the client, and asked Arun "
     "to review the next one himself.",
     ["Arun joined a company after his degree",
      "he found a mistake in an old report",
      "he was afraid to speak because he was new",
      "he told his manager after two days",
      "the manager thanked him and fixed it",
      "Arun was asked to review the next report"]),
    ("A college in Guntur ran a placement drive every February. One year the "
     "training officer noticed that students who practised speaking in pairs "
     "did better than those who only read notes. She made pair practice "
     "compulsory for twenty minutes a day. The next year the number of "
     "students clearing the communication round rose from forty to sixty-five.",
     ["a college ran a placement drive every February",
      "students who practised in pairs did better",
      "those who only read notes did worse",
      "she made pair practice compulsory",
      "twenty minutes a day",
      "students clearing the round rose from forty to sixty-five"]),
    ("Ravi was asked to present his project to a visiting client. He prepared "
     "forty slides and rehearsed for three hours. On the day, the client asked "
     "him to explain the whole thing in five minutes. Ravi closed the laptop "
     "and described the problem, the fix and the result. The client said it "
     "was the clearest explanation he had heard that week.",
     ["Ravi presented his project to a visiting client",
      "he prepared forty slides and rehearsed",
      "the client asked for five minutes only",
      "he closed the laptop",
      "he described the problem, the fix and the result",
      "the client said it was the clearest explanation"]),
    ("A hostel warden in Warangal kept receiving complaints about the water "
     "supply. Instead of replying to each one, he put a whiteboard near the "
     "entrance showing when the pumps would run. Complaints dropped almost "
     "immediately, even though the water timings had not changed at all. What "
     "students had wanted was to know, not to have more water.",
     ["a hostel warden received complaints about water",
      "he put a whiteboard near the entrance",
      "it showed when the pumps would run",
      "complaints dropped almost immediately",
      "the timings had not changed",
      "students wanted information rather than more water"]),
    ("Priya took a communication test in her third year and scored poorly on "
     "fluency. Rather than practise more English, she recorded herself "
     "answering one question every evening and listened back. She found she "
     "was pausing before every long word. She began choosing shorter words on "
     "purpose, and by the next test her fluency score had risen sharply.",
     ["Priya scored poorly on fluency",
      "she recorded herself answering a question every evening",
      "she listened back to the recordings",
      "she found she paused before long words",
      "she began choosing shorter words",
      "her fluency score rose by the next test"]),
]

# Quiz items. Original content in the SVAR Sections 4-5 / SpeechX Section C
# *style* — grammar, error identification and word choice — never their items.
# Written around the mistakes this population actually makes: article use,
# subject-verb agreement with collective nouns, preposition choice, and the
# present-perfect/past-simple boundary.
QUIZ_ITEMS = [
    ("grammar", "She ____ in Hyderabad since 2019.",
     ["is living", "has been living", "lives", "was living"], 1,
     "A state continuing from a past point to now takes the present perfect "
     "continuous. 'Since 2019' fixes the start; 'lives' would need a plain present."),
    ("grammar", "The team ____ its report yesterday.",
     ["submit", "submits", "submitted", "have submitted"], 2,
     "'Yesterday' fixes the action in finished past time, so the past simple. "
     "'Have submitted' cannot sit with a finished time expression."),
    ("grammar", "If I ____ the deadline, I would have asked for help.",
     ["knew", "had known", "would know", "know"], 1,
     "A regret about the past: third conditional, so 'had known' in the if-clause."),
    ("grammar", "Neither of the candidates ____ available on Monday.",
     ["are", "is", "were", "have been"], 1,
     "'Neither of' takes a singular verb — the subject is 'neither', not 'candidates'."),
    ("grammar", "He asked me where ____ .",
     ["was I going", "I was going", "am I going", "I am going"], 1,
     "Reported questions take statement word order: subject then verb."),
    ("grammar", "By the time the results came out, we ____ for three weeks.",
     ["waited", "were waiting", "had been waiting", "have waited"], 2,
     "A duration finishing at a past point takes the past perfect continuous."),
    ("vocabulary", "The manager asked us to ____ the report by Friday.",
     ["submit", "submise", "submition", "submitting"], 0,
     "'Submit' is the base verb after 'to'. The others are not English words "
     "or are the wrong form."),
    ("vocabulary", "Her explanation was very ____ — everyone understood it at once.",
     ["lucid", "loose", "lucrative", "ludicrous"], 0,
     "'Lucid' means clear and easy to follow. 'Lucrative' means profitable."),
    ("vocabulary", "We need to ____ the problem before the client calls.",
     ["resolve", "revolve", "dissolve", "involve"], 0,
     "'Resolve' means settle or solve. The others are unrelated verbs."),
    ("vocabulary", "The company offers ____ training to all new joiners.",
     ["comprehensive", "comprehensible", "compressive", "comprising"], 0,
     "'Comprehensive' means complete and wide-ranging. 'Comprehensible' means "
     "able to be understood."),
    ("vocabulary", "She has a ____ knowledge of data structures.",
     ["deep", "deeply", "depth", "deepen"], 0,
     "An adjective is needed before the noun 'knowledge'."),
    ("sentence_correction", "Which sentence is correct?",
     ["I am having two brothers.", "I have two brothers.",
      "I having two brothers.", "I has two brothers."], 1,
     "'Have' for possession is not used in the continuous. 'I am having' would "
     "mean eating or experiencing."),
    ("sentence_correction", "Which sentence is correct?",
     ["He did not went to the office.", "He did not gone to the office.",
      "He did not go to the office.", "He not went to the office."], 2,
     "After the auxiliary 'did', the main verb stays in its base form."),
    ("sentence_correction", "Which sentence is correct?",
     ["The informations are useful.", "The information are useful.",
      "The information is useful.", "An information is useful."], 2,
     "'Information' is uncountable: no plural, and it takes a singular verb."),
    ("sentence_correction", "Which sentence is correct?",
     ["I am working here since two years.", "I have been working here for two years.",
      "I work here since two years.", "I am working here from two years."], 1,
     "Duration takes 'for'; 'since' takes a starting point. The present perfect "
     "continuous covers a period running up to now."),
    ("sentence_correction", "Which sentence is correct?",
     ["Please revert back to me.", "Please revert to me back.",
      "Please reply to me.", "Please do the reply back."], 2,
     "'Revert' means return to a previous state, not reply. 'Revert back' is "
     "also redundant."),
    ("sentence_correction", "Which sentence is correct?",
     ["One of my friend is a doctor.", "One of my friends is a doctor.",
      "One of my friends are a doctor.", "One of my friend are a doctor."], 1,
     "'One of' takes a plural noun and a singular verb."),
    ("error_id", "Find the error: 'The list of items are on the table.'",
     ["The list", "of items", "are", "on the table"], 2,
     "The subject is 'the list', which is singular, so the verb should be 'is'. "
     "'Of items' does not change the number of the subject."),
    ("error_id", "Find the error: 'She is more taller than her sister.'",
     ["She is", "more", "taller", "than her sister"], 1,
     "'Taller' is already comparative; 'more' makes it a double comparative."),
    ("error_id", "Find the error: 'I discussed about the issue with him.'",
     ["I", "discussed", "about", "with him"], 2,
     "'Discuss' takes a direct object with no preposition: discuss the issue."),
    ("error_id", "Find the error: 'Each of the students have submitted.'",
     ["Each", "of the students", "have", "submitted"], 2,
     "'Each' is singular, so the verb should be 'has'."),
    ("error_id", "Find the error: 'He returned back from Chennai yesterday.'",
     ["He", "returned", "back", "yesterday"], 2,
     "'Return' already means to come back; 'back' is redundant."),
    ("error_id", "Find the error: 'They are working on this project since March.'",
     ["They", "are working", "on this project", "since March"], 1,
     "With 'since March' the verb needs the present perfect continuous: "
     "'have been working'."),
    ("error_id", "Find the error: 'The reason is because the server was down.'",
     ["The reason", "is", "because", "the server was down"], 2,
     "'The reason is because' is redundant. Use 'the reason is that'."),
]


# --------------------------------------------------------------------------
# Platform plane
# --------------------------------------------------------------------------

async def seed_platform(reset: bool) -> dict:
    if reset:
        db = control_db()
        for col_name in await db.list_collection_names():
            if not col_name.startswith("system."):
                await db.drop_collection(col_name)
    await init_store()

    async with platform_sessionmaker()() as s:
        if (await s.execute(select(Plan))).scalars().first() is not None and not reset:
            print("platform already seeded — skipping")
            return {}

        plans = [
            Plan(code="pilot", name="Pilot (free)", billing_model="pilot",
                 price_per_seat=0, attempt_allowance=3,
                 features={"gamification": True, "leagues": False, "sso": False}),
            Plan(code="seat_standard", name="Standard (per seat)", billing_model="per_seat",
                 price_per_seat=450, attempt_allowance=5,
                 features={"gamification": True, "leagues": True, "sso": False}),
            Plan(code="institution_flat", name="Institution (flat)", billing_model="flat",
                 price_flat=250000, attempt_allowance=8,
                 features={"gamification": True, "leagues": True, "sso": True}),
        ]
        s.add_all(plans)
        await s.flush()

        staff = [
            PlatformUser(email="admin@saashx.ai", full_name="Platform Super Admin",
                         password_hash=hash_password(DEMO_PASSWORD), role="super_admin",
                         mfa_enabled=True),
            PlatformUser(email="finance@saashx.ai", full_name="Finance Operator",
                         password_hash=hash_password(DEMO_PASSWORD), role="finance"),
            PlatformUser(email="content@saashx.ai", full_name="Content Lead",
                         password_hash=hash_password(DEMO_PASSWORD), role="content"),
        ]
        s.add_all(staff)

        # The game economy, seeded with defaults rather than hard-coded anywhere.
        s.add(GamificationConfig(
            tenant_id=None,
            xp_table={"attempt_completed": 120, "drill_completed": 60,
                      "quiz_completed": 25, "quest_completed": 80,
                      "streak_milestone": 150},
            difficulty_multipliers={"below_ability": 0.6, "at_ability": 1.0,
                                    "above_ability": 1.4},
            weakness_multiplier=1.5,
            streak_rules={"qualifies_on": "daily_quest_completed",
                          "milestones": [7, 14, 30, 60, 90]},
            free_freezes_per_month=2,
            quiz_xp_cap_percent=40,
            leagues_enabled=True,
            max_engagement_notifications_per_day=1,
        ))

        # Provider registry. Rows whose implementation does not exist yet stay
        # inactive, so the console shows the real state rather than an
        # optimistic one. VAD and fluency are live as of M1.
        registry = [
            # No Tier-0 ASR is registered on purpose. Transcription cannot be
            # faked from an energy envelope, and a provider that returned the
            # reference text would inflate every scripted score it touched.
            ProviderRegistry(capability="asr", provider_key="faster_whisper",
                             name="faster-whisper (Tier 1, local)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.asr:FasterWhisperASR",
                             active=True),
            ProviderRegistry(capability="vad", provider_key="energy_vad",
                             name="Energy-threshold VAD (Tier 0)", tier=0, version="0.1.0",
                             entrypoint="app.engine.providers.tier0.vad:EnergyVAD",
                             active=True),
            ProviderRegistry(capability="vad", provider_key="silero_vad",
                             name="Silero VAD (Tier 1)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.vad:SileroVAD",
                             active=True),
            ProviderRegistry(capability="accuracy", provider_key="reference_match",
                             name="Reference word match (Tier 1)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.accuracy:ReferenceMatchAccuracy",
                             active=True),
            ProviderRegistry(capability="disfluency", provider_key="transcript_disfluency",
                             name="Transcript disfluency (Tier 1)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.disfluency:TranscriptDisfluency",
                             active=True),
            ProviderRegistry(capability="grammar", provider_key="common_error_rules",
                             name="Common error patterns (Tier 1)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.grammar:CommonErrorGrammar",
                             active=True),
            ProviderRegistry(capability="content_relevance", provider_key="rubric_coverage",
                             name="Rubric key-point coverage (Tier 1)", tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.relevance:RubricRelevance",
                             active=True),
            ProviderRegistry(capability="pronunciation", provider_key="wav2vec2_gop",
                             name="wav2vec2 goodness of pronunciation (Tier 1)",
                             tier=1, version="0.1.0",
                             entrypoint="app.engine.providers.tier1.pronunciation:Wav2VecGOP",
                             active=True),
            ProviderRegistry(capability="fluency", provider_key="feature_fluency",
                             name="Feature-based fluency (Tier 0)", tier=0, version="0.1.0",
                             entrypoint="app.engine.providers.tier0.fluency:FeatureFluency",
                             active=True),
            ProviderRegistry(capability="storage", provider_key="local_tmp",
                             name="Local working storage (tmp/)", tier=0, version="0.1.0",
                             entrypoint="app.storage.local:LocalTempStorage",
                             active=True),
            ProviderRegistry(capability="notification", provider_key="in_app",
                             name="In-app notifications", tier=0, version="0.1.0",
                             entrypoint="app.engine.providers.tier0.notify:InAppNotifier",
                             active=False),
            ProviderRegistry(capability="payment", provider_key="razorpay",
                             name="Razorpay", tier=2, version="0.1.0",
                             entrypoint="app.engine.providers.tier2.razorpay:RazorpayGateway",
                             active=False),
        ]
        s.add_all(registry)
        await s.flush()

        by_key = {r.provider_key: r for r in registry}
        s.add_all([
            ProviderConfig(capability="storage", tenant_id=None,
                           primary_provider_id=by_key["local_tmp"].id,
                           mode="live", timeout_ms=5000),
            # Tier 1 leads; Tier 0 catches it. This is the first place the
            # fallback in ENG-19 is doing real work rather than being
            # available: if the speech model will not load on a given host,
            # latency and pause structure are still measured.
            ProviderConfig(capability="vad", tenant_id=None,
                           primary_provider_id=by_key["silero_vad"].id,
                           fallback_provider_id=by_key["energy_vad"].id,
                           mode="live", timeout_ms=15000),
            ProviderConfig(capability="asr", tenant_id=None,
                           primary_provider_id=by_key["faster_whisper"].id,
                           mode="live", timeout_ms=60000),
            # Feature-based fluency has no Tier-1 replacement yet, and does not
            # need one: it reads the VAD output, which just got better.
            ProviderConfig(capability="fluency", tenant_id=None,
                           primary_provider_id=by_key["feature_fluency"].id,
                           mode="live", timeout_ms=5000),
            ProviderConfig(capability="accuracy", tenant_id=None,
                           primary_provider_id=by_key["reference_match"].id,
                           mode="live", timeout_ms=5000),
            ProviderConfig(capability="disfluency", tenant_id=None,
                           primary_provider_id=by_key["transcript_disfluency"].id,
                           mode="live", timeout_ms=5000),
            ProviderConfig(capability="grammar", tenant_id=None,
                           primary_provider_id=by_key["common_error_rules"].id,
                           mode="live", timeout_ms=5000),
            ProviderConfig(capability="content_relevance", tenant_id=None,
                           primary_provider_id=by_key["rubric_coverage"].id,
                           mode="live", timeout_ms=5000),
            ProviderConfig(capability="pronunciation", tenant_id=None,
                           primary_provider_id=by_key["wav2vec2_gop"].id,
                           mode="live", timeout_ms=30000),
        ])

        tenants = [
            Tenant(name="St Mary's Institute of Technology", slug="stmarys",
                   status="active", plan_id=plans[1].id, seat_limit=250,
                   season_start=datetime.now(timezone.utc) + timedelta(days=52),
                   season_end=datetime.now(timezone.utc) + timedelta(days=110),
                   branding={"theme": "blue"}),
            Tenant(name="Vignan Degree College", slug="vignan",
                   status="trial", plan_id=plans[0].id, seat_limit=60,
                   season_start=datetime.now(timezone.utc) + timedelta(days=88),
                   branding={"theme": "royal-blue"}),
        ]
        s.add_all(tenants)
        await s.flush()

        for t in tenants:
            s.add(Subscription(tenant_id=t.id, plan_id=t.plan_id or plans[0].id,
                               status="active" if t.status == "active" else "trialing",
                               seats=t.seat_limit))
            s.add(AuditLog(actor_type="platform_user", actor_id=staff[0].id,
                           actor_label=staff[0].email, tenant_id=t.id,
                           action="tenant.created", entity="Tenant", entity_id=t.id,
                           after={"name": t.name, "slug": t.slug}))

        await s.commit()
        return {t.slug: t.id for t in tenants}


# --------------------------------------------------------------------------
# Item bank
# --------------------------------------------------------------------------

def build_item_bank() -> list[TaskItem]:
    """Every speaking item, as fresh rows.

    A factory rather than a constant because ``TaskItem`` instances are
    session-bound: handing the same objects to two tenants would attach them
    to whichever session touched them last.
    """
    items: list[TaskItem] = []
    for text_ in READ_ALOUD:
        items.append(TaskItem(task_type="read_aloud", prompt_text=text_,
                              reference_text=text_, word_count=len(text_.split()),
                              difficulty=round(RNG.uniform(-0.8, 0.8), 2),
                              skill_tags=["pronunciation", "fluency"]))
    for text_ in READ_ALOUD_PARAGRAPHS:
        # difficulty 2.0 and a distinct topic put these in their own band, so
        # only the paragraph section draws them.
        items.append(TaskItem(task_type="read_aloud", prompt_text=text_,
                              reference_text=text_, word_count=len(text_.split()),
                              difficulty=2.0, topic="paragraph",
                              skill_tags=["pronunciation", "fluency"]))
    for text_ in REPEAT_SENTENCE:
        items.append(TaskItem(task_type="repeat_sentence", prompt_text="",
                              reference_text=text_, word_count=len(text_.split()),
                              difficulty=round(RNG.uniform(-0.5, 1.2), 2),
                              skill_tags=["listening", "pronunciation", "fluency"]))
    for text_ in OPEN_RESPONSE:
        items.append(TaskItem(task_type="open_response", prompt_text=text_,
                              # No key points: an opinion has no right
                              # answer. The prompt is kept so the engine can
                              # tell whether the student addressed it.
                              rubric={"key_points": [], "prompt": text_,
                                      "min_seconds": 25,
                                      "cues": list(TOPIC_CUES.get(text_, []))},
                              difficulty=0.4,
                              skill_tags=["fluency", "grammar", "vocabulary"]))
    for question, accepted in SHORT_ANSWERS:
        # The question goes in prompt_text (heard, never shown — the
        # runner withholds it because short_answer is not a reading task)
        # and the accepted answers are the rubric.
        items.append(TaskItem(task_type="short_answer", prompt_text=question,
                              reference_text=accepted[0],
                              rubric={"key_points": accepted},
                              word_count=1,
                              difficulty=round(RNG.uniform(-1.0, 0.3), 2),
                              skill_tags=["listening", "vocabulary"]))
    for jumbled, correct in SENTENCE_BUILDS:
        items.append(TaskItem(task_type="sentence_build", prompt_text=jumbled,
                              reference_text=correct,
                              word_count=len(correct.split()),
                              difficulty=round(RNG.uniform(-0.2, 1.1), 2),
                              skill_tags=["grammar", "fluency"]))
    for task_type, spoken, rubric, difficulty in SPOKEN_QUESTIONS:
        # The exchange and the question are one piece of audio and live in
        # `reference_text`, which is what SPEAKS_REFERENCE makes the runner
        # play. `prompt_text` stays empty: showing it would turn a listening
        # task into a reading one, and nothing scores against the reference
        # here -- the accuracy provider only compares against scripted tasks.
        items.append(TaskItem(task_type=task_type, prompt_text="",
                              reference_text=spoken,
                              rubric=dict(rubric),
                              word_count=len(spoken.split()),
                              difficulty=difficulty,
                              skill_tags=["listening", "content_recall",
                                          "fluency"]))
    for heard, target in SPOKEN_COMPLETIONS:
        # The gapped sentence is heard (prompt_text); the full correct
        # sentence is the scored target (reference_text). Speaking it is the
        # task, so the item never shows either.
        items.append(TaskItem(task_type="spoken_completion", prompt_text=heard,
                              reference_text=target,
                              word_count=len(target.split()),
                              difficulty=round(RNG.uniform(-0.2, 0.8), 2),
                              skill_tags=["listening", "grammar", "fluency"]))
    for heard, target in SPOKEN_CORRECTIONS:
        items.append(TaskItem(task_type="spoken_correction", prompt_text=heard,
                              reference_text=target,
                              word_count=len(target.split()),
                              difficulty=round(RNG.uniform(0.0, 1.0), 2),
                              skill_tags=["listening", "grammar", "fluency"]))
    for words in WORD_LISTS:
        # Isolated words read aloud (the researched Cognizant word lists).
        # Their reserved difficulty band is what keeps them out of every
        # sentence section and lets one section ask for them by band.
        items.append(TaskItem(task_type="read_aloud", prompt_text=words,
                              reference_text=words,
                              word_count=len(words.replace(",", " ").split()),
                              difficulty=WORD_LIST_DIFFICULTY,
                              topic="word_list",
                              skill_tags=["pronunciation"]))
    for story, points in RETELL_STORIES:
        items.append(TaskItem(task_type="story_retell", prompt_text="",
                              reference_text=story,
                              rubric={"key_points": points, "min_seconds": 30},
                              word_count=len(story.split()),
                              difficulty=0.8,
                              skill_tags=["listening", "content_recall", "fluency"]))
    return items


def _item_key(task_type: str, reference_text: str, prompt_text: str) -> tuple[str, str]:
    """What makes two items the same item.

    Reference text is the natural identity for a scripted task, but an open
    response has none -- there is no correct answer to compare against, so
    the column is empty on every row. Keying on it alone made all of them
    look like one item, and the top-up added the whole set again on every run.
    """
    return (task_type, (reference_text or prompt_text or "").strip())


# Two items whose text differs only after this many characters are, for a
# student sitting one test, the same item twice.
NEAR_DUPLICATE_PREFIX = 40


def _prefix(task_type: str, reference_text: str, prompt_text: str) -> tuple[str, str]:
    text = (reference_text or prompt_text or "").strip().lower()
    return (task_type, text[:NEAR_DUPLICATE_PREFIX])


def _is_reworded(older: str, newer: str) -> bool:
    """Is ``newer`` the same sentence as ``older`` with words added?

    Deliberately strict -- every word of the old sentence present, in order,
    inside a longer new one. Loose similarity would start retiring items that
    merely share a topic, and the bank is small enough that a false retirement
    costs real variety.
    """
    a = older.lower().rstrip(".").split()
    b = newer.lower().rstrip(".").split()
    if len(a) >= len(b) or not a:
        return False
    i = 0
    for word in b:
        if i < len(a) and word == a[i]:
            i += 1
    return i == len(a)


async def retire_superseded_items(s) -> list[str]:
    """Stop serving items that a later edition of the bank replaced.

    Widening the bank reworded some sentences rather than replacing them --
    "the flight was cancelled" became "the flight had been cancelled that
    morning". Both rows then existed, both were published, and a single
    attempt could draw the pair. That is not a duplicate the identity check
    catches, because the texts genuinely differ; it is a duplicate to the
    person reading them out.

    Retired rather than deleted. Responses already reference these rows, and
    an attempt whose item vanished is a scored answer to a question nobody can
    look up. ``_pick_items`` only ever selects published items, so retiring is
    sufficient to keep them out of new tests.
    """
    current = {
        _prefix(i.task_type, i.reference_text, i.prompt_text): (
            i.reference_text or i.prompt_text or "").strip()
        for i in build_item_bank()
    }

    rows = (await s.execute(
        select(TaskItem).where(TaskItem.status == "published"))).scalars().all()

    retired: list[str] = []
    for row in rows:
        text = (row.reference_text or row.prompt_text or "").strip()
        key = _prefix(row.task_type, row.reference_text, row.prompt_text)
        replacement = current.get(key)
        # Shares an opening with something in the current bank, but is not that
        # thing: an older wording the bank has moved on from.
        superseded = replacement is not None and replacement != text

        # And the other way a rewording happens: words inserted into the
        # middle, which leaves the opening different but every original word
        # still present. "Regular practice makes a difference" against
        # "Regular practice over several weeks makes a difference" shares no
        # forty-character prefix and is plainly the same sentence.
        if not superseded:
            superseded = any(
                other != text and _is_reworded(text, other)
                for (tt, _), other in current.items() if tt == row.task_type
            )

        if superseded:
            row.status = "retired"
            retired.append(f"{row.task_type}: {text[:50]}")

    await s.commit()
    return retired


async def top_up_item_bank(s) -> int:
    """Add items the bank does not have yet. Never removes or edits anything.

    The path for an estate that predates a content release. Identity is the
    reference text within a task type, which is what actually distinguishes
    one item from another -- ids are generated per row and would match nothing.
    """
    have = {
        _item_key(t, r, pt) for t, r, pt in (await s.execute(
            select(TaskItem.task_type, TaskItem.reference_text,
                   TaskItem.prompt_text))).all()
    }
    added = 0
    for item in build_item_bank():
        key = _item_key(item.task_type, item.reference_text, item.prompt_text)
        if key in have:
            continue
        # Added to the set as we go: two items in one batch can share a key,
        # and inserting both would recreate the duplication this exists to
        # prevent.
        have.add(key)
        s.add(item)
        added += 1
    await s.commit()
    return added


# --------------------------------------------------------------------------
# Company rounds
# --------------------------------------------------------------------------

async def seed_format_profiles(s) -> dict[str, list[str]]:
    """Create every blueprinted profile, idempotently, and repair empty ones.

    Split out and safe to re-run because these are also installed into
    institutions provisioned before the profiles existed -- see
    ``python -m app.seed --formats``.

    Two behaviours worth being explicit about:

    * A profile that already exists **with sections** is left exactly as it
      is. A tenant admin may have retimed it, and a reseed must not quietly
      undo that.
    * A profile that exists with **no** sections is filled from its blueprint
      and published. That is not an admin's deliberate draft, it is an
      incomplete seed -- the SVAR-style profile shipped in exactly that state
      and would have handed a student a test with nothing in it.
    """
    existing = {
        p.code: p for p in (await s.execute(
            select(SimulationProfile)
            .options(selectinload(SimulationProfile.sections))
        )).scalars().all()
    }

    created: list[str] = []
    repaired: list[str] = []

    for blueprint in formats.ALL_BLUEPRINTS:
        profile = existing.get(blueprint.code)

        if profile is not None and profile.sections:
            continue

        if profile is None:
            profile = SimulationProfile(
                code=blueprint.code, name=blueprint.name, style=blueprint.style,
                company=blueprint.company, description=blueprint.description,
                status="published", estimated_minutes=blueprint.estimated_minutes,
                score_scale=(
                    {"min": blueprint.scale.minimum, "max": blueprint.scale.maximum}
                    if blueprint.scale else {}
                ),
            )
            s.add(profile)
            await s.flush()
            created.append(blueprint.code)
        else:
            # Present but empty. Fill it and let students see it.
            profile.description = profile.description or blueprint.description
            profile.estimated_minutes = blueprint.estimated_minutes
            profile.company = blueprint.company
            if blueprint.scale:
                profile.score_scale = {"min": blueprint.scale.minimum,
                                       "max": blueprint.scale.maximum}
            profile.status = "published"
            repaired.append(blueprint.code)

        for position, section in enumerate(blueprint.sections, start=1):
            s.add(ProfileSection(
                profile_id=profile.id, position=position, title=section.title,
                task_type=section.task_type, item_count=section.item_count,
                prep_seconds=section.prep_seconds,
                response_seconds=section.response_seconds,
                prompt_plays_allowed=section.prompt_plays_allowed,
                instructions=section.instructions,
                selection=section.selection,
            ))

    await s.commit()
    return {"created": created, "repaired": repaired}


async def seed_company_rounds(s) -> list[str]:
    """Backwards-compatible alias used by the tenant seeder."""
    out = await seed_format_profiles(s)
    return out["created"] + out["repaired"]


# --------------------------------------------------------------------------
# Tenant plane
# --------------------------------------------------------------------------

async def seed_tenant(slug: str, tenant_id: str, *, students: int,
                      cohort_specs: list[dict], drive_in_days: int) -> None:
    await create_tenant_schema(slug)

    async with tenant_sessionmaker(slug)() as s:
        # Idempotent: a re-run replaces the demo estate rather than doubling it.
        for model in (XPLedger, Quest, StreakState, SkillMastery, StudentFlag,
                      MistakeBankEntry, ScoreRecord, Response, Attempt,
                      ConsentRecord, CohortMember, ProfileSection, TaskItem,
                      QuizItem, SimulationProfile, Cohort, User):
            await s.execute(delete(model))
        await s.commit()

        admin = User(email=f"admin@{slug}.edu", full_name="Institution Admin",
                     password_hash=hash_password(DEMO_PASSWORD), role="tenant_admin")
        trainers = [
            User(email=f"trainer1@{slug}.edu", full_name="Anitha Rao",
                 password_hash=hash_password(DEMO_PASSWORD), role="trainer"),
            User(email=f"trainer2@{slug}.edu", full_name="Suresh Kumar",
                 password_hash=hash_password(DEMO_PASSWORD), role="trainer"),
        ]
        s.add_all([admin, *trainers])
        await s.flush()

        first_names = ["Aarav", "Divya", "Rahul", "Sneha", "Karthik", "Priya", "Vikram",
                       "Meena", "Arjun", "Lakshmi", "Naveen", "Swathi", "Rohit", "Tejaswi",
                       "Manoj", "Harika", "Sandeep", "Bhavana", "Kiran", "Deepika"]
        last_names = ["Reddy", "Sharma", "Nair", "Patel", "Iyer", "Chowdary", "Rao",
                      "Verma", "Menon", "Das"]
        l1_options = ["telugu", "hindi", "tamil"]

        student_rows: list[User] = []
        for i in range(students):
            first = first_names[i % len(first_names)]
            last = last_names[(i // len(first_names) + i) % len(last_names)]
            student_rows.append(User(
                email=f"{first.lower()}.{last.lower()}{i+1}@{slug}.edu",
                full_name=f"{first} {last}",
                password_hash=hash_password(DEMO_PASSWORD),
                role="student",
                roll_number=f"{20 + (i % 3)}B81A{1000 + i}",
                branch=cohort_specs[i % len(cohort_specs)]["branch"],
                year_of_study=4,
                l1_language=RNG.choice(l1_options),
            ))
        s.add_all(student_rows)
        await s.flush()

        drive = datetime.now(timezone.utc) + timedelta(days=drive_in_days)
        cohorts = []
        for idx, spec in enumerate(cohort_specs):
            cohorts.append(Cohort(
                name=spec["name"], branch=spec["branch"], year_of_study=4,
                section=spec["section"], trainer_id=trainers[idx % len(trainers)].id,
                drive_start=drive, drive_end=drive + timedelta(days=21),
            ))
        s.add_all(cohorts)
        await s.flush()

        for i, student in enumerate(student_rows):
            s.add(CohortMember(cohort_id=cohorts[i % len(cohorts)].id, user_id=student.id))

        # --- content ------------------------------------------------------
        s.add_all(build_item_bank())

        for category, stem, options, correct, explanation in QUIZ_ITEMS:
            s.add(QuizItem(
                category=category, stem=stem, options=list(options),
                correct_index=correct, explanation=explanation,
                seconds_allowed=25 if category == "error_id" else 20,
                difficulty=round(RNG.uniform(-0.6, 0.9), 2),
                skill_tags=["grammar"] if category != "vocabulary" else ["vocabulary"],
            ))

        # --- listening ------------------------------------------------------
        # Passages first, then their questions, because a question needs the
        # passage id. Comprehension is measured over a whole passage, so the
        # grouping is the content model rather than a display detail.
        for (title, kind, seconds, plays, difficulty,
             transcript, questions) in LISTENING_PASSAGES:
            passage = ListeningPassage(
                title=title, kind=kind, transcript=transcript,
                approx_seconds=seconds, plays_allowed=plays,
                difficulty=difficulty,
            )
            s.add(passage)
            await s.flush()
            for n, (stem, options, correct, explanation) in enumerate(questions):
                rolled, key = _rotate_options(n, list(options), correct)
                s.add(QuizItem(
                    category="audio_comprehension", stem=stem,
                    options=rolled, correct_index=key,
                    explanation=explanation, passage_id=passage.id,
                    # No clock on an individual question: the listening was
                    # the timed part, and rushing the answer measures reading
                    # speed instead of comprehension.
                    seconds_allowed=0,
                    difficulty=difficulty,
                    skill_tags=["listening"],
                ))

        # --- writing --------------------------------------------------------
        for (title, kind, difficulty, min_words, minutes,
             scenario, prompt, key_points) in WRITING_PROMPTS:
            s.add(WritingPrompt(
                title=title, kind=kind, difficulty=difficulty,
                min_words=min_words, suggested_minutes=minutes,
                scenario=scenario, prompt=prompt, key_points=list(key_points),
            ))

        # --- reading --------------------------------------------------------
        for title, kind, difficulty, body, questions in READING_PASSAGES:
            passage = ReadingPassage(title=title, kind=kind, body=body,
                                     difficulty=difficulty,
                                     word_count=_word_count(body))
            s.add(passage)
            await s.flush()
            for n, (stem, options, correct, why) in enumerate(questions):
                rolled, key = _rotate_options(n, list(options), correct)
                s.add(QuizItem(
                    category="reading_comprehension", stem=stem,
                    options=rolled, correct_index=key, explanation=why,
                    passage_id=passage.id, seconds_allowed=0,
                    difficulty=difficulty, skill_tags=["vocabulary"],
                ))

        # --- the Phase 4 banks ----------------------------------------------
        #
        # Through the installers rather than inline: they are idempotent and
        # the estate upgrade calls the same functions, so a fresh seed and an
        # upgraded one hold the same content instead of two copies of the
        # loop drifting apart.
        await s.commit()
        await install_selection(s)
        await install_reconstructions(s)
        await install_completions(s)
        await install_voice_change(s)
        await install_classification(s)

        baseline = SimulationProfile(
            code="baseline_v1", name="Baseline Diagnostic",
            style="diagnostic", status="published", estimated_minutes=8,
            is_baseline=True,
            description=("Short diagnostic taken once, before any training is "
                         "assigned. Establishes the starting point every later "
                         "attempt is measured against."),
            score_scale={"min": 20, "max": 80,
                         "bands": {"20-35": "Beginning", "36-50": "Developing",
                                   "51-64": "Competent", "65-80": "Strong"}},
            scoring_weights={"pronunciation": 0.3, "fluency": 0.3,
                             "grammar": 0.2, "content": 0.2},
        )
        s.add(baseline)
        await s.flush()

        await seed_format_profiles(s)

        s.add_all([
            ProfileSection(profile_id=baseline.id, position=1, title="Read Aloud",
                           task_type="read_aloud", item_count=4, prep_seconds=5,
                           response_seconds=20, prompt_plays_allowed=0,
                           instructions="Read each sentence aloud, clearly and at a natural pace."),
            ProfileSection(profile_id=baseline.id, position=2, title="Repeat Sentence",
                           task_type="repeat_sentence", item_count=4, prep_seconds=0,
                           response_seconds=15, prompt_plays_allowed=1,
                           instructions="You will hear each sentence once. Repeat it exactly."),
        ])

        # --- history --------------------------------------------------------
        # Roughly two thirds of the cohort has taken the baseline. The rest have
        # not started, because that is what a real placement cell sees.
        today = date.today()
        for i, student in enumerate(student_rows):
            s.add(ConsentRecord(user_id=student.id, scope="recording", granted=True,
                                retention_days=30))
            s.add(ConsentRecord(user_id=student.id, scope="training_data",
                                granted=i % 3 != 0))

            if i % 3 == 2:
                continue  # never started

            overall = round(RNG.uniform(32, 72), 1)
            attempt = Attempt(
                user_id=student.id, profile_id=baseline.id, attempt_number=1,
                status="scored", mode="official", is_baseline=True,
                env_check={"mic": "ok", "noise_dbfs": -46.2, "headphones": True},
                started_at=datetime.now(timezone.utc) - timedelta(days=RNG.randint(3, 20)),
            )
            attempt.created_at = attempt.started_at
            attempt.submitted_at = attempt.started_at + timedelta(minutes=9)
            attempt.scored_at = attempt.submitted_at + timedelta(seconds=6)
            s.add(attempt)
            await s.flush()

            s.add(ScoreRecord(attempt_id=attempt.id, dimension="overall", score=overall,
                              band="Competent" if overall >= 51 else "Developing",
                              confidence=0.62, provider_key="seed", provider_version="0.0.0"))
            for dim, spread in (("pronunciation", 6), ("fluency", 8),
                                ("grammar", 7), ("content", 9)):
                s.add(ScoreRecord(attempt_id=attempt.id, dimension=dim,
                                  score=round(min(80, max(20, overall + RNG.uniform(-spread, spread))), 1),
                                  confidence=0.55, provider_key="seed",
                                  provider_version="0.0.0"))

            masteries: dict[str, float] = {}
            for skill in SKILLS:
                mastery = round(min(0.95, max(0.05, (overall - 20) / 60 + RNG.uniform(-0.15, 0.15))), 2)
                masteries[skill] = mastery
                s.add(SkillMastery(user_id=student.id, skill=skill, mastery=mastery,
                                   baseline=mastery, confidence=0.4,
                                   observations=RNG.randint(4, 20),
                                   last_change=round(RNG.uniform(-0.03, 0.08), 3)))

            xp = RNG.randint(120, 1800)
            s.add(XPLedger(user_id=student.id, activity="attempt_completed",
                           ref_type="attempt", ref_id=attempt.id, base_xp=120,
                           difficulty_multiplier=1.0, weakness_multiplier=1.0,
                           awarded_xp=120))
            if xp > 120:
                s.add(XPLedger(user_id=student.id, activity="drill_completed",
                               base_xp=60, difficulty_multiplier=1.0,
                               weakness_multiplier=1.5, awarded_xp=xp - 120,
                               target_skill="fluency"))

            # A seeded streak ends *yesterday*, never today. Dating it today
            # would mean the demo student's day is already counted before they
            # do anything, so their first real session moves nothing and the
            # streak looks broken. Ending it yesterday leaves today live: one
            # session extends the streak, and skipping today breaks it, which
            # is the whole point of the mechanic.
            streak_days = RNG.choice([0, 0, 1, 3, 5, 8, 12])
            s.add(StreakState(
                user_id=student.id, current_streak=streak_days,
                best_streak=max(streak_days, RNG.randint(streak_days, streak_days + 6)),
                last_qualifying_day=(today - timedelta(days=1)) if streak_days else None,
                freezes_available=2,
            ))

            # Today's quest is left genuinely open. It used to be seeded at a
            # random progress that could land on the target, which completed
            # the day the moment anything touched it -- the student got the
            # reward without doing the work, and every day after that was a
            # no-op. Demo data should show the loop working, not pre-spend it.
            # The student's *actual* weakest skill, matching how the engine
            # picks one. This used to be min(SKILLS, key=lambda _: random()) --
            # a random skill wearing the name "weakest". Because the drill
            # builder targets the genuinely weakest skill, the two disagreed,
            # and advance_quest only credits work on the quest's own skill:
            # the daily quest sat at 0/5 no matter how many drills a demo
            # student finished. The loop could not close on seeded data.
            weakest = min(masteries, key=lambda k: masteries[k])
            s.add(Quest(
                user_id=student.id, kind="daily", for_date=today,
                title=f"Tighten your {weakest.replace('_', ' ')}",
                description="Five targeted items on the sub-skill costing you the most.",
                target_skill=weakest, objective={"items": 5, "skill": weakest},
                progress=0.0, target=5.0, bonus_xp=80,
            ))

        await s.commit()

    # Directory entries: email → institution, so sign-in can route before a
    # tenant is known. Written last, once the users exist.
    async with tenant_sessionmaker(slug)() as ts:
        emails = list((await ts.execute(select(User.email))).scalars().all())
    async with platform_sessionmaker()() as ps:
        await ps.execute(delete(TenantUserDirectory).where(
            TenantUserDirectory.tenant_slug == slug))
        for email in emails:
            ps.add(TenantUserDirectory(email=email, tenant_id=tenant_id, tenant_slug=slug))
        await ps.commit()

    print(f"  seeded {slug}: {len(emails)} users")


async def main(reset: bool) -> None:
    if reset:
        for slug in ("stmarys", "vignan"):
            await drop_tenant_schema(slug)

    tenant_ids = await seed_platform(reset)
    if not tenant_ids:
        async with platform_sessionmaker()() as s:
            tenant_ids = {t.slug: t.id for t in (await s.execute(select(Tenant))).scalars().all()}

    await seed_tenant(
        "stmarys", tenant_ids["stmarys"], students=30, drive_in_days=52,
        cohort_specs=[
            {"name": "CSE-A Final Year", "branch": "CSE", "section": "A"},
            {"name": "CSE-B Final Year", "branch": "CSE", "section": "B"},
            {"name": "ECE-A Final Year", "branch": "ECE", "section": "A"},
        ],
    )
    await seed_tenant(
        "vignan", tenant_ids["vignan"], students=12, drive_in_days=88,
        cohort_specs=[
            {"name": "BCA Final Year", "branch": "BCA", "section": "A"},
        ],
    )

    print("\nDemo accounts (password for all: %s)" % DEMO_PASSWORD)
    print("  platform   admin@saashx.ai")
    print("  institution admin@stmarys.edu")
    print("  trainer     trainer1@stmarys.edu")
    print("  student     aarav.reddy1@stmarys.edu")
    print("  other tenant admin@vignan.edu")


async def retire_dropped_profiles(s) -> list[str]:
    """Retire seeded profiles whose blueprint no longer exists.

    A blueprint can be withdrawn -- ``versant_style_full`` and
    ``svar_style_full`` were, once the four templates replaced them with the
    same tests done properly. The rows do not disappear with it, and a
    published profile nothing can resync is worse than a retired one: it keeps
    serving the shape it was seeded with while every other profile moves on.

    Retired, never deleted. Attempts point at it, and a result whose profile
    vanished cannot be read back.

    Driven by ``formats.WITHDRAWN_CODES``, an explicit list, and not by "any
    code that is not a blueprint code". The builder gives every admin-authored
    profile a code as well, so the inferred rule retires a tenant's own
    assessments -- which is what it did, to two dozen of them, the first time
    this function ran.
    """
    rows = (await s.execute(
        select(SimulationProfile)
        .where(SimulationProfile.code.in_(sorted(formats.WITHDRAWN_CODES)),
               SimulationProfile.status != "retired")
    )).scalars().all()

    retired: list[str] = []
    for profile in rows:
        profile.status = "retired"
        retired.append(profile.code)

    if retired:
        await s.commit()
    return retired


async def resync_format_profiles(s) -> dict[str, list[str]]:
    """Bring blueprinted profiles back in line with their blueprint.

    Needed because ``seed_format_profiles`` deliberately never overwrites: a
    tenant admin may have retimed a round, and a content release must not undo
    that. But when the blueprint itself is corrected -- as it was when
    SpeechX-style turned out to advertise a Grammar sub-score it could never
    produce -- the fix has to reach profiles that are already seeded.

    So: only profiles that **nobody has touched and nobody has attempted** are
    rewritten. Anything edited away from its blueprint is left alone and
    reported, for a human to decide about. The alternative -- overwriting
    everything -- silently discards an admin's work, and the alternative to
    that -- overwriting nothing -- ships a format that cannot report one of
    its own sub-scores.
    """
    profiles = {
        p.code: p for p in (await s.execute(
            select(SimulationProfile)
            .options(selectinload(SimulationProfile.sections))
        )).scalars().all()
    }

    resynced: list[str] = []
    skipped: list[str] = []

    for blueprint in formats.ALL_BLUEPRINTS:
        profile = profiles.get(blueprint.code)
        if profile is None:
            continue

        current = [(x.title, x.task_type, x.item_count, x.prep_seconds,
                    x.response_seconds, x.prompt_plays_allowed)
                   for x in sorted(profile.sections, key=lambda x: x.position)]
        wanted = [(b.title, b.task_type, b.item_count, b.prep_seconds,
                   b.response_seconds, b.prompt_plays_allowed)
                  for b in blueprint.sections]

        # Text drift counts as drift.
        #
        # This compared sections only, so a blueprint whose *description* was
        # corrected never resynced as long as its sections still matched. The
        # SVAR profile spent months telling students it was a "six-section
        # simulation including grammar and error-ID sections" while being a
        # four-section speaking test with neither -- the blueprint had been
        # fixed and the row had not, and nothing here would ever have noticed.
        # The name and the per-section instructions are wording too. The
        # SVAR profile was renamed to say what it actually is, and a Section
        # B instruction that promised "speaking points" the task never shows
        # was corrected; neither changes anything measured, and both have to
        # reach rows that already exist.
        instructions_drifted = (
            current == wanted and any(
                x.instructions != b.instructions
                for x, b in zip(sorted(profile.sections, key=lambda x: x.position),
                                blueprint.sections)))
        text_drifted = (profile.description != blueprint.description
                        or profile.name != blueprint.name
                        or profile.estimated_minutes != blueprint.estimated_minutes
                        or instructions_drifted)

        if current == wanted and not text_drifted:
            continue

        attempts = (await s.execute(
            select(func.count()).select_from(Attempt)
            .where(Attempt.profile_id == profile.id))).scalar_one()

        # Wording is always safe to correct, even on a profile with attempts.
        #
        # The attempts guard exists to protect *comparability*: changing which
        # sections a test contains would make a new result incomparable with
        # an old one. A description changes nothing that was measured. Holding
        # text hostage to that guard is what left the SVAR profile describing
        # sections it does not have to every student who has ever opened it.
        if text_drifted:
            profile.description = blueprint.description
            profile.name = blueprint.name
            profile.estimated_minutes = blueprint.estimated_minutes
            if current == wanted:
                for x, b in zip(sorted(profile.sections, key=lambda x: x.position),
                                blueprint.sections):
                    x.instructions = b.instructions
                resynced.append(f"{blueprint.code} (wording)")
                continue

        if attempts:
            skipped.append(f"{blueprint.code} ({attempts} attempts)")
            continue

        for existing in list(profile.sections):
            await s.delete(existing)
        profile.sections.clear()
        for position, section in enumerate(blueprint.sections, start=1):
            s.add(ProfileSection(
                profile_id=profile.id, position=position, title=section.title,
                task_type=section.task_type, item_count=section.item_count,
                prep_seconds=section.prep_seconds,
                response_seconds=section.response_seconds,
                prompt_plays_allowed=section.prompt_plays_allowed,
                instructions=section.instructions,
            ))
        profile.estimated_minutes = blueprint.estimated_minutes
        resynced.append(blueprint.code)

    await s.commit()
    return {"resynced": resynced, "skipped": skipped}


async def is_empty() -> bool:
    """Has this deployment ever been seeded?

    Used by ``--if-empty`` so a start command can seed a brand-new database
    and then do nothing on every restart after that. Checking for tenants
    rather than for tables: the tables exist as soon as migrations run, which
    is before there is anything in them.
    """
    async with platform_sessionmaker()() as s:
        return not (await s.execute(select(Tenant.id).limit(1))).scalars().first()


async def install_listening(session) -> int:
    """Add any missing listening passages to one institution. Idempotent.

    Keyed on title, so re-running adds nothing and a passage whose wording is
    revised is left alone rather than duplicated. Questions are only written
    for a passage this call actually created -- editing the bank's questions
    later needs a deliberate migration, not a silent overwrite of items a
    student may already have answered.
    """
    existing = set((await session.execute(
        select(ListeningPassage.title))).scalars().all())

    added = 0
    for (title, kind, seconds, plays, difficulty,
         transcript, questions) in LISTENING_PASSAGES:
        if title in existing:
            continue
        passage = ListeningPassage(
            title=title, kind=kind, transcript=transcript,
            approx_seconds=seconds, plays_allowed=plays, difficulty=difficulty,
        )
        session.add(passage)
        await session.flush()
        for n, (stem, options, correct, explanation) in enumerate(questions):
            rolled, key = _rotate_options(n, list(options), correct)
            session.add(QuizItem(
                category="audio_comprehension", stem=stem,
                options=rolled, correct_index=key,
                explanation=explanation, passage_id=passage.id,
                seconds_allowed=0, difficulty=difficulty,
                skill_tags=["listening"],
            ))
        added += 1
    await session.commit()
    return added


async def install_reading(session) -> int:
    """Add any missing reading passages. Idempotent, keyed on title."""
    existing = set((await session.execute(
        select(ReadingPassage.title))).scalars().all())

    added = 0
    for title, kind, difficulty, body, questions in READING_PASSAGES:
        if title in existing:
            continue
        passage = ReadingPassage(
            title=title, kind=kind, body=body, difficulty=difficulty,
            # Frozen at insert: it is the denominator of every rate measured
            # against this passage, and must not move if the text is edited.
            word_count=_word_count(body),
        )
        session.add(passage)
        await session.flush()
        for n, (stem, options, correct, why) in enumerate(questions):
            rolled, key = _rotate_options(n, list(options), correct)
            session.add(QuizItem(
                category="reading_comprehension", stem=stem,
                options=rolled, correct_index=key, explanation=why,
                passage_id=passage.id, seconds_allowed=0,
                difficulty=difficulty, skill_tags=["vocabulary"],
            ))
        added += 1
    await session.commit()
    return added


async def install_completions(session) -> int:
    """Add the sentence-completion bank. Idempotent, keyed on the sentence.

    Stored as QuizItems whose `options` hold the accepted answers rather than
    choices to pick between -- the candidate types a word and it is checked
    against the set. Reusing the row shape keeps one bank and one selector
    instead of a fourth table that behaves almost identically.
    """
    existing = set((await session.execute(
        select(QuizItem.stem).where(
            QuizItem.category == "sentence_completion"))).scalars().all())

    added = 0
    for sentence, accepted, tests in COMPLETION_ITEMS:
        if sentence in existing:
            continue
        session.add(QuizItem(
            category="sentence_completion", stem=sentence,
            options=sorted(accepted),
            # No index to choose: the answer is typed. Kept at zero rather
            # than null because the column is not nullable, and the marker
            # for this category never reads it.
            correct_index=0,
            explanation=f"Tests {tests}. Accepted: {', '.join(sorted(accepted))}.",
            seconds_allowed=0, difficulty=0.0, skill_tags=["grammar"],
            topic=grammar_bank.LEGACY_TOPIC,
        ))
        added += 1

    # The SVAR-style Section C categories (verb forms, tenses, articles,
    # prepositions), each item tagged so a section can draw its category.
    for sentence, accepted, category in grammar_bank.ITEMS:
        if sentence in existing:
            continue
        session.add(QuizItem(
            category="sentence_completion", stem=sentence,
            options=sorted(accepted), correct_index=0,
            explanation=f"Category: {category}. Accepted: {', '.join(sorted(accepted))}.",
            seconds_allowed=0, difficulty=0.0, skill_tags=["grammar"],
            topic=category,
        ))
        added += 1

    # Rows seeded before `topic` existed: classify them so a category draw
    # cannot be filled with an unclassified connector item.
    legacy = set(s for s, _, _ in COMPLETION_ITEMS)
    by_category = {s: c for s, _, c in grammar_bank.ITEMS}
    rows = (await session.execute(
        select(QuizItem).where(QuizItem.category == "sentence_completion",
                               QuizItem.topic == ""))).scalars().all()
    for row in rows:
        if row.stem in by_category:
            row.topic = by_category[row.stem]
        elif row.stem in legacy:
            row.topic = grammar_bank.LEGACY_TOPIC
    await session.commit()
    return added


async def install_topic_cues(session) -> int:
    """Add any missing Speak-on-the-Topic items and their speaking points.

    Idempotent: keyed on the topic text. Existing rows get `cues` written
    into their rubric; `key_points` is left exactly as it was, so nothing
    about scoring moves.
    """
    rows = (await session.execute(
        select(TaskItem).where(TaskItem.task_type == "open_response"))).scalars().all()
    by_text = {r.prompt_text: r for r in rows}
    changed = 0
    for text_ in OPEN_RESPONSE:
        row = by_text.get(text_)
        cues = list(TOPIC_CUES.get(text_, []))
        if row is None:
            session.add(TaskItem(task_type="open_response", prompt_text=text_,
                                 rubric={"key_points": [], "prompt": text_,
                                         "min_seconds": 25, "cues": cues},
                                 difficulty=0.4,
                                 skill_tags=["fluency", "grammar", "vocabulary"]))
            changed += 1
            continue
        rubric = dict(row.rubric or {})
        if rubric.get("cues") != cues:
            rubric["cues"] = cues
            row.rubric = rubric
            changed += 1
    await session.commit()
    return changed


async def install_classification(session) -> int:
    """Label the existing bank, and add the industry-specific items.

    Two separate jobs that belong together because both are about the Phase 6
    classification columns.

    **Backfill only what is true.** Every item in the general bank is English
    and belongs to no vertical, so `language` and `industry` are recorded.
    `topic` and `role` are *not* backfilled: nobody decided them when the
    items were written, and inferring them from keywords would put a guess in
    a column an admin will later filter on. An empty value means unknown, and
    `selection.matches` treats unknown as eligible.
    """
    from app.industry_bank import READ_ALOUD, SHORT_ANSWERS

    labelled = 0
    rows = (await session.execute(select(TaskItem))).scalars().all()
    for row in rows:
        if not row.language:
            row.language = "en"
            labelled += 1
        if not row.industry:
            row.industry = "general"
            labelled += 1
    await session.commit()

    existing = set((await session.execute(
        select(TaskItem.reference_text))).scalars().all())

    added = 0
    for industry, role, topic, sentence, difficulty in READ_ALOUD:
        if sentence in existing:
            continue
        session.add(TaskItem(
            task_type="read_aloud", prompt_text=sentence,
            reference_text=sentence, word_count=len(sentence.split()),
            difficulty=difficulty, skill_tags=["pronunciation", "fluency"],
            industry=industry, role=role, topic=topic, language="en"))
        added += 1

    heard = set((await session.execute(
        select(TaskItem.prompt_text).where(
            TaskItem.task_type == "short_answer"))).scalars().all())
    for industry, role, topic, question, accepted, difficulty in SHORT_ANSWERS:
        if question in heard:
            continue
        session.add(TaskItem(
            task_type="short_answer", prompt_text=question,
            reference_text=accepted[0], rubric={"key_points": list(accepted)},
            word_count=1, difficulty=difficulty,
            skill_tags=["listening", "vocabulary"],
            industry=industry, role=role, topic=topic, language="en"))
        added += 1

    await session.commit()
    return added


async def install_voice_change(session) -> int:
    """Add the active/passive voice-change bank. Idempotent, keyed on the stem.

    A written multiple-choice grammar item: a sentence and four rewrites, one
    correct. Stored as QuizItems in its own category so the selector serves it
    only to a voice-change section and never as a reply-choice or vocabulary
    item.
    """
    existing = set((await session.execute(
        select(QuizItem.stem).where(
            QuizItem.category == "voice_change"))).scalars().all())

    added = 0
    for n, (stem, options, correct, why) in enumerate(VOICE_CHANGE_ITEMS):
        if stem in existing:
            continue
        rolled, key = _rotate_options(n, list(options), correct)
        session.add(QuizItem(
            category="voice_change", stem=stem,
            options=rolled, correct_index=key, explanation=why,
            passage_id="", seconds_allowed=0, difficulty=0.2,
            skill_tags=["grammar"]))
        added += 1
    await session.commit()
    return added


async def install_selection(session) -> int:
    """Response selection and vocabulary in context.

    Response selection needs a ListeningPassage per item, because the line is
    heard and not read -- one passage per question rather than one shared by
    several, which is the difference between it and comprehension. Vocabulary
    items are standalone: the sentence is the context and it is on the screen.
    """
    added = 0

    heard = set((await session.execute(
        select(ListeningPassage.transcript)
        .where(ListeningPassage.kind == "exchange"))).scalars().all())
    for line, replies, correct, why in RESPONSE_ITEMS:
        if line in heard:
            continue
        passage = ListeningPassage(
            title="Something said to you", kind="exchange", transcript=line,
            plays_allowed=1, approx_seconds=max(4, len(line.split()) // 2))
        session.add(passage)
        await session.flush()
        rolled, key = _rotate_options(added, list(replies), correct)
        session.add(QuizItem(
            category="response_selection",
            stem="Which reply fits best?",
            options=rolled, correct_index=key, explanation=why,
            passage_id=passage.id, seconds_allowed=20,
            difficulty=0.2, skill_tags=["listening", "vocabulary"]))
        added += 1

    seen = set((await session.execute(
        select(QuizItem.stem).where(
            QuizItem.category == "vocabulary_in_context"))).scalars().all())
    for n, (sentence, word, senses, correct, why) in enumerate(VOCABULARY_ITEMS):
        stem = (f"{sentence}" + chr(10) * 2
                + f"What does “{word}” mean here?")
        if stem in seen:
            continue
        rolled, key = _rotate_options(n, list(senses), correct)
        session.add(QuizItem(
            category="vocabulary_in_context", stem=stem,
            options=rolled, correct_index=key, explanation=why,
            # Standalone: no passage, so nothing groups it. The sentence is
            # the context and it is right there in the stem.
            passage_id="", seconds_allowed=0,
            difficulty=0.1, skill_tags=["vocabulary"]))
        added += 1

    await session.commit()
    return added


async def install_reconstructions(session) -> int:
    """Passage reconstruction items. Idempotent, keyed on title.

    WritingPrompt rows with kind "reconstruction": the passage goes in
    `scenario` and the idea units in `key_points`. The kind is what keeps
    them out of an Email Writing section and email briefs out of this one.
    """
    existing = set((await session.execute(
        select(WritingPrompt.title))).scalars().all())

    added = 0
    for title, passage, units in RECONSTRUCTIONS:
        if title in existing:
            continue
        session.add(WritingPrompt(
            title=title, kind="reconstruction", difficulty=0.2,
            # No word floor. A short reconstruction is a low score, not an
            # unscorable one, and the reconstruction scorer says so.
            min_words=0, suggested_minutes=2,
            scenario=passage,
            prompt="Write what the passage said, in your own words.",
            key_points=[{"point": point, "cues": list(cues)}
                        for point, cues in units],
        ))
        added += 1
    await session.commit()
    return added


async def install_phase4_everywhere() -> None:
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())
    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            spoken = await top_up_item_bank(s)
            chosen = await install_selection(s)
            rebuilt = await install_reconstructions(s)
            classified = await install_classification(s)
        print(f"  {slug}: +{spoken} task items, +{chosen} selection items, "
              f"+{rebuilt} reconstruction passages, "
              f"+{classified} industry items")


async def install_completions_everywhere() -> None:
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())
    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            added = await install_completions(s)
        print(f"  {slug}: +{added} sentence-completion items")


async def install_writing(session) -> int:
    """Add any missing writing prompts. Idempotent, keyed on title."""
    existing = set((await session.execute(
        select(WritingPrompt.title))).scalars().all())

    added = 0
    for (title, kind, difficulty, min_words, minutes,
         scenario, prompt, key_points) in WRITING_PROMPTS:
        if title in existing:
            continue
        session.add(WritingPrompt(
            title=title, kind=kind, difficulty=difficulty,
            min_words=min_words, suggested_minutes=minutes,
            scenario=scenario, prompt=prompt, key_points=list(key_points),
        ))
        added += 1
    await session.commit()
    return added


async def install_writing_everywhere() -> None:
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())
    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            added = await install_writing(s)
        print(f"  {slug}: +{added} writing prompts")


async def install_reading_everywhere() -> None:
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())
    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            added = await install_reading(s)
        print(f"  {slug}: +{added} reading passages")


async def install_listening_everywhere() -> None:
    """Retrofit the listening bank onto every existing institution.

    Same reasoning as install_formats: a --reset would install this and also
    delete every attempt, score and consent record on the way, which is not an
    acceptable price for adding content.
    """
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())

    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            added = await install_listening(s)
        print(f"  {slug}: +{added} listening passages")


async def install_formats() -> None:
    """Add the company rounds to every existing institution.

    The path for an estate that was provisioned before these rounds existed.
    A full ``--reset`` would install them too, and would also delete every
    attempt, score and consent record on the way -- which is not an acceptable
    price for adding content.
    """
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())

    for slug in slugs:
        await upgrade_tenant_schema(slug)
        async with tenant_sessionmaker(slug)() as s:
            added = await top_up_item_bank(s)
            retired = await retire_superseded_items(s)
            out = await seed_format_profiles(s)
            sync = await resync_format_profiles(s)
            gone = await retire_dropped_profiles(s)
            for code in gone:
                print(f"      retired, no blueprint any more: {code}")
            if sync["resynced"]:
                out["repaired"] = out["repaired"] + [
                    f"{c} (resynced)" for c in sync["resynced"]]
            listening_added = await install_listening(s)
            reading_added = await install_reading(s)
            writing_added = await install_writing(s)
            await install_completions(s)
            await install_topic_cues(s)
            await install_selection(s)
            await install_reconstructions(s)
            await install_classification(s)
            for stale in sync["skipped"]:
                print(f"      left alone, has attempts: {stale}")
        if listening_added or reading_added:
            print(f"      +{listening_added} listening, "
                  f"+{reading_added} reading, +{writing_added} writing")
        made = ", ".join(out["created"]) or "none"
        fixed = ", ".join(out["repaired"]) or "none"
        print(f"  {slug}: +{added} items, -{len(retired)} superseded; "
              f"created {made}; repaired {fixed}")
        for line in retired:
            print(f"      retired {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed CommunicationIQ")
    parser.add_argument("--reset", action="store_true",
                        help="drop the control plane and both tenant schemas first")
    parser.add_argument("--formats", "--company-rounds", dest="formats",
                        action="store_true",
                        help="add every blueprinted profile (company rounds and "
                             "vendor-style simulations) to existing institutions, "
                             "and fill any that were seeded empty")
    parser.add_argument("--phase4", dest="phase4", action="store_true",
                        help="add the spoken-question, response-selection, "
                             "vocabulary and reconstruction banks")
    parser.add_argument("--completions", dest="completions", action="store_true",
                        help="add the sentence-completion bank to existing "
                             "institutions without touching anything else")
    parser.add_argument("--writing", dest="writing", action="store_true",
                        help="add the writing prompt bank to existing "
                             "institutions without touching anything else")
    parser.add_argument("--reading", dest="reading", action="store_true",
                        help="add the reading passage bank to existing "
                             "institutions without touching anything else")
    parser.add_argument("--listening", dest="listening", action="store_true",
                        help="add the listening passage bank to existing "
                             "institutions without touching anything else")
    parser.add_argument("--if-empty", dest="if_empty", action="store_true",
                        help="seed only when no institution exists yet — safe to "
                             "run on every start, so a fresh deployment comes up "
                             "populated and a restart never wipes it")
    args = parser.parse_args()

    if args.completions:
        asyncio.run(install_completions_everywhere())
    elif args.phase4:
        asyncio.run(install_phase4_everywhere())
    elif args.writing:
        asyncio.run(install_writing_everywhere())
    elif args.reading:
        asyncio.run(install_reading_everywhere())
    elif args.listening:
        asyncio.run(install_listening_everywhere())
    elif args.formats:
        asyncio.run(install_formats())
    elif args.if_empty:
        async def _once() -> None:
            if await is_empty():
                print("No institutions found — seeding the demo estate.")
                await main(reset=False)
            else:
                print("Already seeded; leaving the data alone.")
        asyncio.run(_once())
    else:
        asyncio.run(main(args.reset))
