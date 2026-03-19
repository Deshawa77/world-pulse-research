import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from processing import spillover_graph


class SpilloverGraphTests(unittest.TestCase):
    def test_loader_normalizes_valid_entries(self) -> None:
        payload = {
            "irn": [
                {"country": "irq", "relationship": "Western frontier"},
                {"country": "xx", "relationship": "ignore me"},
            ],
            "bad": "not-a-list",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "country_spillovers.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(spillover_graph, "_CONFIG_PATH", path):
                spillover_graph.load_country_spillover_map.cache_clear()
                loaded = spillover_graph.load_country_spillover_map()
        self.assertEqual(loaded["IRN"], [{"country": "IRQ", "relationship": "Western frontier"}])
        self.assertNotIn("BAD", loaded)

    def test_loader_returns_empty_map_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing.json"
            with patch.object(spillover_graph, "_CONFIG_PATH", path):
                spillover_graph.load_country_spillover_map.cache_clear()
                loaded = spillover_graph.load_country_spillover_map()
        self.assertEqual(loaded, {})


if __name__ == "__main__":
    unittest.main()
