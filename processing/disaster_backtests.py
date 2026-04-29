from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from database.mongo import db
from processing.disaster_hotspot_regions import build_region_metadata
from processing.disaster_feature_builder import _seismic_region_key, clamp, normalize_country, parse_dt, pick_nested, safe_float
from processing.disaster_storage import BACKTEST_LATEST_JSON, STREAMING_HISTORY_DIR, load_json_snapshot, persist_disaster_backtest_snapshot

DEFAULT_LEAD_HOURS = {"earthquake": 24, "wildfire": 24, "flood": 24, "cyclone": 48}
ACTIVE_BANDS = {"active", "critical"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


FLOOD_LOOKBACK_HOURS = int(max(6.0, _env_float("PLANETARY_FLOOD_LOOKBACK_HOURS", 18.0)))
CYCLONE_LOOKBACK_HOURS = int(max(12.0, _env_float("PLANETARY_CYCLONE_LOOKBACK_HOURS", 30.0)))
FLOOD_SIGNAL_RAIN_THRESHOLD = _env_float("PLANETARY_FLOOD_SIGNAL_RAIN_THRESHOLD", 28.0)
FLOOD_SIGNAL_WIND_THRESHOLD = _env_float("PLANETARY_FLOOD_SIGNAL_WIND_THRESHOLD", 24.0)
CYCLONE_SIGNAL_WIND_THRESHOLD = _env_float("PLANETARY_CYCLONE_SIGNAL_WIND_THRESHOLD", 38.0)


def _grid_region_key(lat: float, lon: float, prefix: str, grid_size: int) -> str | None:
    if lat != lat or lon != lon:
        return None
    lat_bucket = int((lat + 90.0) // grid_size)
    lon_bucket = int((lon + 180.0) // grid_size)
    return f"{prefix}_{lat_bucket:02d}_{lon_bucket:02d}"


def _extract_coordinate(doc: dict[str, Any]) -> tuple[float, float] | None:
    lat = safe_float(pick_nested(doc, "lat", "latitude", "meta.lat", "meta.latitude", "data.lat", "data.latitude"), default=float("nan"))
    lon = safe_float(pick_nested(doc, "lon", "longitude", "meta.lon", "meta.longitude", "data.lon", "data.longitude"), default=float("nan"))
    if lat != lat or lon != lon:
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        coords = data.get("coordinates") if isinstance(data.get("coordinates"), list) else []
        if len(coords) >= 2:
            lon = safe_float(coords[0], default=float("nan"))
            lat = safe_float(coords[1], default=float("nan"))
    if lat != lat or lon != lon:
        return None
    return lat, lon


def _future_window(captured_at: datetime, hazard: str, lead_time_hours: Any) -> tuple[datetime, datetime]:
    try:
        lead_hours = max(int(lead_time_hours), 1)
    except Exception:
        lead_hours = DEFAULT_LEAD_HOURS.get(hazard, 24)
    lookback_hours = 0
    if hazard == "flood":
        lookback_hours = FLOOD_LOOKBACK_HOURS
    elif hazard == "cyclone":
        lookback_hours = CYCLONE_LOOKBACK_HOURS
    return captured_at - timedelta(hours=lookback_hours), captured_at + timedelta(hours=lead_hours)


def _signal_region_for_hazard(hazard: str, doc: dict[str, Any]) -> str | None:
    coords = _extract_coordinate(doc)
    if not coords:
        return None
    lat, lon = coords
    if hazard == "earthquake":
        return _seismic_region_key(lat, lon)
    if hazard == "wildfire":
        return _grid_region_key(lat, lon, "wildfire", 20)
    if hazard == "flood":
        return _grid_region_key(lat, lon, "flood", 18)
    if hazard == "cyclone":
        return _grid_region_key(lat, lon, "cyclone", 22)
    return None


def _candidate_regions_for_hazard(hazard: str, doc: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    region = _signal_region_for_hazard(hazard, doc)
    if region:
        candidates.add(region)
    for key in ("region", "region_name", "region_label", "display_label"):
        value = str(pick_nested(doc, key, f"data.{key}") or "").strip()
        if value:
            candidates.add(value)
    coords = _extract_coordinate(doc)
    if coords:
        metadata = build_region_metadata(coords[0], coords[1], hazard=hazard)
        for key in ("region_name", "region_label", "display_label"):
            value = str(metadata.get(key) or "").strip()
            if value:
                candidates.add(value)
    country = normalize_country(pick_nested(doc, "country", "data.country", "data_country"))
    if country:
        candidates.add(country)
    return {item for item in candidates if item}


def _iter_streaming_hotspot_signal_docs(hazard: str, max_runs: int = 240) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history_paths = sorted(STREAMING_HISTORY_DIR.glob("*.json"))[-max_runs:]
    for path in history_paths:
        snapshot = load_json_snapshot(path)
        if not snapshot:
            continue
        payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
        grouped = payload.get("regional_hotspots") if isinstance(payload.get("regional_hotspots"), dict) else {}
        hazard_rows = grouped.get(hazard) if isinstance(grouped, dict) else None
        if not isinstance(hazard_rows, list):
            continue
        fallback_timestamp = snapshot.get("captured_at") or payload.get("generated_at") or payload.get("last_updated")
        for row in hazard_rows:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "source": f"disaster_stream_{hazard}",
                    "timestamp": row.get("updated_at") or fallback_timestamp,
                    "lat": row.get("center_lat"),
                    "lon": row.get("center_lon"),
                    "country": row.get("country"),
                    "meta": {"category": hazard},
                    "data": {
                        "event": hazard,
                        "region": row.get("region"),
                        "region_name": row.get("region_name"),
                        "region_label": row.get("region_label"),
                        "display_label": row.get("display_label"),
                    },
                }
            )
    return rows


def _iter_candidate_signals(hazard: str) -> list[dict[str, Any]]:
    if hazard == "earthquake":
        rows = list(db["world_state_signals"].find({"source": "usgs"}, {"_id": 0, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "meta": 1, "value": 1}).sort("timestamp_utc", 1).limit(60000))
        extra = list(db["earthquakes"].find({}, {"_id": 0, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "data": 1, "meta": 1}).sort("collected_at", 1).limit(60000))
        return rows + extra
    if hazard == "wildfire":
        return list(db["world_state_signals"].find({}, {"_id": 0, "source": 1, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "meta": 1, "value": 1}).sort("timestamp_utc", 1).limit(80000))
    if hazard == "flood":
        weather_rows = list(db["weather"].find({}, {"_id": 0, "timestamp": 1, "collected_at": 1, "country": 1, "data": 1, "lat": 1, "lon": 1}).sort("collected_at", 1).limit(20000))
        world_state_rows = list(db["world_state_signals"].find({}, {"_id": 0, "source": 1, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "meta": 1, "value": 1}).sort("timestamp_utc", 1).limit(80000))
        return weather_rows + world_state_rows + _iter_streaming_hotspot_signal_docs(hazard)
    if hazard == "cyclone":
        weather_rows = list(db["weather"].find({}, {"_id": 0, "timestamp": 1, "collected_at": 1, "country": 1, "data": 1, "lat": 1, "lon": 1}).sort("collected_at", 1).limit(20000))
        world_state_rows = list(db["world_state_signals"].find({}, {"_id": 0, "source": 1, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "meta": 1, "value": 1}).sort("timestamp_utc", 1).limit(80000))
        return weather_rows + world_state_rows + _iter_streaming_hotspot_signal_docs(hazard)
    weather_rows = list(db["weather"].find({}, {"_id": 0, "timestamp": 1, "collected_at": 1, "country": 1, "data": 1, "lat": 1, "lon": 1}).sort("collected_at", 1).limit(20000))
    world_state_rows = list(db["world_state_signals"].find({}, {"_id": 0, "source": 1, "timestamp_utc": 1, "timestamp": 1, "lat": 1, "lon": 1, "meta": 1, "value": 1}).sort("timestamp_utc", 1).limit(80000))
    return weather_rows + world_state_rows


def _signal_matches_hazard(hazard: str, doc: dict[str, Any]) -> bool:
    source = str(doc.get("source") or "").lower()
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    category = str(meta.get("category") or "").lower()
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    weather_text = " ".join(
        str(value or "")
        for value in [data.get("weather"), data.get("description"), data.get("event")]
        if value
    ).lower()
    if hazard == "earthquake":
        mag = safe_float(meta.get("mag"), safe_float(data.get("mag"), safe_float(doc.get("value"), 0.0) * 8.0))
        return mag >= 3.5
    if hazard == "wildfire":
        return source == "firms" or "wildfire" in category or "fire" in category
    if hazard == "flood":
        rain = safe_float(pick_nested(doc, "data.rain.1h", "data.rainfall", "data.precipitation", "precipitation", "rainfall", "value"), 0.0)
        wind = safe_float(pick_nested(doc, "data.wind_speed", "wind_speed", "data_wind_speed", "meta.wind_speed"), 0.0)
        return (
            "flood" in category
            or any(token in weather_text for token in ("flood", "heavy rain", "storm", "overflow", "monsoon", "rain"))
            or rain >= FLOOD_SIGNAL_RAIN_THRESHOLD
            or wind >= FLOOD_SIGNAL_WIND_THRESHOLD
        )
    wind = safe_float(pick_nested(doc, "data.wind_speed", "wind_speed", "data_wind_speed", "meta.wind_speed"), 0.0)
    return (
        any(token in category for token in ("cyclone", "hurricane", "typhoon", "storm", "surge"))
        or any(token in weather_text for token in ("storm", "cyclone", "hurricane", "typhoon", "tropical storm", "landfall"))
        or wind >= CYCLONE_SIGNAL_WIND_THRESHOLD
    )


def _signal_timestamp(doc: dict[str, Any]) -> datetime | None:
    return parse_dt(doc.get("timestamp_utc") or doc.get("timestamp") or doc.get("collected_at") or pick_nested(doc, "data.time", "data_timestamp"))


def _evaluate_hazard(hazard: str, docs: list[dict[str, Any]], signal_docs: list[dict[str, Any]], cutoff: datetime) -> dict[str, Any]:
    evaluated = 0
    matched = 0
    false_positives = 0
    confidences: list[float] = []
    lead_times: list[float] = []
    region_hits: dict[str, int] = defaultdict(int)
    region_misses: dict[str, int] = defaultdict(int)

    filtered_signals = []
    for signal in signal_docs:
        if not _signal_matches_hazard(hazard, signal):
            continue
        stamp = _signal_timestamp(signal)
        regions = _candidate_regions_for_hazard(hazard, signal)
        if not stamp or not regions:
            continue
        filtered_signals.append((stamp, regions, str(signal.get("source") or "")))

    for row in docs:
        captured = parse_dt(row.get("captured_at"))
        if not captured or captured < cutoff:
            continue
        if str(row.get("hotspot_band") or "").lower() not in ACTIVE_BANDS:
            continue
        row_candidates = {
            str(row.get("region") or "").strip(),
            str(row.get("region_name") or "").strip(),
            str(row.get("display_label") or "").strip(),
            str(row.get("country") or "").strip(),
        }
        row_candidates = {item for item in row_candidates if item}
        if not row_candidates:
            continue
        region = next(iter(row_candidates))
        evaluated += 1
        confidences.append(safe_float(row.get("confidence")))
        lead_times.append(max(safe_float(row.get("lead_time_hours"), DEFAULT_LEAD_HOURS.get(hazard, 24)), 1.0))
        window_start, window_end = _future_window(captured, hazard, row.get("lead_time_hours"))
        found = any(
            bool(row_candidates.intersection(signal_regions))
            and (
                (captured < stamp <= window_end)
                if signal_source.startswith("disaster_stream_")
                else (window_start < stamp <= window_end)
            )
            for stamp, signal_regions, signal_source in filtered_signals
        )
        if found:
            matched += 1
            region_hits[region] += 1
        else:
            false_positives += 1
            region_misses[region] += 1

    precision = round(matched / evaluated, 4) if evaluated else 0.0
    false_positive_rate = round(false_positives / evaluated, 4) if evaluated else 0.0
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    avg_lead = round(sum(lead_times) / len(lead_times), 2) if lead_times else float(DEFAULT_LEAD_HOURS.get(hazard, 24))
    return {
        "hazard": hazard,
        "evaluated_alerts": evaluated,
        "matched_follow_on_events": matched,
        "false_positives": false_positives,
        "precision_proxy": precision,
        "false_positive_rate": false_positive_rate,
        "avg_confidence": avg_confidence,
        "avg_lead_time_hours": avg_lead,
        "top_true_positive_regions": dict(sorted(region_hits.items(), key=lambda item: item[1], reverse=True)[:8]),
        "top_false_positive_regions": dict(sorted(region_misses.items(), key=lambda item: item[1], reverse=True)[:8]),
    }


def run_disaster_backtests(days: int = 30, persist: bool = True) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=max(days, 1))
    history_docs = list(db["hotspot_history"].find({"captured_at": {"$gte": cutoff.isoformat()}}, {"_id": 0}).sort("captured_at", 1).limit(150000))
    by_hazard: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history_docs:
        hazard = str(row.get("hazard") or row.get("event_type") or "").strip().lower()
        if hazard in {"earthquake", "wildfire", "flood", "cyclone"}:
            by_hazard[hazard].append(row)

    hazard_results: dict[str, Any] = {}
    total_evaluated = 0
    total_matched = 0
    total_false_positives = 0
    weighted_confidence_numerator = 0.0

    for hazard in ["earthquake", "wildfire", "flood", "cyclone"]:
        result = _evaluate_hazard(hazard, by_hazard.get(hazard, []), _iter_candidate_signals(hazard), cutoff)
        hazard_results[hazard] = result
        total_evaluated += int(result["evaluated_alerts"])
        total_matched += int(result["matched_follow_on_events"])
        total_false_positives += int(result["false_positives"])
        weighted_confidence_numerator += float(result["avg_confidence"]) * int(result["evaluated_alerts"])

    payload = {
        "generated_at": now_utc.isoformat(),
        "run_id": f"disaster_backtest_{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
        "window_days": int(max(days, 1)),
        "status": "ok",
        "hazards": hazard_results,
        "overall": {
            "evaluated_alerts": total_evaluated,
            "matched_follow_on_events": total_matched,
            "false_positives": total_false_positives,
            "precision_proxy": round(total_matched / total_evaluated, 4) if total_evaluated else 0.0,
            "false_positive_rate": round(total_false_positives / total_evaluated, 4) if total_evaluated else 0.0,
            "weighted_avg_confidence": round(weighted_confidence_numerator / total_evaluated, 4) if total_evaluated else 0.0,
        },
        "thresholds": {
            "flood": {
                "lookback_hours": FLOOD_LOOKBACK_HOURS,
                "rain_threshold": FLOOD_SIGNAL_RAIN_THRESHOLD,
                "wind_threshold": FLOOD_SIGNAL_WIND_THRESHOLD,
            },
            "cyclone": {
                "lookback_hours": CYCLONE_LOOKBACK_HOURS,
                "wind_threshold": CYCLONE_SIGNAL_WIND_THRESHOLD,
            },
        },
    }
    if persist:
        persist_disaster_backtest_snapshot(payload)
    return payload


def latest_disaster_backtest() -> dict[str, Any]:
    payload = load_json_snapshot(BACKTEST_LATEST_JSON) or {
        "generated_at": None,
        "status": "missing",
        "window_days": 0,
        "hazards": {},
        "thresholds": {
            "flood": {
                "lookback_hours": FLOOD_LOOKBACK_HOURS,
                "rain_threshold": FLOOD_SIGNAL_RAIN_THRESHOLD,
                "wind_threshold": FLOOD_SIGNAL_WIND_THRESHOLD,
            },
            "cyclone": {
                "lookback_hours": CYCLONE_LOOKBACK_HOURS,
                "wind_threshold": CYCLONE_SIGNAL_WIND_THRESHOLD,
            },
        },
        "overall": {
            "evaluated_alerts": 0,
            "matched_follow_on_events": 0,
            "false_positives": 0,
            "precision_proxy": 0.0,
            "false_positive_rate": 0.0,
            "weighted_avg_confidence": 0.0,
        },
    }
    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    flood = thresholds.get("flood") if isinstance(thresholds.get("flood"), dict) else {}
    cyclone = thresholds.get("cyclone") if isinstance(thresholds.get("cyclone"), dict) else {}
    payload["thresholds"] = {
        "flood": {
            "lookback_hours": flood.get("lookback_hours", FLOOD_LOOKBACK_HOURS),
            "rain_threshold": flood.get("rain_threshold", FLOOD_SIGNAL_RAIN_THRESHOLD),
            "wind_threshold": flood.get("wind_threshold", FLOOD_SIGNAL_WIND_THRESHOLD),
        },
        "cyclone": {
            "lookback_hours": cyclone.get("lookback_hours", CYCLONE_LOOKBACK_HOURS),
            "wind_threshold": cyclone.get("wind_threshold", CYCLONE_SIGNAL_WIND_THRESHOLD),
        },
    }
    return payload
