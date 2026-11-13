import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch
from core import optional_packages


class IntegrationTest(unittest.TestCase):
    def test_epic_uri_uses_handler_not_desktop_typing(self):
        from actions import open_app
        uri = "com.epicgames.launcher://apps/abc?action=launch&silent=true"
        with patch.object(open_app.shutil, "which", return_value=None), patch.object(open_app.os, "startfile", create=True) as start, patch.object(open_app, "_desktop_search") as search:
            self.assertTrue(open_app._launch_windows(uri)); start.assert_called_once_with(uri); search.assert_not_called()

    def test_legacy_groq_stt_catalog_configuration(self):
        from core import meeting
        from providers import registry
        factory = Mock(return_value="provider")
        with patch.object(meeting, "get_pipeline", return_value={"stt": "whisper@groq"}), \
             patch.object(meeting, "get_provider_config", return_value={"api_key": "fake-test-key"}), \
             patch.dict(registry.get_declaration("whisper"), {"factory": factory}):
            self.assertEqual(meeting.stt_provider(), "provider")
            self.assertEqual(factory.call_args.args[0]["backend"], "api")

    def test_optional_installer_refuses_large_or_wrong_source(self):
        for url, size in (("https://files.pythonhosted.org/test.whl", 21 * 1048576), ("https://example.com/test.whl", 100)):
            calls = []
            def run(args, **kwargs):
                calls.append(args)
                plan = {"install": [{"download_info": {"url": url, "archive_info": {"hashes": {"sha256": "a" * 64}}}}]}
                Path(args[args.index("--report") + 1]).write_text(json.dumps(plan))
                return SimpleNamespace(returncode=0)
            response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=None)
            response.headers = {"Content-Length": str(size)}
            with patch.object(optional_packages.subprocess, "run", side_effect=run), patch.object(optional_packages.urllib.request, "urlopen", return_value=response):
                ok, _ = optional_packages.install("meeting")
            self.assertFalse(ok); self.assertEqual(len(calls), 1)

    def test_pt_br_and_english_audio_tool_response_loop(self):
        from providers.engine_pipeline import PipelineEngine
        from providers.base import FunctionCall
        from actions.process_manager import process_manager
        class STT:
            def __init__(self, text): self.text = text
            async def transcribe(self, pcm, rate): return self.text
        class LLM:
            caps = {"tools": True}
            async def chat(self, messages, tools):
                if messages[-1]["role"] == "tool":
                    yield {"text": "Consulta concluída. Query complete."}
                else:
                    yield {"tool_calls": [FunctionCall("1", "process_manager", {"action": "details", "pid": os.getpid()})]}
        class TTS:
            async def speak(self, text): yield b"\x01\x00" * 2400
        async def turn(command):
            engine = PipelineEngine(LLM(), STT(command), TTS(), log=lambda _: None)
            engine._mic = [b"\x00\x00" * 1600]; engine._mic_bytes = 3200
            heard, said, audio = [], [], []
            try:
                self.assertEqual(await engine.flush_microphone(), command)
                async for msg in engine.receive():
                    if msg.tool_call:
                        call = msg.tool_call.function_calls[0]
                        result = process_manager(call.args)
                        self.assertTrue(result.startswith("status=done"))
                        await engine.send_tool_response(function_responses=[SimpleNamespace(id=call.id, name=call.name, response={"result": result})])
                    if msg.data: audio.append(msg.data)
                    if msg.server_content:
                        sc = msg.server_content
                        if sc.input_transcription: heard.append(sc.input_transcription.text)
                        if sc.output_transcription: said.append(sc.output_transcription.text)
                        if sc.turn_complete: break
                self.assertEqual(heard, [command]); self.assertTrue(said and audio)
            finally: await engine.close()
        with patch.dict(os.environ, {"MARK_NO_TIMING": "1"}), patch("core.session_preferences.blocked", return_value=False):
            for command in ("Quem está consumindo minha RAM?", "Which processes use my RAM?"):
                asyncio.run(asyncio.wait_for(turn(command), timeout=4))
