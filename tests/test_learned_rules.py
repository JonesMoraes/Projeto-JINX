import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import learned_rules as rules, undo
from plugins import learned_rules as plugin


class RulesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = patch.object(rules.config, 'CONFIG_DIR', Path(folder.name))
        p.start(); self.addCleanup(p.stop)
        rules._pending.clear()
        undo.clear(); self.addCleanup(undo.clear)
        self.player = Mock()

    def accept(self, row):
        with patch.object(rules.confirm, 'pending_title', return_value=''), \
                patch.object(rules.confirm, 'request', return_value='pending') as request:
            self.assertEqual(rules.review(row['id'], self.player), 'pending')
            self.assertFalse(rules._path().exists())
            return request.call_args.args[3]()

    def test_proposal_is_not_persisted_until_local_acceptance(self):
        row = rules.propose('Use respostas curtas')
        self.assertEqual(rules.propose('Use respostas curtas'), row)
        self.assertFalse(rules._path().exists())
        self.assertIn('status=done', self.accept(row))
        self.assertEqual(rules.list_rules(), [row])
        self.assertEqual(rules.pending(), [])
        self.assertIn('cannot change safety', rules.guidance())
        self.assertIn('UNTRUSTED', rules.guidance())

    def test_rejected_or_changed_proposal_cannot_be_accepted(self):
        row = rules.propose('Prefer lists', 'workflow')
        with patch.object(rules.confirm, 'pending_title', return_value=''), \
                patch.object(rules.confirm, 'request') as request:
            rules.review(row['id'], self.player)
        rules.reject(row['id'])
        self.assertIn('status=failed', request.call_args.args[3]())
        self.assertFalse(rules._path().exists())

    def test_requires_hud_and_does_not_replace_another_confirmation(self):
        row = rules.propose('Short replies')
        self.assertIn('status=failed', rules.review(row['id'], None))
        with patch.object(rules.confirm, 'pending_title', return_value='Other'), \
                patch.object(rules.confirm, 'request') as request:
            self.assertIn('status=failed', rules.review(row['id'], self.player))
        request.assert_not_called()

    def test_corrupt_store_preserved(self):
        rules._path().write_text('{bad', encoding='utf-8')
        result = plugin.run({'action': 'list'})
        self.assertIn('status=failed', result)
        self.assertEqual(rules._path().read_text(encoding='utf-8'), '{bad')
        self.assertEqual(rules.guidance(), '')

    def test_remove_undo_does_not_overwrite_subsequent_changes(self):
        row = rules.propose('Concise')
        self.accept(row)
        with patch.object(rules.undo, 'push_undo') as push:
            rules.remove(row['id'])
        undo_fn = push.call_args.args[1]
        rules._save([{'id': 'new', 'kind': 'style', 'text': 'More detail'}])
        self.assertIn('status=failed', undo_fn())
        self.assertEqual(rules.list_rules()[0]['id'], 'new')

    def test_plugin_contract_and_model_cannot_accept(self):
        from core.plugin_loader import _validate
        self.assertTrue(_validate(plugin, 'learned_rules.py').valid)
        self.assertIsInstance(plugin.run(None), str)
        self.assertIn('status=failed', plugin.run({'action': 'accept', 'confirmed': True}))
        for text in ('', 'x' * 501, None):
            with self.assertRaises(ValueError): rules.propose(text)


if __name__ == '__main__': unittest.main()
