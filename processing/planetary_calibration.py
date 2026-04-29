from __future__ import annotations

from statistics import mean
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return max(0.0, min(1.0, numeric))


def _percentile(values: list[float], quantile: float, default: float = 0.0) -> float:
    if not values:
        return default
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * max(0.0, min(1.0, quantile))))
    return ordered[index]


def build_planetary_calibration_report(
    *,
    country_snapshots: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    hazard_likelihoods = [_ratio(item.get("likelihood"), 0.0) for item in hazard_forecasts]
    hazard_severities = [_ratio(item.get("severity_score"), 0.0) for item in hazard_forecasts]
    hazard_countries = {
        str(item.get("country") or "").strip().upper()
        for item in hazard_forecasts
        if str(item.get("country") or "").strip()
    }
    chain_countries = {
        str(item.get("country") or "").strip().upper()
        for item in correlation_chains
        if str(item.get("country") or "").strip()
    }
    corroborated_hazard_countries = hazard_countries & chain_countries

    score_rows = [item.get("signal_scores") if isinstance(item.get("signal_scores"), dict) else {} for item in country_snapshots]
    direct_behavior = [_ratio(row.get("direct_behavior_score"), 0.0) for row in score_rows if row]
    contextual_pressure = [_ratio(row.get("contextual_pressure_score"), 0.0) for row in score_rows if row]
    coordination_pressure = [_ratio(row.get("coordination_risk_score"), 0.0) for row in score_rows if row]

    fusion_scores = [_ratio(item.get("fused_score"), 0.0) for item in country_fusion_snapshots]
    subsystem_scores: dict[str, list[float]] = {}
    corroborated_fusion = 0
    for item in country_fusion_snapshots:
        active = 0
        subsystems = item.get("subsystem_scores") if isinstance(item.get("subsystem_scores"), dict) else {}
        for name, value in subsystems.items():
            ratio = _ratio(value, 0.0)
            subsystem_scores.setdefault(str(name), []).append(ratio)
            if ratio >= 0.35:
                active += 1
        if active >= 2:
            corroborated_fusion += 1
    subsystem_means = {name: round(mean(values), 4) if values else 0.0 for name, values in subsystem_scores.items()}

    behavior_signals = [item for item in normalized_signals if str(item.get("subsystem") or "") == "global_human_behavior_intelligence_engine"]
    disaster_signals = [item for item in normalized_signals if str(item.get("subsystem") or "") == "global_disaster_early_warning_ai"]
    behavior_countries = {
        str((item.get("geography") or {}).get("country") or "").strip().upper()
        for item in behavior_signals
        if str((item.get("geography") or {}).get("country") or "").strip()
    }

    hazard_alignment_rate = round(len(corroborated_hazard_countries) / max(1, len(hazard_countries)), 4) if hazard_countries else 0.0
    fusion_corroboration_rate = round(corroborated_fusion / max(1, len(country_fusion_snapshots)), 4) if country_fusion_snapshots else 0.0
    behavior_signal_alignment = round(len(behavior_countries) / max(1, len(country_snapshots)), 4) if country_snapshots else 0.0

    return {
        "contract_version": "phase-0.4",
        "notes": [
            "This report is replay-backed internal consistency calibration, not external ground-truth event validation.",
            "Threshold guidance is derived from the currently persisted planetary evidence slice in the repository.",
        ],
        "disaster_likelihood": {
            "forecast_count": len(hazard_forecasts),
            "average_likelihood": round(mean(hazard_likelihoods), 4) if hazard_likelihoods else 0.0,
            "average_severity": round(mean(hazard_severities), 4) if hazard_severities else 0.0,
            "high_likelihood_count": sum(1 for value in hazard_likelihoods if value >= 0.65),
            "high_severity_count": sum(1 for value in hazard_severities if value >= 0.65),
            "corroborated_country_count": len(corroborated_hazard_countries),
            "corroboration_rate": hazard_alignment_rate,
            "recommended_thresholds": {
                "watch": round(_percentile(hazard_likelihoods, 0.5, 0.45), 4),
                "alert": round(_percentile(hazard_likelihoods, 0.75, 0.65), 4),
                "critical": round(_percentile(hazard_likelihoods, 0.9, 0.8), 4),
            },
            "signal_support_count": len(disaster_signals),
        },
        "behavior_thresholds": {
            "country_count": len(country_snapshots),
            "direct_behavior": {
                "median": round(_percentile(direct_behavior, 0.5, 0.0), 4),
                "elevated": round(_percentile(direct_behavior, 0.75, 0.55), 4),
                "critical": round(_percentile(direct_behavior, 0.9, 0.75), 4),
            },
            "contextual_pressure": {
                "median": round(_percentile(contextual_pressure, 0.5, 0.0), 4),
                "elevated": round(_percentile(contextual_pressure, 0.75, 0.55), 4),
                "critical": round(_percentile(contextual_pressure, 0.9, 0.75), 4),
            },
            "coordination_risk": {
                "median": round(_percentile(coordination_pressure, 0.5, 0.0), 4),
                "elevated": round(_percentile(coordination_pressure, 0.75, 0.5), 4),
                "critical": round(_percentile(coordination_pressure, 0.9, 0.7), 4),
            },
            "signal_support_count": len(behavior_signals),
            "alignment_rate": behavior_signal_alignment,
        },
        "fusion_scoring": {
            "country_count": len(country_fusion_snapshots),
            "average_fused_score": round(mean(fusion_scores), 4) if fusion_scores else 0.0,
            "high_fusion_count": sum(1 for value in fusion_scores if value >= 0.65),
            "corroboration_rate": fusion_corroboration_rate,
            "subsystem_mean_scores": subsystem_means,
            "current_weights": {
                "behavior_stress": 0.32,
                "hazard_exposure": 0.20,
                "internet_disruption": 0.18,
                "mobility_pressure": 0.16,
                "economic_pressure": 0.09,
                "narrative_pressure": 0.05,
            },
            "recommendation": (
                "Increase corroboration requirements before critical fusion escalation."
                if fusion_corroboration_rate < 0.5
                else "Current fusion scoring shows acceptable multi-system corroboration for this replay slice."
            ),
        },
        "backtests": {
            "hazard_chain_alignment_rate": hazard_alignment_rate,
            "behavior_signal_alignment_rate": behavior_signal_alignment,
            "fusion_alert_corroboration_rate": fusion_corroboration_rate,
        },
    }
