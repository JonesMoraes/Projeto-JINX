"""Apply the saved opt-in voice interruption setting without restarting."""
from core import barge_in, outcome

PLUGIN = {'name': 'barge_in', 'description': 'Apply saved voice interruption setting / Aplicar configuração salva de interrupção por voz. Uses existing CPU echo guard; hardware latency is not guaranteed.',
    'parameters': {'type': 'OBJECT', 'properties': {'action': {'type': 'STRING', 'enum': ['apply']}}, 'required': ['action']}}
PLUGIN_SETTINGS = {'namespace': 'barge_in', 'title': 'INTERROMPER POR VOZ / VOICE INTERRUPTION', 'fields': [
    {'key': 'enabled', 'label': 'Ativar (experimental; depende do eco da sala) / Enable (experimental; room dependent)', 'type': 'toggle', 'default': False}],
    'action': {'label': 'APLICAR / APPLY', 'run': barge_in.configure}}


def run(parameters, player=None, session_memory=None):
    try:
        if parameters.get('action') != 'apply': return outcome.failed('barge_in', 'Ação inválida / Invalid action')
        return barge_in.configure()[1]
    except Exception:
        return outcome.failed('barge_in', 'Não foi possível aplicar / Could not apply')
