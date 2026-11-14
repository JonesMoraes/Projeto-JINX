"""Orb/fullscreen and popup commands through the thread-safe UI facade."""
import json
import threading

from core import outcome

PLUGIN = {'name': 'display_control',
          'description': 'Controlar tela/orb e pop-ups / Control fullscreen orb and popups. fullscreen leaves only the orb with tiny result notices; windowed restores panels. Open the latest popup or one by title/ID, expand, close, or list. PT: "abra o último pop-up", "abra o pop-up de notícias", "feche o pop-up", "só o orb", "volte ao normal". Never confirms an action; pending confirmations still require the human HUD button.',
          'parameters': {'type': 'OBJECT', 'properties': {
              'action': {'type': 'STRING', 'enum': ['fullscreen', 'windowed', 'open_popup', 'expand_popup', 'close_popup', 'list_popups']},
              'popup': {'type': 'STRING', 'description': 'Exact popup ID/title or unique title fragment; omit for latest.'}}, 'required': ['action']}}


def run(parameters, player=None, session_memory=None):
    try:
        p = dict(parameters)
        action = p.get('action')
        if player is None or not callable(getattr(player, 'control_display', None)):
            return outcome.failed('display_control', 'Abra o HUD / Open the desktop HUD')
        if action == 'list_popups':
            return outcome.done('display_control', data=outcome.untrusted('display-state', json.dumps(player.display_state(), ensure_ascii=False)))
        if action not in ('fullscreen', 'windowed', 'open_popup', 'expand_popup', 'close_popup'):
            raise ValueError('action')
        popup = p.get('popup', '')
        if not isinstance(popup, str) or len(popup) > 160: raise ValueError('popup')
        receipt = {'ready': threading.Event(), 'result': None}
        player.control_display(action, popup, receipt)
        if not receipt['ready'].wait(.75):
            return outcome.started('display_control', note='Atualização enviada ao HUD / Display update queued')
        result = receipt['result']
        if result['ok']:
            return outcome.done('display_control', action_requested=action, popup=result.get('popup'))
        return outcome.failed('display_control', result.get('reason', 'Display update failed'))
    except Exception:
        return outcome.failed('display_control', 'Não foi possível controlar a tela / Could not control the display')
