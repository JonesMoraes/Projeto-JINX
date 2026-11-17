"""Upload local videos through the configured YouTube account."""
from core import confirm, outcome, google_workspace
from core import video_upload as api
from core.plugin_jobs import Jobs

PLUGIN = {'name': 'video_upload', 'description': 'Upload a local video to YouTube through shared Google OAuth. Private by default. Title defaults to filename, description empty. Never invent metadata or retry an ambiguous upload.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['upload', 'status']},
        **{key: {'type': 'STRING'} for key in ('path', 'title', 'description')},
        'privacy': {'type': 'STRING', 'enum': ['private', 'unlisted', 'public']}}, 'required': ['action']}}
_jobs = Jobs('YouTube upload')


def _review(parameters, player):
    try:
        draft = api.prepare(parameters)
    except (OSError, ValueError) as exc:
        return outcome.failed('youtube_upload', f'Vídeo inválido / Invalid video: {str(exc)[:180]}')
    client = google_workspace.Client('youtube', write=True)
    if confirm.pending_title():
        return outcome.failed('youtube_upload', 'Outra confirmação pendente / Another confirmation pending')
    detail = str(draft['path']) + '\n' + str(draft['size']) + ' bytes\n' + str(draft['body'])
    if player is not None and callable(getattr(player, 'show_content', None)):
        player.show_content('Upload do YouTube / YouTube upload', detail)
    def send():
        # Re-use the job lock to prevent overlapping uploads.
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
