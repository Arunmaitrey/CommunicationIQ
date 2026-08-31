import unittest

from app.engine.contracts.types import TranscriptResult, WordTiming
from app.engine.providers.tier1.accuracy import ReferenceMatchAccuracy


class ConstructionScoringTests(unittest.TestCase):
    def setUp(self):
        self.provider = ReferenceMatchAccuracy()

    def transcript(self, text: str) -> TranscriptResult:
        words = [
            WordTiming(word=word, start_ms=index * 100,
                       end_ms=(index + 1) * 100, confidence=0.9)
            for index, word in enumerate(text.split())
        ]
        return TranscriptResult(text=text, words=words, confidence=0.9)

    def test_sentence_build_exposes_coverage_and_order(self):
        result = self.provider.analyse(
            self.transcript("the manager postponed the meeting"),
            "the manager postponed the meeting",
            "sentence_build",
        )

        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.coverage, 1.0)
        self.assertEqual(result.order, 1.0)

    def test_wrong_order_reduces_construction_score(self):
        result = self.provider.analyse(
            self.transcript("meeting the postponed manager the"),
            "the manager postponed the meeting",
            "sentence_build",
        )

        self.assertEqual(result.coverage, 1.0)
        self.assertLess(result.order, 1.0)
        self.assertLess(result.score, 100.0)


if __name__ == "__main__":
    unittest.main()
