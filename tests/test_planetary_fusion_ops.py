import tempfile
import unittest

from backend.planetary_alert_ops import build_planetary_alert_operation_doc, enrich_planetary_alerts_with_ops
from processing.planetary_fusion import (
    load_recent_correlation_chains,
    load_recent_country_fusion_snapshots,
    load_recent_fusion_timeline,
    seed_planetary_fusion_snapshot,
)
from processing.planetary_graph import seed_planetary_graph_snapshot


CAPTURED_AT = "2026-04-15T00:20:00+00:00"


def sample_country_snapshots() -> list[dict[str, object]]:
    return [
        {
            "country": "IND",
            "generated_at": CAPTURED_AT,
            "freshness_sec": 120,
            "confidence_ratio": 0.78,
            "signal_scores": {
                "raw_risk_score": 68.0,
                "direct_behavior_score": 66.0,
                "contextual_pressure_score": 71.0,
                "coordination_risk_score": 62.0,
                "mobility_disruption_score": 64.0,
                "logistics_stress_score": 58.0,
                "household_stress_score": 57.0,
                "energy_stress_score": 63.0,
                "narrative_velocity_score": 61.0,
                "fuel_price_pressure": 54.0,
                "food_price_pressure": 56.0,
                "labor_stress_score": 49.0,
                "fx_pressure_score": 47.0,
                "remittance_stress_score": 44.0,
            },
            "spillover_links": [{"country": "LKA", "risk": 68.0, "relationship": "trade spillover"}],
            "advisory": "Monitor compound disruption.",
            "raw_risk_score": 68.0,
        },
        {
            "country": "LKA",
            "generated_at": CAPTURED_AT,
            "freshness_sec": 90,
            "confidence_ratio": 0.74,
            "signal_scores": {
                "raw_risk_score": 82.0,
                "direct_behavior_score": 72.0,
                "contextual_pressure_score": 76.0,
                "coordination_risk_score": 69.0,
                "mobility_disruption_score": 61.0,
                "logistics_stress_score": 56.0,
                "household_stress_score": 60.0,
                "energy_stress_score": 79.0,
                "narrative_velocity_score": 67.0,
                "fuel_price_pressure": 58.0,
                "food_price_pressure": 57.0,
                "labor_stress_score": 52.0,
                "fx_pressure_score": 51.0,
                "remittance_stress_score": 49.0,
            },
            "spillover_links": [],
            "advisory": "Coordinate with regional ops.",
            "raw_risk_score": 82.0,
        },
    ]


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


def sample_alert_events() -> list[dict[str, object]]:
    return [
        {
            "alert_id": "behavior-ind",
            "alert_type": "behavior_stress",
            "generated_at": CAPTURED_AT,
            "geography": {"scope": "country", "country": "IND"},
            "severity_score": 0.71,
            "confidence_ratio": 0.78,
            "freshness_sec": 120,
            "related_entities_or_regions": ["IND"],
            "summary": "Behavior stress elevated in IND.",
            "recommended_action": "Inspect behavior drivers.",
            "status": "active",
            "assignment": {"team": "behavior-ops", "owner": None},
            "sla_state": {"target_minutes": 60, "status": "open"},
            "provenance_refs": [{"subsystem": "global_human_behavior_intelligence_engine"}],
        },
        {
            "alert_id": "hazard-flood-ind",
            "alert_type": "hazard_flood",
            "generated_at": CAPTURED_AT,
            "geography": {"scope": "region", "country": "IND", "region": "Ganges Delta"},
            "severity_score": 0.74,
            "confidence_ratio": 0.79,
            "freshness_sec": 100,
            "related_entities_or_regions": ["IND", "Ganges Delta"],
            "summary": "Flood risk elevated in Ganges Delta.",
            "recommended_action": "Prepare flood response.",
            "status": "active",
            "assignment": {"team": "hazard-ops", "owner": None},
            "sla_state": {"target_minutes": 45, "status": "open"},
            "provenance_refs": [{"subsystem": "global_disaster_early_warning_ai"}],
        },
        {
            "alert_id": "shutdown-lka",
            "alert_type": "internet_shutdown",
            "generated_at": CAPTURED_AT,
            "geography": {"scope": "country", "country": "LKA"},
            "severity_score": 0.69,
            "confidence_ratio": 0.77,
            "freshness_sec": 80,
            "related_entities_or_regions": ["LKA"],
            "summary": "Internet shutdown risk elevated in LKA.",
            "recommended_action": "Verify gateway reachability.",
            "status": "active",
            "assignment": {"team": "internet-ops", "owner": None},
            "sla_state": {"target_minutes": 30, "status": "open"},
            "provenance_refs": [{"subsystem": "real_time_internet_map"}],
        },
    ]


def sample_replay_frames() -> list[dict[str, object]]:
    return [
        {
            "frame_id": "internet-frame-1",
            "generated_at": CAPTURED_AT,
            "frame_timestamp": CAPTURED_AT,
            "frame_type": "internet_map",
            "snapshot_refs": ["country:IND", "corridor:ind-lka"],
            "alert_refs": ["shutdown-lka"],
            "confidence_summary": {"country_avg_confidence": 0.75},
            "source_health_summary": {"family_count": 4},
        }
    ]


def sample_global_summary() -> dict[str, object]:
    return {
        "global_stress_level": 0.68,
        "infrastructure_fragility_score": 0.57,
    }


def sample_normalized_signals() -> list[dict[str, object]]:
    return [
        {
            "signal_id": "sig-behavior-ind",
            "timestamp": CAPTURED_AT,
            "generated_at": CAPTURED_AT,
            "signal_type": "direct_behavior_score",
            "source_family": "behavior_context",
            "source_name": "direct_behavior_score",
            "geography": {"scope": "country", "country": "IND"},
            "entity_refs": ["IND"],
            "metric_name": "direct_behavior_score",
            "metric_value": 66.0,
            "severity_score": 0.66,
            "confidence_ratio": 0.78,
            "freshness_sec": 80,
            "provenance_refs": [{"subsystem": "global_human_behavior_intelligence_engine"}],
            "subsystem": "global_human_behavior_intelligence_engine",
        },
        {
            "signal_id": "sig-disaster-ind",
            "timestamp": CAPTURED_AT,
            "generated_at": CAPTURED_AT,
            "signal_type": "flood",
            "source_family": "weather_sensors",
            "source_name": "flood_forecast",
            "geography": {"scope": "country", "country": "IND"},
            "entity_refs": ["IND"],
            "metric_name": "flood_forecast",
            "metric_value": 0.74,
            "severity_score": 0.74,
            "confidence_ratio": 0.79,
            "freshness_sec": 60,
            "provenance_refs": [{"subsystem": "global_disaster_early_warning_ai"}],
            "subsystem": "global_disaster_early_warning_ai",
        },
        {
            "signal_id": "sig-internet-ind",
            "timestamp": CAPTURED_AT,
            "generated_at": CAPTURED_AT,
            "signal_type": "routing_latency",
            "source_family": "bgp_routing",
            "source_name": "routeviews",
            "geography": {"scope": "country", "country": "IND"},
            "entity_refs": ["IND"],
            "metric_name": "latency_ms",
            "metric_value": 142.0,
            "severity_score": 0.62,
            "confidence_ratio": 0.76,
            "freshness_sec": 40,
            "provenance_refs": [{"subsystem": "real_time_internet_map"}],
            "subsystem": "real_time_internet_map",
        },
    ]


class FakeCursor(list):
    def sort(self, key: str, direction: int):
        reverse = int(direction) < 0
        return FakeCursor(sorted(self, key=lambda row: str(row.get(key) or ""), reverse=reverse))


class FakeCollection:
    def __init__(self, docs: list[dict[str, object]]):
        self.docs = docs

    def find(self, query: dict[str, object], projection: dict[str, int] | None = None):
        scope = str(query.get("alert_scope") or "")
        cutoff = str(((query.get("timestamp") or {}) if isinstance(query.get("timestamp"), dict) else {}).get("$gte") or "")
        rows = [
            dict(doc)
            for doc in self.docs
            if str(doc.get("alert_scope") or "") == scope and str(doc.get("timestamp") or "") >= cutoff
        ]
        return FakeCursor(rows)


class PlanetaryFusionAndOpsTests(unittest.TestCase):
    def test_seed_and_load_planetary_fusion_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = seed_planetary_fusion_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                sample_alert_events(),
                sample_replay_frames(),
                sample_global_summary(),
                sample_normalized_signals(),
                run_id="fusion_test_1",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )

            self.assertEqual(payload["status"], "ok")
            self.assertGreater(len(payload["country_fusion_snapshots"]), 0)
            self.assertGreater(len(payload["fusion_timeline"]), 0)
            self.assertGreater(len(payload["correlation_chains"]), 0)

            country_rows = load_recent_country_fusion_snapshots(limit=10, root=tmpdir, country="IND")
            timeline_rows = load_recent_fusion_timeline(limit=20, root=tmpdir, country="IND")
            chain_rows = load_recent_correlation_chains(limit=10, root=tmpdir, country="IND")

            self.assertEqual(country_rows[0]["country"], "IND")
            self.assertTrue(any(row["frame_type"] == "correlation_chain" for row in timeline_rows))
            self.assertTrue(any(row["chain_type"] == "hazard -> mobility -> internet -> behavior" for row in chain_rows))

    def test_planetary_alert_ops_enrich_alerts(self) -> None:
        ack_doc = build_planetary_alert_operation_doc(
            {
                "alert_type": "behavior_stress",
                "alert_id": "behavior-ind",
                "country": "IND",
                "action": "acknowledge",
                "comment": "Acknowledged by fusion desk",
            },
            actor="fusion-analyst",
        )
        assign_doc = build_planetary_alert_operation_doc(
            {
                "alert_type": "hazard_flood",
                "alert_id": "hazard-flood-ind",
                "country": "IND",
                "action": "assign",
                "assignee": "hazard-lead",
                "assignment_reason": "Escalated to hazard lead",
                "team_queue": "hazard-ops",
            },
            actor="fusion-analyst",
        )
        collection = FakeCollection([ack_doc, assign_doc])
        alerts, summary = enrich_planetary_alerts_with_ops(sample_alert_events(), collection)

        behavior_alert = next(item for item in alerts if item["alert_id"] == "behavior-ind")
        hazard_alert = next(item for item in alerts if item["alert_id"] == "hazard-flood-ind")

        self.assertEqual(behavior_alert["status"], "acknowledged")
        self.assertEqual(hazard_alert["status"], "assigned")
        self.assertEqual(hazard_alert["assignment"]["owner"], "hazard-lead")
        self.assertGreaterEqual(summary["acknowledged"], 1)
        self.assertGreaterEqual(summary["assigned"], 1)

    def test_graph_seed_expands_to_events_orgs_and_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = seed_planetary_graph_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                alert_events=sample_alert_events(),
                run_id="graph_test_2",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
                entity_limit=40,
                relationship_limit=50,
            )
            entity_types = {item["entity_type"] for item in payload["world_entities"]}
            relationship_types = {item["relationship_type"] for item in payload["world_relationships"]}

            self.assertIn("named_event", entity_types)
            self.assertIn("organization", entity_types)
            self.assertIn("narrative_topic", entity_types)
            self.assertIn("event_impacts_country", relationship_types)
            self.assertIn("organization_responds_to_event", relationship_types)
            self.assertIn("country_topic_pressure", relationship_types)


if __name__ == "__main__":
    unittest.main()
