import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import agenda_store as store, agenda_sync as sync, trello_client as api, undo
from plugins import agenda, trello_control


class AgendaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = patch.object(store, "PATH", Path(temp.name) / "agenda.json")
        self.path.start()
        self.addCleanup(self.path.stop)
        self.cfg = {"agenda": {"enabled": True, "list_id": "mylist"},
                    "trello": {"api_key": "mykey", "token": "mytoken"}}
        self.config = patch.object(sync, "get_plugin_config", side_effect=lambda n: self.cfg[n])
        self.config.start()
        self.addCleanup(self.config.stop)
        self.remote = {}
        self.posts = 0
        def request(method, path, values):
            self.posts += 1
            card = {"id": "card1", "idList": "mylist", "closed": False, **values}
            self.remote["card1"] = card
            return copy.deepcopy(card)
        self.patches = [patch.object(api, "cards", side_effect=lambda _: copy.deepcopy(list(self.remote.values()))),
                        patch.object(api, "request", side_effect=request),
                        patch.object(api, "card", side_effect=lambda cid: copy.deepcopy(self.remote[cid])),
                        patch.object(api, "update", side_effect=self.update)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        undo.clear()
        self.addCleanup(undo.clear)

    def update(self, cid, values):
        self.remote[cid].update(values)
        return copy.deepcopy(self.remote[cid])

    def event(self):
        return store.upsert("Call", "2026-11-14T16:00:00-03:00")

    def test_push_pull_reschedule_idempotent(self):
        event = self.event()
        self.assertIn("status=done", sync.sync_now())
        sync.sync_now()
        self.assertEqual(self.posts, 1)
        self.remote["card1"]["due"] = "2026-11-14T20:00:00Z"
        sync.sync_now()
        self.assertEqual(sync.canonical_due(store.all_events()[0]["due"]),
                         sync.canonical_due("2026-11-14T17:00:00-03:00"))
        result = agenda.run({"action": "reschedule", "title": "Call", "due": "2026-11-14T18:00:00-03:00"})
        self.assertIn("status=done", result)
        self.assertEqual(sync.canonical_due(self.remote["card1"]["due"]),
                         sync.canonical_due("2026-11-14T18:00:00-03:00"))
        undo.undo_last()
        sync.sync_now()
        self.assertEqual(sync.canonical_due(self.remote["card1"]["due"]),
                         sync.canonical_due("2026-11-14T17:00:00-03:00"))

    def test_conflict_preserves_both(self):
        event = self.event()
        sync.sync_now()
        store.upsert("Local edit", event["due"], event["id"])
        self.remote["card1"]["name"] = "Remote edit"
        self.assertIn("status=unverified", sync.sync_now())
        self.assertEqual(store.all_events()[0]["title"], "Local edit")
        self.assertEqual(self.remote["card1"]["name"], "Remote edit")

    def test_missing_remote_does_not_delete_local(self):
        self.event()
        sync.sync_now()
        self.remote.clear()
        sync.sync_now()
        self.assertEqual(len(store.all_events()), 1)
        self.assertIn("sync_issue", store.all_events()[0])

    def test_account_switch_stops_existing_links(self):
        self.event()
        sync.sync_now()
        self.cfg["trello"]["token"] = "different-user"
        self.assertIn("status=failed", sync.sync_now())
        self.assertEqual(self.posts, 1)

    def test_post_timeout_recovers_without_duplicate(self):
        self.event()
        original = api.request.side_effect
        def timed_out(*args):
            original(*args)
            raise api.TrelloError("timeout")
        with patch.object(api, "request", side_effect=timed_out):
            self.assertIn("status=unverified", sync.sync_now())
        self.assertIn("status=done", sync.sync_now())
        self.assertEqual(self.posts, 1)

    def test_corrupt_store_preserved(self):
        store.PATH.write_text("broken", encoding="utf-8")
        self.assertIn("status=unverified", sync.sync_now())
        self.assertEqual(store.PATH.read_text(), "broken")

    def test_import_remote(self):
        self.remote["card2"] = {"id": "card2", "name": "Imported", "due": "2026-11-15T12:00:00Z"}
        sync.sync_now()
        sync.sync_now()
        self.assertEqual(len(store.all_events()), 1)
        self.assertEqual(self.posts, 0)

    def test_disabled_makes_no_requests(self):
        self.cfg["agenda"]["enabled"] = False
        sync.sync_now()
        api.cards.assert_not_called()

    def test_synced_creation_can_be_undone(self):
        result = agenda.run({"action": "add", "title": "Call", "due": "2026-11-14T16:00:00-03:00"})
        self.assertIn("status=done", result)
        with patch("memory.config_manager.get_plugin_config", side_effect=lambda n: self.cfg[n]):
            undo.undo_last()
        self.assertTrue(self.remote["card1"]["closed"])
        self.assertEqual(store.all_events(), [])

    def test_card_mutation_and_undo_verified(self):
        self.remote["card1"] = {"id": "card1", "name": "Mine", "idList": "mylist", "closed": False}
        trello_control._change("card1", {"closed": True})
        self.assertTrue(self.remote["card1"]["closed"])
        undo.undo_last()
        self.assertFalse(self.remote["card1"]["closed"])

    def test_undo_does_not_overwrite_later_remote_change(self):
        self.remote["card1"] = {"id": "card1", "name": "Mine", "idList": "mylist"}
        trello_control._change("card1", {"idList": "other"})
        self.remote["card1"]["idList"] = "later"
        undo.undo_last()
        self.assertEqual(self.remote["card1"]["idList"], "later")

    def test_event_archive_and_restore_sync(self):
        event = self.event()
        sync.sync_now()
        result = agenda.run({"action": "archive", "id": event["id"]})
        self.assertIn("status=done", result)
        self.assertTrue(self.remote["card1"]["closed"])
        self.assertEqual(store.all_events(), [])
        undo.undo_last()
        sync.sync_now()
        self.assertFalse(self.remote["card1"]["closed"])
        self.assertEqual(len(store.all_events()), 1)


class ClientTest(unittest.TestCase):
    def test_transport_error_never_exposes_key(self):
        with patch("requests.request", side_effect=RuntimeError("secret-token-in-url")):
            with self.assertRaises(api.TrelloError) as caught:
                api.request("GET", "/members/me", credentials={"api_key": "mine", "token": "secret"})
        self.assertNotIn("secret", str(caught.exception))

    def test_no_account_defaults(self):
        with patch.object(api, "get_plugin_config", return_value={}):
            with self.assertRaises(api.TrelloError):
                api.boards()

    def test_ambiguous_name_rejected(self):
        with self.assertRaises(api.TrelloError):
            api.pick([{"name": "Call A"}, {"name": "Call B"}], "Call")

    def test_failed_readback_is_unverified(self):
        with patch.object(api, "request"), patch.object(api, "card", return_value={"idList": "old"}):
            with self.assertRaises(api.TrelloError):
                api.update("card1", {"idList": "new"})


if __name__ == "__main__":
    unittest.main()
