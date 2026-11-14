"""User-reviewed preferences; no executable instructions or automatic acceptance."""
import json
from core import learned_rules as rules, outcome

PLUGIN = {'name': 'learned_rules', 'description': 'Preferências aprendidas / Learned preferences: propose a style or workflow rule, list stored/pending, review locally for acceptance, reject, or remove by exact ID. Model parameters cannot accept a proposal. Never changes safety or tool permissions.',
          'parameters': {'type': 'OBJECT', 'properties': {
              'action': {'type': 'STRING', 'enum': ['propose', 'list', 'pending', 'review', 'reject', 'remove']},
              'text': {'type': 'STRING'}, 'id': {'type': 'STRING'},
              'kind': {'type': 'STRING', 'enum': ['style', 'workflow']}}, 'required': ['action']}}


def run(parameters, player=None, session_memory=None):
    try:
        p = dict(parameters)
        action = p.get('action')
        if action == 'propose':
            row = rules.propose(p.get('text'), p.get('kind', 'style'))
            if player:
                player.show_content('Preferência proposta / Proposed preference', row['id'] + '\n' + row['text'])
            return outcome.done('rule_proposal', id=row['id'], note='Pending local acceptance; not stored')
        if action in ('list', 'pending'):
            rows = rules.list_rules() if action == 'list' else rules.pending()
            text = json.dumps(rows, ensure_ascii=False)
            if player:
                player.show_content('Preferências / Preferences', text)
            return outcome.done('learned_rules', data=outcome.untrusted('preferences', text))
        if action == 'review': return rules.review(p.get('id'), player)
        if action == 'reject': return rules.reject(p.get('id'))
        if action == 'remove': return rules.remove(p.get('id'))
        raise ValueError('action')
    except Exception:
        return outcome.failed('learned_rules', 'Não foi possível aplicar; confira ação/ID ou arquivo / Could not apply; check action, ID or store')
