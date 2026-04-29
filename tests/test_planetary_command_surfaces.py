import tempfile
import unittest

from processing.planetary_behavior_surface import build_behavior_operator_surface
from processing.planetary_command_layer import build_planetary_command_layer
from processing.planetary_disaster_command import build_planetary_disaster_command_surface
from processing.planetary_fusion import seed_planetary_fusion_snapshot
from processing.planetary_graph import seed_planetary_graph_snapshot
from processing.planetary_graph_analytics import build_planetary_graph_summary, search_planetary_graph_entities
from tests.test_planetary_fusion_ops import (
    CAPTURED_AT,
    sample_alert_events,
    sample_corridor_snapshots,
    sample_country_snapshots,
    sample_global_summary,
    sample_hazard_forecasts,
    sample_normalized_signals,
    sample_replay_frames,
)
from tests.test_planetary_investigation import sample_source_events


class PlanetaryCommandSurfaceTests(unittest.TestCase):
    def test_behavior_operator_surface_builds_replay_and_health(self) -> None:
        bundle = {
            "country_snapshots": sample_country_snapshots(),
            "global_behavior_snapshot": {
                "global_stress_level": 0.68,
                "global_behavior_index": 0.64,
                "global_attention_index": 0.61,
                "global_disruption_index": 0.58,
                "global_economic_stress_index": 0.53,
                "migration_pressure_index": 0.49,
                "confidence_ratio": 0.77,
                "freshness_sec": 120,
            },
        }
        payload = build_behavior_operator_surface(
            bundle,
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            limit=8,
        )
        self.assertEqual(payload["subsystem"], "global_human_behavior_intelligence_engine")
        self.assertGreaterEqual(len(payload["top_countries"]), 2)
        self.assertGreaterEqual(len(payload["replay_frames"]), 1)
        self.assertIn("behavior_context", payload["source_health"]["normalized_signal_families"])

    def test_graph_summary_and_search_use_canonical_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_payload = seed_planetary_graph_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                alert_events=sample_alert_events(),
                run_id="graph_summary_test",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )
            summary = build_planetary_graph_summary(
                world_entities=graph_payload["world_entities"],
                world_relationships=graph_payload["world_relationships"],
                limit=8,
            )
            search = search_planetary_graph_entities(
                "IND",
                world_entities=graph_payload["world_entities"],
                world_relationships=graph_payload["world_relationships"],
                limit=6,
            )
        self.assertGreater(summary["entity_count"], 0)
        self.assertGreater(summary["relationship_count"], 0)
        self.assertGreaterEqual(len(summary["top_entities"]), 1)
        self.assertGreaterEqual(search["count"], 1)
        self.assertIsNotNone(search["resolved_entity"])

    def test_disaster_command_surface_includes_backtest_and_top_regions(self) -> None:
        payload = build_planetary_disaster_command_surface(
            {
                "forecasts": sample_hazard_forecasts(),
                "source_health": [
                    {
                        "source_family": "weather_sensors",
                        "status": "up",
                        "freshness_minutes": 12,
                        "records": 84,
                        "confidence_ratio": 0.81,
                    }
                ],
                "hotspots_by_hazard": {"flood": [{"region": "Ganges Delta"}]},
            },
            backtest_summary={
                "overall": {"precision_proxy": 0.71, "evaluated_alerts": 24},
                "hazards": {"flood": {"precision_proxy": 0.74}},
            },
            stream_status={"status": "ok", "source_freshness": {"weather_sensors": 12}},
            limit=8,
        )
        self.assertEqual(payload["forecast_count"], 1)
        self.assertEqual(payload["hazard_counts"]["flood"], 1)
        self.assertEqual(payload["backtest_summary"]["overall"]["evaluated_alerts"], 24)
        self.assertEqual(payload["hotspot_summary"]["flood"], 1)

    def test_command_layer_aggregates_theaters_watchlist_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fusion_payload = seed_planetary_fusion_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                sample_alert_events(),
                sample_replay_frames(),
                sample_global_summary(),
                sample_normalized_signals(),
                run_id="command_layer_fusion",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )
            graph_payload = seed_planetary_graph_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                alert_events=sample_alert_events(),
                run_id="command_layer_graph",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )

        behavior_surface = build_behavior_operator_surface(
            {
                "country_snapshots": sample_country_snapshots(),
                "global_behavior_snapshot": {
                    "global_stress_level": 0.68,
                    "global_behavior_index": 0.64,
                    "confidence_ratio": 0.77,
                    "freshness_sec": 120,
                },
            },
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            limit=8,
        )
        graph_summary = build_planetary_graph_summary(
            world_entities=graph_payload["world_entities"],
            world_relationships=graph_payload["world_relationships"],
            limit=8,
        )
        disaster_surface = build_planetary_disaster_command_surface(
            {"forecasts": sample_hazard_forecasts(), "source_health": [], "hotspots_by_hazard": {}},
            backtest_summary={"overall": {"precision_proxy": 0.7}},
            stream_status={"status": "ok"},
            limit=8,
        )
        command = build_planetary_command_layer(
            {
                "global_summary": sample_global_summary(),
                "country_fusion_snapshots": fusion_payload["country_fusion_snapshots"],
                "alert_events": sample_alert_events(),
                "hazard_forecasts": sample_hazard_forecasts(),
                "correlation_chains": fusion_payload["correlation_chains"],
                "replay_frames": sample_replay_frames(),
                "fusion_timeline": fusion_payload["fusion_timeline"],
                "runtime_status": [{"runtime_name": "fusion", "status": "ok"}],
                "alert_ops_summary": {"queue_breakdown": [{"queue": "planetary-ops", "count": 2}]},
            },
            behavior_surface=behavior_surface,
            graph_summary=graph_summary,
            disaster_surface=disaster_surface,
            calibration_report={"backtests": {"fusion_country_count": 2}},
            limit=8,
        )
        self.assertGreaterEqual(len(command["theaters"]), 1)
        self.assertGreaterEqual(len(command["incident_watchlist"]), 1)
        self.assertIn("graph_entity_count", command["validation_summary"])
        self.assertGreaterEqual(len(command["graph_command_focus"]), 1)


if __name__ == "__main__":
    unittest.main()
