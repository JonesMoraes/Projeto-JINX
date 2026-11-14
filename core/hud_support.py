"""Decide whether optional web visuals can run in this process, without Qt."""
import os


def web_hud_block_reason():
    if os.environ.get('JINX_DISABLE_WEBENGINE') == '1' or os.environ.get('JINX_ENABLE_WEBENGINE_HUD') == '0':
        return 'Visuais web desativados para esta execução.'
    if (os.environ.get('CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY')
            or os.environ.get('CODEX_SANDBOX_NETWORK_DISABLED') == '1'):
        return 'O executor restrito desta sessão não suporta o WebEngine. Abra o JINX pelo Windows para usar EVO/ECHO.'
    if os.environ.get('QT_QPA_PLATFORM', '').lower() in ('offscreen', 'minimal'):
        return 'Visuais web não são iniciados em testes sem tela.'
    return ''
