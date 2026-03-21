from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_intelligence_backtests import summarize_country_slices
from processing.country_risk_validation import run_country_risk_backtest, run_country_risk_validation
from processing.global_mood_validation import run_global_mood_backtest, run_global_mood_validation

THRESHOLDS = {
    "country_validation": {
        "sample_count_min": 5,
        "accuracy_at_50_min": 0.50,
        "accuracy_at_70_min": 0.40,
        "brier_score_max": 0.35,
    },
    "country_backtest": {
        "matched_days_min": 3,
        "weighted_accuracy_at_50_min": 0.50,
        "weighted_brier_score_max": 0.35,
    },
    "global_validation": {
        "sample_count_min": 5,
        "classification_brier_score_max": 0.35,
        "classification_accuracy_at_50_min": 0.50,
    },
    "global_backtest": {
        "matched_days_min": 3,
        "weighted_brier_score_max": 0.35,
        "weighted_mae_max": 25.0,
    },
    "country_slices": {
        "sample_count_min": 1,
        "accuracy_at_50_min": 0.40,
    },
}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _evaluate(summary: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    cv = summary.get("country_validation") or {}
    cvm = cv.get("metrics") or {}
    if str(cv.get("status")) != "ok":
        failures.append(f"country_validation.status={cv.get('status')}")
    if _safe_int(cv.get("sample_count")) < THRESHOLDS["country_validation"]["sample_count_min"]:
        failures.append("country_validation.sample_count below threshold")
    if _safe_float(cvm.get("accuracy_at_50")) < THRESHOLDS["country_validation"]["accuracy_at_50_min"]:
        failures.append("country_validation.accuracy_at_50 below threshold")
    if _safe_float(cvm.get("accuracy_at_70")) < THRESHOLDS["country_validation"]["accuracy_at_70_min"]:
        failures.append("country_validation.accuracy_at_70 below threshold")
    if _safe_float(cvm.get("brier_score"), 1.0) > THRESHOLDS["country_validation"]["brier_score_max"]:
        failures.append("country_validation.brier_score above threshold")

    cb = summary.get("country_backtest") or {}
    cbm = cb.get("metrics") or {}
    if str(cb.get("status")) != "ok":
        failures.append(f"country_backtest.status={cb.get('status')}")
    if _safe_int(cb.get("matched_days")) < THRESHOLDS["country_backtest"]["matched_days_min"]:
        failures.append("country_backtest.matched_days below threshold")
    if _safe_float(cbm.get("weighted_accuracy_at_50")) < THRESHOLDS["country_backtest"]["weighted_accuracy_at_50_min"]:
        failures.append("country_backtest.weighted_accuracy_at_50 below threshold")
    if _safe_float(cbm.get("weighted_brier_score"), 1.0) > THRESHOLDS["country_backtest"]["weighted_brier_score_max"]:
        failures.append("country_backtest.weighted_brier_score above threshold")

    gv = summary.get("global_validation") or {}
    gvm = gv.get("metrics") or {}
    gvc = gvm.get("classification") or {}
    if str(gv.get("status")) != "ok":
        failures.append(f"global_validation.status={gv.get('status')}")
    if _safe_int(gv.get("sample_count")) < THRESHOLDS["global_validation"]["sample_count_min"]:
        failures.append("global_validation.sample_count below threshold")
    if _safe_float(gvc.get("accuracy_at_50")) < THRESHOLDS["global_validation"]["classification_accuracy_at_50_min"]:
        failures.append("global_validation.classification.accuracy_at_50 below threshold")
    if _safe_float(gvc.get("brier_score"), 1.0) > THRESHOLDS["global_validation"]["classification_brier_score_max"]:
        failures.append("global_validation.classification.brier_score above threshold")

    gb = summary.get("global_backtest") or {}
    gbm = gb.get("metrics") or {}
    if str(gb.get("status")) != "ok":
        failures.append(f"global_backtest.status={gb.get('status')}")
    if _safe_int(gb.get("matched_days")) < THRESHOLDS["global_backtest"]["matched_days_min"]:
        failures.append("global_backtest.matched_days below threshold")
    if _safe_float(gbm.get("weighted_brier_score"), 1.0) > THRESHOLDS["global_backtest"]["weighted_brier_score_max"]:
        failures.append("global_backtest.weighted_brier_score above threshold")
    if _safe_float(gbm.get("weighted_mae"), 999.0) > THRESHOLDS["global_backtest"]["weighted_mae_max"]:
        failures.append("global_backtest.weighted_mae above threshold")

    slices = summary.get("country_slice_backtests") or []
    for row in slices:
        sample_count = _safe_int(row.get("sample_count"))
        if sample_count < THRESHOLDS["country_slices"]["sample_count_min"]:
            failures.append(f"country_slice.{row.get('slice')}.sample_count below threshold")
            continue
        if _safe_float(row.get("accuracy_at_50")) < THRESHOLDS["country_slices"]["accuracy_at_50_min"]:
            failures.append(f"country_slice.{row.get('slice')}.accuracy_at_50 below threshold")

    return failures, {
        "country_validation": cvm,
        "country_backtest": cbm,
        "global_validation": gvc,
        "global_backtest": gbm,
        "country_slices": slices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run intelligence promotion gates")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write gate report JSON")
    args = parser.parse_args()

    country_validation = run_country_risk_validation(persist=False)
    country_backtest = run_country_risk_backtest(days=60, persist=False)
    global_validation = run_global_mood_validation(persist=False)
    global_backtest = run_global_mood_backtest(days=60, persist=False)
    summary = {
        "country_validation": country_validation,
        "country_backtest": country_backtest,
        "global_validation": global_validation,
        "global_backtest": global_backtest,
        "country_slice_backtests": summarize_country_slices(country_validation),
    }
    failures, metrics = _evaluate(summary)
    report = {
        "passed": not failures,
        "failures": failures,
        "thresholds": THRESHOLDS,
        "metrics": metrics,
    }
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
