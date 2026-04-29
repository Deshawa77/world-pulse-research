from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processing.disaster_backtests import latest_disaster_backtest
from processing.planetary_fusion import load_recent_correlation_chains, load_recent_country_fusion_snapshots, load_recent_fusion_timeline
from processing.planetary_graph import load_recent_planetary_world_entities, load_recent_planetary_world_relationships
from processing.planetary_runtime_store import (
    load_latest_planetary_behavior_surface,
    load_latest_planetary_command_layer,
    load_recent_planetary_map_replay_frames,
    load_latest_planetary_runtime_manifest,
)
from processing.planetary_signal_store import load_recent_platform_normalized_signals, load_recent_platform_source_events


def main() -> int:
    runtime_scheduler_script = ROOT / "scripts" / "run_planetary_runtime_scheduler.py"
    runtime_stack_script = ROOT / "scripts" / "start_planetary_local_stack.ps1"
    runtime_frontend_script = ROOT / "scripts" / "restart_frontend.ps1"
    runtime_scheduler_restart_script = ROOT / "scripts" / "restart_planetary_runtime_scheduler.ps1"
    browser_smoke_script = ROOT / "scripts" / "check_planetary_browser_smoke.mjs"
    provider_config_script = ROOT / "scripts" / "check_planetary_provider_config.py"
    activation_doc = ROOT / "docs" / "planetary_production_activation.md"
    provider_template = ROOT / "config" / "planetary_provider_activation.env.example"
    runtime_manifest = load_latest_planetary_runtime_manifest() or {}
    runtime_behavior = load_latest_planetary_behavior_surface()
    runtime_command = load_latest_planetary_command_layer()
    map_replay_frames = load_recent_planetary_map_replay_frames(limit=48)
    manifest_runtime_status = runtime_manifest.get("runtime_status") if isinstance(runtime_manifest.get("runtime_status"), dict) else {}
    manifest_status = runtime_manifest.get("status") or manifest_runtime_status.get("status")
    manifest_freshness = runtime_manifest.get("freshness_sec")
    warnings: list[str] = []
    if not runtime_manifest or manifest_status == "missing":
        warnings.append("planetary runtime manifest missing")
    elif manifest_freshness is not None and int(manifest_freshness or 0) > 1800:
        warnings.append("planetary runtime manifest stale")
    if not runtime_behavior:
        warnings.append("planetary runtime behavior surface missing")
    if not runtime_command:
        warnings.append("planetary runtime command layer missing")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not warnings else "warning",
        "signals": {
            "source_events": len(load_recent_platform_source_events(limit=200)),
            "normalized_signals": len(load_recent_platform_normalized_signals(limit=200)),
        },
        "graph": {
            "entities": len(load_recent_planetary_world_entities(limit=200)),
            "relationships": len(load_recent_planetary_world_relationships(limit=240)),
        },
        "fusion": {
            "country_fusion_snapshots": len(load_recent_country_fusion_snapshots(limit=120)),
            "timeline_frames": len(load_recent_fusion_timeline(limit=160)),
            "correlation_chains": len(load_recent_correlation_chains(limit=120)),
        },
        "runtime": {
            "manifest_status": manifest_status,
            "freshness_sec": manifest_freshness,
            "run_id": runtime_manifest.get("run_id"),
            "behavior_country_count": runtime_manifest.get("behavior_country_count", 0),
            "behavior_replay_count": runtime_manifest.get("behavior_replay_count", 0),
            "map_replay_frame_count": runtime_manifest.get("map_replay_frame_count", len(map_replay_frames)),
            "command_theater_count": runtime_manifest.get("command_theater_count", 0),
            "command_watchlist_count": runtime_manifest.get("command_watchlist_count", 0),
            "graph_focus_count": runtime_manifest.get("graph_focus_count", 0),
            "disaster_focus_count": runtime_manifest.get("disaster_focus_count", 0),
            "runtime_reason": manifest_runtime_status.get("reason"),
            "behavior_payload_present": bool(runtime_behavior),
            "command_payload_present": bool(runtime_command),
        },
        "activation": {
            "runtime_scheduler_script_present": runtime_scheduler_script.exists(),
            "runtime_stack_script_present": runtime_stack_script.exists(),
            "runtime_frontend_script_present": runtime_frontend_script.exists(),
            "runtime_scheduler_restart_script_present": runtime_scheduler_restart_script.exists(),
            "browser_smoke_script_present": browser_smoke_script.exists(),
            "provider_config_script_present": provider_config_script.exists(),
            "activation_doc_present": activation_doc.exists(),
            "provider_template_present": provider_template.exists(),
            "runtime_env": {
                "enabled": os.environ.get("PLANETARY_RUNTIME_ENABLED", "true"),
                "interval_seconds": os.environ.get("PLANETARY_RUNTIME_INTERVAL_SECONDS", "300"),
                "source_refresh_interval_seconds": os.environ.get("PLANETARY_RUNTIME_SOURCE_REFRESH_INTERVAL_SECONDS", "900"),
                "backtest_interval_seconds": os.environ.get("PLANETARY_RUNTIME_BACKTEST_INTERVAL_SECONDS", "21600"),
            },
            "provider_wiring_scope": "deployment_env_pending",
        },
        "disaster_backtests": latest_disaster_backtest(),
        "warnings": warnings,
    }
    if report["graph"]["entities"] == 0 or report["graph"]["relationships"] == 0:
        warnings.append("graph snapshot persistence empty")
    if report["fusion"]["country_fusion_snapshots"] == 0 or report["fusion"]["timeline_frames"] == 0:
        warnings.append("fusion snapshot persistence empty")
    if report["runtime"]["map_replay_frame_count"] == 0:
        warnings.append("planetary map replay history empty")
    report["status"] = "ok" if not warnings else "warning"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
