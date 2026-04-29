import unittest
from datetime import datetime, timezone

from processing.disaster_backtests import (
    CYCLONE_SIGNAL_WIND_THRESHOLD,
    FLOOD_SIGNAL_RAIN_THRESHOLD,
    FLOOD_SIGNAL_WIND_THRESHOLD,
    _candidate_regions_for_hazard,
    _evaluate_hazard,
    latest_disaster_backtest,
)


class DisasterBacktestsTests(unittest.TestCase):
    def test_latest_backtest_exposes_threshold_defaults(self) -> None:
        payload = latest_disaster_backtest()
        thresholds = payload.get("thresholds") or {}
        self.assertEqual((thresholds.get("flood") or {}).get("rain_threshold"), FLOOD_SIGNAL_RAIN_THRESHOLD)
        self.assertEqual((thresholds.get("flood") or {}).get("wind_threshold"), FLOOD_SIGNAL_WIND_THRESHOLD)
        self.assertEqual((thresholds.get("cyclone") or {}).get("wind_threshold"), CYCLONE_SIGNAL_WIND_THRESHOLD)

    def test_candidate_regions_include_explicit_region_fields(self) -> None:
        doc = {
            "country": "USA",
            "data": {
                "region": "flood_06_04",
                "region_name": "Lower Mississippi Basin",
                "display_label": "Lower Mississippi Basin (34N / 95W sector)",
            },
        }

        candidates = _candidate_regions_for_hazard("flood", doc)

        self.assertIn("flood_06_04", candidates)
        self.assertIn("Lower Mississippi Basin", candidates)
        self.assertIn("Lower Mississippi Basin (34N / 95W sector)", candidates)
        self.assertIn("USA", candidates)

    def test_disaster_stream_signals_do_not_self_match_same_timestamp(self) -> None:
        docs = [
            {
                "hazard": "flood",
                "captured_at": "2026-04-27T00:00:00+00:00",
                "hotspot_band": "active",
                "region": "flood_06_04",
                "region_name": "Lower Mississippi Basin",
                "display_label": "Lower Mississippi Basin (34N / 95W sector)",
                "country": "GLB",
                "lead_time_hours": 24,
                "confidence": 0.72,
            }
        ]
        signal_docs = [
            {
                "source": "disaster_stream_flood",
                "timestamp": "2026-04-27T00:00:00+00:00",
                "meta": {"category": "flood"},
                "data": {
                    "region": "flood_06_04",
                    "region_name": "Lower Mississippi Basin",
                    "display_label": "Lower Mississippi Basin (34N / 95W sector)",
                },
                "country": "GLB",
            }
        ]

        result = _evaluate_hazard("flood", docs, signal_docs, cutoff=datetime(2026, 4, 1, tzinfo=timezone.utc))

        self.assertEqual(result["matched_follow_on_events"], 0)
        self.assertEqual(result["false_positives"], 1)


if __name__ == "__main__":
    unittest.main()
