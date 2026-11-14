"""Confirmed streaming YouTube upload using the shared OAuth account."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from core import google_workspace as google, outcome


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(parameters):
    path = Path(str(parameters.get('path') or '')).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.mp4', '.mov', '.mkv', '.webm', '.avi') or path.stat().st_size == 0:
        raise ValueError('Invalid video')
    title = str(parameters.get('title') or path.stem)
    description = str(parameters.get('description') or '')
    privacy = parameters.get('privacy', 'private')
    if not 1 <= len(title) <= 100 or len(description.encode('utf-8')) > 5000 or privacy not in ('private', 'unlisted', 'public'):
        raise ValueError('Invalid metadata')
    return {'path': path, 'size': path.stat().st_size, 'sha256': fingerprint(path),
            'body': {'snippet': {'title': title, 'description': description}, 'status': {'privacyStatus': privacy}}}


def upload(client, draft):
    import requests
    client.check_connection()
    path = draft['path']
    if path.stat().st_size != draft['size'] or fingerprint(path) != draft['sha256']:
        return outcome.failed('youtube_upload', 'Vídeo mudou após revisão / Video changed after review')
    headers = {'Authorization': 'Bearer ' + client.creds.token,
               'X-Upload-Content-Length': str(draft['size']), 'X-Upload-Content-Type': 'application/octet-stream'}
    with requests.post('https://www.googleapis.com/upload/youtube/v3/videos',
            params={'uploadType': 'resumable', 'part': 'snippet,status'}, json=draft['body'],
            headers=headers, timeout=(4, 20), allow_redirects=False) as response:
        if response.status_code not in (200, 201):
            return outcome.failed('youtube_upload', 'Não iniciou upload / Upload not initiated')
        location = response.headers.get('Location', '')
    parsed = urlsplit(location)
    if (parsed.scheme != 'https' or parsed.netloc != 'www.googleapis.com' or
            parsed.path != '/upload/youtube/v3/videos' or parsed.fragment):
        return outcome.failed('youtube_upload', 'Destino de upload inválido / Invalid upload destination')
    client.check_connection()
    with path.open('rb') as stream:
        with requests.put(location, data=stream, headers={'Content-Type': 'application/octet-stream',
                'Content-Length': str(draft['size']), 'Authorization': 'Bearer ' + client.creds.token},
                timeout=(4, 120), allow_redirects=False) as response:
            if response.status_code not in (200, 201):
                return outcome.unverified('youtube_upload', 'Confira seu canal antes de repetir / Check your channel before retrying')
            data = response.json()
    video_id = google.identifier(data.get('id'))
    result = client.request('GET', '/videos', params={'id': video_id, 'part': 'status,snippet'})
    rows = (result or {}).get('items', [])
    if not rows or rows[0].get('id') != video_id or rows[0].get('status', {}).get('privacyStatus') != draft['body']['status']['privacyStatus']:
        return outcome.unverified('youtube_upload', 'Visibilidade não confirmada / Visibility not confirmed', id=video_id)
    return outcome.done('youtube_upload', id=video_id, privacy=rows[0]['status']['privacyStatus'],
                        processing='YouTube processing may still be pending')
