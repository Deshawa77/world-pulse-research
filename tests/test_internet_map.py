import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.internet_map import build_internet_map_snapshot
from backend.internet_map_ops import build_internet_alert_operation_doc
from backend.internet_map_thresholds import load_internet_map_thresholds
from backend.runtime_config import bootstrap_runtime_environment
from collectors.internet_source_families import collect_internet_source_families
from processing.internet_map_maintenance import build_internet_retention_policy


class InternetMapSnapshotTests(unittest.TestCase):

    def _sample_docs(self) -> list[dict]:
        return [
            {
                "country": "LKA",
                "risk": 0.78,
                "public_attention_score": 0.66,
                "mobility_disruption_score": 0.82,
                "logistics_stress_score": 0.76,
                "energy_stress_score": 0.88,
                "coordination_risk_score": 0.61,
                "external_signal_freshness": 0.22,
                "evidence_quality_score": 0.69,
                "source_count": 6,
                "validated_today": True,
                "data_quality": "verified",
            },
            {
                "country": "IND",
                "risk": 0.67,
                "public_attention_score": 0.71,
                "mobility_disruption_score": 0.48,
                "logistics_stress_score": 0.44,
                "energy_stress_score": 0.39,
                "coordination_risk_score": 0.58,
                "external_signal_freshness": 0.74,
                "evidence_quality_score": 0.63,
                "source_count": 7,
                "validated_today": True,
                "data_quality": "verified",
            },
            {
                "country": "USA",
                "risk": 0.41,
                "public_attention_score": 0.43,
                "mobility_disruption_score": 0.18,
                "logistics_stress_score": 0.17,
                "energy_stress_score": 0.14,
                "coordination_risk_score": 0.28,
                "external_signal_freshness": 0.81,
                "evidence_quality_score": 0.72,
                "source_count": 8,
                "validated_today": True,
                "data_quality": "verified",
            },
            {
                "country": "GBR",
                "risk": 0.38,
                "public_attention_score": 0.36,
                "mobility_disruption_score": 0.16,
                "logistics_stress_score": 0.19,
                "energy_stress_score": 0.18,
                "coordination_risk_score": 0.21,
                "external_signal_freshness": 0.76,
                "evidence_quality_score": 0.7,
                "source_count": 6,
                "validated_today": True,
                "data_quality": "verified",
            },
        ]

    def test_snapshot_contains_expected_sections(self) -> None:
        snapshot = build_internet_map_snapshot(self._sample_docs(), global_doc={"features": {"timestamp": "2026-04-06T00:00:00+00:00"}})
        self.assertIn("summary", snapshot)
        self.assertIn("countries", snapshot)
        self.assertIn("flows", snapshot)
        self.assertIn("source_health", snapshot)
        self.assertIn("generated_from", snapshot)
        self.assertGreaterEqual(len(snapshot["countries"]), 3)
        self.assertGreaterEqual(len(snapshot["flows"]), 1)
        self.assertLessEqual(snapshot["summary"]["visible_countries"], 42)
        self.assertEqual(snapshot["summary"]["source_stage"], "phase-1-derived")

    def test_high_shutdown_risk_country_surfaces_alert(self) -> None:
        snapshot = build_internet_map_snapshot(self._sample_docs(), global_doc={"features": {"timestamp": "2026-04-06T00:00:00+00:00"}})
        alerts = snapshot["shutdown_alerts"]
        self.assertTrue(any(item["country"] == "LKA" for item in alerts))
        lka = next(item for item in alerts if item["country"] == "LKA")
        self.assertGreaterEqual(lka["shutdown_risk"], 56.0)
        self.assertIn("risk", lka["reason"].lower())

    def test_empty_snapshot_returns_limited_state(self) -> None:
        snapshot = build_internet_map_snapshot([], global_doc={"features": {"timestamp": "2026-04-06T00:00:00+00:00"}})
        self.assertEqual(snapshot["summary"]["visible_countries"], 0)
        self.assertEqual(snapshot["summary"]["source_status"], "limited")
        self.assertEqual(snapshot["flows"], [])
        self.assertEqual(snapshot["cyber_attacks"], [])

    def test_collectors_emit_direct_events_from_local_exports(self) -> None:
        snapshot = build_internet_map_snapshot(self._sample_docs(), global_doc={"features": {"timestamp": "2026-04-06T00:00:00+00:00"}})
        collector_bundle = collect_internet_source_families(snapshot, mode="online", refresh=True)
        self.assertGreater(len(collector_bundle["raw_events"]), 0)
        self.assertEqual(len(collector_bundle["raw_events"]), len(collector_bundle["normalized_events"]))
        self.assertEqual(len(collector_bundle["source_health"]), 4)
        self.assertTrue(all(item["measurement_mode"] == "direct" for item in collector_bundle["source_health"]))
        self.assertGreaterEqual(int((collector_bundle["collector_summary"] or {}).get("direct_families") or 0), 4)

    def test_collectors_can_reuse_persisted_bundle_without_refresh(self) -> None:
        snapshot = build_internet_map_snapshot(self._sample_docs(), global_doc={"features": {"timestamp": "2026-04-06T00:00:00+00:00"}})
        collect_internet_source_families(snapshot, mode="online", refresh=True)
        cached = collect_internet_source_families(snapshot, mode="online", refresh=False)
        self.assertTrue(bool((cached.get("collector_summary") or {}).get("served_from_cache")))
        self.assertGreater(int((cached.get("collector_summary") or {}).get("total_records") or 0), 0)

    def test_ops_doc_includes_queue_and_sla_defaults(self) -> None:
        doc = build_internet_alert_operation_doc(
            {
                "alert_type": "attack",
                "flow_id": "lka-ind-primary",
                "action": "assign",
                "owner": "tester",
                "severity": "critical",
            },
            actor="tester",
        )
        self.assertEqual(doc["team_queue"], "network-security")
        self.assertTrue(str(doc.get("escalation_destination") or "").startswith("security-command"))
        self.assertIsNotNone(doc.get("sla_due_at"))
        self.assertEqual(int(doc.get("sla_hours") or 0), 1)

    def test_retention_policy_lists_internet_collections(self) -> None:
        retention = build_internet_retention_policy()
        self.assertIn("internet_alerts", retention["collections"])
        self.assertTrue(retention["mongo_retention_days"] >= 1)

    def test_threshold_config_file_can_override_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            threshold_file = Path(temp_dir) / "thresholds.json"
            threshold_file.write_text('{"alert_filters": {"min_attack_signals": 3}}', encoding="utf-8")
            with patch.dict(os.environ, {"INTERNET_MAP_THRESHOLD_CONFIG_FILE": str(threshold_file)}, clear=False):
                thresholds = load_internet_map_thresholds(refresh=True)
            self.assertEqual(int(thresholds["alert_filters"]["min_attack_signals"]), 3)

    def test_runtime_config_auto_loads_environment_secret_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "runtime-secrets.production.json").write_text('{"INTERNET_MAP_BGP_FEED_URL": "https://provider.example.com/bgp"}', encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "WORLD_PULSE_ENVIRONMENT": "production",
                    "WORLD_PULSE_ENABLE_DOTENV_FALLBACK": "false",
                },
                clear=False,
            ):
                state = bootstrap_runtime_environment(root)
            self.assertEqual(state["environment"], "production")
            self.assertTrue(state["secret_file_loaded"])
            self.assertTrue(state["production_safe"])


if __name__ == "__main__":
    unittest.main()
