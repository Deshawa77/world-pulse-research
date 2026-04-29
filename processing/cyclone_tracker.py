from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import log1p, sqrt
from typing import Any

from machine_learning.disaster_models import predict_hazard_forecast
from processing.disaster_feature_builder import (
    _latest_docs,
    _recent_social_signals,
    _recent_world_state,
    clamp,
    normalize_country,
    parse_dt,
    pick_nested,
    safe_float,
)
from processing.disaster_hotspot_regions import HOTSPOT_TREND_WINDOWS, build_region_metadata
from processing.disaster_storage import persist_cyclone_tracker_snapshot

TRACK_SOURCE_FAMILIES = ["weather_sensors", "ocean_sensors", "satellite_imagery", "social_media_signals"]
CYCLONE_TOKENS = ("cyclone", "hurricane", "typhoon", "tropical storm", "landfall", "storm surge")


def _extract_coordinate(doc: dict[str, Any]) -> tuple[float, float] | None:
    lat = safe_float(pick_nested(doc, "lat", "latitude", "meta.lat", "meta.latitude", "data.lat", "data.latitude"), default=float("nan"))
    lon = safe_float(pick_nested(doc, "lon", "longitude", "meta.lon", "meta.longitude", "data.lon", "data.longitude"), default=float("nan"))
    if lat != lat or lon != lon:
        return None
    return lat, lon


def _region_key(lat: float, lon: float, grid_size: int = 22) -> str | None:
    if lat != lat or lon != lon:
        return None
    lat_bucket = int((lat + 90.0) // grid_size)
    lon_bucket = int((lon + 180.0) // grid_size)
    return f"cyclone_{lat_bucket:02d}_{lon_bucket:02d}"


def _heading_from_shift(lat_shift: float, lon_shift: float) -> str:
    ns = "north" if lat_shift >= 1.2 else "south" if lat_shift <= -1.2 else "steady"
    ew = "east" if lon_shift >= 1.2 else "west" if lon_shift <= -1.2 else "steady"
    if ns == "steady" and ew == "steady":
        return "stationary"
    if ns == "steady":
        return f"{ew}ward"
    if ew == "steady":
        return f"{ns}ward"
    return f"{ns}-{ew} drift"


def _build_cyclone_window_activity(window_rows: list[dict[str, Any]]) -> float:
    detections = sum(1 for row in window_rows if row.get("detected"))
    wind_peak = max([safe_float(row.get("wind")) for row in window_rows], default=0.0)
    ocean_peak = max([safe_float(row.get("ocean")) for row in window_rows], default=0.0)
    pressure_peak = max([safe_float(row.get("pressure_score")) for row in window_rows], default=0.0)
    trajectory_peak = max([safe_float(row.get("trajectory_score")) for row in window_rows], default=0.0)
    return 0.3 * clamp(detections / 8.0) + 0.26 * clamp(wind_peak / 120.0) + 0.18 * clamp(ocean_peak) + 0.14 * clamp(pressure_peak) + 0.12 * clamp(trajectory_peak)


def _derive_window_series(rows: list[dict[str, Any]], now_utc: datetime, hours: int) -> list[dict[str, Any]]:
    bucket_hours = 6 if hours > 6 else 1
    count = max(2, hours // bucket_hours)
    series: list[dict[str, Any]] = []
    for idx in range(count):
        window_end = now_utc - timedelta(hours=(count - idx - 1) * bucket_hours)
        window_start = window_end - timedelta(hours=bucket_hours)
        window_rows = [row for row in rows if window_start < row["ts"] <= window_end]
        activity = _build_cyclone_window_activity(window_rows)
        wind_peak = max([safe_float(row.get("wind")) for row in window_rows], default=0.0)
        series.append({
            "timestamp": window_end.isoformat(),
            "activity": round(clamp(activity), 3),
            "band": "active" if activity >= 0.55 else "monitor" if activity >= 0.35 else "guarded",
            "event_count": sum(1 for row in window_rows if row.get("detected")),
            "intensity_peak": round(wind_peak, 3),
            "max_wind_speed": round(wind_peak, 3),
        })
    return series


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


def _collect_cyclone_social_signal(country: str | None, now_utc: datetime) -> tuple[int, float, datetime | None]:
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
        if any(token in text for token in CYCLONE_TOKENS) or (not text and intensity >= 0.72):
            count += 1
            max_intensity = max(max_intensity, intensity)
            if stamp and (latest is None or stamp > latest):
                latest = stamp
    return count, max_intensity, latest


def _collect_cyclone_rows(country: str | None, now_utc: datetime) -> dict[str, list[dict[str, Any]]]:
    weather_docs = _latest_docs("weather", 420)
    world_state_docs = _recent_world_state(1200)
    rows_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, "country", "data.country", "data_country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(pick_nested(doc, "timestamp", "data_timestamp", "data.date", "collected_at"))
        coords = _extract_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=120) or not coords:
            continue
        lat, lon = coords
        wind = safe_float(pick_nested(doc, "wind_speed", "data.wind_speed", "data_wind_speed"))
        temp = safe_float(pick_nested(doc, "temperature", "data.temperature", "data.temp", "data_temperature"))
        text_value = str(pick_nested(doc, "event", "data.weather", "data_weather", "data.description", default="")).lower()
        detected = any(token in text_value for token in CYCLONE_TOKENS) or wind >= 45
        if not detected:
            continue
        region = _region_key(lat, lon)
        if not region:
            continue
        rows_by_region[region].append({
            "ts": stamp,
            "lat": lat,
            "lon": lon,
            "wind": max(wind, 45.0 if any(token in text_value for token in CYCLONE_TOKENS) else 0.0),
            "ocean": clamp(max((temp - 26.0) / 8.0, 0.45 if "tropical" in text_value else 0.0)),
            "pressure_score": clamp(max(wind / 120.0, 0.55 if any(token in text_value for token in ("hurricane", "typhoon")) else 0.0)),
            "trajectory_score": clamp(wind / 100.0),
            "source": "weather",
            "country": doc_country,
            "detected": True,
            "text": text_value,
        })

    for doc in world_state_docs:
        source = str(doc.get("source") or "").lower()
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        category = str(meta.get("category") or "").lower()
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        if not any(token in category for token in ("cyclone", "hurricane", "typhoon", "storm", "surge")) and source not in {"eonet", "noaa_cdo"}:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        coords = _extract_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=120) or not coords:
            continue
        lat, lon = coords
        region = _region_key(lat, lon)
        if not region:
            continue
        value = safe_float(doc.get("value"), 0.0)
        rows_by_region[region].append({
            "ts": stamp,
            "lat": lat,
            "lon": lon,
            "wind": max(55.0, value * 100.0),
            "ocean": clamp(max(0.55, safe_float(meta.get("ocean_heat"), value))),
            "pressure_score": clamp(max(0.6, value)),
            "trajectory_score": clamp(max(0.55, safe_float(meta.get("trajectory_score"), 0.0))),
            "source": source or "world_state",
            "country": doc_country,
            "detected": True,
            "text": category,
        })

    return rows_by_region

def _build_cyclone_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    *,
    history_points: list[dict[str, Any]] | None = None,
    social_hits: int = 0,
    social_boost: float = 0.0,
) -> dict[str, Any]:
    sorted_rows = sorted(rows, key=lambda row: row["ts"])
    detection_count = sum(1 for row in sorted_rows if row.get("detected"))
    wind_peak = max([safe_float(row.get("wind")) for row in sorted_rows], default=0.0)
    ocean_peak = max([safe_float(row.get("ocean")) for row in sorted_rows], default=0.0)
    pressure_peak = max([safe_float(row.get("pressure_score")) for row in sorted_rows], default=0.0)
    source_overlap = len({str(row.get("source") or "") for row in sorted_rows if row.get("source")})
    recent_24h_count = sum(1 for row in sorted_rows if row["ts"] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in sorted_rows if row["ts"] < now_utc - timedelta(hours=24))
    baseline_rate = prior_48h_count / 2.0
    acceleration = clamp(recent_24h_count / 8.0) if baseline_rate <= 0 else clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    latest_signal = max([row["ts"] for row in sorted_rows], default=None)
    recency = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (120 * 3600))) if latest_signal else 0.0

    center_lat = sum(float(row["lat"]) for row in sorted_rows) / len(sorted_rows) if sorted_rows else 0.0
    center_lon = sum(float(row["lon"]) for row in sorted_rows) / len(sorted_rows) if sorted_rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard="cyclone")
    history_summary = _history_feature_summary(history_points or [])

    track_points = [{
        "timestamp": row["ts"].isoformat(),
        "lat": round(float(row["lat"]), 3),
        "lon": round(float(row["lon"]), 3),
        "wind": round(safe_float(row.get("wind")), 3),
        "source": str(row.get("source") or ""),
    } for row in sorted_rows[-8:]]
    first_point = sorted_rows[0] if sorted_rows else None
    last_point = sorted_rows[-1] if sorted_rows else None
    lat_shift = float(last_point["lat"] - first_point["lat"]) if first_point and last_point else 0.0
    lon_shift = float(last_point["lon"] - first_point["lon"]) if first_point and last_point else 0.0
    movement_km_proxy = sqrt((lat_shift * 111.0) ** 2 + (lon_shift * 111.0) ** 2)
    movement_score = clamp(movement_km_proxy / 900.0)
    heading = _heading_from_shift(lat_shift, lon_shift)
    trajectory_continuity_score = clamp(len(track_points) / 8.0)
    landfall_proxy_score = clamp(max(ocean_peak, pressure_peak) * max(movement_score, 0.35))
    intensity_outlook_score = clamp(0.34 * clamp(wind_peak / 120.0) + 0.22 * ocean_peak + 0.18 * pressure_peak + 0.14 * acceleration + 0.12 * trajectory_continuity_score)
    lead_time_hours = int(max(18, min(60, round(24 + (movement_score * 24) + (trajectory_continuity_score * 12)))))

    contributors = ["storm track clustering", "wind field intensification", "ocean heat support", "pressure consolidation"]
    if trajectory_continuity_score >= 0.45:
        contributors.append("trajectory continuity")
    if social_hits > 0:
        contributors.append("social storm chatter")

    countries = [str(row.get("country") or "").upper() for row in sorted_rows if row.get("country")]
    return {
        "event_type": "cyclone",
        "country": max(set(countries), key=countries.count) if countries else "GLB",
        "region": region,
        **metadata,
        "center_lat": round(center_lat, 3),
        "center_lon": round(center_lon, 3),
        "lead_time_hours": lead_time_hours,
        "signal_sources": TRACK_SOURCE_FAMILIES,
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Review coastal readiness, logistics staging, and evacuation messaging for basins on the projected storm path.",
        "updated_at": latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        "trajectory_summary": f"{heading}; {len(track_points)} points; {round(movement_km_proxy, 1)} km movement proxy.",
        "track_points": track_points,
        "feature_values": {
            "storm_keyword_score": round(max(clamp(detection_count / 10.0), social_boost), 4),
            "wind_score": round(clamp(wind_peak / 120.0), 4),
            "storm_signal_density": round(clamp((detection_count + social_hits) / 10.0), 4),
            "ocean_proxy_score": round(clamp(ocean_peak), 4),
            "pressure_proxy_score": round(clamp(pressure_peak), 4),
            "source_coverage": round(clamp((source_overlap + (1 if social_hits else 0)) / 4.0), 4),
            "trajectory_continuity_score": round(trajectory_continuity_score, 4),
            "movement_score": round(movement_score, 4),
            "landfall_proxy_score": round(landfall_proxy_score, 4),
            "short_term_acceleration_score": round(acceleration, 4),
            "recency_score": round(recency, 4),
            **history_summary,
        },
        "hotspot_stats": {
            "event_count": detection_count,
            "storm_detection_count": detection_count,
            "max_wind_speed": round(wind_peak, 3),
            "ocean_heat_proxy": round(ocean_peak, 3),
            "pressure_proxy": round(pressure_peak, 3),
            "cross_source_hits": source_overlap,
            "recent_24h_count": recent_24h_count,
            "track_point_count": len(track_points),
            "movement_km_proxy": round(movement_km_proxy, 3),
            "track_heading": heading,
            "intensity_outlook_score": round(intensity_outlook_score, 3),
        },
        "activity_trend": "accelerating" if acceleration >= 0.25 else "steady",
        "trend_points": [row.get("activity") for row in _derive_window_series(sorted_rows, now_utc, 36)],
        "history": {key: _derive_window_series(sorted_rows, now_utc, hours) for key, hours in HOTSPOT_TREND_WINDOWS.items()},
    }


def _calibrate_cyclone_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    env = __import__("os").environ
    cyclone_monitor_threshold = float(env.get("PLANETARY_CYCLONE_MONITOR_THRESHOLD") or 0.33)
    cyclone_active_threshold = float(env.get("PLANETARY_CYCLONE_ACTIVE_THRESHOLD") or 0.5)
    cyclone_critical_threshold = float(env.get("PLANETARY_CYCLONE_CRITICAL_THRESHOLD") or 0.68)
    stats = item.get("hotspot_stats") or {}
    features = item.get("feature_values") or {}
    detection_component = clamp(log1p(safe_float(stats.get("storm_detection_count"))) / log1p(60.0))
    wind_component = clamp(safe_float(features.get("wind_score")))
    ocean_component = clamp(safe_float(features.get("ocean_proxy_score")))
    pressure_component = clamp(safe_float(features.get("pressure_proxy_score")))
    overlap_component = clamp(safe_float(features.get("source_coverage")))
    movement_component = clamp(safe_float(features.get("movement_score")))
    trajectory_component = clamp(safe_float(features.get("trajectory_continuity_score")))
    acceleration_component = clamp(safe_float(features.get("short_term_acceleration_score")))
    recency_component = clamp(safe_float(features.get("recency_score")))
    history_avg_component = clamp(safe_float(features.get("history_avg_activity")))
    history_delta_component = clamp((safe_float(features.get("history_recent_delta")) + 1.0) / 2.0)
    hotspot_score = clamp(0.16 * detection_component + 0.2 * wind_component + 0.14 * ocean_component + 0.11 * pressure_component + 0.1 * overlap_component + 0.09 * movement_component + 0.08 * trajectory_component + 0.05 * acceleration_component + 0.04 * recency_component + 0.02 * history_avg_component + 0.01 * history_delta_component)
    hotspot_confidence = clamp(0.34 + 0.16 * detection_component + 0.14 * wind_component + 0.12 * trajectory_component + 0.1 * recency_component + 0.08 * overlap_component)
    hotspot_band = (
        "critical" if hotspot_score >= cyclone_critical_threshold
        else "active" if hotspot_score >= cyclone_active_threshold
        else "monitor" if hotspot_score >= cyclone_monitor_threshold
        else "guarded"
    )
    return {
        **item,
        "activity_score": round(hotspot_score, 3),
        "hotspot_score": round(hotspot_score, 3),
        "hotspot_confidence": round(hotspot_confidence, 3),
        "hotspot_band": hotspot_band,
        "calibration_adjustments": {
            "thresholds": {
                "monitor": round(cyclone_monitor_threshold, 4),
                "active": round(cyclone_active_threshold, 4),
                "critical": round(cyclone_critical_threshold, 4),
            },
        },
    }


def compute_cyclone_tracker(country: str | None = None, limit: int = 6, history_lookup: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    normalized_country = normalize_country(country) if country else None
    region_rows = _collect_cyclone_rows(normalized_country, now_utc)
    social_hits, social_boost, social_ts = _collect_cyclone_social_signal(normalized_country, now_utc)

    hotspots: list[dict[str, Any]] = []
    for region, rows in region_rows.items():
        bundle = _build_cyclone_bundle(region, rows, now_utc, history_points=(history_lookup or {}).get(region) or [], social_hits=social_hits, social_boost=social_boost)
        scored = _calibrate_cyclone_hotspot_score(predict_hazard_forecast(bundle))
        if social_ts and str(scored.get("updated_at") or "") < social_ts.isoformat():
            scored["updated_at"] = social_ts.isoformat()
        hotspots.append(scored)

    hotspots.sort(key=lambda item: (float(item.get("hotspot_score") or 0.0), safe_float((item.get("hotspot_stats") or {}).get("max_wind_speed")), safe_float((item.get("hotspot_stats") or {}).get("storm_detection_count"))), reverse=True)
    top_hotspots = hotspots[:limit]
    forecasts = [{**item, "regional_hotspots_count": len(top_hotspots)} for item in top_hotspots[:limit]]
    storm_tracks = [{
        "region": item.get("region"),
        "region_name": item.get("region_name"),
        "display_label": item.get("display_label"),
        "latest_timestamp": item.get("updated_at"),
        "lead_time_hours": item.get("lead_time_hours"),
        "track_heading": (item.get("hotspot_stats") or {}).get("track_heading"),
        "movement_km_proxy": (item.get("hotspot_stats") or {}).get("movement_km_proxy"),
        "intensity_outlook_score": (item.get("hotspot_stats") or {}).get("intensity_outlook_score"),
        "track_points": item.get("track_points") or [],
    } for item in top_hotspots[:limit]]

    payload = {
        "generated_at": now_utc.isoformat(),
        "event_type": "cyclone",
        "country": normalized_country or "GLB",
        "source_families": TRACK_SOURCE_FAMILIES,
        "summary": {
            "tracked_regions": len(top_hotspots),
            "social_signal_hits": social_hits,
            "lead_region": top_hotspots[0].get("region_name") if top_hotspots else None,
        },
        "forecasts": forecasts,
        "regional_hotspots": top_hotspots,
        "storm_tracks": storm_tracks,
        "notes": [
            "Cyclone tracker now builds basin-level storm clusters from weather and world-state coordinates.",
            "Output emphasizes trajectory and intensity outlook, not deterministic landfall prediction.",
        ],
        "last_updated": max([str(item.get("updated_at") or now_utc.isoformat()) for item in top_hotspots], default=now_utc.isoformat()),
    }
    persist_cyclone_tracker_snapshot(payload)
    return payload
