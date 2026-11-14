import io
import os
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from core.voice_preview import PreviewPlayer, sample_pcm
from core.hud_support import web_hud_block_reason
from core import gemini
from PyQt6.QtWidgets import QApplication
from gui.overlays import CustomizeOverlay
from memory.config_manager import AVAILABLE_VOICES


class PreviewTests(unittest.TestCase):
    def test_normal_desktop_allows_web_hud_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(web_hud_block_reason(), '')
        for env in ({'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY': 'restricted'},
                    {'CODEX_SANDBOX_NETWORK_DISABLED': '1'}, {'QT_QPA_PLATFORM': 'offscreen'},
                    {'JINX_DISABLE_WEBENGINE': '1'}):
            with patch.dict(os.environ, env, clear=True):
                self.assertTrue(web_hud_block_reason())

    def test_sample_converts_wav_and_bounds_duration(self):
        f = io.BytesIO()
        with wave.open(f, 'wb') as w:
            w.setparams((2, 2, 16000, 0, 'NONE', 'not compressed'))
            w.writeframes(b'\x01\x00' * 3200)
        self.assertEqual(len(sample_pcm(f.getvalue(), 'audio/wav')), 4800)
        self.assertEqual(len(sample_pcm(b'\0\0' * 300000, 'audio/L16;rate=24000')), 384000)
        with self.assertRaises(ValueError): sample_pcm(b'garbage', 'audio/mp3')

    def test_cancel_discards_late_sample_and_coalesces_requests(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        generated, played = [], []
        def generate(voice, cancel):
            generated.append(voice)
            if voice == 'Kore':
                entered.set()
                self.assertTrue(release.wait(3))
            return b'\0\0' * 2400, 'audio/L16;rate=24000'
        player = PreviewPlayer(lambda *args: None)
        def play(voice, pcm, cancel):
            played.append(voice)
            done.set()
        with patch.object(gemini, 'preview_voice', side_effect=generate), patch.object(player, '_play', side_effect=play):
            player.request('Kore')
            self.assertTrue(entered.wait(3))
            player.request('Puck')
            player.request('Aoede')
            release.set()
            self.assertTrue(done.wait(3))
            worker = player._worker
            if worker: worker.join(3)
        self.assertEqual(generated, ['Kore', 'Aoede'])
        self.assertEqual(played, ['Aoede'])

    def test_cache_reuses_same_sample_without_new_request(self):
        player = PreviewPlayer(lambda *args: None)
        with patch.object(gemini, 'preview_voice', return_value=(b'\0\0' * 100, 'audio/L16')), \
                patch.object(player, '_play') as play:
            for _ in range(2):
                player.request('Kore')
                with player._lock: worker = player._worker
                if worker: worker.join(3)
            self.assertEqual(gemini.preview_voice.call_count, 1)
            self.assertEqual(play.call_count, 2)

    def test_output_close_failure_still_resumes_microphone(self):
        stream = Mock()
        stream.close.side_effect = RuntimeError('closed')
        activity = Mock(return_value=0)
        player = PreviewPlayer(lambda *args: None, activity)
        with patch('core.audio_devices.resolve', return_value=3), \
                patch('memory.config_manager.get_output_device', return_value='speakers'), \
                patch('sounddevice.RawOutputStream', return_value=stream):
            with self.assertRaises(RuntimeError):
                player._play('Kore', b'\0\0' * 100, threading.Event())
        self.assertEqual([call.args[0] for call in activity.call_args_list], [True, False])

    def test_gemini_uses_selected_voice_and_closes_client(self):
        data = b'\0\0' * 100
        response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type='audio/wav'))]))])
        client = Mock()
        client.models.generate_content.return_value = response
        with patch('memory.config_manager.get_plugin_config', return_value={}), \
                patch('core.gemini_accounts.attempt', side_effect=lambda f: f('fake')), \
                patch.object(gemini, 'client', return_value=client):
            self.assertEqual(gemini.preview_voice('Kore'), (data, 'audio/wav'))
        cfg = client.models.generate_content.call_args.kwargs['config']
        self.assertEqual(cfg['speech_config']['voice_config'], {'voice': 'Kore'})
        client.close.assert_called_once()


class PreviewQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_voice_has_preview_without_selecting_or_saving(self):
        overlay = CustomizeOverlay(voice='Kore')
        try:
            overlay.show()
            combo = overlay._voice_combo
            combo.showPopup()
            self.app.processEvents()
            saved = Mock()
            overlay.saved.connect(saved)
            initial = combo.currentData()
            with patch.object(overlay._voice_preview.player, 'request') as request:
                for voice in AVAILABLE_VOICES:
                    combo.preview_buttons[voice].click()
                    request.assert_called_with(voice)
                    self.assertEqual(combo.currentData(), initial)
            saved.assert_not_called()
            combo.hidePopup()
            with patch.object(overlay._voice_preview.player, 'stop') as stop:
                overlay.hide()
                stop.assert_called_once()
        finally:
            overlay.close()
            overlay.deleteLater()
            self.app.processEvents()


if __name__ == '__main__': unittest.main()
