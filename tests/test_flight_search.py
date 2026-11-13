import unittest
from unittest.mock import patch, Mock
from urllib.parse import urlsplit, parse_qs
from core import flight_search as f


class FlightTest(unittest.TestCase):
    def test_encoded_link_no_fixed_route(self):
        link = f.booking_url("São Paulo & GRU", "Lisboa", "2030-02-01", passengers=2)
        query = parse_qs(urlsplit(link).query)
        self.assertIn("São Paulo & GRU", query["q"][0]); self.assertNotIn("tfs", query)
        self.assertEqual(query["curr"], ["BRL"])

    def test_pt_date_and_no_silent_today(self):
        self.assertEqual(f.normalize_date("01/02/2030"), "2030-02-01")
        with self.assertRaises(ValueError): f.normalize_date("2030-99-99")
        with patch.object(f.gemini, "text", return_value="UNKNOWN"):
            with self.assertRaises(ValueError): f.normalize_date("algum dia")

    def test_multi_mode_search_panel_and_honest_outcome(self):
        player = Mock()
        with patch("actions.web_search.web_search", return_value="Web result https://example.com/flight") as search:
            result = f.run({"origin": "GRU", "destination": "LIS", "date": "2030-02-01", "mode": "research"}, player)
            self.assertIn("status=unverified", result); self.assertIn("<<<UNTRUSTED", result)
            self.assertEqual(search.call_args.args[0]["mode"], "research")
            player.show_content.assert_called_once()

    def test_invalid_return_passengers_and_same_route(self):
        base = {"origin": "GRU", "destination": "LIS", "date": "2030-02-01"}
        with patch("actions.web_search.web_search") as search:
            for extra in ({"return_date": "2030-01-01"}, {"passengers": 0}, {"destination": "GRU"}, {"date": "2000-01-01"}):
                self.assertIn("status=failed", f.run({**base, **extra}))
            search.assert_not_called()
