import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import games
from plugins import game_launcher


class GamesTest(unittest.TestCase):
    def test_steam_manifest_library_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); apps = root / "steamapps"; apps.mkdir()
            (apps / "common/Test").mkdir(parents=True)
            (apps / "appmanifest_1.acf").write_text('"appid" "1" "name" "Test" "installdir" "Test"')
            (apps / "appmanifest_2.acf").write_text('"appid" "2" "name" "Bad" "installdir" "../../escape"')
            result = games.steam(root)
            self.assertEqual(len(result), 1); self.assertEqual(result[0]["launch"], "steam://rungameid/1")

    def test_epic_requires_installed_exe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "game.exe").touch()
            file = root / "test.item"
            data = {"AppName": "abc", "InstallLocation": str(root), "LaunchExecutable": "game.exe", "DisplayName": "Test"}
            file.write_text(json.dumps(data)); self.assertEqual(len(games.epic(root)), 1)
            data["LaunchExecutable"] = "missing.exe"; file.write_text(json.dumps(data)); self.assertEqual(games.epic(root), [])

    def test_riot_only_known_products(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / "VALORANT.exe"; game.touch()
            client = root / "RiotClientServices.exe"; client.touch()
            file = root / "installs.json"; file.write_text(json.dumps({"associated_client": {str(game): str(client)}}))
            self.assertEqual(games.riot(file)[0]["product"], "valorant")

    def test_ambiguous_names_never_launch(self):
        with patch.object(games, "discover", return_value=[{"id": "1", "name": "Test", "store": "steam"}, {"id": "2", "name": "Test", "store": "epic"}]), patch.object(games, "launch") as launch:
            self.assertIn("status=failed", game_launcher.run({"action": "launch", "name": "Test"}))
            launch.assert_not_called()
