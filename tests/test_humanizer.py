"""Tests for core/humanizer.py — the spoken-reply clean-up pass."""
import unittest

from core import humanizer


class HumanizerTests(unittest.TestCase):

    def test_plain_text_passes_through(self):
        text = "O backup terminou às nove e meia."
        self.assertEqual(humanizer.humanize(text), text)

    def test_empty_and_none(self):
        self.assertEqual(humanizer.humanize(""), "")
        self.assertEqual(humanizer.humanize(None), "")
        self.assertEqual(humanizer.humanize("   "), "")

    def test_bold_italic_and_backticks(self):
        self.assertEqual(humanizer.humanize("O arquivo **oka.cmd** está `pronto` e *salvo*."),
                         "O arquivo oka.cmd está pronto e salvo.")

    def test_code_fence_dropped(self):
        text = ("Criei o script.\n\n```python\nprint('oi')\n```\n\n"
                "Ele roda sozinho.")
        self.assertEqual(humanizer.humanize(text).split(), 
                         "Criei o script. Ele roda sozinho.".split())
        self.assertNotIn("print", humanizer.humanize(text))

    def test_unclosed_fence_dropped_to_end(self):
        text = "Analisei tudo. ```bash\npwd\ngit status"
        self.assertEqual(humanizer.humanize(text), "Analisei tudo.")

    def test_header_hash_removed(self):
        self.assertEqual(humanizer.humanize("## Relatório\nTudo certo."),
                         "Relatório\nTudo certo.")

    def test_bullet_marker_removed(self):
        text = "- saco de arroz\n- feijão\n- café"
        out = humanizer.humanize(text)
        self.assertNotIn("-", out)
        self.assertIn("Saco de arroz", out)
    def test_link_keeps_label(self):
        self.assertEqual(humanizer.humanize("Veja [o relatório](https://exemplo.com/a/b) depois."),
                         "Veja o relatório depois.")

    def test_bare_url_removed(self):
        out = humanizer.humanize("Está em https://exemplo.com/pagina/longa, acesse depois.")
        self.assertNotIn("http", out)

    def test_ai_opener_removed(self):
        self.assertFalse(humanizer.humanize("Claro! Vou verificar os furinhos.").startswith("Claro"))

    def test_ai_closer_removed(self):
        out = humanizer.humanize("O relatório está pronto. Espero ter ajudado!")
        self.assertFalse(out.lower().startswith("espero"))

    def test_opener_mid_sentence_survives(self):
        """'Com certeza' antes de um verbo é conteúdo, não filler."""
        text = "Ele disse com certeza que viria."
        self.assertEqual(humanizer.humanize(text), text)

    def test_as_ai_opener_removed(self):
        out = humanizer.humanize("Como uma inteligência artificial, devo avisar que não sei.")
        self.assertTrue(out.startswith("Devo avisar"))

    def test_version_numbers_survive(self):
        """A narrow regex: versions, placa de rede, nomes com sublinhado."""
        text = "A versão 1.2.3 do sdk_v2 está em C:/Users."
        self.assertEqual(humanizer.humanize(text), text)

    def test_portuguese_text_not_eaten(self):
        """The lesson of _UNSPEAKABLE: no broad range may eat real text."""
        text = "日本語も大丈夫です。アシスタントはいつもここにいます。"
        self.assertEqual(humanizer.humanize(text), text)

    def test_english_filler(self):
        out = humanizer.humanize("Great question! The backup finished. I hope this helps!")
        self.assertNotIn("Great question", out)
        self.assertNotIn("hope this helps", out)

    def test_deep_dressing_removed(self):
        """blader/humanizer §3: o fora-de-modalidade não vira fala."""
        out = humanizer.humanize("Em última análise, o backup falhou às 09:00.")
        self.assertEqual(out, "O backup falhou às 09:00.")
        out = humanizer.humanize("A verdade é que ele saiu.")
        self.assertEqual(out, "Ele saiu.")

    def test_deep_dressing_mid_sentence_survives(self):
        """Na boca do usuário citado, a expressão é conteúdo."""
        text = "Ela disse que no fundo ele sabia."
        self.assertEqual(humanizer.humanize(text), text)

    def test_dramatic_closer_removed(self):
        out = humanizer.humanize("O cache corta o trabalho repetido. Simples assim.")
        self.assertEqual(out, "O cache corta o trabalho repetido.")

    def test_table_pipes_flattened(self):
        text = "Resumo:\n| item | valor |\n|---|---|\n| arroz | 10 |"
        out = humanizer.humanize(text)
        self.assertNotIn("|", out)
        self.assertIn("arroz", out)

    def test_never_empty(self):
        """A reply made only of stripped parts degrades, never vanishes."""
        text = "**Claro!**"
        self.assertTrue(humanizer.humanize(text).strip())

    def test_quote_marker_removed(self):
        self.assertEqual(humanizer.humanize("> disse ele\nEntão paramos."),
                         "Disse ele\nEntão paramos.")

    def test_capitalises_after_opener_removal(self):
        self.assertTrue(humanizer.humanize("Claro! vou verificar.").startswith("Vou"))

    def test_config_switch(self):
        from unittest.mock import patch
        from memory import config_manager
        with patch.object(config_manager, "get_humanizer_enabled", return_value=False):
            humanizer._ON = None
            text = "Claro! **Feito.**"
            self.assertEqual(humanizer.humanize(text), text)
        humanizer._ON = None
        self.assertFalse(humanizer.humanize("Claro! Feito.").startswith("Claro"))

    def tearDown(self):
        humanizer._ON = None


if __name__ == "__main__":
    unittest.main()
