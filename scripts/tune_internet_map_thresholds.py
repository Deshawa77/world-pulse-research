from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.internet_map_thresholds import DEFAULT_INTERNET_MAP_THRESHOLDS

BACKTEST_PATH = PROJECT_ROOT / "monitoring" / "internet_map" / "backtests" / "latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "internet-map-thresholds.local.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _recommend(backtest: dict[str, Any], *, target_precision: float) -> tuple[dict[str, Any], list[str]]:
    recommendations = json.loads(json.dumps(DEFAULT_INTERNET_MAP_THRESHOLDS))
    notes: list[str] = []

    attacks = backtest.get("attacks") if isinstance(backtest.get("attacks"), dict) else {}
    shutdowns = backtest.get("shutdowns") if isinstance(backtest.get("shutdowns"), dict) else {}
    overall = backtest.get("overall") if isinstance(backtest.get("overall"), dict) else {}

    attack_precision = float(attacks.get("feedback_adjusted_precision_proxy") or attacks.get("precision_proxy") or 0.0)
    attack_false_positive_rate = float(attacks.get("false_positive_rate") or 0.0)
    shutdown_precision = float(shutdowns.get("feedback_adjusted_precision_proxy") or shutdowns.get("precision_proxy") or 0.0)
    shutdown_false_positive_rate = float(shutdowns.get("false_positive_rate") or 0.0)

    if attack_precision < target_precision or attack_false_positive_rate > 0.3:
        notes.append("Tightened attack gates because attack precision is below target or false positives remain elevated.")
        recommendations["flow_signals"]["attack_index"] = round(_clamp(recommendations["flow_signals"]["attack_index"] + 4.0, 45.0, 85.0), 2)
        recommendations["flow_signals"]["hijack_suspect_score"] = round(_clamp(recommendations["flow_signals"]["hijack_suspect_score"] + 0.03, 0.1, 0.6), 3)
        recommendations["alert_filters"]["min_attack_signals"] = 3
        recommendations["alert_filters"]["attack_index_gate"] = round(_clamp(recommendations["alert_filters"]["attack_index_gate"] + 4.0, 50.0, 90.0), 2)
        recommendations["alert_filters"]["attack_hijack_gate"] = round(_clamp(recommendations["alert_filters"]["attack_hijack_gate"] + 0.03, 0.1, 0.8), 3)
        recommendations["alert_filters"]["attack_active_index"] = round(_clamp(recommendations["alert_filters"]["attack_active_index"] + 3.0, 60.0, 95.0), 2)
    elif attack_precision >= max(target_precision, 0.72):
        notes.append("Attack precision is strong; lightly relaxed attack gates to preserve sensitivity.")
        recommendations["alert_filters"]["attack_index_gate"] = round(_clamp(recommendations["alert_filters"]["attack_index_gate"] - 2.0, 50.0, 90.0), 2)

    if shutdown_precision < target_precision or shutdown_false_positive_rate > 0.25:
        notes.append("Tightened shutdown gates because shutdown precision is below target or false positives remain elevated.")
        recommendations["shutdown_signals"]["shutdown_risk"] = round(_clamp(recommendations["shutdown_signals"]["shutdown_risk"] + 4.0, 45.0, 90.0), 2)
        recommendations["shutdown_signals"]["subscriber_availability_ratio"] = round(_clamp(recommendations["shutdown_signals"]["subscriber_availability_ratio"] - 0.04, 0.4, 0.95), 3)
        recommendations["alert_filters"]["min_shutdown_signals"] = 3
        recommendations["alert_filters"]["shutdown_risk_gate"] = round(_clamp(recommendations["alert_filters"]["shutdown_risk_gate"] + 4.0, 50.0, 95.0), 2)
        recommendations["alert_filters"]["shutdown_availability_gate"] = round(_clamp(recommendations["alert_filters"]["shutdown_availability_gate"] - 0.04, 0.4, 0.95), 3)
        recommendations["alert_filters"]["shutdown_active_risk"] = round(_clamp(recommendations["alert_filters"]["shutdown_active_risk"] + 3.0, 55.0, 98.0), 2)
    elif shutdown_precision >= max(target_precision, 0.72):
        notes.append("Shutdown precision is strong; lightly relaxed shutdown risk gate to preserve sensitivity.")
        recommendations["alert_filters"]["shutdown_risk_gate"] = round(_clamp(recommendations["alert_filters"]["shutdown_risk_gate"] - 2.0, 50.0, 95.0), 2)

    overall_precision = float(overall.get("feedback_adjusted_precision_proxy") or overall.get("precision_proxy") or 0.0)
    notes.append(f"Observed overall precision proxy: {overall_precision:.4f}")
    return recommendations, notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend calibrated Internet Map thresholds from backtest outputs.")
    parser.add_argument("--backtest", default=str(BACKTEST_PATH), help="Path to the latest Internet Map backtest JSON.")
    parser.add_argument("--target-precision", type=float, default=0.6)
    parser.add_argument("--write", action="store_true", help="Write the recommended thresholds to the output path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Where to write the recommended threshold overrides.")
    args = parser.parse_args()

    backtest_path = Path(args.backtest)
    if not backtest_path.is_absolute():
        backtest_path = PROJECT_ROOT / backtest_path
    backtest = _load_json(backtest_path)
    recommendations, notes = _recommend(backtest, target_precision=args.target_precision)

    payload = {
        "status": "ok",
        "backtest": str(backtest_path),
        "target_precision": args.target_precision,
        "notes": notes,
        "recommended_thresholds": recommendations,
    }

    if args.write:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
        payload["output"] = str(output_path)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
