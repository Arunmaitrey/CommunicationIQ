"""Tier 1 — goodness of pronunciation (ENG-04).

How clearly was each word articulated, measured by forced-aligning the target
text against a wav2vec2 CTC model's own frame posteriors and reading off how
confident the acoustic model was at each aligned frame. That is the classic
GOP construction: the log-posterior of the target unit given the audio.

**It is character-level, not phoneme-level.** The model's vocabulary is 32
characters, so a word's score is the mean posterior over its aligned letters
rather than its phones. That is a real approximation and it is named as one —
a phoneme-level GOP, and with it the per-phoneme confusion pairs that DIAG-03
wants, needs a phoneme-output acoustic model and a grapheme-to-phoneme front
end. Neither is built.

**It scores intelligibility, not nativeness.** The question it answers is "how
confidently did an English recogniser hear this word here", which is close to
"would a listener catch it". It is not "how close to a native reference", and
the difference is the whole reason this product exists. An accented speaker who
articulates clearly scores well.

Distinct from word accuracy on purpose: accuracy asks whether the right words
came out at all, this asks how clearly they were said. A word can be recovered
correctly and still be mumbled, and those are different things to tell a
student.
"""
from __future__ import annotations

import logging
import re
import threading

import numpy as np

from app.engine.contracts.types import (AlignmentResult, AudioRef, ProviderMeta,
                                        PronunciationResult)
from app.engine.providers.tier1.accuracy import normalise
from app.engine.providers.tier1.asr import SAMPLE_RATE, load_samples

log = logging.getLogger(__name__)

SCALE_MIN = 20.0
SCALE_MAX = 80.0

MODEL_NAME = "facebook/wav2vec2-base-960h"

# Mean posterior below this and the word was not clearly articulated. Above the
# upper bound it is as clear as the model ever gets. Between them the score
# moves linearly, so the number a student sees tracks something real.
POSTERIOR_FLOOR = 0.15
POSTERIOR_CEILING = 0.90

# Words the model was unsure of across the board usually mean a bad recording
# rather than bad speech, so confidence drops instead of the score.
NOISY_MEAN_POSTERIOR = 0.25

# Silence padded onto both ends before aligning.
#
# Not cosmetic. CTC forced alignment needs frames to place the target's first
# and last units into, and a recording that stops the instant the speaker does
# — which is exactly what a runner ending on the timer produces — leaves none.
# Measured on a clean clip: the final word scored 0.08 posterior against a tight
# end and 0.99 with a second of silence after it. Without this pad the product
# would tell most students their last word was mispronounced.
EDGE_PAD_SECONDS = 1.0

_model = None
_processor = None
_lock = threading.Lock()

_STRIP = re.compile(r"[^A-Z' ]+")


def _load():
    """The acoustic model, loaded once per process."""
    global _model, _processor
    if _model is not None:
        return _model, _processor
    with _lock:
        if _model is not None:
            return _model, _processor
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        torch.set_grad_enabled(False)
        _processor = Wav2Vec2Processor.from_pretrained(MODEL_NAME)
        _model = Wav2Vec2ForCTC.from_pretrained(MODEL_NAME).eval()
        log.info("loaded pronunciation model %s", MODEL_NAME)
        return _model, _processor


def warm() -> None:
    try:
        _load()
    except Exception as exc:  # noqa: BLE001
        log.warning("pronunciation model unavailable (%s) — the dimension stays "
                    "unscored rather than guessed", exc)


def reset() -> None:
    """Tests only."""
    global _model, _processor
    with _lock:
        _model = _processor = None


def _tokenisable(text: str) -> str:
    """Uppercase letters and spaces only — the model's vocabulary.

    Digits are spelled out first, reusing the same normalisation the accuracy
    provider uses, so "9" and "nine" align identically.
    """
    spelled = " ".join(normalise(text)).upper()
    return _STRIP.sub("", spelled).strip()


class Wav2VecGOP:
    """Capability: ``pronunciation``."""

    contract_version = "1.0"
    provider_key = "wav2vec2_gop"
    version = "0.1.0"

    coverage_note = ("Character-level goodness of pronunciation. Measures how "
                     "clearly each word was articulated, not how close it is to "
                     "any particular accent.")

    async def score(self, audio: AudioRef, *, reference_text: str,
                    alignment: AlignmentResult | None = None,
                    l1_language: str = "") -> PronunciationResult:
        samples = load_samples(audio.storage_key)
        return self.analyse(samples, reference_text)

    @staticmethod
    def snr_penalty(snr_db: float | None) -> float:
        """How much of the confidence a noisy recording costs.

        Stands in for the normalisation this GOP variant does not do. Without
        a competing-unit denominator every posterior falls together in a noisy
        room, and the score cannot tell an unclear speaker from an unclear
        recording. Until that denominator exists, a poor SNR reduces how much
        the number is trusted rather than silently reducing the number.
        """
        if snr_db is None:
            return 1.0
        if snr_db >= 20:
            return 1.0
        if snr_db >= 12:
            return 0.75
        if snr_db >= 6:
            return 0.45
        return 0.2

    def analyse(self, samples: np.ndarray, reference_text: str,
                snr_db: float | None = None) -> PronunciationResult:
        import torch
        import torchaudio

        meta = ProviderMeta(provider_id="", provider_key=self.provider_key,
                            version=self.version, tier=1)

        target = _tokenisable(reference_text)
        if not target or samples.size < SAMPLE_RATE // 4:
            return PronunciationResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        model, processor = _load()
        tokenizer = processor.tokenizer

        pad = np.zeros(int(EDGE_PAD_SECONDS * SAMPLE_RATE), dtype=np.float32)
        padded = np.concatenate([pad, samples, pad])

        with torch.inference_mode():
            logits = model(torch.tensor(padded).unsqueeze(0)).logits
        log_probs = torch.log_softmax(logits, dim=-1)

        ids = tokenizer(target.replace(" ", "|")).input_ids
        ids = [i for i in ids if i not in
               {tokenizer.pad_token_id, tokenizer.bos_token_id, tokenizer.eos_token_id}]
        if not ids:
            return PronunciationResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        # More target tokens than frames cannot be aligned — a long sentence
        # read into a two-second recording, usually a truncated upload.
        if len(ids) > log_probs.shape[1]:
            return PronunciationResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        try:
            alignment, scores = torchaudio.functional.forced_align(
                log_probs, torch.tensor([ids], dtype=torch.int32),
                blank=tokenizer.pad_token_id)
        except (RuntimeError, ValueError) as exc:
            log.info("forced alignment failed: %s", exc)
            return PronunciationResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        frames = alignment[0].tolist()
        frame_scores = scores[0].tolist()
        # Timings are reported against the original recording, so the pad is
        # subtracted back out before anything reaches the listen-back.
        ms_per_frame = 1000.0 * padded.size / SAMPLE_RATE / len(frames)
        pad_ms = EDGE_PAD_SECONDS * 1000.0
        separator = tokenizer.convert_tokens_to_ids("|")
        blank = tokenizer.pad_token_id

        # Walk the alignment, collecting the posterior of every non-blank,
        # non-separator frame into the word it belongs to.
        words = target.split()
        per_word: list[list[float]] = [[] for _ in words]
        spans: list[list[int]] = [[] for _ in words]
        index = 0
        seen_letter = False

        for frame_index, (token, score) in enumerate(zip(frames, frame_scores)):
            if token == blank:
                continue
            if token == separator:
                if seen_letter:
                    index += 1
                    seen_letter = False
                continue
            if index >= len(words):
                break
            per_word[index].append(score)
            spans[index].append(frame_index)
            seen_letter = True

        details: list[dict] = []
        mispronounced: list[dict] = []
        word_scores: list[float] = []

        for word, posteriors, frame_span in zip(words, per_word, spans):
            if not posteriors:
                continue
            mean_posterior = float(np.exp(np.mean(posteriors)))
            clarity = (mean_posterior - POSTERIOR_FLOOR) / (POSTERIOR_CEILING - POSTERIOR_FLOOR)
            clarity = max(0.0, min(1.0, clarity))
            word_score = SCALE_MIN + clarity * (SCALE_MAX - SCALE_MIN)
            word_scores.append(word_score)

            # Clamping both bounds independently collapsed a word aligned
            # inside the leading pad to a zero-width span, which the
            # listen-back drew as nothing at all. The start is clamped; the
            # end is kept at least one frame beyond it.
            start_ms = max(0, int(frame_span[0] * ms_per_frame - pad_ms))
            end_ms = max(start_ms + int(ms_per_frame) + 1,
                         int((frame_span[-1] + 1) * ms_per_frame - pad_ms))

            entry = {
                "word": word.lower(),
                "score": round(word_score, 1),
                "posterior": round(mean_posterior, 3),
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
            details.append(entry)
            # "Worth a second look", not "wrong". The report says it that way
            # too — a low posterior is our uncertainty as much as their speech.
            if word_score < 45:
                mispronounced.append(entry)

        if not word_scores:
            return PronunciationResult(score=SCALE_MIN, confidence=0.0, meta=meta)

        overall = float(np.mean(word_scores))
        mean_posterior = float(np.mean([d["posterior"] for d in details]))

        confidence = 0.55
        if mean_posterior < NOISY_MEAN_POSTERIOR:
            # Everything unclear usually means the microphone, not the mouth.
            confidence *= 0.5
        if len(words) < 3:
            confidence *= 0.6
        confidence *= self.snr_penalty(snr_db)

        return PronunciationResult(
            score=round(overall, 1),
            phonemes=details,
            mispronounced_words=sorted(mispronounced, key=lambda d: d["score"])[:10],
            confidence=round(confidence, 2),
            meta=meta,
        )
