"""Small, exact local display commands; no model/network needed for typing."""
import re
import unicodedata


def parse(text):
    raw = str(text or '').strip().rstrip('.!?')
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', raw.casefold())
                         if not unicodedata.combining(c))
    if normalized in ('tela cheia', 'modo orb', 'so o orb', 'ativar modo orb', 'fullscreen', 'orb mode'):
        return 'fullscreen', ''
    if normalized in ('sair da tela cheia', 'voltar ao normal', 'volte ao normal', 'modo janela', 'windowed', 'exit fullscreen'):
        return 'windowed', ''
    match = re.fullmatch(r'(abra|abrir|mostre|mostrar|amplie|ampliar|feche|fechar|open|show|expand|close)\s+(?:(?:o|a|the)\s+)?(?:(?:ultimo|latest|last)\s+)?(?:pop-?up|aviso|notification)(?:\s+(?:(?:de|do|da|the)\s+)?(.+))?', normalized)
    if match:
        verb, target = match.groups()
        action = 'close_popup' if verb in ('feche', 'fechar', 'close') else 'expand_popup' if verb in ('amplie', 'ampliar', 'expand') else 'open_popup'
        return action, target or ''
    return None
