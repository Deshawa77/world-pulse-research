from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

import numpy as np

from collectors.country_news import get_country_catalog
from database.mongo import db

PLACEHOLDER_TOPICS = {"global_expansion", "no data"}
COUNTRY_VALIDATION_FRESHNESS_WINDOW_HOURS = 30.0
DEFAULT_FORECAST_HORIZON_HOURS = 24
MEANINGFUL_EXTERNAL_FIELDS = (
    "public_attention_score",
    "narrative_velocity_score",
    "coordination_risk_score",
    "mobility_disruption_score",
    "logistics_stress_score",
    "household_stress_score",
    "fuel_price_pressure",
    "food_price_pressure",
    "labor_stress_score",
    "fx_pressure_score",
    "remittance_stress_score",
    "energy_stress_score",
    "weather_stress",
)

SOURCE_RELIABILITY_HINTS = {
    "reuters": 0.98,
    "associated press": 0.97,
    " ap ": 0.95,
    "bbc": 0.93,
    "financial times": 0.92,
    "bloomberg": 0.94,
    "washington post": 0.9,
    "new york times": 0.92,
    "the guardian": 0.88,
    "al jazeera": 0.88,
    "france 24": 0.87,
    "dw": 0.86,
    "euronews": 0.85,
    "cnn": 0.82,
    "newsapi": 0.74,
    "gdelt": 0.78,
    "globenewswire": 0.55,
    "pr newswire": 0.55,
}

REGION_GROUPS = {
    "north_america": {
        "USA", "CAN", "MEX", "BLZ", "GTM", "HND", "SLV", "NIC", "CRI", "PAN", "PRI", "BHS", "BRB",
        "GRD", "VCT", "LCA", "DMA", "ATG", "KNA", "ABW", "CUW", "SXM", "MAF", "BMU", "CYM", "TCA",
        "AIA", "MSR", "VIR", "VGB", "BES", "CUB", "HTI", "DOM", "TTO", "SPM", "JAM",
    },
    "south_america": {
        "BRA", "ARG", "COL", "PER", "CHL", "ECU", "BOL", "URY", "PRY", "VEN", "GUY", "SUR", "GUF",
        "FLK", "SGS",
    },
    "europe": {
        "GBR", "DEU", "FRA", "ITA", "ESP", "POL", "CZE", "ROU", "PRT", "GRC", "HUN", "SVK", "BGR",
        "HRV", "LUX", "LTU", "SVN", "SRB", "ALB", "BIH", "MKD", "MDA", "ISL", "IRL", "DNK", "FIN",
        "NOR", "SWE", "EST", "LVA", "BLR", "MNE", "CYP", "MLT", "GIB", "GGY", "JEY", "IMN", "FRO",
        "ALA", "SJM", "UKR", "RUS", "XKX", "AND", "CHE", "AUT", "BEL", "NLD", "LIE", "SMR", "MCO",
    },
    "middle_east_north_africa": {
        "TUR", "SAU", "QAT", "KWT", "MAR", "TUN", "LBN", "YEM", "PSE", "IRN", "IRQ", "SYR", "JOR",
        "ISR", "OMN", "ARE", "BHR", "LBY", "DZA", "MRT", "EGY", "SDN", "ESH",
    },
    "sub_saharan_africa": {
        "ZAF", "NGA", "ETH", "KEN", "CIV", "SEN", "GHA", "NER", "TGO", "MLI", "RWA", "SOM", "BDI",
        "TCD", "GNB", "BFA", "LBR", "SLE", "CAF", "LSO", "GMB", "SWZ", "DJI", "COM", "CPV", "STP",
        "SYC", "ERI", "CMR", "BEN", "GIN", "GNQ", "GAB", "COG", "COD", "UGA", "TZA", "MWI", "MOZ",
        "ZMB", "ZWE", "BWA", "NAM", "MDG", "REU", "MYT", "SSD", "AGO",
    },
    "south_asia": {"IND", "PAK", "BGD", "NPL", "LKA", "BTN", "MDV", "AFG"},
    "east_asia": {"JPN", "CHN", "KOR", "PRK", "TWN", "HKG", "MAC", "MNG"},
    "southeast_asia": {"IDN", "VNM", "PHL", "MYS", "THA", "MMR", "KHM", "LAO", "BRN", "SGP", "TLS"},
    "central_asia": {"KAZ", "UZB", "KGZ", "TJK", "TKM", "AZE", "ARM", "GEO"},
    "oceania": {
        "AUS", "NZL", "PNG", "VUT", "WSM", "TON", "FSM", "KIR", "SLB", "PLW", "NRU", "TUV", "COK",
        "NIU", "TKL", "GUM", "NFK", "CXR", "CCK", "HMD", "ATA", "ATF", "BVT", "IOT", "MNP", "ASM",
        "MHL", "FJI", "WLF", "NCL", "PYF", "PCN", "VGB", "SHN", "ASC", "TAA",
    },
}

_OPERATIONAL_CACHE: dict[str, dict[str, Any]] = {}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return fallback
    return parsed if np.isfinite(parsed) else fallback


def _clamp(value: Any, low: float, high: float) -> float:
    return max(low, min(high, _safe_float(value, low)))


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except Exception:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalized_topics(features: dict[str, Any]) -> list[str]:
    raw_topics = features.get("top_topics") or []
    topics = []
    for topic in raw_topics:
        text = str(topic).strip().lower()
        if text:
            topics.append(text)
    return topics


def _is_recent_country_feature_timestamp(feature_timestamp: datetime | None, *, window_hours: float = COUNTRY_VALIDATION_FRESHNESS_WINDOW_HOURS) -> bool:
    if not feature_timestamp:
        return False
    age_hours = (datetime.now(timezone.utc) - feature_timestamp).total_seconds() / 3600.0
    return 0.0 <= age_hours <= float(window_hours)


def is_verified_country_feature(features: dict[str, Any], doc_timestamp: Any = None) -> dict[str, Any]:
    topics = _normalized_topics(features)
    feature_timestamp = _parse_timestamp(features.get("timestamp") or doc_timestamp)
    updated_today = _is_recent_country_feature_timestamp(feature_timestamp)
    is_placeholder = (not topics) or any(topic in PLACEHOLDER_TOPICS for topic in topics)

    source_count_value = max(int(features.get("source_count") or 0), 0)
    external_sources = features.get("external_sources") if isinstance(features.get("external_sources"), list) else []
    external_source_count = len(external_sources)
    freshness_value = _clamp(features.get("external_signal_freshness"), 0.0, 1.0)
    evidence_value = _clamp(_safe_float(features.get("evidence_quality_score"), 0.0), 0.0, 100.0)
    strongest_non_news_signal = max((_safe_float(features.get(field), 0.0) for field in MEANINGFUL_EXTERNAL_FIELDS), default=0.0)
    has_war_rules = bool(features.get("war_state_rules"))

    multi_signal_verified = (
        has_war_rules
        or source_count_value >= 1
        or (external_source_count >= 3 and freshness_value >= 0.33 and strongest_non_news_signal >= 0.45)
        or (evidence_value >= 32.0 and strongest_non_news_signal >= 0.55)
    )
    validated_today = updated_today and ((not is_placeholder) or multi_signal_verified)

    if validated_today:
        data_quality = "verified"
    elif is_placeholder:
        data_quality = "synthetic"
    elif feature_timestamp:
        data_quality = "stale"
    else:
        data_quality = "unknown"
    return {
        "validated_today": validated_today,
        "data_quality": data_quality,
        "feature_timestamp": feature_timestamp,
        "verification_mode": "multi_signal" if validated_today and is_placeholder else ("topic" if validated_today else "none"),
    }


def _country_region(country_code: str) -> str:
    normalized = str(country_code or "").strip().upper()
    for region_name, members in REGION_GROUPS.items():
        if normalized in members:
            return region_name
    return "other"


def _source_reliability_from_label(label: str) -> float:
    normalized = f" {str(label or '').strip().lower()} "
    for token, weight in SOURCE_RELIABILITY_HINTS.items():
        if token in normalized:
            return weight
    return 0.72


def _country_source_metrics(features: dict[str, Any]) -> tuple[float, float]:
    diversity = features.get("source_diversity_score")
    reliability = features.get("source_reliability_score")
    if diversity is None:
        diversity = min(max(_safe_float(features.get("source_count"), 0.0) / 4.0, 0.0), 1.0)
    if reliability is None:
        reliability = _source_reliability_from_label(str(features.get("source") or ""))
    return round(_clamp(diversity, 0.0, 1.0), 4), round(_clamp(reliability, 0.3, 1.0), 4)


def _load_country_sentiment_baseline(country_code: str, mode: str, current_timestamp: datetime | None, history_window: int = 10) -> tuple[float, float]:
    cursor = db.country_features.find(
        {"country": country_code, "mode": mode},
        {"features": 1, "timestamp": 1},
    ).sort("_id", -1).limit(history_window + 6)

    samples: list[float] = []
    for doc in cursor:
        features = doc.get("features") or {}
        sample_timestamp = _parse_timestamp(features.get("timestamp") or doc.get("timestamp"))
        if current_timestamp and sample_timestamp and sample_timestamp >= current_timestamp:
            continue
        values = [
            _safe_float(features.get("news_sentiment"), 0.0),
            _safe_float(features.get("gdelt_sentiment"), 0.0),
        ]
        samples.append(float(np.mean(values)))
        if len(samples) >= history_window:
            break

    if not samples:
        return 0.0, 0.08
    baseline_mean = float(np.mean(samples))
    baseline_std = float(np.std(samples)) if len(samples) > 1 else 0.08
    return round(baseline_mean, 5), max(round(baseline_std, 5), 0.08)


def build_country_mood_fields(country_code: str, feature_doc: dict[str, Any], mode: str = "online") -> dict[str, Any]:
    existing_keys = {
        "country_mood_score",
        "country_mood_baseline",
        "country_mood_sentiment_delta",
        "country_mood_sentiment_zscore",
        "source_diversity_score",
        "source_reliability_score",
    }
    if existing_keys.issubset(feature_doc.keys()):
        existing_score = _safe_float(feature_doc.get("country_mood_score"), 50.0)
        existing_baseline = _safe_float(feature_doc.get("country_mood_baseline"), 0.0)
        existing_delta = _safe_float(feature_doc.get("country_mood_sentiment_delta"), 0.0)
        existing_zscore = _safe_float(feature_doc.get("country_mood_sentiment_zscore"), 0.0)
        # Avoid preserving neutral default placeholders (all zeros) as real mood estimates.
        has_computed_mood = not (
            abs(existing_score) < 1e-9
            and abs(existing_baseline) < 1e-9
            and abs(existing_delta) < 1e-9
            and abs(existing_zscore) < 1e-9
        )
        if has_computed_mood:
            return {
                "country_mood_score": round(_clamp(feature_doc.get("country_mood_score"), 0.0, 100.0), 2),
                "country_mood_baseline": round(_safe_float(feature_doc.get("country_mood_baseline"), 0.0), 5),
                "country_mood_sentiment_delta": round(_safe_float(feature_doc.get("country_mood_sentiment_delta"), 0.0), 5),
                "country_mood_sentiment_zscore": round(_safe_float(feature_doc.get("country_mood_sentiment_zscore"), 0.0), 4),
                "source_diversity_score": round(_clamp(feature_doc.get("source_diversity_score"), 0.0, 1.0), 4),
                "source_reliability_score": round(_clamp(feature_doc.get("source_reliability_score"), 0.3, 1.0), 4),
            }
    current_timestamp = _parse_timestamp(feature_doc.get("timestamp"))
    raw_sentiment = float(np.mean([
        _safe_float(feature_doc.get("news_sentiment"), 0.0),
        _safe_float(feature_doc.get("gdelt_sentiment"), 0.0),
    ]))
    baseline_mean, baseline_std = _load_country_sentiment_baseline(country_code, mode, current_timestamp)
    sentiment_delta = raw_sentiment - baseline_mean
    sentiment_zscore = float(np.clip(sentiment_delta / max(baseline_std, 0.08), -2.5, 2.5))

    conflict_headline_count = _safe_float(feature_doc.get("conflict_headline_count"), 0.0)
    weighted_keyword_severity = _clamp(feature_doc.get("weighted_keyword_severity"), 0.0, 1.0)
    regional_escalation = _clamp(feature_doc.get("regional_escalation"), 0.0, 1.0)
    social_unrest_score = _clamp(feature_doc.get("social_unrest_score"), 0.0, 1.0)
    google_trends_pressure = _clamp(feature_doc.get("google_trends_pressure"), 0.0, 1.0)
    public_attention_score = _clamp(feature_doc.get("public_attention_score"), 0.0, 1.0)
    weather_stress = _clamp(feature_doc.get("weather_stress"), 0.0, 1.0)
    war_state_penalty = 10.0 if feature_doc.get("war_state_rules") else 0.0

    sentiment_component = (raw_sentiment * 24.0) + (sentiment_zscore * 7.5)
    pressure_penalty = (
        min(conflict_headline_count / 4.0, 1.0) * 8.0
        + weighted_keyword_severity * 18.0
        + regional_escalation * 12.0
        + social_unrest_score * 8.0
        + google_trends_pressure * 11.0
        + public_attention_score * 12.0
        + weather_stress * 9.0
        + war_state_penalty
    )
    source_diversity_score, source_reliability_score = _country_source_metrics(feature_doc)
    source_count = max(_safe_float(feature_doc.get("source_count"), 0.0), 0.0)
    source_count_weight = min(max(source_count / 4.0, 0.25), 1.0)
    source_confidence_factor = _clamp(
        (0.25 + (0.5 * source_diversity_score) + (0.25 * source_reliability_score)) * (0.7 + (0.3 * source_count_weight)),
        0.35,
        1.0,
    )
    effective_penalty = pressure_penalty * source_confidence_factor
    country_mood_score = _clamp(50.0 + sentiment_component - effective_penalty, 0.0, 100.0)

    return {
        "country_mood_score": round(country_mood_score, 2),
        "country_mood_baseline": round(baseline_mean, 5),
        "country_mood_sentiment_delta": round(sentiment_delta, 5),
        "country_mood_sentiment_zscore": round(sentiment_zscore, 4),
        "source_diversity_score": source_diversity_score,
        "source_reliability_score": source_reliability_score,
    }


def augment_country_mood_fields(country_code: str, feature_doc: dict[str, Any], mode: str = "online") -> dict[str, Any]:
    feature_doc.update(build_country_mood_fields(country_code, feature_doc, mode=mode))
    return feature_doc


def _freshness_weight(feature_timestamp: datetime | None) -> float:
    if feature_timestamp is None:
        return 0.55
    age_hours = max((datetime.now(timezone.utc) - feature_timestamp).total_seconds() / 3600.0, 0.0)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.88
    if age_hours <= 48:
        return 0.65
    return 0.4


def _load_latest_country_rows(mode: str) -> list[dict[str, Any]]:
    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"_id": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
    ]
    return list(db.country_features.aggregate(pipeline))


def _weighted_mean(points: list[dict[str, Any]]) -> float:
    total_weight = sum(point["weight"] for point in points)
    if total_weight <= 0:
        return 50.0
    return float(sum(point["score"] * point["weight"] for point in points) / total_weight)


def _weighted_std(points: list[dict[str, Any]], mean_value: float) -> float:
    total_weight = sum(point["weight"] for point in points)
    if total_weight <= 0:
        return 0.0
    variance = sum(point["weight"] * ((point["score"] - mean_value) ** 2) for point in points) / total_weight
    return float(np.sqrt(max(variance, 0.0)))


def _observation_confidence(features: dict[str, Any], feature_timestamp: datetime | None) -> float:
    freshness = _freshness_weight(feature_timestamp)
    raw_source_confidence = _clamp(features.get("source_confidence"), 0.0, 1.0)
    source_diversity = _clamp(features.get("source_diversity_score"), 0.0, 1.0)
    source_reliability = _clamp(features.get("source_reliability_score"), 0.3, 1.0)
    source_count = max(_safe_float(features.get("source_count"), 0.0), 0.0)
    external_sources = features.get("external_sources") if isinstance(features.get("external_sources"), list) else []
    external_source_count = float(len(external_sources))
    effective_source_count = max(source_count, external_source_count)
    source_count_weight = min(max(effective_source_count / 4.0, 0.25), 1.0)
    source_diversity = max(source_diversity, min(max(external_source_count / 4.0, 0.0), 1.0))
    evidence_quality = _clamp(_safe_float(features.get("evidence_quality_score"), 0.0) / 100.0, 0.0, 1.0)
    strongest_non_news_signal = max((_safe_float(features.get(field), 0.0) for field in MEANINGFUL_EXTERNAL_FIELDS), default=0.0)
    source_confidence = max(raw_source_confidence, freshness, evidence_quality, min(strongest_non_news_signal, 1.0) * 0.8)
    observation_confidence = (
        (0.22 * freshness)
        + (0.18 * source_confidence)
        + (0.16 * source_diversity)
        + (0.12 * source_reliability)
        + (0.12 * source_count_weight)
        + (0.12 * evidence_quality)
        + (0.08 * min(strongest_non_news_signal, 1.0))
    )
    return round(_clamp(observation_confidence, 0.0, 1.0), 4)


def _score_median(points: list[dict[str, Any]]) -> float:
    if not points:
        return 50.0
    scores = sorted(point["score"] for point in points)
    return float(np.median(scores))


def _score_mad(points: list[dict[str, Any]], median_score: float) -> float:
    if not points:
        return 0.0
    deviations = [abs(point["score"] - median_score) for point in points]
    return float(np.median(deviations))


def _suspicion_downweight(point: dict[str, Any], median_score: float, mad_score: float) -> float:
    features = point["features"]
    observation_confidence = point["observation_confidence"]
    score_scale = max(mad_score * 1.4826, 4.0)
    score_deviation = abs(point["score"] - median_score) / score_scale
    sentiment_extremeness = abs(_safe_float(features.get("country_mood_sentiment_zscore"), 0.0))
    pressure_spike = max(
        _clamp(features.get("weighted_keyword_severity"), 0.0, 1.0),
        _clamp(features.get("social_unrest_score"), 0.0, 1.0),
        _clamp(features.get("google_trends_pressure"), 0.0, 1.0),
        _clamp(features.get("public_attention_score"), 0.0, 1.0),
        _clamp(features.get("weather_stress"), 0.0, 1.0),
    )
    low_confidence = max(0.0, 0.65 - observation_confidence) / 0.65
    outlier_component = min(max(0.0, score_deviation - 1.75) / 1.75, 1.0)
    sentiment_component = min(max(0.0, sentiment_extremeness - 1.8) / 1.4, 1.0)
    pressure_component = min(max(0.0, pressure_spike - 0.85) / 0.15, 1.0)
    suspiciousness = min(
        (0.55 * outlier_component)
        + (0.2 * sentiment_component)
        + (0.15 * low_confidence)
        + (0.1 * pressure_component),
        1.0,
    )
    return round(max(0.3, 1.0 - (0.7 * suspiciousness)), 4)


def _dynamic_trim_ratio(eligible_count: int, coverage_ratio: float) -> float:
    if eligible_count < 40 or coverage_ratio < 0.2:
        return 0.0
    if eligible_count < 80 or coverage_ratio < 0.35:
        return 0.05
    return 0.1


def _is_meaningful_global_candidate(
    features: dict[str, Any],
    quality: dict[str, Any],
    *,
    risk: float,
    observation_confidence: float,
    evidence_quality: float,
    strongest_non_news_signal: float,
) -> bool:
    if bool(quality.get("validated_today")):
        return True
    if bool(features.get("war_state_rules")):
        return True
    if risk >= 70.0:
        return True
    if risk >= 55.0 and observation_confidence >= 0.45:
        return True
    if evidence_quality >= 0.42 and strongest_non_news_signal >= 0.45:
        return True
    return False


def _trim_points(points: list[dict[str, Any]], trim_ratio: float = 0.0) -> list[dict[str, Any]]:
    if trim_ratio <= 0 or len(points) < 6:
        return points
    trim_count = int(len(points) * trim_ratio)
    if trim_count <= 0 or (trim_count * 2) >= len(points):
        return points
    ordered = sorted(points, key=lambda point: point["score"])
    trimmed = ordered[trim_count:len(ordered) - trim_count]
    return trimmed or points


def compute_global_mood_summary(mode: str = "online", country_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = country_rows if country_rows is not None else _load_latest_country_rows(mode)
    total_countries = max(len(get_country_catalog()), len(rows), 1)

    verified_candidates: list[dict[str, Any]] = []
    region_counts: Counter[str] = Counter()
    verified_count = 0
    screened_out_count = 0
    for row in rows:
        doc = row.get("doc") or row
        country = str(doc.get("country") or row.get("_id") or "").strip().upper()
        features = dict(doc.get("features") or {})
        quality = is_verified_country_feature(features, doc.get("timestamp"))
        mood_fields = build_country_mood_fields(country, features, mode=mode)
        features.update(mood_fields)
        if not quality["validated_today"]:
            continue

        verified_count += 1
        observation_confidence = _observation_confidence(features, quality["feature_timestamp"])
        if observation_confidence < 0.55:
            screened_out_count += 1
            continue

        region = _country_region(country)
        region_counts[region] += 1
        verified_candidates.append({
            "country": country,
            "region": region,
            "features": features,
            "quality": quality,
            "observation_confidence": observation_confidence,
        })

    if not verified_candidates:
        return {
            "global_mood_score": 50.0,
            "global_mood_confidence": 0.0,
            "global_mood_uncertainty": 18.0,
            "global_mood_verified_countries": verified_count,
            "global_mood_eligible_countries": 0,
            "global_mood_contributing_countries": 0,
            "global_mood_used_countries": 0,
            "global_mood_excluded_countries": 0,
            "global_mood_screened_out_countries": screened_out_count,
            "global_mood_total_countries": total_countries,
            "global_mood_coverage_ratio": 0.0,
            "global_mood_active_regions": 0,
            "global_mood_trim_ratio": 0.0,
            "global_mood_downweighted_countries": 0,
            "global_mood_method": "verified-country-confidence-gated-robust-weighted-mean",
        }

    points: list[dict[str, Any]] = []
    for item in verified_candidates:
        features = item["features"]
        quality = item["quality"]
        feature_timestamp = quality["feature_timestamp"]
        freshness = _freshness_weight(feature_timestamp)
        observation_confidence = item["observation_confidence"]
        recency_weight_raw = _safe_float(features.get("recency_weight"), 0.0)
        recency_weight = _clamp(recency_weight_raw if recency_weight_raw > 0 else freshness, 0.0, 1.0)
        base_weight = (
            freshness
            * (0.4 + (0.6 * observation_confidence))
            * (0.4 + (0.6 * recency_weight))
        )
        region_balance_weight = 1.0 / max(region_counts.get(item["region"], 1), 1)
        final_weight = base_weight * region_balance_weight
        if final_weight <= 0:
            continue
        points.append({
            "country": item["country"],
            "region": item["region"],
            "score": _safe_float(features.get("country_mood_score"), 50.0),
            "weight": final_weight,
            "base_weight": base_weight,
            "features": features,
            "observation_confidence": observation_confidence,
        })

    if not points:
        return {
            "global_mood_score": 50.0,
            "global_mood_confidence": 0.0,
            "global_mood_uncertainty": 18.0,
            "global_mood_verified_countries": verified_count,
            "global_mood_eligible_countries": len(verified_candidates),
            "global_mood_contributing_countries": 0,
            "global_mood_used_countries": 0,
            "global_mood_excluded_countries": 0,
            "global_mood_screened_out_countries": screened_out_count,
            "global_mood_total_countries": total_countries,
            "global_mood_coverage_ratio": 0.0,
            "global_mood_active_regions": len(region_counts),
            "global_mood_trim_ratio": 0.0,
            "global_mood_downweighted_countries": 0,
            "global_mood_method": "verified-country-confidence-gated-robust-weighted-mean",
        }

    median_score = _score_median(points)
    mad_score = _score_mad(points, median_score)
    downweighted_count = 0
    for point in points:
        suspicious_multiplier = _suspicion_downweight(point, median_score, mad_score)
        if suspicious_multiplier < 0.999:
            downweighted_count += 1
        point["weight"] *= suspicious_multiplier
        point["effective_weight"] = point["base_weight"] * suspicious_multiplier
        point["suspicious_multiplier"] = suspicious_multiplier

    eligible_count = len(points)
    coverage_ratio = eligible_count / float(total_countries)
    trim_ratio = _dynamic_trim_ratio(eligible_count, coverage_ratio)
    trimmed_points = _trim_points(points, trim_ratio=trim_ratio)
    used_count = len(trimmed_points)
    excluded_count = max(eligible_count - used_count, 0)
    global_mood_score = round(_weighted_mean(trimmed_points), 2)
    dispersion = _weighted_std(trimmed_points, global_mood_score)
    avg_effective_weight = float(np.mean([point.get("effective_weight", point["base_weight"]) for point in points])) if points else 0.0
    total_regions = max(len(REGION_GROUPS) + 1, 1)
    active_regions = len(region_counts)
    region_coverage = active_regions / float(total_regions)
    retention_ratio = used_count / float(eligible_count) if eligible_count else 0.0
    confidence = _clamp(
        (coverage_ratio ** 0.85)
        * (0.55 + (0.45 * avg_effective_weight))
        * (0.75 + (0.25 * region_coverage))
        * (0.85 + (0.15 * retention_ratio)),
        0.0,
        1.0,
    )
    uncertainty = _clamp(2.5 + (dispersion * 0.35) + ((1.0 - confidence) * 12.0), 2.0, 18.0)

    return {
        "global_mood_score": global_mood_score,
        "global_mood_confidence": round(confidence, 4),
        "global_mood_uncertainty": round(uncertainty, 2),
        "global_mood_verified_countries": verified_count,
        "global_mood_eligible_countries": eligible_count,
        "global_mood_contributing_countries": used_count,
        "global_mood_used_countries": used_count,
        "global_mood_excluded_countries": excluded_count,
        "global_mood_screened_out_countries": screened_out_count,
        "global_mood_total_countries": total_countries,
        "global_mood_coverage_ratio": round(coverage_ratio, 4),
        "global_mood_active_regions": active_regions,
        "global_mood_trim_ratio": round(trim_ratio, 4),
        "global_mood_downweighted_countries": downweighted_count,
        "global_mood_method": "verified-country-confidence-gated-robust-weighted-mean",
    }


def _load_global_risk_series(mode: str, limit: int = 48) -> list[tuple[datetime, float]]:
    docs = list(db.global_features.find({"mode": mode}, {"features": 1, "timestamp": 1}).sort("_id", -1).limit(limit))
    if not docs:
        docs = list(db.dashboard_features.find({"mode": mode}, {"features": 1, "timestamp": 1}).sort("_id", -1).limit(limit))
    series: list[tuple[datetime, float]] = []
    for doc in reversed(docs):
        features = doc.get("features") or {}
        timestamp = _parse_timestamp(features.get("timestamp") or doc.get("timestamp"))
        if timestamp is None:
            continue
        series.append((timestamp, _clamp(features.get("global_risk_score"), 0.0, 100.0)))
    return series


def compute_global_risk_forecast(
    mode: str = "online",
    current_risk_score: float | None = None,
    current_timestamp: Any = None,
    horizon_hours: int = DEFAULT_FORECAST_HORIZON_HOURS,
) -> dict[str, Any]:
    series = _load_global_risk_series(mode)
    current_value = _clamp(current_risk_score if current_risk_score is not None else (series[-1][1] if series else 50.0), 0.0, 100.0)
    current_point_ts = _parse_timestamp(current_timestamp) or (series[-1][0] if series else datetime.now(timezone.utc))
    if not series or current_point_ts > series[-1][0]:
        series.append((current_point_ts, current_value))

    if len(series) < 2:
        return {
            "forecast_risk_score": round(current_value, 2),
            "forecast_risk_delta": 0.0,
            "forecast_confidence": 0.35,
            "forecast_horizon_hours": horizon_hours,
            "forecast_basis": "insufficient-history",
        }

    origin = series[0][0]
    xs = [max((timestamp - origin).total_seconds() / 3600.0, float(idx)) for idx, (timestamp, _) in enumerate(series)]
    ys = [value for _, value in series]
    if len(set(round(x, 4) for x in xs)) < 2:
        slope = 0.0
        intercept = ys[-1]
    else:
        slope, intercept = np.polyfit(xs, ys, 1)
    forecast_value = _clamp(current_value + (float(slope) * horizon_hours), 0.0, 100.0)
    residuals = [y - ((float(slope) * x) + float(intercept)) for x, y in zip(xs, ys)]
    residual_std = float(np.std(residuals)) if len(residuals) > 2 else abs(float(slope)) * 4.0
    confidence = _clamp(0.42 + (min(len(series), 24) / 70.0) - min(residual_std / 45.0, 0.25), 0.3, 0.88)

    return {
        "forecast_risk_score": round(forecast_value, 2),
        "forecast_risk_delta": round(forecast_value - current_value, 2),
        "forecast_confidence": round(confidence, 4),
        "forecast_horizon_hours": horizon_hours,
        "forecast_basis": "linear-risk-trend",
    }




def _global_signal_indices(mode: str = "online") -> dict[str, float]:
    rows = _load_latest_country_rows(mode)
    raw_signal_defaults = {
        "direct_behavior_score": 0.0,
        "contextual_pressure_score": 0.0,
        "evidence_quality_score": 0.0,
        "narrative_velocity_score": 0.0,
        "coordination_risk_score": 0.0,
        "mobility_disruption_score": 0.0,
        "logistics_stress_score": 0.0,
        "household_stress_score": 0.0,
        "fuel_price_pressure": 0.0,
        "food_price_pressure": 0.0,
        "labor_stress_score": 0.0,
        "fx_pressure_score": 0.0,
        "remittance_stress_score": 0.0,
        "energy_stress_score": 0.0,
    }
    if not rows:
        return {
            "global_behavior_index": 50.0,
            "global_context_index": 50.0,
            "global_attention_index": 0.0,
            "global_disruption_index": 0.0,
            "global_economic_stress_index": 0.0,
            **raw_signal_defaults,
        }

    filtered_features: list[dict[str, Any]] = []
    all_features = [dict((row.get("doc") or row).get("features") or {}) for row in rows]
    for row in rows:
        doc = row.get("doc") or row
        features = dict(doc.get("features") or {})
        quality = is_verified_country_feature(features, doc.get("timestamp"))
        feature_timestamp = quality.get("feature_timestamp")
        observation_confidence = _observation_confidence(features, feature_timestamp)
        evidence_quality = _clamp(_safe_float(features.get("evidence_quality_score"), 0.0) / 100.0, 0.0, 1.0)
        strongest_non_news_signal = max((_safe_float(features.get(field), 0.0) for field in MEANINGFUL_EXTERNAL_FIELDS), default=0.0)
        risk = _clamp(features.get("global_risk_score"), 0.0, 100.0)
        if _is_meaningful_global_candidate(features, quality, risk=risk, observation_confidence=observation_confidence, evidence_quality=evidence_quality, strongest_non_news_signal=strongest_non_news_signal):
            filtered_features.append(features)

    features = filtered_features or all_features

    def avg(key: str) -> float:
        vals = [_safe_float(item.get(key), 0.0) for item in features]
        return float(np.mean(vals)) if vals else 0.0

    return {
        "direct_behavior_score": round(avg("direct_behavior_score"), 2),
        "contextual_pressure_score": round(avg("contextual_pressure_score"), 2),
        "evidence_quality_score": round(avg("evidence_quality_score"), 2),
        "narrative_velocity_score": round(avg("narrative_velocity_score"), 4),
        "coordination_risk_score": round(avg("coordination_risk_score"), 4),
        "mobility_disruption_score": round(avg("mobility_disruption_score"), 4),
        "logistics_stress_score": round(avg("logistics_stress_score"), 4),
        "household_stress_score": round(avg("household_stress_score"), 4),
        "fuel_price_pressure": round(avg("fuel_price_pressure"), 4),
        "food_price_pressure": round(avg("food_price_pressure"), 4),
        "labor_stress_score": round(avg("labor_stress_score"), 4),
        "fx_pressure_score": round(avg("fx_pressure_score"), 4),
        "remittance_stress_score": round(avg("remittance_stress_score"), 4),
        "energy_stress_score": round(avg("energy_stress_score"), 4),
        "global_behavior_index": round(avg("direct_behavior_score"), 2),
        "global_context_index": round(avg("contextual_pressure_score"), 2),
        "global_attention_index": round(np.mean([avg("public_attention_score") * 100.0, avg("narrative_velocity_score") * 100.0]), 2),
        "global_disruption_index": round(np.mean([avg("mobility_disruption_score") * 100.0, avg("logistics_stress_score") * 100.0]), 2),
        "global_economic_stress_index": round(np.mean([avg("household_stress_score") * 100.0, avg("energy_stress_score") * 100.0, avg("remittance_stress_score") * 100.0]), 2),
    }

def _compute_global_risk_consensus(current_risk_score: float | None, mode: str, mood_summary: dict[str, Any], signal_indices: dict[str, float]) -> dict[str, Any]:
    rows = _load_latest_country_rows(mode)
    legacy_score = _clamp(current_risk_score, 0.0, 100.0)
    if not rows:
        return {
            "legacy_model_global_risk_score": round(legacy_score, 2),
            "country_aggregate_global_risk": round(legacy_score, 2),
            "system_global_risk_score": round(legacy_score, 2),
            "global_risk_confidence": 0.0,
            "global_risk_definition": "legacy-global-model-fallback",
            "global_risk_alignment_gap": 0.0,
        }

    region_counts: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    meaningful_support_count = 0
    for row in rows:
        doc = row.get("doc") or row
        country = str(doc.get("country") or row.get("_id") or "").strip().upper()
        if not country:
            continue
        features = dict(doc.get("features") or {})
        quality = is_verified_country_feature(features, doc.get("timestamp"))
        feature_timestamp = quality.get("feature_timestamp")
        observation_confidence = _observation_confidence(features, feature_timestamp)
        evidence_quality = _clamp(_safe_float(features.get("evidence_quality_score"), 0.0) / 100.0, 0.0, 1.0)
        freshness = _freshness_weight(feature_timestamp)
        risk = _clamp(features.get("global_risk_score"), 0.0, 100.0)
        strongest_non_news_signal = max((_safe_float(features.get(field), 0.0) for field in MEANINGFUL_EXTERNAL_FIELDS), default=0.0)
        meaningful_support = _is_meaningful_global_candidate(features, quality, risk=risk, observation_confidence=observation_confidence, evidence_quality=evidence_quality, strongest_non_news_signal=strongest_non_news_signal)
        if not meaningful_support and observation_confidence < 0.5 and risk < 45.0:
            continue
        region = _country_region(country)
        region_counts[region] += 1
        if meaningful_support:
            meaningful_support_count += 1
        candidates.append({
            "country": country,
            "region": region,
            "risk": risk,
            "observation_confidence": observation_confidence,
            "evidence_quality": evidence_quality,
            "freshness": freshness,
            "meaningful_support": meaningful_support,
        })

    if not candidates:
        return {
            "legacy_model_global_risk_score": round(legacy_score, 2),
            "country_aggregate_global_risk": round(legacy_score, 2),
            "system_global_risk_score": round(legacy_score, 2),
            "global_risk_confidence": 0.0,
            "global_risk_definition": "legacy-global-model-fallback",
            "global_risk_alignment_gap": 0.0,
        }

    weighted_points: list[dict[str, float]] = []
    for item in candidates:
        region_balance = 1.0 / max(region_counts.get(item["region"], 1), 1)
        base_weight = ((0.34 * item["freshness"]) + (0.36 * item["observation_confidence"]) + (0.3 * item["evidence_quality"]))
        support_multiplier = 1.0 if item["meaningful_support"] else 0.4
        risk_emphasis = 1.0 + max(item["risk"] - 55.0, 0.0) / 120.0
        weight = base_weight * region_balance * support_multiplier * risk_emphasis
        if weight <= 0:
            continue
        weighted_points.append({"score": item["risk"], "weight": weight})

    if not weighted_points:
        country_aggregate = legacy_score
        aggregate_confidence = 0.0
        high_risk_band = legacy_score
    else:
        country_aggregate = _weighted_mean(weighted_points)
        aggregate_confidence = float(np.mean([point["weight"] for point in weighted_points]))
        ranked_points = sorted(weighted_points, key=lambda point: point["score"], reverse=True)
        top_band_size = max(3, min(len(ranked_points), int(np.ceil(len(ranked_points) * 0.15))))
        high_risk_band = _weighted_mean(ranked_points[:top_band_size])

    mood_pressure = _clamp(100.0 - _safe_float(mood_summary.get("global_mood_score"), 50.0), 0.0, 100.0)
    structural_pressure = ((_safe_float(signal_indices.get("global_behavior_index"), 50.0) * 0.24) + (_safe_float(signal_indices.get("global_context_index"), 50.0) * 0.28) + (_safe_float(signal_indices.get("global_attention_index"), 0.0) * 0.14) + (_safe_float(signal_indices.get("global_disruption_index"), 0.0) * 0.18) + (_safe_float(signal_indices.get("global_economic_stress_index"), 0.0) * 0.16))
    escalation_bias = max(high_risk_band - country_aggregate, 0.0)
    consensus_score = ((country_aggregate * 0.34) + (high_risk_band * 0.28) + (structural_pressure * 0.2) + (mood_pressure * 0.06) + (legacy_score * 0.12) + min(escalation_bias * 0.4, 12.0))
    coverage_ratio = _clamp(_safe_float(mood_summary.get("global_mood_coverage_ratio"), 0.0), 0.0, 1.0)
    mood_confidence = _clamp(_safe_float(mood_summary.get("global_mood_confidence"), 0.0), 0.0, 1.0)
    meaningful_support_ratio = meaningful_support_count / float(len(candidates)) if candidates else 0.0
    confidence = _clamp((aggregate_confidence * 0.34) + (coverage_ratio * 0.24) + (mood_confidence * 0.22) + (meaningful_support_ratio * 0.2), 0.0, 1.0)

    if confidence < 0.28:
        system_global_risk_score = (legacy_score * 0.82) + (consensus_score * 0.18)
    elif confidence < 0.45 and consensus_score < legacy_score:
        system_global_risk_score = (legacy_score * 0.68) + (consensus_score * 0.32)
    else:
        blend_weight = 0.18 + (confidence * 0.52)
        system_global_risk_score = (legacy_score * (1.0 - blend_weight)) + (consensus_score * blend_weight)

    if high_risk_band > system_global_risk_score and (high_risk_band - system_global_risk_score) > 8.0:
        system_global_risk_score = max(system_global_risk_score, (system_global_risk_score * 0.7) + (high_risk_band * 0.3))
    if confidence < 0.35:
        system_global_risk_score = max(system_global_risk_score, legacy_score - 6.0)
    system_global_risk_score = _clamp(system_global_risk_score, 0.0, 100.0)

    return {
        "legacy_model_global_risk_score": round(legacy_score, 2),
        "country_aggregate_global_risk": round(country_aggregate, 2),
        "system_global_risk_score": round(system_global_risk_score, 2),
        "global_risk_confidence": round(confidence, 4),
        "global_risk_definition": "country-intelligence-consensus-v3",
        "global_risk_alignment_gap": round(system_global_risk_score - legacy_score, 2),
    }

def compute_global_operational_features(
    current_risk_score: float | None,
    mode: str = "online",
    current_timestamp: Any = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    cache_signature = None
    if use_cache:
        latest_country = db.country_features.find_one({"mode": mode}, sort=[("_id", -1)], projection={"_id": 1})
        latest_global = db.global_features.find_one({"mode": mode}, sort=[("_id", -1)], projection={"_id": 1})
        if latest_global is None:
            latest_global = db.dashboard_features.find_one({"mode": mode}, sort=[("_id", -1)], projection={"_id": 1})
        cache_signature = {
            "country_id": str((latest_country or {}).get("_id") or ""),
            "global_id": str((latest_global or {}).get("_id") or ""),
            "risk": round(_safe_float(current_risk_score, 50.0), 2),
        }
        cached = _OPERATIONAL_CACHE.get(mode)
        if cached and cached.get("signature") == cache_signature:
            return dict(cached.get("value") or {})

    mood_summary = compute_global_mood_summary(mode=mode)
    forecast_summary = compute_global_risk_forecast(
        mode=mode,
        current_risk_score=current_risk_score,
        current_timestamp=current_timestamp,
    )
    signal_indices = _global_signal_indices(mode=mode)
    risk_consensus = _compute_global_risk_consensus(
        current_risk_score=current_risk_score,
        mode=mode,
        mood_summary=mood_summary,
        signal_indices=signal_indices,
    )
    result = {**mood_summary, **forecast_summary, **signal_indices, **risk_consensus}

    if use_cache and cache_signature is not None:
        _OPERATIONAL_CACHE[mode] = {
            "signature": cache_signature,
            "value": dict(result),
        }
    return result

