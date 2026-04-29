import unittest

from backend.planetary_contracts import build_contract_catalog_payload
from backend.planetary_intelligence import build_planetary_overview_payload


class PlanetaryContractTests(unittest.TestCase):
    def test_contract_catalog_includes_all_master_plan_families(self) -> None:
        payload = build_contract_catalog_payload()
        names = {item["name"] for item in payload["contract_families"]}
        self.assertEqual(
            names,
            {
                "source_event",
                "normalized_signal",
                "world_entity",
                "world_relationship",
                "country_snapshot",
                "corridor_snapshot",
                "hazard_forecast",
                "alert_event",
                "replay_frame",
                "runtime_status",
            },
        )
        country_schema = next(item for item in payload["contract_families"] if item["name"] == "country_snapshot")
        self.assertIn("country", country_schema["required_fields"])
        self.assertIn("signal_scores", country_schema["required_fields"])

    def test_planetary_overview_composes_existing_subsystems(self) -> None:
        payload = build_planetary_overview_payload(
            mode="online",
            country_rows=[
                {
                    "country": "LKA",
                    "display_risk": 82.0,
                    "raw_risk_score": 82.0,
                    "confidence_score": 74.0,
                    "direct_behavior_score": 70.0,
                    "contextual_pressure_score": 76.0,
                    "coordination_risk_score": 71.0,
                    "mobility_disruption_score": 63.0,
                    "logistics_stress_score": 58.0,
                    "household_stress_score": 61.0,
                    "energy_stress_score": 79.0,
                    "narrative_velocity_score": 66.0,
                    "fuel_price_pressure": 59.0,
                    "food_price_pressure": 57.0,
                    "labor_stress_score": 54.0,
                    "fx_pressure_score": 52.0,
                    "remittance_stress_score": 49.0,
                    "source_status": "verified_live",
                    "validated_today": True,
                    "source_count": 6,
                    "data_quality": "verified",
                    "country_quality_status": "country_ready",
                    "risk_band": "critical",
                    "confidence_band": "high",
                    "risk_delta_24h": 4.6,
                    "risk_delta_7d": 7.1,
                    "risk_trend_direction": "worsening",
                    "spillover_links": [{"country": "IND", "risk": 68.0, "relationship": "trade spillover"}],
                    "advisory": "Coordinate with regional ops.",
                    "feature_timestamp": "2026-04-15T00:01:00+00:00",
                },
                {
                    "country": "IND",
                    "display_risk": 68.0,
                    "raw_risk_score": 68.0,
                    "confidence_score": 78.0,
                    "direct_behavior_score": 64.0,
                    "contextual_pressure_score": 62.0,
                    "coordination_risk_score": 58.0,
                    "mobility_disruption_score": 52.0,
                    "logistics_stress_score": 49.0,
                    "household_stress_score": 56.0,
                    "energy_stress_score": 51.0,
                    "narrative_velocity_score": 60.0,
                    "fuel_price_pressure": 53.0,
                    "food_price_pressure": 55.0,
                    "labor_stress_score": 47.0,
                    "fx_pressure_score": 44.0,
                    "remittance_stress_score": 42.0,
                    "source_status": "verified_live",
                    "validated_today": True,
                    "source_count": 7,
                    "data_quality": "verified",
                    "country_quality_status": "country_ready",
                    "risk_band": "high",
                    "confidence_band": "high",
                    "risk_delta_24h": 1.8,
                    "risk_delta_7d": 3.9,
                    "risk_trend_direction": "worsening",
                    "spillover_links": [],
                    "advisory": "Monitor cross-border logistics stress.",
                    "feature_timestamp": "2026-04-15T00:02:00+00:00",
                },
            ],
            internet_payload={
                "generated_at": "2026-04-15T00:00:00+00:00",
                "summary": {
                    "global_congestion_index": 64.0,
                    "cyber_attack_index": 55.0,
                    "source_status": "healthy",
                    "source_stage": "phase-4-direct-hybrid",
                },
                "top_corridors": [
                    {
                        "id": "ind-lka",
                        "origin": "IND",
                        "origin_label": "India",
                        "destination": "LKA",
                        "destination_label": "Sri Lanka",
                        "throughput_gbps": 120.4,
                        "latency_ms": 72.0,
                        "packet_loss_pct": 2.4,
                        "reroute_factor": 1.2,
                        "congestion_index": 58.0,
                        "attack_index": 61.0,
                        "anomaly_score": 64.0,
                        "traffic_share": 0.86,
                        "confidence_ratio": 0.76,
                        "freshness_sec": 33,
                        "status": "degraded",
                        "severity": "elevated",
                        "source_families": ["bgp_routing", "cdn_traffic"],
                    }
                ],
                "shutdown_alerts": [
                    {
                        "id": "shutdown-lka",
                        "country": "LKA",
                        "shutdown_risk": 71.0,
                        "confidence_ratio": 0.81,
                        "freshness_sec": 52,
                        "reason": "Compounded energy and logistics stress detected.",
                        "advisory": "Verify mobile and gateway reachability.",
                        "status": "active",
                        "source_families": ["isp_telemetry"],
                    }
                ],
                "cyber_attacks": [
                    {
                        "id": "attack-ind-lka",
                        "origin": "IND",
                        "target": "LKA",
                        "attack_index": 63.0,
                        "confidence_ratio": 0.74,
                        "freshness_sec": 40,
                        "vector": "BGP Hijack Pressure",
                        "status": "monitoring",
                        "source_families": ["bgp_routing"],
                    }
                ],
                "runtime_status": {
                    "status": "ok",
                    "last_cycle_status": "ok",
                    "last_cycle_finished_at": "2026-04-15T00:00:30+00:00",
                    "queue_depth": 1,
                    "cycle_latency_ms": 410.5,
                    "collector_total_records": 1200,
                    "source_stage": "phase-4-direct-hybrid",
                },
                "collector_summary": {"served_from_cache": False},
            },
            disaster_payload={
                "generated_at": "2026-04-15T00:05:00+00:00",
                "forecasts": [
                    {
                        "forecast_id": "flood:IND:delta",
                        "event_type": "flood",
                        "region": "Ganges Delta",
                        "country": "IND",
                        "updated_at": "2026-04-15T00:05:00+00:00",
                        "lead_time_hours": 18,
                        "likelihood": 0.74,
                        "severity_score": 0.67,
                        "confidence": 0.79,
                        "top_contributing_signals": ["rainfall anomaly", "river surge"],
                        "recommended_action": "Pre-position flood response resources.",
                        "signal_sources": ["weather_sensors", "social_media_signals"],
                        "regional_hotspots_count": 3,
                    }
                ],
            },
            playback_frames=[
                {
                    "run_id": "internet-map-run-1",
                    "captured_at": "2026-04-15T00:00:00+00:00",
                    "generated_at": "2026-04-15T00:00:00+00:00",
                    "summary": {"source_status": "healthy"},
                    "countries": [{"country": "IND", "confidence_ratio": 0.71}],
                    "top_corridors": [{"id": "ind-lka", "confidence_ratio": 0.76}],
                    "cyber_attacks": [{"id": "attack-ind-lka"}],
                    "shutdown_alerts": [{"id": "shutdown-lka"}],
                    "source_health": [{"status": "healthy"}, {"status": "degraded"}],
                }
            ],
            global_context={
                "freshness": {
                    "sources": [{"last_updated": "2026-04-15T00:04:00+00:00", "age_hours": 0.1}],
                    "newest_age_hours": 0.1,
                },
                "source_health": {"critical_down_live": 1},
                "quality_gate": {"active": False, "message": "Coverage healthy", "reasons": []},
            },
            global_doc={"features": {"global_risk_score": 64.0, "global_mood_confidence": 0.72}},
            disaster_stream_status={
                "status": "ok",
                "captured_at": "2026-04-15T00:05:00+00:00",
                "cycle_latency_ms": 520.0,
                "forecast_count": 4,
                "active_alerts": 2,
                "collector_total_records": 300,
                "down_families": 0,
                "stale_families": 1,
            },
        )

        self.assertEqual(payload["contract_version"], "phase-0.2")
        self.assertGreater(len(payload["country_snapshots"]), 0)
        self.assertGreater(len(payload["corridor_snapshots"]), 0)
        self.assertGreater(len(payload["hazard_forecasts"]), 0)
        self.assertGreater(len(payload["alert_events"]), 0)
        self.assertGreater(len(payload["world_entities"]), 0)
        self.assertGreater(len(payload["world_relationships"]), 0)
        self.assertGreater(len(payload["replay_frames"]), 0)
        self.assertGreater(len(payload["runtime_status"]), 0)
        self.assertGreater(payload["global_summary"]["global_stress_level"], 0.0)
        self.assertEqual(payload["country_snapshots"][0]["country"], "LKA")

        alert_types = {item["alert_type"] for item in payload["alert_events"]}
        self.assertIn("behavior_stress", alert_types)
        self.assertIn("internet_shutdown", alert_types)
        self.assertIn("hazard_flood", alert_types)

        relationship_types = {item["relationship_type"] for item in payload["world_relationships"]}
        self.assertIn("behavioral_spillover", relationship_types)
        self.assertIn("network_corridor", relationship_types)
        self.assertIn("exposed_to_hazard", relationship_types)

        runtime_names = {item["runtime_name"] for item in payload["runtime_status"]}
        self.assertIn("country_intelligence_platform", runtime_names)
        self.assertIn("real_time_internet_map", runtime_names)
        self.assertIn("global_disaster_early_warning_ai", runtime_names)


if __name__ == "__main__":
    unittest.main()
