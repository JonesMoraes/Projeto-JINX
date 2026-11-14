"""Home Assistant / local Tuya, opt-in and explicit discovery."""
from core import smart_home as api, outcome
from core.plugin_jobs import Jobs

PLUGIN = {'name': 'smart_home', 'description': 'Casa inteligente / Smart home: explicitly discover configured Home Assistant lights/switches or configured Tuya device; read state, turn on/off exact entity ID with verified readback and undo. No automatic network scan.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['status', 'discover', 'state', 'on', 'off']},
        'backend': {'type': 'STRING', 'enum': ['ha', 'tuya']},
        'entity_id': {'type': 'STRING'}}, 'required': ['action']}}
PLUGIN_SETTINGS = {'namespace': 'smart_home', 'title': 'CASA / SMART HOME', 'fields': [
    {'key': 'enabled', 'label': 'Ativar / Enable', 'type': 'toggle', 'default': False},
    *[{'key': key, 'label': label, 'type': kind} for key, label, kind in (
        ('ha_url', 'URL Home Assistant', 'text'), ('ha_token', 'Token Home Assistant', 'password'),
        ('tuya_id', 'ID Tuya', 'text'), ('tuya_ip', 'IP local Tuya / Tuya LAN IP', 'text'),
        ('tuya_key', 'Chave local Tuya / Tuya local key', 'password'),
        ('tuya_version', 'Versão Tuya / Tuya version (3.3)', 'text'),
        ('tuya_dp', 'DPS interruptor / Switch DPS (1)', 'text'))]]}
_jobs = Jobs('Casa / Smart home')


def run(parameters, player=None, session_memory=None):
    try:
        parameters = dict(parameters)
        action = parameters.get('action', 'status')
        if action == 'status':
            return _jobs.last
        if action not in ('discover', 'state', 'on', 'off'):
            return outcome.failed('smart_home', 'Ação inválida / Invalid action')
        return _jobs.start(lambda: api.execute(parameters), player)
    except Exception:
        return outcome.failed('smart_home', 'Parâmetros inválidos / Invalid parameters')
