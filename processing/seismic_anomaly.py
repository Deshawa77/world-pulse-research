from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import log1p
from typing import Any

from machine_learning.disaster_models import predict_hazard_forecast
from processing.disaster_feature_builder import (
    _latest_docs,
    _recent_seismic_world_state,
    _recent_social_signals,
    _seismic_region_key,
    clamp,
    normalize_country,
    parse_dt,
    safe_float,
)
from processing.disaster_hotspot_regions import HOTSPOT_TREND_WINDOWS, build_region_metadata
from processing.disaster_storage import persist_seismic_anomaly_snapshot

SEISMIC_SOURCE_FAMILIES = ["seismic_data", "social_media_signals"]
SEISMIC_TOKENS = ("earthquake", "quake", "tremor", "aftershock", "seismic", "foreshock")


def _history_feature_summary(history_points: list[dict[str, Any]]) -> dict[str, float]:
    if not history_points:
        return {"history_avg_activity": 0.0, "history_max_activity": 0.0, "history_recent_delta": 0.0}
    activity_values = [safe_float(point.get("activity")) for point in history_points]
    recent_delta = activity_values[-1] - activity_values[0] if len(activity_values) >= 2 else 0.0
    return {
        "history_avg_activity": round(sum(activity_values) / len(activity_values), 4),
        "history_max_activity": round(max(activity_values), 4),
        "history_recent_delta": round(recent_delta, 4),
    }


def _build_seismic_window_activity(window_rows: list[dict[str, Any]]) -> float:
    event_count = len(window_rows)
    max_mag = max([safe_float(row.get("mag")) for row in window_rows], default=0.0)
    strong_count = sum(1 for row in window_rows if safe_float(row.get("mag")) >= 4.5)
    social_peak = max([safe_float(row.get("social_intensity")) for row in window_rows], default=0.0)
    count_component = clamp(event_count / 8.0)
    magnitude_component = clamp(max(max_mag - 3.0, 0.0) / 3.2)
    strong_component = clamp(strong_count / 4.0)
    return 0.42 * count_component + 0.28 * magnitude_component + 0.18 * strong_component + 0.12 * social_peak


def _derive_window_series(rows: list[dict[str, Any]], now_utc: datetime, hours: int) -> list[dict[str, Any]]:
    bucket_hours = 6 if hours > 6 else 1
    count = max(2, hours // bucket_hours)
    series: list[dict[str, Any]] = []
    for idx in range(count):
        window_end = now_utc - timedelta(hours=(count - idx - 1) * bucket_hours)
        window_start = window_end - timedelta(hours=bucket_hours)
        window_rows = [row for row in rows if window_start < row["ts"] <= window_end]
        activity = _build_seismic_window_activity(window_rows)
        max_mag = max([safe_float(row.get("mag")) for row in window_rows], default=0.0)
        series.append(
            {
                "timestamp": window_end.isoformat(),
                "activity": round(clamp(activity), 3),
                "band": "critical" if activity >= 0.72 else "active" if activity >= 0.54 else "monitor" if activity >= 0.33 else "guarded",
                "event_count": len(window_rows),
                "intensity_peak": round(max_mag, 3),
                "quake_count": len(window_rows),
                "max_magnitude": round(max_mag, 3),
            }
        )
    return series


def _collect_social_signal(country: str | None, now_utc: datetime) -> tuple[int, float, datetime | None]:
    count = 0
    max_intensity = 0.0
    latest: datetime | None = None
    cutoff = now_utc - timedelta(hours=120)
    for doc in _recent_social_signals(180):
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = doc.get("timestamp") if isinstance(doc.get("timestamp"), datetime) else parse_dt(doc.get("timestamp"))
        if stamp and stamp < cutoff:
            continue
        text = str(doc.get("text") or "").lower()
        intensity = clamp(safe_float(doc.get("intensity"), 0.0))
        if any(token in text for token in SEISMIC_TOKENS) or (not text and intensity >= 0.7):
            count += 1
            max_intensity = max(max_intensity, intensity)
            if stamp and (latest is None or stamp > latest):
                latest = stamp
    return count, max_intensity, latest


def _collect_seismic_rows(country: str | None, now_utc: datetime) -> dict[str, list[dict[str, Any]]]:
    earthquake_docs = _latest_docs("earthquakes", 3200)
    world_state_docs = _recent_seismic_world_state(2800)
    rows_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for doc in earthquake_docs:
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp") or doc.get("collected_at") or ((doc.get("data") or {}).get("time")))
        if not stamp or stamp < now_utc - timedelta(hours=120):
            continue
        lat = safe_float(doc.get("lat"), default=float("nan"))
        lon = safe_float(doc.get("lon"), default=float("nan"))
        if lat != lat or lon != lon:
            data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
            coords = data.get("coordinates") if isinstance(data.get("coordinates"), list) else []
            if len(coords) >= 2:
                lon = safe_float(coords[0], default=float("nan"))
                lat = safe_float(coords[1], default=float("nan"))
        region = _seismic_region_key(lat, lon)
        if not region:
            continue
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        mag = safe_float(((doc.get("meta") or {}).get("mag")), safe_float(data.get("mag"), 0.0))
        rows_by_region[region].append(
            {
                "ts": stamp,
                "lat": lat,
                "lon": lon,
                "mag": mag,
                "source": "earthquakes",
                "country": doc_country,
            }
        )

    for doc in world_state_docs:
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if not stamp or stamp < now_utc - timedelta(hours=120):
            continue
        lat = safe_float(doc.get("lat"), default=float("nan"))
        lon = safe_float(doc.get("lon"), default=float("nan"))
        region = _seismic_region_key(lat, lon)
        if not region:
            continue
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        mag = safe_float(meta.get("mag"), safe_float(doc.get("value"), 0.0) * 8.0)
        rows_by_region[region].append(
            {
                "ts": stamp,
                "lat": lat,
                "lon": lon,
                "mag": mag,
                "source": str(doc.get("source") or "usgs"),
                "country": doc_country,
            }
        )

    return rows_by_region


def _build_seismic_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    *,
    history_points: list[dict[str, Any]] | None = None,
    social_hits: int = 0,
    social_boost: float = 0.0,
    social_latest: datetime | None = None,
) -> dict[str, Any]:
    sorted_rows = sorted(rows, key=lambda row: row["ts"])
    recent_quake_count = len([row for row in sorted_rows if safe_float(row.get("mag")) > 0.0])
    magnitude_sum = sum(safe_float(row.get("mag")) for row in sorted_rows if safe_float(row.get("mag")) > 0.0)
    max_mag = max([safe_float(row.get("mag")) for row in sorted_rows], default=0.0)
    major_count = sum(1 for row in sorted_rows if safe_float(row.get("mag")) >= 5.5)
    strong_count = sum(1 for row in sorted_rows if safe_float(row.get("mag")) >= 4.5)
    swarm_count = sum(1 for row in sorted_rows if safe_float(row.get("mag")) >= 3.0)
    energy_proxy_total = sum(max(0.0, safe_float(row.get("mag"))) ** 2 for row in sorted_rows)
    recent_12h_count = sum(1 for row in sorted_rows if row["ts"] >= now_utc - timedelta(hours=12))
    recent_24h_count = sum(1 for row in sorted_rows if row["ts"] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in sorted_rows if row["ts"] < now_utc - timedelta(hours=24))
    latest_signal = max([row["ts"] for row in sorted_rows], default=None)

    avg_mag = magnitude_sum / recent_quake_count if recent_quake_count else 0.0
    baseline_rate = prior_48h_count / 2.0
    if recent_quake_count:
        if baseline_rate <= 0:
            short_term_acceleration_score = clamp(recent_24h_count / 6.0)
        else:
            short_term_acceleration_score = clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    else:
        short_term_acceleration_score = 0.0

    source_overlap = len({str(row.get("source") or "") for row in sorted_rows if row.get("source")})
    history_summary = _history_feature_summary(history_points or [])
    recency_score = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (120 * 3600))) if latest_signal else 0.0
    if social_hits > 0:
        recency_score = max(recency_score, social_boost)
        if social_latest:
            latest_signal = max([value for value in [latest_signal, social_latest] if value is not None])

    center_lat = sum(float(row["lat"]) for row in sorted_rows) / len(sorted_rows) if sorted_rows else 0.0
    center_lon = sum(float(row["lon"]) for row in sorted_rows) / len(sorted_rows) if sorted_rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard="earthquake")
    lead_time_hours = int(max(6, min(18, round(8 + (short_term_acceleration_score * 8) + (recency_score * 4)))))

    anomaly_signal_score = clamp(
        0.22 * clamp(recent_quake_count / 20.0)
        + 0.18 * clamp(max(max_mag - 4.0, 0.0) / 3.0)
        + 0.18 * short_term_acceleration_score
        + 0.12 * clamp(strong_count / 8.0)
        + 0.1 * clamp(major_count / 3.0)
        + 0.1 * clamp(log1p(energy_proxy_total) / log1p(300.0))
        + 0.1 * social_boost
    )
    swarm_frequency_score = clamp(swarm_count / 14.0)
    aftershock_burst_score = clamp(recent_12h_count / 5.0)
    magnitude_clustering_score = clamp(((avg_mag - 3.5) / 2.5) + (strong_count / max(recent_quake_count, 1) * 0.35))

    contributors = ["regional seismic sequence", "seismic swarm frequency", "magnitude clustering"]
    if aftershock_burst_score >= 0.35:
        contributors.append("aftershock burst")
    if short_term_acceleration_score >= 0.35:
        contributors.append("short-term acceleration")
    if major_count > 0:
        contributors.append("major magnitude concentration")
    if social_hits > 0:
        contributors.append("social seismic chatter")

    countries = [str(row.get("country") or "").upper() for row in sorted_rows if row.get("country")]
    return {
        "event_type": "earthquake",
        "country": max(set(countries), key=countries.count) if countries else "GLB",
        "region": region,
        **metadata,
        "center_lat": round(center_lat, 3),
        "center_lon": round(center_lon, 3),
        "lead_time_hours": lead_time_hours,
        "signal_sources": list(SEISMIC_SOURCE_FAMILIES),
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Treat this as anomaly likelihood, not deterministic prediction, and verify readiness channels for the next operational window.",
        "updated_at": latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        "prediction_mode": "anomaly_likelihood",
        "prediction_guardrail": "not_deterministic",
        "anomaly_signature": f"{recent_quake_count} events with max magnitude {round(max_mag, 1)} and acceleration {round(short_term_acceleration_score, 2)}.",
        "feature_values": {
            "recent_quake_density": round(clamp(recent_quake_count / 18.0), 4),
            "average_magnitude_score": round(clamp(max(avg_mag - 3.5, 0.0) / 4.0), 4),
            "major_quake_ratio": round(clamp(major_count / max(recent_quake_count, 1)), 4),
            "aftershock_cluster_score": round(aftershock_burst_score, 4),
            "max_magnitude_score": round(clamp(max(max_mag - 4.0, 0.0) / 3.0), 4),
            "short_term_acceleration_score": round(short_term_acceleration_score, 4),
            "strong_event_density": round(clamp(strong_count / 6.0), 4),
            "energy_proxy_score": round(clamp(energy_proxy_total / 250.0), 4),
            "source_coverage": round(clamp((source_overlap + (1 if social_hits else 0)) / 4.0), 4),
            "recency_score": round(recency_score, 4),
            "swarm_frequency_score": round(swarm_frequency_score, 4),
            "magnitude_clustering_score": round(clamp(magnitude_clustering_score), 4),
            "aftershock_burst_score": round(aftershock_burst_score, 4),
            "anomaly_signal_score": round(anomaly_signal_score, 4),
            **history_summary,
        },
        "hotspot_stats": {
            "event_count": recent_quake_count,
            "intensity_peak": round(max_mag, 3),
            "quake_count": recent_quake_count,
            "max_magnitude": round(max_mag, 3),
            "strong_event_count": strong_count,
            "major_event_count": major_count,
            "recent_12h_count": recent_12h_count,
            "recent_24h_count": recent_24h_count,
            "social_hits": social_hits,
            "source_overlap": source_overlap,
        },
        "history": {key: _derive_window_series(sorted_rows, now_utc, hours) for key, hours in HOTSPOT_TREND_WINDOWS.items()},
        "trend_points": [round(point.get("activity") or 0.0, 3) for point in _derive_window_series(sorted_rows, now_utc, 24)],
    }


def _calibrate_seismic_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get("hotspot_stats") or {}
    features = item.get("feature_values") or {}

    quake_component = clamp(log1p(safe_float(stats.get("quake_count"))) / log1p(200.0))
    magnitude_component = clamp(safe_float(features.get("max_magnitude_score")))
    acceleration_component = clamp(safe_float(features.get("short_term_acceleration_score")))
    aftershock_component = clamp(safe_float(features.get("aftershock_cluster_score")))
    energy_component = clamp(safe_float(features.get("energy_proxy_score")))
    social_component = clamp(safe_float(stats.get("social_hits")) / 4.0)
    history_component = clamp(safe_float(features.get("history_avg_activity")))
    likelihood = clamp(safe_float(item.get("likelihood")))

    hotspot_score = clamp(
        0.18 * quake_component
        + 0.18 * magnitude_component
        + 0.16 * acceleration_component
        + 0.14 * aftershock_component
        + 0.12 * energy_component
        + 0.08 * social_component
        + 0.08 * history_component
        + 0.06 * likelihood
    )
    hotspot_confidence = clamp(
        0.32
        + 0.16 * quake_component
        + 0.16 * acceleration_component
        + 0.12 * magnitude_component
        + 0.12 * clamp(safe_float(item.get("confidence")))
        + 0.06 * history_component
    )
    hotspot_band = "critical" if hotspot_score >= 0.74 else "active" if hotspot_score >= 0.55 else "monitor" if hotspot_score >= 0.34 else "guarded"

    adjusted = {
        **item,
        "activity_score": round(hotspot_score, 3),
        "hotspot_score": round(hotspot_score, 3),
        "hotspot_confidence": round(hotspot_confidence, 3),
        "hotspot_band": hotspot_band,
        "prediction_mode": "anomaly_likelihood",
        "prediction_guardrail": "not_deterministic",
    }
    adjusted["severity_score"] = round(min(safe_float(adjusted.get("severity_score")), 0.72), 3)
    adjusted["confidence"] = round(min(safe_float(adjusted.get("confidence")), 0.68), 3)
    return adjusted


def compute_seismic_anomaly_scoring(
    country: str | None = None,
    limit: int = 6,
    history_lookup: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    normalized_country = normalize_country(country) if country else None
    rows_by_region = _collect_seismic_rows(normalized_country, now_utc)
    social_hits, social_boost, social_latest = _collect_social_signal(normalized_country, now_utc)

    hotspots: list[dict[str, Any]] = []
    for region, rows in rows_by_region.items():
        bundle = _build_seismic_bundle(
            region,
            rows,
            now_utc,
            history_points=(history_lookup or {}).get(region) or [],
            social_hits=social_hits,
            social_boost=social_boost,
            social_latest=social_latest,
        )
        hotspots.append(_calibrate_seismic_hotspot_score(predict_hazard_forecast(bundle)))

    hotspots.sort(
        key=lambda item: (
            float(item.get("hotspot_score") or 0.0),
            safe_float((item.get("hotspot_stats") or {}).get("max_magnitude")),
            safe_float((item.get("hotspot_stats") or {}).get("quake_count")),
            float(item.get("likelihood") or 0.0),
        ),
        reverse=True,
    )
    hotspots = hotspots[:limit]

    forecasts = []
    for item in hotspots[: max(limit, 1)]:
        forecasts.append(
            {
                **item,
                "event_type": "earthquake",
                "prediction_mode": "anomaly_likelihood",
                "prediction_guardrail": "not_deterministic",
            }
        )

    payload = {
        "generated_at": now_utc.isoformat(),
        "event_type": "earthquake",
        "country": normalized_country or "GLB",
        "source_families": list(SEISMIC_SOURCE_FAMILIES),
        "summary": {
            "critical_or_high_count": sum(1 for item in hotspots if str(item.get("hotspot_band") or "") in {"critical", "active"}),
            "watch_count": sum(1 for item in hotspots if str(item.get("hotspot_band") or "") == "monitor"),
            "top_seismic_region": hotspots[0].get("region") if hotspots else None,
            "top_seismic_region_name": hotspots[0].get("region_name") if hotspots else None,
            "social_signal_hits": social_hits,
        },
        "forecasts": forecasts,
        "regional_hotspots": hotspots,
        "anomaly_clusters": hotspots,
        "notes": [
            "Earthquake output is anomaly likelihood, not deterministic event prediction.",
            "Signals combine seismic swarm frequency, magnitude clustering, aftershock bursts, and social anomaly chatter.",
            "Severity and confidence remain conservatively capped for operator-facing use.",
        ],
        "last_updated": max((str(item.get("updated_at") or now_utc.isoformat()) for item in forecasts), default=now_utc.isoformat()),
    }
    persist_seismic_anomaly_snapshot(payload)
    return payload
