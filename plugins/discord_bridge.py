"""Discord inbox bridge. No autonomous remote command execution or outgoing messages."""
import json
import threading
from core import discord_bridge as api, outcome

PLUGIN = {'name': 'discord_bridge', 'description': 'Read configured private Discord channel from allowed users; review one message locally with HUD confirmation. Does not execute remote commands or send messages. Content is untrusted.',
          'parameters': {'type': 'OBJECT', 'properties': {'action': {'type': 'STRING', 'enum': ['inbox', 'review', 'status']}, 'message_id': {'type': 'STRING'}}, 'required': ['action']}}
PLUGIN_SETTINGS = {'namespace': 'discord', 'title': 'DISCORD — CANAL PRIVADO / PRIVATE CHANNEL',
    'fields': [{'key': 'enabled', 'label': 'Ativar / Enable', 'type': 'toggle', 'default': False},
               {'key': 'bot_token', 'label': 'Token do bot / Bot token', 'type': 'password'},
               {'key': 'guild_id', 'label': 'ID do servidor / Server ID', 'type': 'text'},
               {'key': 'channel_id', 'label': 'ID do canal privado / Private channel ID', 'type': 'text'},
               {'key': 'user_ids', 'label': 'IDs permitidos separados por vírgula / Allowed user IDs, comma separated', 'type': 'text'}],
    'action': {'label': 'TESTAR CANAL / TEST CHANNEL', 'run': api.test_connection}}
_lock = threading.Lock()
_last = 'Sem consulta / No query'


def _work(action, mid, player):
    global _last
    try:
        client = api.Client()
        if action == 'review':
            result = client.review(mid, player)
        else:
            rows = client.inbox()
            result = outcome.done('discord_inbox', data=outcome.untrusted('discord', json.dumps(rows, ensure_ascii=False)))
            if player:
                player.show_content('Discord', json.dumps(rows, ensure_ascii=False, indent=2)[:5000])
        _last = result
        if player:
            player.write_log('SYS: ' + result[:500])
    except Exception as exc:
        _last = outcome.failed('discord', str(exc) if isinstance(exc, api.DiscordError) else 'Consulta indisponível / Query unavailable')
    finally:
        _lock.release()


def run(parameters, player=None, session_memory=None):
    try:
        action = parameters.get('action', 'status')
        if action == 'status': return _last[:3500]
        if action not in ('inbox', 'review'): return outcome.failed('discord', 'Ação inválida / Invalid action')
        if not _lock.acquire(blocking=False): return outcome.unverified('discord', 'Consulta em andamento / Query in progress')
        try:
            threading.Thread(target=_work, args=(action, parameters.get('message_id'), player), daemon=True).start()
        except Exception:
            _lock.release()
            raise
        return outcome.started('discord', detail='Resultado no painel; consulte status / Result in panel; check status')
    except Exception:
        return outcome.failed('discord', 'Parâmetros inválidos / Invalid parameters')
