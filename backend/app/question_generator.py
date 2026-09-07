"""AI Question Generator using Groq API.

Generates grammar, vocabulary, reading, writing, and listening questions
automatically. Designed to run on a schedule (e.g., daily at 3 AM) to keep
the question bank fresh with new content for all companies and general use.

Uses Groq's fast inference for question generation. Each run produces
5 questions per category (grammar, vocabulary) and 2 reading passages
with 5 questions each, for both general and company-specific use.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

# Groq API configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

COMPANIES = ["Accenture", "TCS", "Cognizant", "Wipro", "Infosys", "HCL", "Tech Mahindra", "Capgemini"]


def _assign_difficulty() -> float:
    """Assign a difficulty level with a realistic distribution:
    ~30% easy, ~40% medium, ~30% hard.
    """
    r = random.random()
    if r < 0.30:
        return round(random.uniform(0.1, 0.33), 2)   # easy
    elif r < 0.70:
        return round(random.uniform(0.34, 0.66), 2)  # medium
    else:
        return round(random.uniform(0.67, 0.95), 2)  # hard


GRAMMAR_TOPICS = [
    "subject-verb agreement", "tense consistency", "article usage",
    "preposition selection", "passive voice", "reported speech",
    "conditionals", "relative clauses", "gerunds vs infinitives",
    "parallel structure", "modifier placement", "verb forms",
]

VOCABULARY_TOPICS = [
    "business English", "technology terms", "workplace communication",
    "academic vocabulary", "formal register", "idioms and phrasal verbs",
    "collocations", "word roots and affixes", "contextual meaning",
    "synonyms and antonyms", "industry-specific terms", "professional jargon",
]


def _get_api_key() -> str:
    """Get Groq API key from environment."""
    return os.environ.get("GROQ_API_KEY", "")


async def _call_groq(prompt: str, system: str = "You are an expert English language test question writer.", temperature: float = 0.7) -> str:
    """Call Groq API with a prompt and return the response text."""
    api_key = _get_api_key()
    if not api_key:
        log.warning("GROQ_API_KEY not set, skipping AI question generation")
        return ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def generate_grammar_questions(count: int = 5, company: str = "") -> list[dict]:
    """Generate grammar MCQ questions using Groq API."""
    topic = random.choice(GRAMMAR_TOPICS)
    company_ctx = f" specifically about {company} workplace scenarios" if company else ""
    prompt = f"""Generate exactly {count} multiple-choice grammar questions about "{topic}"{company_ctx}.

Return ONLY a JSON array (no markdown fences, no explanation) with this exact format:
[
  {{
    "stem": "question text here",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_index": 0,
    "explanation": "Brief explanation of the correct answer"
  }}
]

Rules:
- Each question must have exactly 4 options
- correct_index is 0-3
- Questions should be appropriate for college students preparing for placement
- Mix difficulty levels: some easy (basic grammar rules), some medium (tricky cases), some hard (subtle errors)
- Include real workplace/academic contexts"""

    try:
        raw = await _call_groq(prompt)
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        items = json.loads(raw)
        if isinstance(items, list):
            return items[:count]
    except Exception:
        log.exception("Failed to generate grammar questions via Groq")
    return []


async def generate_vocabulary_questions(count: int = 5, company: str = "") -> list[dict]:
    """Generate vocabulary MCQ questions using Groq API."""
    topic = random.choice(VOCABULARY_TOPICS)
    company_ctx = f" in the context of {company} recruitment" if company else ""
    prompt = f"""Generate exactly {count} multiple-choice vocabulary questions about "{topic}"{company_ctx}.

Return ONLY a JSON array (no markdown fences, no explanation) with this exact format:
[
  {{
    "stem": "Choose the word that best fits: 'The manager _____ the proposal during the meeting.'",
    "options": ["reviewed", "revue", "revising", "reviews"],
    "correct_index": 0,
    "explanation": "Brief explanation"
  }}
]

Rules:
- Each question must have exactly 4 options
- correct_index is 0-3
- Test word meaning, usage, or context
- Mix difficulty levels: some easy (common words), some medium (business vocabulary), some hard (advanced/academic)
- Appropriate for college placement preparation"""

    try:
        raw = await _call_groq(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        items = json.loads(raw)
        if isinstance(items, list):
            return items[:count]
    except Exception:
        log.exception("Failed to generate vocabulary questions via Groq")
    return []


async def generate_reading_passage(company: str = "") -> dict | None:
    """Generate a reading passage with 5 comprehension questions."""
    company_ctx = f" related to {company} and its industry" if company else ""
    prompt = f"""Generate one reading comprehension passage{company_ctx} with 5 questions.

Return ONLY a JSON object (no markdown fences) with this exact format:
{{
  "title": "Passage Title",
  "paragraph": "The full passage text (150-250 words). Make it informative and workplace-relevant.",
  "questions": [
    {{
      "question": "Question text about the passage",
      "options": ["Answer A", "Answer B", "Answer C", "Answer D"],
      "correctAnswer": 0,
      "marks": 1
    }}
  ]
}}

Rules:
- Passage should be 150-250 words
- Exactly 5 comprehension questions
- Questions test understanding, inference, and detail recall
- Each question has 4 options
- correctAnswer is 0-3"""

    try:
        raw = await _call_groq(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        data = json.loads(raw)
        if isinstance(data, dict) and "paragraph" in data:
            return data
    except Exception:
        log.exception("Failed to generate reading passage via Groq")
    return None


async def generate_writing_prompt(company: str = "") -> dict | None:
    """Generate a writing prompt (email or essay)."""
    kind = random.choice(["email", "essay"])
    company_ctx = f" in a {company} workplace context" if company else ""

    if kind == "email":
        prompt = f"""Generate a professional email writing prompt{company_ctx}.
Return ONLY a JSON object (no markdown fences):
{{
  "title": "Short title for the task",
  "kind": "email",
  "prompt": "Write an email to [person] about [topic]. Include specific details about [context].",
  "scenario": "A brief workplace scenario context",
  "key_points": ["Point 1 to include", "Point 2 to include", "Point 3 to include"],
  "min_words": 80
}}"""
    else:
        prompt = f"""Generate an essay writing prompt{company_ctx}.
Return ONLY a JSON object (no markdown fences):
{{
  "title": "Short title for the task",
  "kind": "essay",
  "prompt": "Write an essay discussing [topic]. Consider [aspects].",
  "scenario": "A brief academic/workplace context",
  "key_points": ["Point 1 to address", "Point 2 to address", "Point 3 to address"],
  "min_words": 200
}}"""

    try:
        raw = await _call_groq(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        data = json.loads(raw)
        if isinstance(data, dict) and "prompt" in data:
            return data
    except Exception:
        log.exception("Failed to generate writing prompt via Groq")
    return None


async def generate_listening_passage(company: str = "") -> dict | None:
    """Generate a listening passage with transcript and comprehension questions."""
    company_ctx = f" in a {company} workplace context" if company else ""
    prompt = f"""Generate a short listening passage{company_ctx} with comprehension questions.
Return ONLY a JSON object (no markdown fences):
{{
  "title": "Short title for the audio",
  "transcript": "A 150-200 word passage that would be read aloud in a workplace setting",
  "kind": "short_talk",
  "approx_seconds": 45,
  "questions": [
    {{"question": "Question text", "options": ["A", "B", "C", "D"], "correctAnswer": 0}}
  ]
}}"""
    try:
        raw = await _call_groq(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        data = json.loads(raw.strip())
        if isinstance(data, dict) and "transcript" in data:
            return data
    except Exception:
        log.exception("Failed to generate listening passage via Groq")
    return None


def _assign_speaking_task_type() -> str:
    """Pick a random speaking task type."""
    return random.choice([
        "open_response", "read_aloud", "repeat_sentence",
        "short_answer", "story_retell", "sentence_build",
    ])


async def generate_speaking_prompt(company: str = "") -> dict | None:
    """Generate a speaking prompt."""
    task_type = _assign_speaking_task_type()
    company_ctx = f" in a {company} context" if company else ""
    prompt = f"""Generate a {task_type.replace('_', ' ')} speaking prompt{company_ctx}.
Return ONLY a JSON object (no markdown fences):
{{
  "task_type": "{task_type}",
  "prompt_text": "What the student should read, repeat, or say",
  "reference_text": "Expected answer or reference for scoring",
  "audio_key": ""
}}"""
    try:
        raw = await _call_groq(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        data = json.loads(raw.strip())
        if isinstance(data, dict) and "prompt_text" in data:
            data["task_type"] = task_type
            return data
    except Exception:
        log.exception("Failed to generate speaking prompt via Groq")
    return None


async def run_daily_generation(tenant_session=None):
    """Run the daily question generation cycle.

    Generates:
    - 5 grammar questions (general)
    - 5 vocabulary questions (general)
    - 2 reading passages with questions (general)
    - 2 writing prompts (general)
    - For each company: 3 grammar + 2 vocabulary questions

    Total: ~50 new questions per day.
    """
    from app.models.tenant import QuizItem, ReadingPassage, WritingPrompt, ListeningPassage, TaskItem
    from app.config import settings

    log.info("Starting daily AI question generation")

    generated = {"grammar": 0, "vocabulary": 0, "reading": 0, "writing": 0}

    # 1. General grammar questions
    grammar_qs = await generate_grammar_questions(5)
    for q in grammar_qs:
        try:
            item = QuizItem(
                category="grammar",
                stem=q.get("stem", ""),
                options=q.get("options", []),
                correct_index=q.get("correct_index", 0),
                explanation=q.get("explanation", ""),
                difficulty=_assign_difficulty(),
                company="",
                status="published",
            )
            await item.create()
            generated["grammar"] += 1
        except Exception:
            log.exception("Failed to save grammar question")

    # 2. General vocabulary questions
    vocab_qs = await generate_vocabulary_questions(5)
    for q in vocab_qs:
        try:
            item = QuizItem(
                category="vocabulary",
                stem=q.get("stem", ""),
                options=q.get("options", []),
                correct_index=q.get("correct_index", 0),
                explanation=q.get("explanation", ""),
                difficulty=_assign_difficulty(),
                company="",
                status="published",
            )
            await item.create()
            generated["vocabulary"] += 1
        except Exception:
            log.exception("Failed to save vocabulary question")

    # 3. General reading passages
    for _ in range(2):
        passage_data = await generate_reading_passage()
        if passage_data:
            try:
                passage = ReadingPassage(
                    title=passage_data.get("title", "AI-Generated Passage"),
                    paragraph=passage_data.get("paragraph", ""),
                    company="",
                    status="published",
                )
                await passage.create()
                # Create linked quiz items for the passage questions
                for qi, q in enumerate(passage_data.get("questions", [])):
                    item = QuizItem(
                        category="reading_comprehension",
                        stem=q.get("question", ""),
                        options=q.get("options", []),
                        correct_index=q.get("correctAnswer", 0),
                        passage_id=str(passage.id),
                        difficulty=_assign_difficulty(),
                        company="",
                        status="published",
                    )
                    await item.create()
                generated["reading"] += 1
            except Exception:
                log.exception("Failed to save reading passage")

    # 4. General writing prompts
    for _ in range(2):
        prompt_data = await generate_writing_prompt()
        if prompt_data:
            try:
                wp = WritingPrompt(
                    title=prompt_data.get("title", "AI-Generated Prompt"),
                    kind=prompt_data.get("kind", "essay"),
                    prompt=prompt_data.get("prompt", ""),
                    scenario=prompt_data.get("scenario", ""),
                    key_points=prompt_data.get("key_points", []),
                    min_words=prompt_data.get("min_words", 100),
                    company="",
                    status="published",
                )
                await wp.create()
                generated["writing"] += 1
            except Exception:
                log.exception("Failed to save writing prompt")

    # 4b. General listening passages
    for _ in range(2):
        listen_data = await generate_listening_passage()
        if listen_data:
            try:
                lp = ListeningPassage(
                    title=listen_data.get("title", "AI-Generated Listening"),
                    transcript=listen_data.get("transcript", ""),
                    company="",
                    status="published",
                )
                await lp.create()
                for qi, q in enumerate(listen_data.get("questions", [])):
                    item = QuizItem(
                        category="audio_comprehension",
                        stem=q.get("question", ""),
                        options=q.get("options", []),
                        correct_index=q.get("correctAnswer", 0),
                        passage_id=str(lp.id),
                        difficulty=_assign_difficulty(),
                        company="",
                        status="published",
                    )
                    await item.create()
                generated["listening"] = generated.get("listening", 0) + 1
            except Exception:
                log.exception("Failed to save listening passage")

    # 4c. General speaking prompts
    for _ in range(3):
        speak_data = await generate_speaking_prompt()
        if speak_data:
            try:
                tp = TaskItem(
                    task_type=speak_data.get("task_type", "open_response"),
                    prompt_text=speak_data.get("prompt_text", ""),
                    reference_text=speak_data.get("reference_text", ""),
                    company="",
                    difficulty=_assign_difficulty(),
                    status="published",
                )
                await tp.create()
                generated["speaking"] = generated.get("speaking", 0) + 1
            except Exception:
                log.exception("Failed to save speaking prompt")

    # 5. Company-specific questions (3 grammar + 2 vocabulary per company)
    for company in COMPANIES:
        grammar_qs = await generate_grammar_questions(3, company)
        for q in grammar_qs:
            try:
                item = QuizItem(
                    category="grammar",
                    stem=q.get("stem", ""),
                    options=q.get("options", []),
                    correct_index=q.get("correct_index", 0),
                    explanation=q.get("explanation", ""),
                    difficulty=_assign_difficulty(),
                    company=company,
                    status="published",
                )
                await item.create()
                generated["grammar"] += 1
            except Exception:
                log.exception(f"Failed to save {company} grammar question")

        vocab_qs = await generate_vocabulary_questions(2, company)
        for q in vocab_qs:
            try:
                item = QuizItem(
                    category="vocabulary",
                    stem=q.get("stem", ""),
                    options=q.get("options", []),
                    correct_index=q.get("correct_index", 0),
                    explanation=q.get("explanation", ""),
                    difficulty=_assign_difficulty(),
                    company=company,
                    status="published",
                )
                await item.create()
                generated["vocabulary"] += 1
            except Exception:
                log.exception(f"Failed to save {company} vocabulary question")

        # 1 reading passage per company
        passage_data = await generate_reading_passage(company)
        if passage_data:
            try:
                passage = ReadingPassage(
                    title=f"{company}: {passage_data.get('title', 'AI Passage')}",
                    paragraph=passage_data.get("paragraph", ""),
                    company=company,
                    status="published",
                )
                await passage.create()
                for q in passage_data.get("questions", []):
                    item = QuizItem(
                        category="reading_comprehension",
                        stem=q.get("question", ""),
                        options=q.get("options", []),
                        correct_index=q.get("correctAnswer", 0),
                        passage_id=str(passage.id),
                        difficulty=_assign_difficulty(),
                        company=company,
                        status="published",
                    )
                    await item.create()
                generated["reading"] += 1
            except Exception:
                log.exception(f"Failed to save {company} reading passage")

        # 1 writing prompt per company
        prompt_data = await generate_writing_prompt(company)
        if prompt_data:
            try:
                wp = WritingPrompt(
                    title=f"{company}: {prompt_data.get('title', 'AI Prompt')}",
                    kind=prompt_data.get("kind", "essay"),
                    prompt=prompt_data.get("prompt", ""),
                    scenario=prompt_data.get("scenario", ""),
                    key_points=prompt_data.get("key_points", []),
                    min_words=prompt_data.get("min_words", 100),
                    company=company,
                    status="published",
                )
                await wp.create()
                generated["writing"] += 1
            except Exception:
                log.exception(f"Failed to save {company} writing prompt")

        # 1 listening passage per company
        listen_data = await generate_listening_passage(company)
        if listen_data:
            try:
                lp = ListeningPassage(
                    title=f"{company}: {listen_data.get('title', 'AI Listening')}",
                    transcript=listen_data.get('transcript', ''),
                    company=company,
                    status="published",
                )
                await lp.create()
                for q in listen_data.get('questions', []):
                    item = QuizItem(
                        category="audio_comprehension",
                        stem=q.get('question', ''),
                        options=q.get('options', []),
                        correct_index=q.get('correctAnswer', 0),
                        passage_id=str(lp.id),
                        difficulty=_assign_difficulty(),
                        company=company,
                        status="published",
                    )
                    await item.create()
                generated["listening"] = generated.get("listening", 0) + 1
            except Exception:
                log.exception(f"Failed to save {company} listening passage")

        # 2 speaking prompts per company
        for _ in range(2):
            speak_data = await generate_speaking_prompt(company)
            if speak_data:
                try:
                    tp = TaskItem(
                        task_type=speak_data.get("task_type", "open_response"),
                        prompt_text=speak_data.get("prompt_text", ""),
                        reference_text=speak_data.get("reference_text", ""),
                        company=company,
                        difficulty=_assign_difficulty(),
                        status="published",
                    )
                    await tp.create()
                    generated["speaking"] = generated.get("speaking", 0) + 1
                except Exception:
                    log.exception(f"Failed to save {company} speaking prompt")

        # Small delay between companies to avoid rate limits
        await asyncio.sleep(0.5)

    total = sum(generated.values())
    log.info("Daily generation complete: %s (total: %d)", generated, total)
    return generated


# --- Scheduler ---

_scheduler_task = None


async def _scheduler_loop():
    """Background loop that runs daily generation at 3:00 AM UTC."""
    import app.db as db
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Calculate seconds until next 3:00 AM UTC
            target_hour = 3
            if now.hour >= target_hour:
                # Tomorrow at 3 AM
                from datetime import timedelta
                next_run = (now + timedelta(days=1)).replace(hour=target_hour, minute=0, second=0, microsecond=0)
            else:
                next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)

            wait_seconds = (next_run - now).total_seconds()
            log.info("Next AI question generation at %s (in %.0f seconds)", next_run.isoformat(), wait_seconds)
            await asyncio.sleep(wait_seconds)

            # Run generation
            log.info("Running scheduled AI question generation...")
            try:
                await run_daily_generation()
            except Exception:
                log.exception("Scheduled question generation failed")

        except asyncio.CancelledError:
            log.info("Question generator scheduler cancelled")
            break
        except Exception:
            log.exception("Scheduler error, retrying in 1 hour")
            await asyncio.sleep(3600)


def start_scheduler():
    """Start the background scheduler. Call once during app lifespan."""
    global _scheduler_task
    if _scheduler_task is None:
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        log.info("AI question generator scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        _scheduler_task = None
        log.info("AI question generator scheduler stopped")
