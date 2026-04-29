import tempfile
import unittest

from backend.planetary_alert_ops import build_planetary_alert_operation_doc
from processing.planetary_calibration import build_planetary_calibration_report
from processing.planetary_evidence import (
    build_alert_detail,
    build_correlation_chain_detail,
    build_corridor_detail,
    build_country_fusion_detail,
)
from processing.planetary_fusion import seed_planetary_fusion_snapshot
from processing.planetary_graph import build_planetary_entity_profile, canonicalize_world_entities, seed_planetary_graph_snapshot
from tests.test_planetary_fusion_ops import (
    CAPTURED_AT,
    FakeCollection,
    sample_alert_events,
    sample_corridor_snapshots,
    sample_country_snapshots,
    sample_global_summary,
    sample_hazard_forecasts,
    sample_normalized_signals,
    sample_replay_frames,
)


def sample_source_events() -> list[dict[str, object]]:
    return [
        {
            "event_id": "evt-behavior-ind",
            "timestamp": CAPTURED_AT,
            "ingested_at": CAPTURED_AT,
            "source_family": "behavior_context",
            "source_name": "direct_behavior_score",
            "source_provenance": {"subsystem": "global_human_behavior_intelligence_engine"},
            "geography": {"scope": "country", "country": "IND"},
            "raw_payload_ref": "behavior:ind:1",
            "freshness_sec": 60,
            "licensing_or_usage_tier": "internal",
            "metric_name": "direct_behavior_score",
            "metric_value": 66.0,
            "event_type": "behavior_signal",
            "subsystem": "global_human_behavior_intelligence_engine",
            "confidence_ratio": 0.78,
        },
        {
            "event_id": "evt-disaster-ind",
            "timestamp": CAPTURED_AT,
            "ingested_at": CAPTURED_AT,
            "source_family": "weather_sensors",
            "source_name": "flood_forecast",
            "source_provenance": {"subsystem": "global_disaster_early_warning_ai"},
            "geography": {"scope": "country", "country": "IND"},
            "raw_payload_ref": "hazard:ind:1",
            "freshness_sec": 45,
            "licensing_or_usage_tier": "internal",
            "metric_name": "flood_forecast",
            "metric_value": 0.74,
            "event_type": "hazard_signal",
            "subsystem": "global_disaster_early_warning_ai",
            "confidence_ratio": 0.79,
        },
        {
            "event_id": "evt-internet-lka",
            "timestamp": CAPTURED_AT,
            "ingested_at": CAPTURED_AT,
            "source_family": "bgp_routing",
            "source_name": "routeviews",
            "source_provenance": {"subsystem": "real_time_internet_map"},
            "geography": {"scope": "country", "country": "LKA"},
            "raw_payload_ref": "internet:lka:1",
            "freshness_sec": 35,
            "licensing_or_usage_tier": "internal",
            "metric_name": "latency_ms",
            "metric_value": 142.0,
            "event_type": "internet_signal",
            "subsystem": "real_time_internet_map",
            "confidence_ratio": 0.76,
        },
    ]


class PlanetaryInvestigationTests(unittest.TestCase):
    def _build_context(self) -> tuple[dict[str, object], dict[str, object]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            fusion_payload = seed_planetary_fusion_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                sample_alert_events(),
                sample_replay_frames(),
                sample_global_summary(),
                sample_normalized_signals(),
                run_id="investigation_fusion",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
            )
            graph_payload = seed_planetary_graph_snapshot(
                sample_country_snapshots(),
                sample_corridor_snapshots(),
                sample_hazard_forecasts(),
                alert_events=sample_alert_events(),
                run_id="investigation_graph",
                captured_at=CAPTURED_AT,
                root=tmpdir,
                persist_db=False,
                entity_limit=48,
                relationship_limit=56,
            )
            return fusion_payload, graph_payload

    def test_country_fusion_detail_includes_supporting_evidence(self) -> None:
        fusion_payload, graph_payload = self._build_context()
        ack_doc = build_planetary_alert_operation_doc(
            {
                "alert_type": "behavior_stress",
                "alert_id": "behavior-ind",
                "country": "IND",
                "action": "acknowledge",
                "comment": "Acknowledged by investigation test",
            },
            actor="fusion-analyst",
        )
        detail = build_country_fusion_detail(
            "IND",
            country_snapshots=sample_country_snapshots(),
            country_fusion_snapshots=fusion_payload["country_fusion_snapshots"],
            correlation_chains=fusion_payload["correlation_chains"],
            fusion_timeline=fusion_payload["fusion_timeline"],
            corridor_snapshots=sample_corridor_snapshots(),
            hazard_forecasts=sample_hazard_forecasts(),
            alert_events=sample_alert_events(),
            world_entities=graph_payload["world_entities"],
            world_relationships=graph_payload["world_relationships"],
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            operator_events_collection=FakeCollection([ack_doc]),
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["country"], "IND")
        self.assertGreaterEqual(len(detail["supporting_alerts"]), 1)
        self.assertGreaterEqual(len(detail["supporting_signals"]), 1)
        self.assertGreaterEqual(len(detail["related_entities"]), 1)
        self.assertGreaterEqual(len(detail["operator_history"]), 1)
        self.assertGreater(detail["evidence_summary"]["signal_count"], 0)

    def test_alert_and_chain_detail_build_from_same_evidence_slice(self) -> None:
        fusion_payload, graph_payload = self._build_context()
        chain = fusion_payload["correlation_chains"][0]
        chain_id = chain["chain_id"]
        chain_country = chain["country"]
        matching_alert = next(
            (
                item
                for item in sample_alert_events()
                if str((item.get("geography") or {}).get("country") or "").strip().upper() == str(chain_country or "").strip().upper()
            ),
            sample_alert_events()[0],
        )
        op_doc = build_planetary_alert_operation_doc(
            {
                "alert_type": matching_alert["alert_type"],
                "alert_id": matching_alert["alert_id"],
                "country": chain_country,
                "chain_id": chain_id,
                "action": "assign",
                "assignee": "lead-analyst",
                "team_queue": "planetary-ops",
                "assignment_reason": "Investigation drilldown",
            },
            actor="fusion-analyst",
        )
        chain_detail = build_correlation_chain_detail(
            chain_id,
            country_snapshots=sample_country_snapshots(),
            country_fusion_snapshots=fusion_payload["country_fusion_snapshots"],
            correlation_chains=fusion_payload["correlation_chains"],
            fusion_timeline=fusion_payload["fusion_timeline"],
            corridor_snapshots=sample_corridor_snapshots(),
            hazard_forecasts=sample_hazard_forecasts(),
            alert_events=sample_alert_events(),
            world_entities=graph_payload["world_entities"],
            world_relationships=graph_payload["world_relationships"],
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            operator_events_collection=FakeCollection([op_doc]),
        )
        alert_detail = build_alert_detail(
            str(matching_alert["alert_id"]),
            country_snapshots=sample_country_snapshots(),
            country_fusion_snapshots=fusion_payload["country_fusion_snapshots"],
            correlation_chains=fusion_payload["correlation_chains"],
            fusion_timeline=fusion_payload["fusion_timeline"],
            corridor_snapshots=sample_corridor_snapshots(),
            hazard_forecasts=sample_hazard_forecasts(),
            alert_events=sample_alert_events(),
            world_entities=graph_payload["world_entities"],
            world_relationships=graph_payload["world_relationships"],
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            operator_events_collection=FakeCollection([op_doc]),
        )
        self.assertIsNotNone(chain_detail)
        self.assertIsNotNone(alert_detail)
        self.assertEqual(chain_detail["chain_id"], chain_id)
        self.assertEqual(alert_detail["alert_id"], str(matching_alert["alert_id"]))
        self.assertGreaterEqual(len(chain_detail["operator_history"]), 1)
        self.assertGreaterEqual(len(alert_detail["operator_history"]), 1)
        self.assertGreaterEqual(len(alert_detail["related_correlation_chains"]), 1)

    def test_corridor_detail_includes_country_and_timeline_context(self) -> None:
        fusion_payload, graph_payload = self._build_context()
        corridor = sample_corridor_snapshots()[0]
        op_doc = build_planetary_alert_operation_doc(
            {
                "alert_type": "routing_anomaly",
                "alert_id": "internet-ind-lka",
                "country": str((corridor.get("from_region") or {}).get("country") or "IND"),
                "action": "acknowledge",
                "comment": "Corridor acknowledged from investigation test",
            },
            actor="corridor-analyst",
        )
        detail = build_corridor_detail(
            str(corridor["corridor_id"]),
            country_snapshots=sample_country_snapshots(),
            country_fusion_snapshots=fusion_payload["country_fusion_snapshots"],
            correlation_chains=fusion_payload["correlation_chains"],
            fusion_timeline=fusion_payload["fusion_timeline"],
            corridor_snapshots=sample_corridor_snapshots(),
            hazard_forecasts=sample_hazard_forecasts(),
            alert_events=sample_alert_events(),
            world_entities=graph_payload["world_entities"],
            world_relationships=graph_payload["world_relationships"],
            normalized_signals=sample_normalized_signals(),
            source_events=sample_source_events(),
            operator_events_collection=FakeCollection([op_doc]),
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["corridor_id"], str(corridor["corridor_id"]))
        self.assertGreaterEqual(len(detail["country_scope"]), 1)
        self.assertGreaterEqual(len(detail["related_country_fusion_snapshots"]), 1)
        self.assertGreaterEqual(len(detail["supporting_corridors"]), 1)
        self.assertGreaterEqual(len(detail["supporting_timeline"]), 1)
        self.assertGreaterEqual(len(detail["operator_history"]), 1)

    def test_canonical_entity_resolution_merges_aliases(self) -> None:
        entities = [
            {
                "entity_id": "organization:ministry-of-communications",
                "entity_type": "organization",
                "canonical_name": "Ministry of Communications",
                "aliases": ["MOC", "Communications Ministry"],
                "geography": {"country": "IND"},
                "confidence_ratio": 0.92,
                "provenance_refs": [{"source": "ops"}],
            },
            {
                "entity_id": "organization:communications-ministry",
                "entity_type": "organization",
                "canonical_name": "Communications Ministry",
                "aliases": ["Ministry of Communications"],
                "geography": {"country": "IND"},
                "confidence_ratio": 0.86,
                "provenance_refs": [{"source": "ops"}],
            },
            {
                "entity_id": "country:IND",
                "entity_type": "country",
                "canonical_name": "India",
                "aliases": ["IND"],
                "geography": {"country": "IND"},
                "confidence_ratio": 0.97,
                "provenance_refs": [{"source": "ops"}],
            },
        ]
        relationships = [
            {
                "relationship_id": "rel:ministry-country",
                "relationship_type": "organization_operates_in_country",
                "source_entity_id": "organization:communications-ministry",
                "target_entity_id": "country:IND",
                "timestamp": CAPTURED_AT,
                "geography": {"country": "IND"},
                "strength_score": 0.72,
                "confidence_ratio": 0.82,
                "provenance_refs": [{"source": "ops"}],
                "supporting_evidence_refs": [{"doc": "ops-1"}],
            }
        ]
        canonical_entities, alias_map = canonicalize_world_entities(entities)
        profile = build_planetary_entity_profile(
            "MOC",
            world_entities=entities,
            world_relationships=relationships,
            limit=8,
        )
        self.assertEqual(len(canonical_entities), 2)
        self.assertIn("organization:communications-ministry", alias_map)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["entity"]["canonical_name"], "Ministry of Communications")
        self.assertGreaterEqual(len(profile["neighborhood_entities"]), 1)

    def test_calibration_report_returns_backtest_metrics(self) -> None:
        fusion_payload, _graph_payload = self._build_context()
        report = build_planetary_calibration_report(
            country_snapshots=sample_country_snapshots(),
            country_fusion_snapshots=fusion_payload["country_fusion_snapshots"],
            hazard_forecasts=sample_hazard_forecasts(),
            correlation_chains=fusion_payload["correlation_chains"],
            normalized_signals=sample_normalized_signals(),
        )
        self.assertEqual(report["contract_version"], "phase-0.4")
        self.assertIn("hazard_chain_alignment_rate", report["backtests"])
        self.assertGreaterEqual(report["disaster_likelihood"]["high_likelihood_count"], 1)
        self.assertGreaterEqual(report["fusion_scoring"]["country_count"], 1)


if __name__ == "__main__":
    unittest.main()
