import unittest

from app.engine.contracts.types import TranscriptResult, WordTiming
from app.engine.pipeline import (SCALE_MAX, SCALE_MIN, WEIGHTS, band_label,
                                 latency_score)
from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy
from app.weighting import ENGINE_WEIGHTS


class NativeScaleSmokeTests(unittest.TestCase):
    def test_scale_and_weights_are_native_and_consistent(self):
        self.assertEqual((SCALE_MIN, SCALE_MAX), (0.0, 100.0))
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)
        self.assertEqual(WEIGHTS, ENGINE_WEIGHTS)
        self.assertNotIn("pronunciation", WEIGHTS)

    def test_latency_uses_full_native_range(self):
        self.assertEqual(latency_score(800), 100.0)
        self.assertEqual(latency_score(3500), 0.0)
        self.assertEqual(band_label(75), "Strong")

    def test_accuracy_deducts_inserted_words(self):
        heard = "please open the extra window"
        transcript = TranscriptResult(
            text=heard,
            words=[WordTiming(word=w, start_ms=i * 100,
                              end_ms=(i + 1) * 100, confidence=0.95)
                   for i, w in enumerate(heard.split())],
            confidence=0.95,
        )
        result = ReferenceMatchAccuracy().analyse(
            transcript, "please open the window", "repeat_sentence")
        self.assertEqual(result.accuracy, 0.75)
        self.assertEqual(result.score, 75.0)
        self.assertTrue(any(e["kind"] == "insertion" for e in result.word_errors))

    def test_open_response_has_no_reference_accuracy(self):
        result = ReferenceMatchAccuracy().analyse(
            TranscriptResult(text="My city is busy and welcoming."),
            "", "open_response")
        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
