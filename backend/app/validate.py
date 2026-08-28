"""Run the validation study end to end.

    python -m app.validate freeze  --study pilot-2026   # pin the engine first
    python -m app.validate sheet   --study pilot-2026   # blank rating sheet
    python -m app.validate score   --study pilot-2026   # engine scores for the set
    python -m app.validate report  --study pilot-2026   # verdict

Freeze before scoring. The engine is fingerprinted and the hash recorded with
the study; if the scoring code changes before the report is run, the report
says so and refuses to emit a calibration. A study measures one version of a
scorer, and the version has to be the one you are calibrating.

Recordings live in ``tmp/validation/<study>/`` with a ``manifest.csv``
describing speaker, L1 and condition. Ratings come back as ``ratings.csv``.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
from pathlib import Path

from app.config import settings
from app.engine import freeze
from app.engine.audio import decode_wav, resample_to, signal_quality
from app.validation.study import Recording, Study


def study_dir(name: str) -> Path:
    return settings.media_path / "validation" / name


def load(name: str) -> Study:
    study = Study(name)
    manifest = study_dir(name) / "manifest.csv"
    if not manifest.exists():
        raise SystemExit(f"no manifest at {manifest}")

    for row in csv.DictReader(io.StringIO(manifest.read_text(encoding="utf-8"))):
        study.add_recording(Recording(
            recording_id=row["recording_id"].strip(),
            speaker_id=row["speaker_id"].strip(),
            l1_language=row["l1_language"].strip().lower(),
            task_type=row.get("task_type", "read_aloud").strip(),
            reference_text=row.get("reference_text", "").strip(),
            condition=row.get("condition", "quiet").strip(),
            storage_key=row.get("file", "").strip(),
        ))

    scores = study_dir(name) / "engine_scores.csv"
    if scores.exists():
        for row in csv.DictReader(io.StringIO(scores.read_text(encoding="utf-8"))):
            recording = study.recordings.get(row["recording_id"].strip())
            if recording is None:
                continue
            for key, value in row.items():
                if key != "recording_id" and (value or "").strip():
                    recording.engine_scores[key] = float(value)

    ratings = study_dir(name) / "ratings.csv"
    if ratings.exists():
        study.load_ratings_csv(ratings.read_text(encoding="utf-8"))

    return study


async def score_recordings(name: str) -> int:
    """Run the engine over the study set and write engine_scores.csv."""
    # Dummy ASR and VAD providers (Whisper-related removed)
    class DummyASR:
        def analyse(self, samples):
            from app.engine.contracts.types import TranscriptResult
            return TranscriptResult(text="", language="", language_probability=0.0, words=[], duration_ms=0)
    
    class DummyVAD:
        def analyse(self, samples, *, prompt_end_ms=0):
            from app.engine.contracts.types import VADResult
            return VADResult(segments=[], speech_ms=0, silence_ms=0, onset_ms=None, meta=None)
    
    from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy
    from app.engine.providers.tier1.fluency import FeatureFluency  # noqa: F401
    from app.engine.providers.tier0.fluency import FeatureFluency as Fluency
    from app.engine.providers.tier1.pronunciation import Wav2VecGOP
    
    asr, vad, gop, accuracy, fluency = (DummyASR(), DummyVAD(),
                                         Wav2VecGOP(), ReferenceMatchAccuracy(),
                                         Fluency())

    rows = []
    for recording in study.recordings.values():
        path = study_dir(name) / recording.storage_key
        if not path.exists():
            print(f"  missing audio: {path.name}")
            continue

        wave = decode_wav(path.read_bytes())
        samples = resample_to(wave, 16000).samples.astype("float32")
        quality = signal_quality(wave)

        transcript = asr.analyse(samples)
        speech = vad.analyse(samples, prompt_end_ms=0)
        flu = fluency.analyse(resample_to(wave, 16000), vad=speech)
        pron = gop.analyse(samples, recording.reference_text or transcript.text,
                           snr_db=quality.snr_db)
        acc = accuracy.analyse(transcript, recording.reference_text,
                               recording.task_type)

        rows.append({
            "recording_id": recording.recording_id,
            "pronunciation": round(pron.score, 1),
            "pronunciation_confidence": pron.confidence,
            "fluency": round(flu.score, 1),
            "accuracy": round(acc.score, 1) if acc.confidence else "",
            "snr_db": round(quality.snr_db, 1),
            "transcript": transcript.text,
        })
        print(f"  {recording.recording_id}: pron {pron.score:.1f} "
              f"flu {flu.score:.1f} snr {quality.snr_db:.0f}dB")

    out = study_dir(name) / "engine_scores.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else
                                ["recording_id"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validation study")
    parser.add_argument("command",
                        choices=["freeze", "sheet", "score", "report"])
    parser.add_argument("--study", required=True)
    args = parser.parse_args()

    if args.command == "freeze":
        baseline = freeze.freeze(args.study,
                                 note="frozen for validation data collection")
        print(f"engine frozen as {baseline.name}: {baseline.engine_hash}")
        print(f"  {len(baseline.files)} scoring files, models {baseline.models}")
        print()
        print("Do not change the scoring path until the report is run. "
              "If you do, the report will refuse to calibrate and will "
              "tell you exactly what moved.")
        return

    if args.command == "sheet":
        study = load(args.study)
        out = study_dir(args.study) / "rating_sheet.csv"
        out.write_text(study.rating_sheet(), encoding="utf-8")
        print(f"{len(study.recordings)} recordings -> {out}")
        print("No engine scores in this file, deliberately — a rater who can "
              "see the machine's answer is not an independent check.")
        return

    if args.command == "score":
        print(f"scored {asyncio.run(score_recordings(args.study))} recordings")
        return

    study = load(args.study)
    report = study.analyse()
    study.save(study_dir(args.study) / "report.json", report)

    changes = freeze.drift(args.study)

    print(f"\n{report.name}: {report.recordings} recordings, "
          f"{report.speakers} speakers, {report.raters} raters")
    print(f"L1: {report.l1_distribution}")
    print(f"conditions: {report.condition_distribution}\n")

    for result in report.dimensions:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  [{mark}] {result.dimension:16s} n={result.n:4d}  "
              f"ICC={result.rater_agreement:.2f}  r={result.pearson:.2f}  "
              f"rho={result.spearman:.2f}  MAE={result.mean_absolute_error:.1f}  "
              f"L1 spread={result.l1_group_bias:.1f}")
        for reason in result.failures:
            print(f"         {reason}")

    print(f"\nVERDICT: {report.verdict.upper()}")
    for reason in report.blocking:
        print(f"  - {reason}")
    if report.passed:
        fits = study.calibrations(report)
        print(f"\n{len(fits)} dimension(s) can now be calibrated: {sorted(fits)}")


if __name__ == "__main__":
    main()
