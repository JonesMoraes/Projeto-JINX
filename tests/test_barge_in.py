"""Synchronous audio/queue checks; no device, account, network or event loop."""
import ast
import asyncio
from pathlib import Path
import threading
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

import numpy as np
from core import barge_in
from core.echo import EchoGuard
from providers.base import Msg, FunctionCall
from providers.engine_pipeline import PipelineEngine


class BargeInTests(unittest.TestCase):
    def setUp(self):
        barge_in.configure({'enabled': True})
        self.addCleanup(barge_in.configure, {'enabled': False})
        self.gate = barge_in.Gate()
        self.pcm = np.zeros(1024, dtype=np.int16)

    def feed(self, echo, **kw):
        return self.gate.feed(echo, self.pcm, 16000, 0.5,
                              speaking=kw.pop('speaking', True),
                              allowed=kw.pop('allowed', True), **kw)

    def test_disabled_and_privacy_gates_do_not_classify(self):
        echo = Mock()
        barge_in.configure({'enabled': False})
        self.assertFalse(self.feed(echo))
        barge_in.configure({'enabled': True})
        self.assertFalse(self.feed(echo, allowed=False))
        self.assertFalse(self.feed(echo, speaking=False))
        echo.is_user_speech.assert_not_called()

    def test_sustained_detection_preserves_start_and_fires_once(self):
        echo = Mock(required_blocks=5)
        echo.is_user_speech.return_value = True
        for i in range(5):
            self.assertEqual(self.feed(echo, now=i * .064), i == 4)
        self.assertEqual(self.gate.last_detection_ms, 256)
        self.assertEqual(self.gate.take_audio(), (self.pcm.tobytes(),) * 5)
        self.assertEqual(self.gate.take_audio(), ())
        self.assertFalse(self.feed(echo))
        self.gate.reset()
        self.assertFalse(self.feed(echo))

    def test_noise_breaks_the_run_and_errors_fail_closed(self):
        echo = Mock(required_blocks=3)
        echo.is_user_speech.side_effect = [True, True, False, True, RuntimeError()]
        for _ in range(5):
            self.assertFalse(self.feed(echo))
        self.assertEqual(self.gate.take_audio(), ())

    def test_real_echo_guard_rejects_synthetic_echo(self):
        echo = EchoGuard()
        t = np.arange(1024) / 16000
        self.pcm = (12000 * np.sin(2 * np.pi * 600 * t)).astype(np.int16).reshape(-1, 1)
        for _ in range(40):
            echo.note_output(self.pcm, 16000, .5)
            self.assertFalse(self.feed(echo))
        # A sustained voice in another band is distinct from the played signal.
        self.pcm = (12000 * np.sin(2 * np.pi * 3000 * t)).astype(np.int16).reshape(-1, 1)
        results = [self.feed(echo) for _ in range(5)]
        self.assertEqual(results, [False] * 4 + [True])

    def test_pipeline_cancels_and_discards_stale_output_keeps_tools(self):
        engine = PipelineEngine(Mock(caps={}))
        engine._gen = Mock()
        engine._gen.done.return_value = False
        engine._followup = True
        call = Msg.calls([FunctionCall(id='1', name='test')])
        for msg in (Msg.audio(b'old'), Msg.said('old'), call):
            engine._queue.put_nowait(msg)
        engine.interrupt()
        engine._gen.cancel.assert_called_once()
        self.assertTrue(engine._queue.get_nowait().server_content.turn_complete)
        self.assertIs(engine._queue.get_nowait(), call)
        self.assertTrue(engine._queue.empty())
        self.assertFalse(engine._followup)

    def test_main_loop_handoff_rechecks_privacy_and_preserves_pcm(self):
        # Load actual methods without starting main.py (Qt/audio/boot side effects).
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JinxLive')
        names = {'_voice_interruption_allowed', '_interrupt_from_voice'}
        selected = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
        scope = {'barge_in': barge_in, 'time': time}
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'main.py', 'exec'), scope)
        obj = NS(ui=NS(muted=False, write_log=Mock()), _phone_active=False,
                 _wake_enabled=False, _awake=True, _ptt_enabled=False, _ptt_held=False,
                 _speaking_lock=threading.Lock(), _is_speaking=True,
                 interrupt=Mock(), out_queue=asyncio.Queue())
        obj._voice_interruption_allowed = lambda: scope['_voice_interruption_allowed'](obj)
        obj.ui.muted = True
        scope['_interrupt_from_voice'](obj, (b'first',), 256)
        obj.interrupt.assert_not_called()
        obj.ui.muted = False
        scope['_interrupt_from_voice'](obj, (b'first',), 256)
        obj.interrupt.assert_called_once()
        self.assertEqual(obj.out_queue.get_nowait()['data'], b'first')
        for key, val in (('_phone_active', True), ('_ptt_enabled', True), ('_wake_enabled', True)):
            obj._phone_active = obj._ptt_enabled = obj._wake_enabled = False
            obj._awake = False
            setattr(obj, key, val)
            self.assertFalse(obj._voice_interruption_allowed())


if __name__ == '__main__':
    unittest.main()
