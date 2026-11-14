import asyncio
from contextlib import redirect_stdout
import io
import socket
import unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

from core import voice_runtime as runtime


class VoiceRuntimeTests(unittest.TestCase):
    def sockets(self):
        listener, client, peer = (MagicMock() for _ in range(3))
        contexts = [listener, client, peer]
        for obj in contexts:
            obj.__enter__.return_value = obj
        listener.getsockname.return_value = ('127.0.0.1', 12345)
        client.getpeername.return_value = ('127.0.0.1', 12345)
        client.getsockname.return_value = ('127.0.0.1', 12346)
        peer.getpeername.return_value = ('127.0.0.1', 12346)
        peer.getsockname.return_value = ('127.0.0.1', 12345)
        listener.accept.return_value = (contexts[2], ('127.0.0.1', 12346))
        return listener, client, peer, contexts

    def test_bounded_probe_checks_peer_and_closes_sockets(self):
        listener, client, peer, contexts = self.sockets()
        with patch.object(runtime.sys, 'platform', 'win32'), \
                patch.object(runtime.socket, 'socket', side_effect=contexts[:2]):
            self.assertIsNone(runtime.prerequisite_problem(timeout=.2))
        listener.settimeout.assert_called_once_with(.2)
        client.settimeout.assert_called_once_with(.2)
        client.connect.assert_called_once_with(('127.0.0.1', 12345))
        for context in contexts:
            context.__exit__.assert_called_once()

    def test_denied_connection_is_reported_without_unbounded_accept(self):
        listener, client, peer, contexts = self.sockets()
        error = PermissionError('sensitive details')
        error.winerror = 10013
        client.connect.side_effect = error
        with patch.object(runtime.sys, 'platform', 'win32'), \
                patch.object(runtime.socket, 'socket', side_effect=contexts[:2]):
            problem = runtime.prerequisite_problem()
        self.assertIn('WinError 10013', problem)
        self.assertNotIn('sensitive details', problem)
        listener.accept.assert_not_called()
        contexts[0].__exit__.assert_called_once()
        contexts[1].__exit__.assert_called_once()

    def test_timeout_and_wrong_peer_are_unavailable(self):
        for wrong_peer in (False, True):
            listener, client, peer, contexts = self.sockets()
            if wrong_peer:
                peer.getpeername.return_value = ('127.0.0.1', 9999)
            else:
                listener.accept.side_effect = socket.timeout()
            with patch.object(runtime.sys, 'platform', 'win32'), \
                    patch.object(runtime.socket, 'socket', side_effect=contexts[:2]):
                self.assertIn('Voice unavailable', runtime.prerequisite_problem())

    def test_non_windows_does_not_require_windows_loopback(self):
        with patch.object(runtime.sys, 'platform', 'linux'), patch.object(runtime.socket, 'socket') as create:
            self.assertIsNone(runtime.prerequisite_problem())
        create.assert_not_called()

    def test_blocked_runner_keeps_ui_and_never_creates_event_loop(self):
        ui, factory, on_created = Mock(), Mock(), Mock()
        with patch.object(runtime, 'prerequisite_problem', return_value='Local connection denied'), \
                patch.object(runtime.asyncio, 'run') as run, redirect_stdout(io.StringIO()):
            self.assertFalse(runtime.run_voice_session(ui, factory, on_created))
        ui.wait_for_api_key.assert_called_once()
        on_created.assert_called_once_with(factory.return_value)
        run.assert_not_called()
        factory.return_value.run.assert_not_called()
        ui.set_state.assert_called_with('ERROR')
        ui.show_content.assert_called_once()
        self.assertEqual(factory.return_value._startup_problem, 'Local connection denied')
        self.assertTrue(factory.return_value._runtime_stopped.is_set())

    def test_success_path_uses_standard_asyncio_and_releases_coroutine(self):
        async def session():
            return None
        coroutine = session()
        voice = NS(run=Mock(return_value=coroutine))
        with patch.object(runtime, 'prerequisite_problem', return_value=None), \
                patch.object(runtime.asyncio, 'run') as run:
            self.assertTrue(runtime.run_voice_session(Mock(), lambda ui: voice))
        run.assert_called_once_with(coroutine)
        self.assertIsNone(coroutine.cr_frame)

    def test_initialization_failure_is_visible_without_secret_text(self):
        ui = Mock()
        factory = Mock(side_effect=RuntimeError('secret-token'))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(runtime.run_voice_session(ui, factory))
        self.assertIn('RuntimeError', output.getvalue())
        self.assertNotIn('secret-token', output.getvalue())
        self.assertNotIn('secret-token', str(ui.show_content.call_args))

    def test_event_loop_creation_error_closes_coroutine_and_reports(self):
        async def session():
            pass
        coroutine = session()
        voice, ui = NS(run=lambda: coroutine), Mock()
        with patch.object(runtime, 'prerequisite_problem', return_value=None), \
                patch.object(runtime.asyncio, 'run', side_effect=RuntimeError('secret')), \
                redirect_stdout(io.StringIO()):
            self.assertFalse(runtime.run_voice_session(ui, lambda ui: voice))
        self.assertIsNone(coroutine.cr_frame)
        self.assertIn('RuntimeError', voice._startup_problem)
        self.assertNotIn('secret', voice._startup_problem)


if __name__ == '__main__': unittest.main()
