from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def compute_quality_gate(
    *,
    verified_countries: int,
    total_countries: int,
    freshness_ratio: float,
    critical_sources_down: int,
    threshold_coverage: int = 90,
    threshold_freshness: float = 0.70,
    threshold_critical_down: int = 2,
) -> dict[str, Any]:
    total = max(_as_int(total_countries, 0), 1)
    verified = max(_as_int(verified_countries, 0), 0)
    coverage_ratio = verified / float(total)
    fresh_ratio = max(0.0, min(1.0, _as_float(freshness_ratio, 0.0)))
    critical_down = max(_as_int(critical_sources_down, 0), 0)

    reasons: list[str] = []
    if verified < threshold_coverage:
        reasons.append(f"coverage {verified}/{total} below threshold {threshold_coverage}")
    if fresh_ratio < threshold_freshness:
        reasons.append(f"freshness {fresh_ratio:.2%} below threshold {threshold_freshness:.0%}")
    if critical_down >= threshold_critical_down:
        reasons.append(f"critical sources down {critical_down} >= threshold {threshold_critical_down}")

    active = len(reasons) > 0
    status = "insufficient_global_coverage" if active else "sufficient"
    return {
        "active": active,
        "status": status,
        "message": "Insufficient Global Coverage" if active else "Coverage healthy",
        "reasons": reasons,
        "metrics": {
            "verified_countries": verified,
            "total_countries": total,
            "coverage_ratio": round(coverage_ratio, 4),
            "freshness_ratio": round(fresh_ratio, 4),
            "critical_sources_down": critical_down,
        },
        "thresholds": {
            "coverage": threshold_coverage,
            "freshness_ratio": threshold_freshness,
            "critical_sources_down": threshold_critical_down,
        },
        "rollout": {
            "phase": "A",
            "shadow_mode": True,
            "rollback_toggle_enabled": True,
        },
    }
