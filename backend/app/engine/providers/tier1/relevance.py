"""Tier 1 — content coverage and staying on topic (ENG-11).

Two different questions wearing one contract:

* **Story Retell** has a right answer in the loose sense — a set of key points
  the item author wrote down. Coverage is how many of them came back.
* **Open Response** has no right answer at all. The only content judgement
  that can honestly be made is whether the student addressed the prompt, and
  even that is reported as a flag rather than folded into a score.

The rubric is the whole authority. ENG-11 is explicit that content must be
rubric-constrained and never scored on sole model judgement — so this matches
against key points a human wrote, and where there is no rubric it says it
cannot score rather than producing a number from nothing.
"""
from __future__ import annotations

import re

from app.engine.contracts.types import ProviderMeta, RelevanceResult

SCALE_MIN = 0.0
SCALE_MAX = 100.0

# Words that carry no topic information. Matching on these would make any
# answer look like it covered any point.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "because",
    "as", "of", "at", "by", "for", "with", "about", "into", "through", "during",
    "to", "from", "in", "on", "off", "over", "under", "again", "further",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "have", "has", "had", "having", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must", "i", "me", "my", "we", "us", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "this", "that", "these", "those", "there", "here", "what",
    "which", "who", "when", "where", "how", "why", "all", "any", "both",
    "each", "more", "most", "some", "such", "no", "not", "only", "own", "same",
    "very", "just", "also", "very", "too", "s", "t",
}

_WORD = re.compile(r"[^\w']+")

# A key point counts as covered when this share of its content words appear.
# Not all of them: "the manager approved the budget" and "manager approved
# budget" are the same point, and a student who paraphrases has not failed.
COVERAGE_THRESHOLD = 0.5

# Below this overlap with the prompt, and with enough speech to judge by, an
# open response is probably about something else.
OFF_TOPIC_OVERLAP = 0.08

# How much speech it takes before "off topic" is a fair call rather than a
# guess. Twenty words is roughly two sentences — enough that a student who
# addressed the prompt would have touched it by now, and short enough that a
# genuinely wandering answer gets caught. Below it the honest output is "not
# enough to judge", not a verdict.
MIN_WORDS_TO_JUDGE = 20

# A retell needs less, because there is a concrete rubric to miss rather than
# a topic to wander from: zero coverage across a couple of sentences is
# already evidence.
MIN_RETELL_WORDS = 8


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.sub(" ", (text or "").lower()).split()
            if w and w not in STOPWORDS and len(w) > 2}


class RubricRelevance:
    """Capability: ``content_relevance``."""

    contract_version = "1.0"
    provider_key = "rubric_coverage"
    version = "0.1.0"

    async def score(self, transcript: str, *, rubric: dict,
                    task_type: str = "") -> RelevanceResult:
        return self.analyse(transcript, rubric or {}, task_type)

    def analyse(self, transcript: str, rubric: dict,
                task_type: str = "") -> RelevanceResult:
        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        said = content_words(transcript)
        spoken_words = len((transcript or "").split())

        key_points = [p for p in (rubric.get("key_points") or []) if str(p).strip()]

        if key_points:
            if task_type == "short_answer":
                return self._any_of(said, key_points, meta)
            return self._coverage(said, key_points, spoken_words, meta)
        if task_type == "open_response":
            return self._on_topic(said, rubric, spoken_words, meta)

        # No rubric and not an open response: nothing to judge against.
        return RelevanceResult(score=SCALE_MIN, coverage=0.0, meta=meta)

    def _any_of(self, said: set[str], accepted: list,
                meta: ProviderMeta) -> RelevanceResult:
        """Short Answer: the rubric lists alternatives, not a checklist.

        "What do you check before boarding a train?" accepts ticket, platform
        or timing. Scoring a student who said "my ticket" as one-of-three
        correct would mark down a right answer for not also giving the other
        two — which is not what the question asked.
        """
        matched = [str(a) for a in accepted if content_words(str(a)) & said]
        correct = bool(matched)
        return RelevanceResult(
            score=SCALE_MAX if correct else SCALE_MIN,
            key_points=[{"point": " / ".join(str(a) for a in accepted),
                         "covered": correct,
                         "matched_words": sorted(
                             {w for a in matched for w in content_words(a)} & said),
                         "share": 1.0 if correct else 0.0}],
            coverage=1.0 if correct else 0.0,
            off_topic=not correct,
            confidence=0.7,
            meta=meta,
        )

    def _coverage(self, said: set[str], key_points: list, spoken_words: int,
                  meta: ProviderMeta) -> RelevanceResult:
        """How many of the author's key points came back."""
        results: list[dict] = []
        matched = 0

        for point in key_points:
            wanted = content_words(str(point))
            if not wanted:
                continue
            hits = wanted & said
            share = len(hits) / len(wanted)
            covered = share >= COVERAGE_THRESHOLD
            matched += int(covered)
            results.append({
                "point": str(point),
                "covered": covered,
                # Which words carried it — this is what makes the report
                # reviewable rather than a verdict to be taken on faith.
                "matched_words": sorted(hits),
                "share": round(share, 2),
            })

        total = len(results) or 1
        coverage = matched / total
        score = SCALE_MIN + coverage * (SCALE_MAX - SCALE_MIN)

        # A retell so short it cannot have covered the points is reported with
        # low confidence rather than a confident zero.
        confidence = 0.6 if spoken_words >= 20 else 0.3

        return RelevanceResult(
            score=round(score, 1), key_points=results,
            coverage=round(coverage, 3),
            off_topic=coverage == 0.0 and spoken_words >= MIN_RETELL_WORDS,
            confidence=confidence, meta=meta,
        )

    def _on_topic(self, said: set[str], rubric: dict, spoken_words: int,
                  meta: ProviderMeta) -> RelevanceResult:
        """Did they address the prompt at all?

        Not scored — flagged. There is no defensible way to grade the content
        of a free opinion, and pretending otherwise would be the "sole LLM
        judgement" the requirement rules out.
        """
        prompt = content_words(str(rubric.get("prompt", "")))
        if not prompt or spoken_words < MIN_WORDS_TO_JUDGE:
            return RelevanceResult(score=SCALE_MIN, coverage=0.0,
                                   confidence=0.0, meta=meta)

        overlap = len(prompt & said) / len(prompt)
        off_topic = overlap < OFF_TOPIC_OVERLAP

        return RelevanceResult(
            score=SCALE_MIN, coverage=round(overlap, 3), off_topic=off_topic,
            key_points=[{"point": "addressed the prompt", "covered": not off_topic,
                         "matched_words": sorted(prompt & said),
                         "share": round(overlap, 2)}],
            # Zero on purpose: this is a flag, not a score, and the pipeline
            # must not fold it into the overall.
            confidence=0.0, meta=meta,
        )
