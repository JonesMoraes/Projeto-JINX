"""Explicit, local camera pinch control; UI stays on the Qt main thread."""
from core import outcome
from core.gesture_control import control


def prepare_install(_values):
    from core import gesture_install, confirm
    try:
        if confirm.pending_title():
            return False, 'Outra confirmação está aberta.'
        plan = gesture_install.prepare()
        mb = plan['bytes'] / 1048576
        def apply():
            ok, message = gesture_install.install(plan, approved=True)
            return outcome.done('gesture_install', note=message) if ok else outcome.failed('gesture_install', message)
        result = confirm.request('gesture_install', f'Instalar controle por gestos · {mb:.1f} MB?',
            f'MediaPipe e modelo de mãos: até {mb:.1f} MB. Ambiente separado em config/gesture_runtime. '
            'Não altera as bibliotecas principais e não liga câmera ou mouse após instalar.', apply)
        return True, result
    except Exception:
        return False, 'Não foi possível preparar o instalador. Confira a conexão; nenhum gesto foi ativado.'


PLUGIN = {'name': 'gesture_control',
    'description': 'Controle por gestos / hand pinch mouse control. Only after explicit user request, start local webcam hand tracking: index finger moves cursor, sustained thumb-index pinch holds left mouse, open pinch releases. Stop releases mouse. Windows primary screen, Esc/F10 emergency stop. Never enable just because webcam is on.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['start', 'stop', 'status']}}, 'required': ['action']}}
PLUGIN_SETTINGS = {'namespace': 'gesture_control', 'title': 'GESTOS / PINÇA — CONTROLE LOCAL',
    'fields': [], 'action': {'label': 'PREPARAR INSTALAÇÃO (MOSTRA TAMANHO E PEDE CONFIRMAÇÃO)',
                            'run': prepare_install}}


def run(parameters, player=None, session_memory=None):
    try:
        action = (parameters or {}).get('action', 'status')
        if action == 'status':
            state = control.status()
            return outcome.done('gesture_control', **state)
        if action == 'stop':
            control.stop()
            return 'Controle por gestos interrompido; botão do mouse solto.'
        if action != 'start':
            return outcome.failed('gesture_control', 'Ação desconhecida')
        if player is None or not callable(getattr(player, 'toggle_gestures', None)):
            return outcome.failed('gesture_control', 'Abra o HUD para ativar gestos com indicador visível.')
        player.toggle_gestures(True)
        return outcome.started('gesture_control', note='Pedido enviado ao HUD; abra a mão quando aparecer o indicador. Esc/F10 para parar.')
    except Exception:
        return outcome.failed('gesture_control', 'Não foi possível controlar os gestos.')
