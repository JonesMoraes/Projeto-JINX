import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
from core import google_workspace as api


class ScopeGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = {'calendar': True, 'drive': True, 'youtube': True}
        self.definition = {'installed': {'client_id': 'sample.apps.googleusercontent.com',
            'client_secret': 'sample-secret', 'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token'}}
        (self.root / 'google_client_secret.json').write_text(json.dumps(self.definition))
        for p in (patch.object(api, 'CONFIG_DIR', self.root), patch.object(api, 'config', return_value=self.cfg)):
            p.start()
            self.addCleanup(p.stop)

    def credential(self, scopes, refresh):
        info = {'client_id': self.definition['installed']['client_id'], 'token_uri': 'https://oauth2.googleapis.com/token',
                'refresh_token': refresh, 'token': refresh + '-access', 'scopes': scopes}
        return SimpleNamespace(valid=True, refresh_token=refresh, granted_scopes=scopes, scopes=scopes,
                               to_json=lambda: json.dumps(info))

    def fake_flows(self, fail_second=False):
        installed = Mock()
        flows = []
        def create(definition, scopes, **kwargs):
            flow = Mock()
            flow.run_local_server.return_value = self.credential(scopes, str(len(flows)))
            if flows and fail_second:
                flow.run_local_server.side_effect = RuntimeError('denied')
            flows.append(flow)
            return flow
        installed.from_client_config.side_effect = create
        return installed, flows

    def test_mixed_services_use_two_consents_and_two_tokens(self):
        installed, flows = self.fake_flows()
        with patch.dict(sys.modules, {'google_auth_oauthlib.flow': SimpleNamespace(InstalledAppFlow=installed)}):
            self.assertTrue(api.connect(self.cfg)[0])
        self.assertEqual(len(flows), 2)
        for call, flow in zip(installed.from_client_config.call_args_list, flows):
            scopes = call.kwargs['scopes']
            self.assertFalse(api.SCOPES['drive'] in scopes and api.SCOPES['youtube'] in scopes)
            self.assertEqual(flow.run_local_server.call_args.kwargs['include_granted_scopes'], 'false')
            self.assertTrue(flow.run_local_server.call_args.kwargs['open_browser'])
        workspace = api._read_token()
        youtube = api._read_token('youtube')
        self.assertIn(api.SCOPES['drive'], workspace['scopes'])
        self.assertNotIn(api.SCOPES['youtube'], workspace['scopes'])
        self.assertNotIn(api.SCOPES['drive'], youtube['scopes'])
        self.assertIn(api.SCOPES['youtube_read'], youtube['scopes'])

    def test_second_consent_failure_preserves_both_previous_tokens(self):
        previous = {}
        for filename in (api.TOKEN_NAME, api.YOUTUBE_TOKEN_NAME):
            path = self.root / filename
            path.write_text('previous-' + filename)
            previous[filename] = path.read_bytes()
        installed, _ = self.fake_flows(fail_second=True)
        with patch.dict(sys.modules, {'google_auth_oauthlib.flow': SimpleNamespace(InstalledAppFlow=installed)}):
            self.assertFalse(api.connect(self.cfg)[0])
        for filename, content in previous.items():
            self.assertEqual((self.root / filename).read_bytes(), content)

    def test_youtube_only_needs_one_consent_and_no_workspace_file(self):
        self.cfg.clear()
        self.cfg['youtube'] = True
        installed, flows = self.fake_flows()
        with patch.dict(sys.modules, {'google_auth_oauthlib.flow': SimpleNamespace(InstalledAppFlow=installed)}):
            self.assertTrue(api.connect(self.cfg)[0])
        self.assertEqual(len(flows), 1)
        self.assertFalse((self.root / api.TOKEN_NAME).exists())
        self.assertTrue((self.root / api.YOUTUBE_TOKEN_NAME).exists())

    def test_actual_library_generates_separate_scope_urls(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        for _, scopes in api.scope_groups(api.selected_scopes(self.cfg)):
            flow = InstalledAppFlow.from_client_config(self.definition, scopes=scopes, autogenerate_code_verifier=True)
            url, _ = flow.authorization_url(include_granted_scopes='false')
            query = parse_qs(urlparse(url).query)
            self.assertEqual(set(query['scope'][0].split()), set(scopes))
            self.assertEqual(query['include_granted_scopes'], ['false'])
            self.assertEqual(query['code_challenge_method'], ['S256'])

    def test_youtube_request_uses_its_own_token(self):
        workspace = json.loads(self.credential([api.SCOPES['drive']], 'workspace').to_json())
        youtube = json.loads(self.credential([api.SCOPES['youtube'], api.SCOPES['youtube_read']], 'youtube').to_json())
        api.write_secret(self.root / api.TOKEN_NAME, workspace)
        api.write_secret(self.root / api.YOUTUBE_TOKEN_NAME, youtube)
        factory = Mock(return_value=SimpleNamespace(valid=True))
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_info', factory):
            api.credentials('youtube')
        self.assertEqual(factory.call_args.args[0]['refresh_token'], 'youtube')

    def test_legacy_youtube_token_remains_readable(self):
        info = json.loads(self.credential([api.SCOPES['youtube'], api.SCOPES['youtube_read']], 'legacy').to_json())
        api.write_secret(self.root / api.TOKEN_NAME, info)
        self.assertEqual(api._read_token('youtube')['refresh_token'], 'legacy')
