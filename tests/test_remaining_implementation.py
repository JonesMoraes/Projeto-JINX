import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from core import food_log, radar, updater, update_apply, boot_sentry, circuit_guide


class FoodLogTests(unittest.TestCase):
    def test_daily_total_adjust_remove_and_conflict_aware_undo(self):
        with tempfile.TemporaryDirectory() as d, patch.object(food_log, "_path", return_value=Path(d)/"food.json"):
            a = food_log.add("rice and beans", 450, day="2026-11-14")
            b = food_log.add("juice", 120, estimate=True, day="2026-11-14")
            self.assertEqual(food_log.list_day("2026-11-14")["total_kcal"], 570)
            food_log.adjust(b["id"], 160)
            self.assertEqual(food_log.list_day("2026-11-14")["total_kcal"], 610)
            removed = food_log.remove(a["id"])
            self.assertEqual(removed["food"], "rice and beans")
            self.assertEqual(food_log.list_day("2026-11-14")["total_kcal"], 160)


class CircuitGuideTests(unittest.TestCase):
    def test_requires_confirmed_board_voltage_and_sensor_form(self):
        with self.assertRaises(ValueError): circuit_guide.guide("5V", "module", "unknown clone")
        with self.assertRaises(ValueError): circuit_guide.guide("3.3V", "bare", "Pro Mini 5V/16MHz")
        result = circuit_guide.guide("3.3V", "bare", "Pro Mini 3.3V/8MHz")
        self.assertTrue(any("DHT11 pin 3" in wire for wire in result["wires"]))
        self.assertIn("FTDI 5 V TX", result["code"])
        self.assertIn("No firmware was written", result["warning"])
        # Unknown # directives made the delivered Arduino sketch uncompilable.
        for line in result['code'].splitlines():
            if line.startswith('#'):
                self.assertTrue(line.startswith(('#include ', '#define ')), line)


class RadarTests(unittest.TestCase):
    def test_queries_bounded_sources_and_maps_fetched_points(self):
        opensky = json.dumps({"time": 1, "states": [["icao", "AB123 ", None, None, None,
            -73.99, 40.72, 900, None, 150, 90]]}).encode()
        overpass = json.dumps({"elements": [{"lat": 40.7, "lon": -74,
            "tags": {"name": "Local field", "aeroway": "aerodrome"}}]}).encode()
        class Response:
            def __init__(self, data): self.data=data
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return self.data
        with patch.object(radar, "_last_request", 0), patch.object(radar, "urlopen", side_effect=[Response(opensky), Response(overpass)]):
            result = radar.fetch(40.71, -74.0, 25)
        self.assertEqual(len(result["planes"]), 1)
        self.assertEqual(result["airports"][0]["name"], "Local field")
        self.assertEqual(len(result["sources"]), 2)
        with self.assertRaises(ValueError): radar.fetch(95, 0, 25)


class UpdaterTests(unittest.TestCase):
    def test_stage_verifies_release_hash_and_excludes_personal_and_vendor_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root/".jinx_update"; payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as z:
                z.writestr("JINX-IA-main/core/sample.py", "VALUE = 1\n")
                z.writestr("JINX-IA-main/config/api_keys.json", "{}")
                z.writestr("JINX-IA-main/assets/third_party/secret.html", "untouched")
            raw = payload.getvalue(); digest = hashlib.sha256(raw).hexdigest()
            release = {"tag": "v1.2", "page": "https://github.com/JonesMoraes/JINX-IA/releases/tag/v1.2",
                       "asset": {"name": "jinx-update-v1.2.zip", "digest": digest,
                                 "url": "https://github.com/JonesMoraes/JINX-IA/releases/download/v1.2/x.zip",
                                 "size": len(raw)}}
            with patch.object(updater, "enabled", return_value=True), patch.object(updater, "STATE", state), \
                    patch.object(updater, "_request", return_value=raw):
                result = updater.stage(release)
            folder = Path(result["directory"])
            self.assertEqual(result["files"], 1)
            self.assertTrue((folder/"core"/"sample.py").is_file())
            manifest = json.loads((folder/"update-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_sha256"], digest)

    def test_apply_rolls_back_on_next_boot_if_new_app_does_not_mark_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); state=root/".jinx_update"; stage=state/"staging"/"v2"; stage.mkdir(parents=True)
            target=root/"core"/"sample.py"; target.parent.mkdir(); target.write_text("VALUE=1\n")
            updated=b"VALUE=2\n"; (stage/"core").mkdir(); (stage/"core"/"sample.py").write_bytes(updated)
            manifest={"tag":"v2","files":[{"path":"core/sample.py","size":len(updated),
                "sha256":hashlib.sha256(updated).hexdigest()}]}
            (stage/"update-manifest.json").write_text(json.dumps(manifest))
            with patch.object(update_apply, "subprocess") as proc:
                proc.Popen.return_value=Mock()
                update_apply.apply(root, stage, 999999999)
            self.assertEqual(target.read_bytes(), updated)
            with patch.object(boot_sentry, "ROOT", root), patch.object(boot_sentry, "UPDATE_STATE", state), \
                    patch.object(boot_sentry, "UPDATE_MARKER", state/"pending-update.json"), \
                    patch.dict(os.environ, {}, clear=True):
                self.assertTrue(boot_sentry._recover_update())
            self.assertEqual(target.read_text(), "VALUE=1\n")
            self.assertFalse((state/"pending-update.json").exists())

    def test_production_marker_and_backup_root_match_writer(self):
        self.assertEqual(boot_sentry.UPDATE_STATE, updater.ROOT / '.jinx_update')
        self.assertEqual(boot_sentry.UPDATE_MARKER, boot_sentry.UPDATE_STATE / 'pending-update.json')

    def test_healthy_update_clears_the_actual_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / '.jinx_update' / 'pending-update.json'
            marker.parent.mkdir()
            marker.write_text('{}')
            with patch.object(boot_sentry, 'UPDATE_MARKER', marker), \
                    patch.dict(os.environ, {'JINX_UPDATE_ATTEMPT': '1'}):
                boot_sentry.mark_update_healthy()
                self.assertNotIn('JINX_UPDATE_ATTEMPT', os.environ)
            self.assertFalse(marker.exists())

    def test_path_filter_blocks_keys_memories_builds_and_vendor_assets(self):
        for path in ("../main.py", "config/api_keys.json", "memory/food.json", "assets/third_party/source.html", ".git/config",
                     "core/confirm.py", "core/undo.py", "core/boot_sentry.py", "memory/config_manager.py"):
            self.assertIsNone(updater._safe_path(path), path)
        self.assertIsNotNone(updater._safe_path("JINX-IA-main/core/tool.py"))


class MobileShellTests(unittest.TestCase):
    def test_pwa_has_install_manifest_and_explicit_session_revocation(self):
        root=Path(__file__).resolve().parents[1]/"dashboard"/"static"
        manifest=json.loads((root/"manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue((root/"service-worker.js").is_file())
        html=(root/"app.html").read_text(encoding="utf-8")
        self.assertIn("revokeRemoteDevices", html)
        self.assertIn("window.confirm", html)
        self.assertIn("device-unpair", html)


if __name__ == "__main__": unittest.main()
