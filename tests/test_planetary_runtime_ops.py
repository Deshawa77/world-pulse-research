import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from processing.planetary_runtime_store import (
    load_latest_planetary_behavior_surface,
    load_latest_planetary_command_layer,
    load_recent_planetary_map_replay_frames,
    load_latest_planetary_runtime_manifest,
    persist_planetary_runtime_batch,
)
from scripts import run_planetary_validation


class PlanetaryRuntimeOpsTests(unittest.TestCase):
    def test_runtime_store_persists_manifest_and_payloads(self) -> None:
        behavior_surface = {
            "generated_at": "2026-04-27T00:00:00+00:00",
            "top_countries": [{"country": "IND"}, {"country": "BRA"}],
            "replay_frames": [{"frame_id": "behavior-1"}],
        }
        command_layer = {
            "generated_at": "2026-04-27T00:00:00+00:00",
            "theaters": [{"country": "IND"}],
            "incident_watchlist": [{"id": "incident-1"}],
            "graph_command_focus": [{"entity_id": "entity-1"}],
            "disaster_command_focus": [{"forecast_id": "forecast-1"}],
        }
        map_replay_frame = {
            "frame_id": "runtime_test",
            "frame_timestamp": "2026-04-27T00:00:00+00:00",
            "captured_at": "2026-04-27T00:00:00+00:00",
            "countries": [{"country": "IND", "fused_score": 0.62}],
            "corridors": [{"corridor_id": "ind-pak", "from_country": "IND", "to_country": "PAK"}],
            "hotspots": [{"marker_id": "alert-1", "kind": "alert", "country": "IND"}],
        }
        runtime_status = {"status": "idle", "cycle_count": 4}

        with tempfile.TemporaryDirectory() as tmpdir:
            persisted = persist_planetary_runtime_batch(
                behavior_surface=behavior_surface,
                command_layer=command_layer,
                map_replay_frame=map_replay_frame,
                runtime_status=runtime_status,
                run_id="runtime_test",
                captured_at="2026-04-27T00:00:00+00:00",
                root=tmpdir,
            )
            manifest = load_latest_planetary_runtime_manifest(tmpdir)
            latest_behavior = load_latest_planetary_behavior_surface(tmpdir)
            latest_command = load_latest_planetary_command_layer(tmpdir)
            replay_frames = load_recent_planetary_map_replay_frames(tmpdir)

        self.assertEqual(persisted["status"], "ok")
        self.assertEqual(manifest["behavior_country_count"], 2)
        self.assertEqual(manifest["command_theater_count"], 1)
        self.assertEqual(manifest["map_replay_frame_count"], 1)
        self.assertEqual(latest_behavior["top_countries"][0]["country"], "IND")
        self.assertEqual(latest_command["incident_watchlist"][0]["id"], "incident-1")
        self.assertEqual(replay_frames[0]["frame_id"], "runtime_test")

    def test_validation_script_reports_runtime_snapshot_and_warnings(self) -> None:
        output = io.StringIO()
        with (
            patch.object(run_planetary_validation, "load_recent_platform_source_events", return_value=[{"event_id": "1"}]),
            patch.object(run_planetary_validation, "load_recent_platform_normalized_signals", return_value=[{"signal_id": "1"}]),
            patch.object(run_planetary_validation, "load_recent_planetary_world_entities", return_value=[{"entity_id": "e1"}]),
            patch.object(run_planetary_validation, "load_recent_planetary_world_relationships", return_value=[{"relationship_id": "r1"}]),
            patch.object(run_planetary_validation, "load_recent_country_fusion_snapshots", return_value=[{"fusion_id": "f1"}]),
            patch.object(run_planetary_validation, "load_recent_fusion_timeline", return_value=[{"frame_id": "t1"}]),
            patch.object(run_planetary_validation, "load_recent_correlation_chains", return_value=[{"chain_id": "c1"}]),
            patch.object(run_planetary_validation, "latest_disaster_backtest", return_value={"status": "ok"}),
            patch.object(run_planetary_validation, "load_recent_planetary_map_replay_frames", return_value=[{"frame_id": "map-1"}]),
            patch.object(
                run_planetary_validation,
                "load_latest_planetary_runtime_manifest",
                return_value={
                    "freshness_sec": 60,
                    "behavior_country_count": 2,
                    "map_replay_frame_count": 1,
                    "run_id": "runtime-test",
                    "runtime_status": {"status": "ok", "reason": "test"},
                },
            ),
            patch.object(run_planetary_validation, "load_latest_planetary_behavior_surface", return_value={"top_countries": [{"country": "IND"}]}),
            patch.object(run_planetary_validation, "load_latest_planetary_command_layer", return_value={"theaters": [{"country": "IND"}]}),
            redirect_stdout(output),
        ):
            exit_code = run_planetary_validation.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["runtime"]["manifest_status"], "ok")
        self.assertEqual(payload["runtime"]["behavior_country_count"], 2)
        self.assertEqual(payload["runtime"]["map_replay_frame_count"], 1)
        self.assertIn("activation", payload)
        self.assertEqual(payload["activation"]["provider_wiring_scope"], "deployment_env_pending")
        self.assertIn("provider_config_script_present", payload["activation"])
        self.assertIn("provider_template_present", payload["activation"])
        self.assertEqual(payload["warnings"], [])

    def test_smoke_files_reference_runtime_routes_and_operator_pages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        backend_main = (root / "backend" / "main.py").read_text(encoding="utf-8")
        app_file = (root / "world-pulse-frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        planetary_page = (root / "world-pulse-frontend" / "src" / "pages" / "PlanetaryIntelligence.tsx").read_text(encoding="utf-8")
        behavior_page = (root / "world-pulse-frontend" / "src" / "pages" / "BehaviorIntelligence.tsx").read_text(encoding="utf-8")
        hazard_page = (root / "world-pulse-frontend" / "src" / "pages" / "HazardOperations.tsx").read_text(encoding="utf-8")
        validation_script = (root / "scripts" / "run_planetary_validation.py").read_text(encoding="utf-8")
        smoke_script = (root / "scripts" / "check_planetary_browser_smoke.mjs").read_text(encoding="utf-8")

        self.assertIn("/api/planetary-intelligence/runtime/status", backend_main)
        self.assertIn("/api/planetary-intelligence/runtime/materialize", backend_main)
        self.assertIn("/api/planetary-intelligence/corridors/detail", backend_main)
        self.assertIn("/api/planetary-intelligence/replay/map-frames", backend_main)
        self.assertIn("/dashboard/planetary-intelligence", app_file)
        self.assertIn("Planetary Intelligence Console", planetary_page)
        self.assertIn("Search + jump", planetary_page)
        self.assertIn("onFlowArcClick", planetary_page)
        self.assertIn("Stored map frame", planetary_page)
        self.assertIn("Behavior timeline frames", behavior_page)
        self.assertIn("Model Quality", hazard_page)
        self.assertIn("runtime_scheduler_script_present", validation_script)
        self.assertIn("provider_template_present", validation_script)
        self.assertIn("/dashboard/planetary-intelligence", smoke_script)


if __name__ == "__main__":
    unittest.main()
