"""Bounded startup diagnostics for the normal asyncio voice runner.

No event-loop replacement, socket monkeypatch, firewall change or Qt imports.
"""
import asyncio
import socket
import sys
import threading


def prerequisite_problem(timeout=2.0):
    """Windows' Python socketpair fallback requires a local TCP connection.

    Checking it with deadlines prevents entering an unbounded accept() inside
    ProactorEventLoop on a host that refuses loopback connections.
    """
    if sys.platform != 'win32':
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.settimeout(timeout)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(listener.getsockname())
                peer, _ = listener.accept()
                with peer:
                    if (peer.getpeername() != client.getsockname()
                            or peer.getsockname() != client.getpeername()):
                        raise ConnectionError('Unexpected local peer')
        return None
    except OSError as exc:
        code = getattr(exc, 'winerror', None) or exc.errno
        if getattr(exc, 'winerror', None):
            detail = f' (WinError {code})'
        elif code is not None:
            detail = f' (erro {code})'
        else:
            detail = ' (tempo limite)' if isinstance(exc, TimeoutError) else ' (conexão local não validada)'
        return ('A voz não pôde iniciar: a conexão local exigida pelo asyncio foi recusada '
                'ou não respondeu' + detail + '.\n'
                'O HUD continua disponível. Este processo não alterou permissões de rede.\n'
                'Encerre esta instância e abra main.py pelo ambiente Python local em uma '
                'sessão que permita conexões locais. Se a recusa persistir, o responsável '
                'pelo ambiente precisa verificar a política de acesso.\n'
                'Voice unavailable: the local connection required by asyncio was refused '
                'or timed out. Network permissions were not changed.')


def report_problem(ui, message):
    for method, args in (
        ('set_state', ('ERROR',)),
        ('write_log', ('ERR: ' + message,)),
        ('show_content', ('VOZ INDISPONÍVEL / VOICE UNAVAILABLE', message)),
    ):
        try:
            getattr(ui, method)(*args)
        except Exception:
            pass
    print('[JINX] ' + message, flush=True)


def run_voice_session(ui, factory, on_created=None):
    """Run on the existing worker, reporting failures through the UI facade."""
    voice = None
    coroutine = None
    try:
        ui.wait_for_api_key()
        voice = factory(ui)
        voice._runtime_stopped = threading.Event()
        if on_created is not None:
            on_created(voice)
        problem = prerequisite_problem()
        if problem:
            voice._startup_problem = problem
            report_problem(ui, problem)
            return False
        coroutine = voice.run()
        asyncio.run(coroutine)
        return True
    except KeyboardInterrupt:
        return False
    except Exception as exc:
        # Transport/SDK exceptions may embed credentials or signed URLs.
        # Never print their raw text into the HUD or startup logs.
        message = ('Falha ao iniciar a voz / Voice startup failed: '
                   + type(exc).__name__ + '. A interface continua disponível.')
        if voice is not None:
            voice._startup_problem = message
        report_problem(ui, message)
        return False
    finally:
        if coroutine is not None:
            coroutine.close()
        if voice is not None and getattr(voice, '_runtime_stopped', None) is not None:
            voice._runtime_stopped.set()
