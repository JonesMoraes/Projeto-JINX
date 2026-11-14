"""Every upload is reviewed and confirmed locally; private by default."""
from core import confirm, outcome, google_workspace
from core import video_upload as api
from core.plugin_jobs import Jobs

PLUGIN = {'name': 'video_upload', 'description': 'Upload a local video to YouTube through shared Google OAuth. Always requires local HUD confirmation; private by default. Title defaults to filename, description empty. Never invent metadata or retry an ambiguous upload.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['upload', 'status']},
        **{key: {'type': 'STRING'} for key in ('path', 'title', 'description')},
        'privacy': {'type': 'STRING', 'enum': ['private', 'unlisted', 'public']}}, 'required': ['action']}}
_jobs = Jobs('YouTube upload')


def _review(parameters, player):
    if player is None or not callable(getattr(player, 'show_confirm', None)):
        return outcome.failed('youtube_upload', 'Abra o HUD para revisar / Open HUD for review')
    client = google_workspace.Client('youtube', write=True)
    draft = api.prepare(parameters)
    if confirm.pending_title():
        return outcome.failed('youtube_upload', 'Outra confirmação pendente / Another confirmation pending')
    detail = str(draft['path']) + '\n' + str(draft['size']) + ' bytes\n' + str(draft['body'])
    player.show_content('Revisar upload / Review upload', detail)
    def send():
        # Confirmation runs on a worker. Re-use the job lock to prevent overlapping uploads.
        return _jobs.start(lambda: api.upload(client, draft), player)
    return confirm.request('youtube_upload', 'Enviar vídeo / Upload video', detail, send)


def run(parameters, player=None, session_memory=None):
    try:
        parameters = dict(parameters)
        if parameters.get('action') == 'status': return _jobs.last
        if parameters.get('action') != 'upload': return outcome.failed('youtube_upload', 'Ação inválida / Invalid action')
        return _jobs.start(lambda: _review(parameters, player), player)
    except Exception:
        return outcome.failed('youtube_upload', 'Parâmetros inválidos / Invalid parameters')
