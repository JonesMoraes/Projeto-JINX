import unittest

from core.wake_phrase import is_wake_phrase, normalize_phrase


class WakePhraseTests(unittest.TestCase):
    def test_normalizes_accents_and_case(self):
        self.assertEqual(normalize_phrase("Olá, JINX!"), "ola jinx")

    def test_accepts_requested_phrases(self):
        for text in ("Ei JINX", "OLÁ JINX", "jinx", "JINX, você está aí?"):
            with self.subTest(text=text):
                self.assertTrue(is_wake_phrase(text))

    def test_rejects_unrelated_or_embedded_words(self):
        for text in ("jarvis", "index", "jins", "meu jinxia", "olá amigo"):
            with self.subTest(text=text):
                self.assertFalse(is_wake_phrase(text))


if __name__ == "__main__":
    unittest.main()
