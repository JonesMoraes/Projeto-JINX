import asyncio
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
import numpy as np
from core import meeting, office, undo


def wav(path):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        data = (np.sin(np.arange(16000) / 15) * 3000).astype("<i2").tobytes()
        f.writeframes(data)


class MeetingTest(unittest.TestCase):
    def setUp(self):
        undo.clear(); self.addCleanup(undo.clear)

    def test_no_indicator_no_capture(self):
        with patch.object(meeting, "devices") as devices:
            with self.assertRaises(RuntimeError): meeting.Manager().start(None)
            devices.assert_not_called()

    def test_unconfigured_stt_does_not_download(self):
        with patch.object(meeting, "get_pipeline", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "Groq"): meeting.stt_provider()

    def test_full_synthetic_capture_stop_transcribe_summary_file(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = meeting.Manager(); player = Mock()
            player.meeting_recording.side_effect = lambda active, ack=None: ack.set() if ack else None
            def capture(device, path, stop, barrier, deadline):
                wav(path); barrier.wait(timeout=1); stop.wait(2)
            provider = Mock(); provider.transcribe = AsyncMock(return_value="Precisamos revisar o circuito amanhã")
            with patch.object(meeting, "stt_provider", return_value=provider), patch.object(meeting, "devices", return_value=[("mic", object()), ("system", object())]), \
                 patch.object(meeting, "capture", side_effect=capture), patch.object(meeting.gemini, "text", return_value="Resumo\nAção: revisar circuito") as ladder, \
                 patch.object(office, "destination", return_value=Path(temp)):
                manager.start(player)
                until = time.monotonic() + 2
                while manager.status()["state"] == "starting" and time.monotonic() < until: time.sleep(.01)
                self.assertEqual(manager.status()["state"], "recording")
                manager.stop(); manager.thread.join(4)
                self.assertFalse(manager.thread.is_alive())
                status = manager.status(); self.assertEqual(status["state"], "done")
                self.assertTrue(Path(status["path"]).is_file())
                self.assertIn("<<<UNTRUSTED", ladder.call_args.args[0])
                self.assertEqual(provider.transcribe.await_count, 2)
                player.meeting_recording.assert_any_call(False)
                undo.undo_last(); self.assertFalse(Path(status["path"]).exists())

    def test_backend_failure_stops_indicator_and_no_summary(self):
        manager = meeting.Manager(); player = Mock()
        player.meeting_recording.side_effect = lambda active, ack=None: ack.set() if ack else None
        with patch.object(meeting, "stt_provider", return_value=Mock()), patch.object(meeting, "devices", return_value=[("mic", object()), ("loop", object())]), \
             patch.object(meeting, "capture", side_effect=RuntimeError), patch.object(meeting.gemini, "text") as ladder:
            manager.start(player); manager.thread.join(3)
            self.assertEqual(manager.status()["state"], "failed")
            player.meeting_recording.assert_any_call(False); ladder.assert_not_called()

    def test_transcription_partial_reports_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.wav"; wav(path)
            provider = Mock(transcribe=AsyncMock(side_effect=RuntimeError))
            text, failures = asyncio.run(meeting.transcribe(provider, [("mic", path)]))
            self.assertEqual(text, ""); self.assertEqual(failures, 1)

    def test_actual_conversion_all_channels_and_bounded_pcm(self):
        with tempfile.TemporaryDirectory() as temp:
            stop = threading.Event()
            recorder = Mock(); recorder.__enter__ = Mock(return_value=recorder); recorder.__exit__ = Mock(return_value=None)
            def samples(**kwargs):
                stop.set(); return np.ones((4800, 2), dtype=np.float32) * .1
            recorder.record.side_effect = samples
            device = Mock(); device.recorder.return_value = recorder
            path = Path(temp) / "x.wav"
            meeting.capture(device, path, stop, threading.Barrier(1), time.monotonic() + 5)
            with wave.open(str(path), "rb") as f:
                self.assertEqual(f.getframerate(), 16000); self.assertEqual(f.getnframes(), 1600)
            self.assertIsNone(device.recorder.call_args.kwargs["channels"])
