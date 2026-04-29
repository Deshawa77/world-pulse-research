import tempfile
import unittest

from backend.planetary_behavior import BEHAVIOR_SUBSYSTEM, materialize_behavior_payload
from processing.planetary_graph import (
    load_recent_planetary_world_entities,
    load_recent_planetary_world_relationships,
    seed_planetary_graph_snapshot,
)
from processing.planetary_signal_store import (
    load_recent_platform_normalized_signals,
    load_recent_platform_source_events,
)


CAPTURED_AT = "2026-04-15T00:10:00+00:00"


def sample_country_rows() -> list[dict[str, object]]:
    return [
        {
            "country": "LKA",
            "display_risk": 82.0,
            "raw_risk_score": 82.0,
            "confidence_score": 74.0,
            "evidence_quality_score": 72.0,
            "source_count": 6,
            "source_status": "verified_live",
            "validated_today": True,
            "data_quality": "verified",
            "country_quality_status": "country_ready",
            "risk_band": "critical",
            "confidence_band": "high",
            "advisory": "Coordinate with regional ops.",
            "feature_timestamp": "2026-04-15T00:01:00+00:00",
            "social_unrest_score": 73.0,
            "google_trends_pressure": 61.0,
            "public_attention_score": 64.0,
            "narrative_velocity_score": 66.0,
            "coordination_risk_score": 71.0,
            "mobility_disruption_score": 63.0,
            "logistics_stress_score": 58.0,
            "aviation_disruption_score": 41.0,
            "household_stress_score": 61.0,
            "fuel_price_pressure": 59.0,
            "food_price_pressure": 57.0,
            "labor_stress_score": 54.0,
            "fx_pressure_score": 52.0,
            "remittance_stress_score": 49.0,
            "energy_stress_score": 79.0,
            "weather_stress": 38.0,
            "direct_behavior_score": 70.0,
            "contextual_pressure_score": 76.0,
            "risk_delta_24h": 4.6,
            "risk_delta_7d": 7.1,
            "risk_trend_direction": "worsening",
            "spillover_links": [{"country": "IND", "risk": 68.0, "relationship": "trade spillover"}],
        },
        {
            "country": "IND",
            "display_risk": 68.0,
            "raw_risk_score": 68.0,
            "confidence_score": 78.0,
            "evidence_quality_score": 75.0,
            "source_count": 7,
            "source_status": "verified_live",
            "validated_today": True,
            "data_quality": "verified",
            "country_quality_status": "country_ready",
            "risk_band": "high",
            "confidence_band": "high",
            "advisory": "Monitor cross-border logistics stress.",
            "feature_timestamp": "2026-04-15T00:02:00+00:00",
            "social_unrest_score": 59.0,
            "google_trends_pressure": 52.0,
            "public_attention_score": 55.0,
            "narrative_velocity_score": 60.0,
            "coordination_risk_score": 58.0,
            "mobility_disruption_score": 52.0,
            "logistics_stress_score": 49.0,
            "aviation_disruption_score": 34.0,
            "household_stress_score": 56.0,
            "fuel_price_pressure": 53.0,
            "food_price_pressure": 55.0,
            "labor_stress_score": 47.0,
            "fx_pressure_score": 44.0,
            "remittance_stress_score": 42.0,
            "energy_stress_score": 51.0,
            "weather_stress": 29.0,
            "direct_behavior_score": 64.0,
            "contextual_pressure_score": 62.0,
            "risk_delta_24h": 1.8,
            "risk_delta_7d": 3.9,
            "risk_trend_direction": "worsening",
            "spillover_links": [],
        },
    ]


def sample_global_context() -> dict[str, object]:
    return {
        "freshness": {
            "sources": [{"last_updated": "2026-04-15T00:04:00+00:00", "age_hours": 0.1}],
            "newest_age_hours": 0.1,
        },
        "source_health": {"critical_down_live": 1, "stale_sources": 0},
        "quality_gate": {"active": False, "message": "Coverage healthy", "reasons": []},
    }


def sample_global_doc() -> dict[str, object]:
    return {
        "timestamp": CAPTURED_AT,
        "features": {
            "global_risk_score": 64.0,
            "global_mood_score": 58.0,
            "global_mood_confidence": 0.72,
            "global_behavior_index": 0.69,
            "global_context_index": 0.66,
            "global_attention_index": 0.63,
            "global_disruption_index": 0.55,
            "global_economic_stress_index": 0.57,
        },
    }


def sample_corridor_snapshots() -> list[dict[str, object]]:
    return [
        {
            "corridor_id": "ind-lka",
            "from_region": {"country": "IND", "label": "India"},
            "to_region": {"country": "LKA", "label": "Sri Lanka"},
            "generated_at": CAPTURED_AT,
            "freshness_sec": 33,
            "confidence_ratio": 0.76,
            "flow_metrics": {
                "throughput_gbps": 120.4,
                "latency_ms": 72.0,
                "packet_loss_pct": 2.4,
                "reroute_factor": 1.2,
                "congestion_index": 58.0,
                "attack_index": 61.0,
                "anomaly_score": 64.0,
                "traffic_share": 0.86,
            },
            "severity_score": 0.64,
            "related_entities": ["IND", "LKA", "ind-lka"],
            "provenance_summary": {"subsystem": "real_time_internet_map"},
        }
    ]


def sample_hazard_forecasts() -> list[dict[str, object]]:
    return [
        {
            "forecast_id": "flood:IND:delta",
            "hazard_type": "flood",
            "region": "Ganges Delta",
            "country": "IND",
            "generated_at": CAPTURED_AT,
            "forecast_horizon": {"hours": 18},
            "likelihood": 0.74,
            "severity_score": 0.67,
            "confidence_ratio": 0.79,
            "top_contributing_signals": ["rainfall anomaly", "river surge"],
            "recommended_action": "Pre-position flood response resources.",
            "provenance_refs": [{"subsystem": "global_disaster_early_warning_ai"}],
        }
    ]


class PlanetaryBehaviorAndGraphTests(unittest.TestCase):
    def test_behavior_payload_persists_country_and_global_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = materialize_behavior_payload(
                sample_country_rows(),
                sample_global_context(),
                sample_global_doc(),
                mode="online",
                run_id="behavior_test_1",
                captured_at=CAPTURED_AT,
                country_limit=8,
                persist=False,
                root=tmpdir,
            )

            self.assertEqual(payload["contract_version"], "phase-0.2")
            self.assertEqual(len(payload["country_snapshots"]), 2)
            self.assertGreater(payload["counts"]["source_event_count"], 0)
            self.assertGreater(payload["counts"]["normalized_signal_count"], 0)
            self.assertGreater(payload["global_behavior_snapshot"]["global_stress_level"], 0.0)
            self.assertEqual(payload["global_behavior_snapshot"]["provenance_summary"]["subsystem"], BEHAVIOR_SUBSYSTEM)

            country_events = load_recent_platform_source_events(
                limit=200,
                root=tmpdir,
                subsystem=BEHAVIOR_SUBSYSTEM,
                event_type="behavior_metric",
            )
            global_events = load_recent_platform_source_events(
                limit=50,
                root=tmpdir,
                subsystem=BEHAVIOR_SUBSYSTEM,
                event_type="global_behavior_metric",
            )
            global_signals = load_recent_platform_normalized_signals(
                limit=50,
                root=tmpdir,
                subsystem=BEHAVIOR_SUBSYSTEM,
                signal_type="global_behavior_index",
            )

            self.assertTrue(any((item.get("geography") or {}).get("country") == "LKA" for item in country_events))
            self.assertGreater(len(global_events), 0)
            self.assertEqual(len(global_signals), 1)
            self.assertEqual(global_signals[0]["source_family"], "global_behavior_aggregate")

    def test_graph_seed_persists_entities_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            behavior_payload = materialize_behavior_payload(
                sample_country_rows(),
                sample_global_context(),
                sample_global_doc(),
                mode="online",
                run_id="behavior_test_2",
                captured_at=CAPTURED_AT,
                country_limit=8,
                persist=False,
                root=tmpdir,
            )
            graph_payload = seed_planetary_graph_snapshot(
                behavior_payload["country_snapshots"],
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                run_id="graph_test_1",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )

            self.assertEqual(graph_payload["status"], "ok")
            self.assertGreater(len(graph_payload["world_entities"]), 0)
            self.assertGreater(len(graph_payload["world_relationships"]), 0)

            country_entities = load_recent_planetary_world_entities(limit=20, root=tmpdir, entity_type="country")
            hazard_entities = load_recent_planetary_world_entities(limit=20, root=tmpdir, entity_type="hazard_region")
            spillover_relationships = load_recent_planetary_world_relationships(
                limit=20,
                root=tmpdir,
                relationship_type="behavioral_spillover",
            )
            corridor_relationships = load_recent_planetary_world_relationships(
                limit=20,
                root=tmpdir,
                relationship_type="network_corridor",
            )

            self.assertTrue(any(item["entity_id"] == "country:LKA" for item in country_entities))
            self.assertEqual(len(hazard_entities), 1)
            self.assertEqual(len(spillover_relationships), 1)
            self.assertEqual(spillover_relationships[0]["target_entity_id"], "country:IND")
            self.assertEqual(len(corridor_relationships), 1)
            self.assertEqual(corridor_relationships[0]["target_entity_id"], "country:LKA")


if __name__ == "__main__":
    unittest.main()
