import asyncio
import io
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from providers import stt_groq as groq, registry
from plugins import groq_listen


class GroqTest(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.http.__enter__ = Mock(return_value=self.http)
        self.http.__exit__ = Mock(return_value=False)
        self.patcher = patch("httpx.Client", return_value=self.http)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.pcm = b"\x01\0" * 16000

    def test_provider_defaults_no_key_no_download(self):
        self.assertEqual(groq.PROVIDER["needs"][0].default, "")
        inst = groq.GroqSTT({})
        self.assertFalse(inst.probe()[0])
        self.http.get.assert_not_called()
        self.assertEqual(inst.backend, "api")
        self.assertIsNone(inst._model)
        self.assertNotIn("install", groq.PROVIDER)

    def test_fixed_official_endpoint_and_wav(self):
        self.http.post.return_value = SimpleNamespace(status_code=200, json=lambda: {
            "text": "Olá, como você está?", "language": "portuguese"})
        inst = groq.GroqSTT({"api_key": "mine", "language": "pt-BR", "base_url": "https://foreign.example"})
        self.assertEqual(asyncio.run(inst.transcribe(self.pcm)), "Olá, como você está?")
        call = self.http.post.call_args
        self.assertEqual(call.args[0], groq.BASE + "/audio/transcriptions")
        self.assertEqual(call.kwargs["data"]["language"], "pt")
        self.assertEqual(inst.detected_language, "pt")
        with wave.open(io.BytesIO(call.kwargs["files"]["file"][1])) as wav:
            self.assertEqual((wav.getframerate(), wav.getnchannels()), (16000, 1))

    def test_auto_language_omits_language_parameter(self):
        self.http.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"text": "Hello there", "language": "english"})
        inst = groq.GroqSTT({"api_key": "mine"})
        asyncio.run(inst.transcribe(self.pcm))
        self.assertNotIn("language", self.http.post.call_args.kwargs["data"])
        self.assertEqual(inst.detected_language, "en")

    def test_missing_key_does_not_send_audio(self):
        with self.assertRaises(RuntimeError):
            asyncio.run(groq.GroqSTT({}).transcribe(self.pcm))
        self.http.post.assert_not_called()

    def test_invalid_model_or_short_audio_not_sent(self):
        with self.assertRaises(RuntimeError):
            asyncio.run(groq.GroqSTT({"api_key": "mine", "model": "unknown"}).transcribe(self.pcm))
        self.assertEqual(asyncio.run(groq.GroqSTT({"api_key": "mine"}).transcribe(b"\0" * 100)), "")
        self.http.post.assert_not_called()

    def test_http_and_transport_errors_redacted(self):
        inst = groq.GroqSTT({"api_key": "my-secret"})
        self.http.post.return_value = SimpleNamespace(status_code=429, text="my-secret")
        with self.assertRaisesRegex(RuntimeError, "429") as caught:
            asyncio.run(inst.transcribe(self.pcm))
        self.assertNotIn("my-secret", str(caught.exception))
        self.http.post.side_effect = RuntimeError("transport contains my-secret")
        with self.assertRaises(RuntimeError) as caught:
            asyncio.run(inst.transcribe(self.pcm))
        self.assertNotIn("my-secret", str(caught.exception))

    def test_probe_checks_key_and_supported_model_without_recording(self):
        self.http.get.return_value = SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": groq.MODELS[0]}]})
        with patch("sounddevice.RawInputStream") as mic:
            self.assertTrue(groq.GroqSTT({"api_key": "mine"}).probe()[0])
            mic.assert_not_called()
        self.http.post.assert_not_called()

    def test_record_test_uses_chosen_device_and_capture(self):
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        stream.read.return_value = (b"\x01\0" * 1600, False)
        inst = groq.GroqSTT({"api_key": "mine"})
        with patch("memory.config_manager.get_input_device", return_value="my microphone"), \
             patch("core.audio_devices.resolve", return_value=7), patch("sounddevice.RawInputStream", return_value=stream) as mic, \
             patch.object(inst, "transcribe", new_callable=AsyncMock, return_value="Teste de audição") as transcribe:
            self.assertTrue(inst.record_test()[0])
            self.assertEqual(mic.call_args.kwargs["device"], 7)
            self.assertEqual(stream.read.call_count, 40)
            self.assertEqual(len(transcribe.call_args.args[0]), 128000)

    def test_cancelled_capture_not_sent(self):
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        cancel = threading.Event()
        cancel.set()
        inst = groq.GroqSTT({"api_key": "mine"})
        with patch("memory.config_manager.get_input_device", return_value=""), patch("core.audio_devices.resolve", return_value=None), \
             patch("sounddevice.RawInputStream", return_value=stream), patch.object(inst, "transcribe", new_callable=AsyncMock) as transcribe:
            self.assertFalse(inst.record_test(cancel)[0])
            transcribe.assert_not_called()

    def test_provider_registered_and_legacy_kept(self):
        self.assertIsNotNone(registry.get_declaration("groq_stt"))
        self.assertEqual(registry.defaults("groq_stt")["api_key"], "")
        self.assertIn("SUA chave Groq / YOUR Groq key", registry.missing_fields("groq_stt", {}))
        self.assertEqual(registry.catalog_entry("whisper@groq")["id"], "groq")

    def test_status_does_not_claim_real_transcription(self):
        with patch.object(groq_listen, "get_provider_mode", return_value="pipeline"), \
             patch.object(groq_listen, "get_pipeline", return_value={"stt": "groq_stt"}), \
             patch.object(groq_listen, "get_provider_config", return_value={"api_key": "hidden-secret"}):
            result = groq_listen.run({})
        self.assertIn("status=done", result)
        self.assertNotIn("hidden-secret", result)
        self.assertIn("not proven", result)


if __name__ == "__main__":
    unittest.main()
