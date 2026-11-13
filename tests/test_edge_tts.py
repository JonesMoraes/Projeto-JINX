import array
import asyncio
import json
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from providers import tts_edge as edge, edge_install, registry


class EdgeTest(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(edge, "available", return_value=True)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_blank_and_invalid_settings(self):
        self.assertEqual(edge.EdgeTTS({}).voice_id, "pt-BR-AntonioNeural")
        for cfg in ({"voice_id": "https://other.example"}, {"rate": "+500%"}, {"rate": "20"}):
            with self.assertRaises(ValueError):
                edge.EdgeTTS(cfg)

    def test_voice_list_ptbr_and_english_only(self):
        async def voices():
            return [{"ShortName": "fr-FR-TestNeural", "Locale": "fr-FR"},
                    {"ShortName": "en-US-AriaNeural", "Locale": "en-US"},
                    {"ShortName": "pt-BR-AntonioNeural", "Locale": "pt-BR", "Gender": "Male"}]
        with patch.dict(sys.modules, {"edge_tts": SimpleNamespace(list_voices=voices)}), \
             patch.object(edge, "find_spec", return_value=True):
            result = edge.EdgeTTS({}).voices()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "pt-BR-AntonioNeural")

    def test_synthesis_yields_pcm_chunks_at_existing_contract(self):
        async def stream():
            yield {"type": "metadata"}
            yield {"type": "audio", "data": b"compressed"}
        communicate = Mock(return_value=SimpleNamespace(stream=stream))
        pcm = b"\x01\0" * 5000
        async def gather():
            return [c async for c in edge.EdgeTTS({"rate": "+10%"}).speak("Olá")]
        with patch.dict(sys.modules, {"edge_tts": SimpleNamespace(Communicate=communicate)}), patch.object(edge, "_decode", return_value=pcm):
            chunks = asyncio.run(gather())
        self.assertEqual(b"".join(chunks), pcm)
        self.assertTrue(all(len(c) <= 2400 and len(c) % 2 == 0 for c in chunks))
        communicate.assert_called_once_with("Olá", "pt-BR-AntonioNeural", rate="+10%")

    def test_decoder_requests_mono_signed16_24khz(self):
        decoder = Mock(return_value=SimpleNamespace(samples=array.array("h", [1, 2, 3])))
        fake = SimpleNamespace(decode=decoder, SampleFormat=SimpleNamespace(SIGNED16=2))
        with patch.dict(sys.modules, {"miniaudio": fake}):
            self.assertEqual(len(edge._decode(b"mp3")), 6)
        self.assertEqual(decoder.call_args.kwargs, {"output_format": 2, "nchannels": 1, "sample_rate": 24000})

    def test_empty_audio_and_failure_not_success(self):
        async def empty():
            if False:
                yield None
        async def gather():
            return [c async for c in edge.EdgeTTS({}).speak("Hello")]
        with patch.dict(sys.modules, {"edge_tts": SimpleNamespace(Communicate=lambda *a, **k: SimpleNamespace(stream=empty))}):
            with self.assertRaises(RuntimeError):
                asyncio.run(gather())

    def test_cancel_preserved_and_stream_closed(self):
        closed = []
        async def stream():
            try:
                await asyncio.sleep(100)
                yield {"type": "audio", "data": b"mp3"}
            finally:
                closed.append(True)
        async def run():
            async def consume():
                return [c async for c in edge.EdgeTTS({}).speak("Test")]
            task = asyncio.create_task(consume())
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        with patch.dict(sys.modules, {"edge_tts": SimpleNamespace(Communicate=lambda *a, **k: SimpleNamespace(stream=stream))}):
            asyncio.run(run())
        self.assertEqual(closed, [True])

    def test_missing_dependency_does_not_install(self):
        async def gather():
            return [c async for c in edge.EdgeTTS({}).speak("Hello")]
        with patch.object(edge, "available", return_value=False), patch("subprocess.run") as install:
            with self.assertRaises(RuntimeError):
                asyncio.run(gather())
            self.assertFalse(edge.EdgeTTS({}).probe()[0])
            install.assert_not_called()

    def test_playback_selected_output_and_cancel(self):
        instance = edge.EdgeTTS({})
        async def speak(*args, **kwargs):
            yield b"\x01\0" * 2400
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        stream.write.return_value = False
        with patch.object(instance, "speak", side_effect=speak), patch("sounddevice.RawOutputStream", return_value=stream) as output, \
             patch("memory.config_manager.get_output_device", return_value="My speaker"), patch("core.audio_devices.resolve", return_value=8):
            self.assertTrue(instance.playback_test()[0])
            self.assertEqual(output.call_args.kwargs["device"], 8)
            cancel = threading.Event()
            cancel.set()
            output.reset_mock()
            self.assertFalse(instance.playback_test(cancel)[0])
            output.assert_not_called()

    def test_provider_registered_no_keys(self):
        declaration = registry.get_declaration("edge_tts")
        self.assertEqual(declaration["kind"], "tts")
        self.assertNotIn("api_key", registry.defaults("edge_tts"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{"download_info": {"url": "https://files.pythonhosted.org/edge.whl",
            "archive_info": {"hashes": {"sha256": "a" * 64}}}}]
        def run(cmd, **kwargs):
            if "--report" in cmd:
                Path(cmd[cmd.index("--report") + 1]).write_text(json.dumps({"install": self.rows}), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=b"ok")
        self.p = patch.object(edge_install.subprocess, "run", side_effect=run)
        self.proc = self.p.start()
        self.addCleanup(self.p.stop)
        self.head = Mock()
        self.head.__enter__ = Mock(return_value=SimpleNamespace(headers={"Content-Length": "1000"}))
        self.head.__exit__ = Mock(return_value=False)
        self.h = patch.object(edge_install.urllib.request, "urlopen", return_value=self.head)
        self.h.start()
        self.addCleanup(self.h.stop)

    def test_explicit_install_uses_size_checked_hashed_artifact(self):
        with patch.object(edge, "available", return_value=True):
            self.assertTrue(edge_install.install()[0])
        cmd = self.proc.call_args.args[0]
        self.assertIn("--no-deps", cmd)
        self.assertTrue(any("#sha256=" in value for value in cmd))

    def test_above_20mb_stops_before_install(self):
        self.head.__enter__.return_value.headers["Content-Length"] = str(21 * 1024 * 1024)
        self.assertFalse(edge_install.install()[0])
        self.assertEqual(self.proc.call_count, 1)

    def test_foreign_or_unverifiable_package_stops(self):
        self.rows[0]["download_info"]["url"] = "https://foreign.example/edge.whl"
        self.assertFalse(edge_install.install()[0])
        self.assertEqual(self.proc.call_count, 1)


if __name__ == "__main__":
    unittest.main()
