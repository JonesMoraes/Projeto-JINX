import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from core import smart_home as home, gemini, video_upload as video, google_workspace as google
from core.plugin_jobs import Jobs
from plugins import smart_home, generate_image, instagram_assistant, video_upload


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'enabled': True, 'ha_url': 'http://192.168.1.2:8123', 'ha_token': 'secret'}
        p = patch.object(home, 'get_plugin_config', side_effect=lambda _: dict(self.cfg))
        p.start(); self.addCleanup(p.stop)
        self.client = home.Client('ha')

    def test_off_and_changed_settings(self):
        self.cfg['enabled'] = False
        with self.assertRaises(home.HomeError): self.client.check()
        with self.assertRaises(home.HomeError): home.Client('ha')

    def test_no_write_to_unknown_domain(self):
        with patch.object(self.client, 'request') as request:
            for entity in ('lock.front', 'light.a/../x', 'light.a?x'):
                with self.assertRaises(home.HomeError): self.client.change(entity, 'on')
            request.assert_not_called()

    def test_change_checks_state_and_undo_preserves_newer_changes(self):
        before = {'entity_id': 'light.a', 'state': 'off', 'last_updated': '1'}
        after = {**before, 'state': 'on', 'last_updated': '2'}
        newer = {**after, 'last_updated': '3'}
        with patch.object(self.client, 'state', side_effect=[before, after, newer]), \
                patch.object(self.client, 'request') as request, patch.object(home.undo, 'push_undo') as push:
            self.assertIn('status=done', self.client.change('light.a', 'on'))
            request.assert_called_once_with('POST', 'services/light/turn_on', {'entity_id': 'light.a'})
            with self.assertRaises(home.HomeError): push.call_args.args[1]()

    def test_delayed_readback_not_done(self):
        with patch.object(self.client, 'state', return_value={'state': 'off'}), \
                patch.object(self.client, 'request'), patch.object(home.undo, 'push_undo') as push:
            self.assertIn('status=unverified', self.client.change('light.a', 'on'))
            push.assert_not_called()

    def test_public_http_rejected(self):
        self.cfg['ha_url'] = 'http://example.com'
        with self.assertRaises(home.HomeError): home.Client('ha').request('GET', 'states')

    def test_transport_hides_token_and_no_redirect(self):
        with patch('requests.request', side_effect=RuntimeError('secret')) as request:
            with self.assertRaises(home.HomeError) as caught: self.client.request('GET', 'states')
            self.assertNotIn('secret', str(caught.exception))
            self.assertFalse(request.call_args.kwargs['allow_redirects'])


class ImageTests(unittest.TestCase):
    def test_image_ladder_uses_core_and_ignores_text_only_reply(self):
        data = b'fake'
        response = NS(candidates=[NS(content=NS(parts=[NS(inline_data=NS(data=data, mime_type='image/png'))]))])
        session = Mock()
        session.models.generate_content.side_effect = [NS(candidates=[]), response]
        with patch('memory.config_manager.get_plugin_config', return_value={'enabled': True, 'models': 'image-a,image-b'}), \
                patch('core.gemini_accounts.attempt', side_effect=lambda fn: fn('fake-key')), patch.object(gemini, 'client', return_value=session):
            self.assertEqual(gemini.generate_image('A tree'), (data, 'image/png'))
            self.assertEqual(session.close.call_count, 2)

    def test_generation_disabled(self):
        with patch('memory.config_manager.get_plugin_config', return_value={}), patch.object(gemini, 'client') as client:
            self.assertIsNone(gemini.generate_image('test')); client.assert_not_called()

    def test_valid_image_saved_and_displayed(self):
        from PIL import Image
        stream = io.BytesIO(); Image.new('RGB', (8, 8)).save(stream, 'PNG')
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_image, 'get_base_dir', return_value=folder), \
                patch.object(gemini, 'generate_image', return_value=(stream.getvalue(), 'image/png')):
            player = Mock()
            result = generate_image._generate('test', player)
            self.assertIn('status=done', result)
            path = Path(player.show_image.call_args.args[0])
            self.assertEqual(path.read_bytes(), stream.getvalue())

    def test_invalid_image_not_saved(self):
        with patch.object(gemini, 'generate_image', return_value=(b'bad', 'image/png')):
            with self.assertRaises(Exception): generate_image._generate('test', None)


class ServiceTests(unittest.TestCase):
    def test_instagram_off_no_network(self):
        with patch.object(instagram_assistant, 'get_plugin_config', return_value={}), patch('requests.get') as get:
            self.assertIn('status=failed', instagram_assistant._work({'action': 'media'})); get.assert_not_called()

    def test_instagram_suggestion_failure(self):
        with patch.object(instagram_assistant, 'get_plugin_config', return_value={'enabled': True}), patch.object(gemini, 'text', return_value=''):
            self.assertIn('status=failed', instagram_assistant._work({'action': 'suggest', 'brief': 'test'}))

    def test_upload_requires_local_hud(self):
        with patch.object(google, 'Client') as client:
            self.assertIn('status=failed', video_upload._review({}, None)); client.assert_not_called()

    def test_upload_defaults_private_and_checks_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.mp4'; path.write_bytes(b'video')
            draft = video.prepare({'path': str(path)})
            self.assertEqual(draft['body']['status']['privacyStatus'], 'private')
            self.assertEqual(draft['body']['snippet']['description'], '')
            path.write_bytes(b'changed')
            with patch('requests.post') as post:
                self.assertIn('status=failed', video.upload(Mock(), draft)); post.assert_not_called()

    def test_google_upload_has_verification_scope(self):
        scopes = google.selected_scopes({'youtube': True})
        self.assertEqual(set(scopes), {google.SCOPES['youtube'], google.SCOPES['youtube_read']})

    def test_plugin_contracts_and_bad_inputs(self):
        from core.plugin_loader import _validate
        for module in (smart_home, generate_image, instagram_assistant, video_upload):
            self.assertTrue(_validate(module, module.__name__ + '.py').valid)
            self.assertIsInstance(module.run(None), str)
            self.assertIsInstance(module.run({'action': 'invalid'}), str)

    def test_background_failure_delivered_and_lock_released(self):
        jobs = Jobs('test'); notified = threading.Event()
        player = Mock(); player.request_say.side_effect = lambda _: notified.set()
        def fail(): raise RuntimeError('secret-token')
        self.assertIn('status=started', jobs.start(fail, player))
        self.assertTrue(notified.wait(2))
        self.assertNotIn('secret-token', jobs.last)
        self.assertIn('status=unverified', jobs.last)


if __name__ == '__main__': unittest.main()
