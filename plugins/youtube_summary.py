from core import youtube_summary


def install(values):
    from core.optional_packages import install as packages
    return packages("youtube")


PLUGIN = {"name": "youtube_summary", "description": "Summarize captions of a YouTube HTTPS URL into the content panel, through the configured model. Reports absent captions/access limits; leaves HUD playback untouched.",
    "parameters": {"type": "OBJECT", "properties": {"url": {"type": "STRING"}, "language": {"type": "STRING", "enum": ["pt-BR", "en"]}}, "required": ["url"]}}
PLUGIN_SETTINGS = {"namespace": "youtube_summary", "title": "LEGENDAS YOUTUBE / YOUTUBE CAPTIONS", "fields": [],
    "action": {"label": "INSTALAR DEPENDÊNCIA OPCIONAL / INSTALL OPTIONAL DEPENDENCY", "run": install}}


def run(parameters, player=None, session_memory=None):
    return youtube_summary.run(parameters, player)
