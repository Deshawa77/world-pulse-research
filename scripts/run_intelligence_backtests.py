from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.country_risk_validation import run_country_risk_backtest, run_country_risk_validation
from processing.global_mood_validation import run_global_mood_backtest, run_global_mood_validation

COUNTRY_SLICES = {
    "open_war_alignment": {"curated_open_war"},
    "baseline_stability": {"curated_baseline"},
    "economic_disruption": {"curated_economic_disruption", "curated_household_stress", "curated_fx_stress"},
}


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except Exception:
        return fallback


def _safe_int(value, fallback=0):
    try:
        return int(value)
    except Exception:
        return fallback


def summarize_country_slices(validation_result: dict) -> list[dict]:
    rows = validation_result.get("evaluated_rows") or []
    summaries: list[dict] = []
    for name, source_tags in COUNTRY_SLICES.items():
        matched = [row for row in rows if str(row.get("source") or "") in source_tags]
        if not matched:
            summaries.append({
                "slice": name,
                "status": "no_matches",
                "sample_count": 0,
            })
            continue
        labels = [_safe_int(row.get("label"), 0) for row in matched]
        probs = [_safe_float(row.get("prob"), 0.0) for row in matched]
        acc50 = sum(int((1 if prob >= 0.5 else 0) == label) for prob, label in zip(probs, labels)) / max(len(labels), 1)
        avg_risk = sum(_safe_float(row.get("risk_score"), 0.0) for row in matched) / max(len(matched), 1)
        summaries.append({
            "slice": name,
            "status": "ok",
            "sample_count": len(matched),
            "accuracy_at_50": round(acc50, 4),
            "avg_risk_score": round(avg_risk, 2),
            "countries": [row.get("country") for row in matched],
        })
    return summaries


def main() -> int:
    timestamp = datetime.now(timezone.utc).isoformat()
    country_validation = run_country_risk_validation(persist=False)
    country_backtest = run_country_risk_backtest(days=60, persist=False)
    global_validation = run_global_mood_validation(persist=False)
    global_backtest = run_global_mood_backtest(days=60, persist=False)

    payload = {
        "timestamp": timestamp,
        "country_validation": country_validation,
        "country_slice_backtests": summarize_country_slices(country_validation),
        "country_backtest": country_backtest,
        "global_validation": global_validation,
        "global_backtest": global_backtest,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
