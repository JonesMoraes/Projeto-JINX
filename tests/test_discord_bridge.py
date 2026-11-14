import unittest
from unittest.mock import Mock, patch
from core import discord_bridge as api
from plugins import discord_bridge as plugin

G, C, U, M = ('1'*18, '2'*18, '3'*18, '4'*18)
CFG = {'enabled': True, 'bot_token': 'fake-token', 'guild_id': G, 'channel_id': C, 'user_ids': U}


class DiscordTest(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(CFG)
        p = patch.object(api, 'config', side_effect=lambda: dict(self.cfg)); p.start(); self.addCleanup(p.stop)
        self.client = api.Client()
        self.channel = {'id': C, 'guild_id': G, 'type': 0, 'permission_overwrites': [{'id': G, 'type': 0, 'deny': '1024'}]}
        self.row = {'id': M, 'channel_id': C, 'author': {'id': U}, 'type': 0, 'content': 'Que horas são?'}

    def test_defaults_disabled_and_empty_allowlist_rejected(self):
        for cfg in ({}, {**CFG, 'user_ids': ''}, {**CFG, 'channel_id': '../secret'}):
            with self.assertRaises(api.DiscordError): api.settings(cfg)

    def test_change_of_account_channel_or_users_invalidates_client(self):
        for key in ('bot_token', 'channel_id', 'user_ids'):
            self.cfg = {**CFG, key: '5'*18}
            with self.assertRaises(api.DiscordError): self.client.check()

    def test_public_channel_rejected(self):
        with patch.object(self.client, 'get', return_value={**self.channel, 'permission_overwrites': []}):
            with self.assertRaises(api.DiscordError): self.client.inbox()

    def test_wrong_server_and_thread_rejected(self):
        for change in ({'guild_id': '9'*18}, {'type': 11}):
            with patch.object(self.client, 'get', return_value={**self.channel, **change}):
                with self.assertRaises(api.DiscordError): self.client.private_channel()

    def test_allowlist_bot_webhook_and_channel_filters(self):
        self.assertTrue(self.client.allowed_message(self.row))
        for change in ({'author': {'id': '9'*18}}, {'author': {'id': U, 'bot': True}},
                       {'channel_id': '9'*18}, {'webhook_id': '9'*18}, {'content': ''}, {'type': 7}):
            self.assertFalse(self.client.allowed_message({**self.row, **change}))

    def test_inbox_reads_only_configured_channel_and_filters_users(self):
        with patch.object(self.client, 'get', side_effect=[self.channel, [self.row, {**self.row, 'author': {'id': '9'*18}}]]):
            rows = self.client.inbox()
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['id'], M)

    def test_review_does_not_dispatch_before_local_confirmation(self):
        player = Mock()
        with patch.object(self.client, 'get', side_effect=[self.channel, self.row]), patch.object(api.confirm, 'pending_title', return_value=''), \
             patch.object(api.confirm, 'request', return_value='[CONFIRMATION_PENDING]') as request:
            self.assertIn('CONFIRMATION_PENDING', self.client.review(M, player))
        player.request_say.assert_not_called()
        callback = request.call_args.args[3]
        with patch.object(self.client, 'get', side_effect=[self.channel, self.row]):
            result = callback()
        self.assertIn('status=unverified', result)
        self.assertIn('UNTRUSTED', player.request_say.call_args.args[0])

    def test_edit_after_review_invalidates_approval(self):
        player = Mock()
        with patch.object(self.client, 'get', side_effect=[self.channel, self.row]), patch.object(api.confirm, 'pending_title', return_value=''), \
             patch.object(api.confirm, 'request') as request:
            self.client.review(M, player)
        with patch.object(self.client, 'get', side_effect=[self.channel, {**self.row, 'content': 'changed'}]):
            result = request.call_args.args[3]()
        self.assertIn('status=failed', result); player.request_say.assert_not_called()

    def test_transport_sanitized_no_redirect_or_retry(self):
        with patch('requests.get', side_effect=RuntimeError('fake-token')) as get:
            with self.assertRaises(api.DiscordError) as caught: self.client.get()
        self.assertNotIn('fake-token', str(caught.exception))
        get.assert_called_once(); self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_headless_review_refused(self):
        with patch.object(self.client, 'get', side_effect=[self.channel, self.row]):
            with self.assertRaises(api.DiscordError): self.client.review(M, None)

    def test_plugin_schema_and_bad_input(self):
        from core.plugin_loader import _validate
        self.assertTrue(_validate(plugin, 'discord_bridge.py').valid)
        self.assertIn('status=failed', plugin.run(None))
        self.assertIn('status=failed', plugin.run({'action': 'execute'}))


if __name__ == '__main__': unittest.main()
