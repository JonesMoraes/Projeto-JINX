import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import agenda_sync, agenda_store, undo, google_workspace, google_calendar_sync
from plugins import agenda


class GoogleAgendaRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(agenda_store, 'PATH', Path(self.temp.name) / 'agenda.json')
        patcher.start(); self.addCleanup(patcher.stop)
        undo.clear(); self.addCleanup(undo.clear)
        self.cfg = {'agenda': {'enabled': True, 'list_id': 'old-trello-list'},
                    'google_workspace': {'calendar': True, 'calendar_sync': True, 'calendar_id': 'primary'}}
        for item in (
            patch.object(agenda_sync, 'get_plugin_config', side_effect=lambda name: self.cfg.get(name, {})),
            patch.object(agenda_sync, 'get_plugin_enabled', return_value=True),
            patch.object(google_workspace, 'config', side_effect=lambda: self.cfg['google_workspace']),
        ):
            item.start(); self.addCleanup(item.stop)

    def test_legacy_trello_configuration_does_not_route_default_agenda_to_trello(self):
        client = Mock()
        with patch.object(google_workspace, 'Client', return_value=client), \
                patch.object(google_calendar_sync, 'sync', return_value={'complete': True, 'changes': 2}) as sync, \
                patch.object(agenda_sync, '_sync_trello_now') as trello:
            result = agenda_sync.sync_now()
        self.assertIn('status=done', result)
        self.assertIn('agenda_google_sync', result)
        sync.assert_called_once_with(client, 'primary')
        trello.assert_not_called()

    def test_disabled_google_sync_is_plain_instruction_and_preserves_local_data(self):
        event = agenda_store.upsert('Reunião', '2026-11-14T17:00:00-03:00')
        before = agenda_store.PATH.read_bytes()
        self.cfg['google_workspace']['calendar_sync'] = False
        with patch.object(google_workspace, 'Client') as client:
            result = agenda_sync.sync_now()
        client.assert_not_called()
        message = agenda_sync.display_result(result)
        self.assertIn('Google Agenda', message)
        self.assertNotIn('Tell the user', message)
        self.assertNotIn('status=', message)
        self.assertEqual(agenda_store.PATH.read_bytes(), before)

    def test_google_failure_never_falls_back_to_trello(self):
        with patch.object(google_workspace, 'Client', side_effect=google_workspace.GoogleError('Reconecte a conta Google.')), \
                patch.object(agenda_sync, '_sync_trello_now') as trello:
            result = agenda_sync.sync_now()
        self.assertIn('status=unverified', result)
        trello.assert_not_called()

    def test_local_crud_and_undo_never_upload_events_or_modify_trello(self):
        with patch.object(agenda_sync, 'sync_now') as sync:
            result = agenda.run({'action': 'add', 'title': 'Local', 'due': '2026-11-14T17:00:00-03:00'})
            self.assertIn('status=done', result)
            self.assertEqual(len(agenda_store.all_events()), 1)
            undo.undo_last()
            self.assertEqual(agenda_store.all_events(), [])
            sync.assert_not_called()

    def test_voice_sync_is_queued_off_the_tool_thread(self):
        player = Mock()
        with patch.object(agenda._google_jobs, 'start', return_value='queued') as job:
            self.assertEqual(agenda.run({'action': 'sync'}, player), 'queued')
        self.assertIs(job.call_args.args[1], player)


class GoogleAgendaPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_uses_google_fields_and_preserves_other_google_services(self):
        from gui.agenda_panel import AgendaPanel
        with patch('gui.agenda_panel.get_plugin_config', return_value={'calendar_sync': False, 'calendar_id': 'primary'}), \
                patch.object(AgendaPanel, '_execute'), \
                patch('gui.agenda_panel.save_plugin_config') as save:
            panel = AgendaPanel()
            try:
                self.assertFalse(hasattr(panel, 'list_id'))
                self.assertIn('Google', panel.connect_btn.text())
                panel.enabled.setChecked(True)
                panel.calendar_id.setText('my-calendar')
                self.assertTrue(panel._save())
                self.assertEqual(save.call_args_list[0].args, ('agenda', {'provider': 'google', 'enabled': False}))
                namespace, values = save.call_args_list[1].args
                self.assertEqual(namespace, 'google_workspace')
                self.assertEqual(values['calendar_id'], 'my-calendar')
                self.assertNotIn('gmail_read', values)
                self.assertNotIn('drive', values)
            finally:
                panel.close(); panel.deleteLater(); self.app.processEvents()


if __name__ == '__main__': unittest.main()
