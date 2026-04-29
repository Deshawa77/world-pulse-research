from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from database.mongo import db
from processing.disaster_storage import persist_disaster_feature_store


def parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def pick_nested(doc: dict[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        current: Any = doc
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found:
            return current
    return default


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def normalize_country(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    if len(raw) in {2, 3}:
        return raw
    return raw[:3]


def _latest_docs(collection_name: str, limit: int) -> list[dict[str, Any]]:
    return list(db[collection_name].find().sort("collected_at", -1).limit(limit))


def _recent_world_state(limit: int = 400) -> list[dict[str, Any]]:
    return list(db["world_state_signals"].find().sort("timestamp_utc", -1).limit(limit))


def _recent_seismic_world_state(limit: int = 2400) -> list[dict[str, Any]]:
    return list(db["world_state_signals"].find({"source": "usgs"}).sort("timestamp_utc", -1).limit(limit))


def _recent_social_signals(limit_per_collection: int = 140) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    reddit_docs = list(db["reddit"].find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("collected_at", -1).limit(limit_per_collection))
    for doc in reddit_docs:
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        text = " ".join(part for part in [str(data.get("title") or ""), str(data.get("text") or "")] if part).strip()
        rows.append(
            {
                "country": normalize_country(doc.get("country")) or "GLB",
                "timestamp": parse_dt(data.get("created_utc") or doc.get("collected_at")) or datetime.now(timezone.utc),
                "text": text,
                "intensity": clamp(safe_float(data.get("score"), 0.0) / 500.0),
            }
        )

    telegram_docs = list(db["telegram_public"].find({}, {"_id": 0, "country": 1, "collected_at": 1, "timestamp": 1, "data": 1}).sort("collected_at", -1).limit(limit_per_collection))
    for doc in telegram_docs:
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        rows.append(
            {
                "country": normalize_country(doc.get("country")) or "GLB",
                "timestamp": parse_dt(doc.get("timestamp") or doc.get("collected_at")) or datetime.now(timezone.utc),
                "text": " ".join(str(v) for v in [data.get("summary"), data.get("topic"), data.get("label")] if v),
                "intensity": clamp(
                    max(
                        safe_float(data.get("social_unrest_score"), 0.0),
                        safe_float(data.get("narrative_velocity_score"), 0.0),
                        safe_float(data.get("public_attention_score"), 0.0),
                    )
                ),
            }
        )

    youtube_docs = list(db["youtube_trends"].find({}, {"_id": 0, "country": 1, "collected_at": 1, "timestamp": 1, "data": 1}).sort("collected_at", -1).limit(limit_per_collection))
    for doc in youtube_docs:
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        rows.append(
            {
                "country": normalize_country(doc.get("country")) or "GLB",
                "timestamp": parse_dt(doc.get("timestamp") or doc.get("collected_at")) or datetime.now(timezone.utc),
                "text": " ".join(str(v) for v in [data.get("headline"), data.get("topic"), data.get("label")] if v),
                "intensity": clamp(max(safe_float(data.get("public_attention_score"), 0.0), safe_float(data.get("narrative_velocity_score"), 0.0))),
            }
        )

    rows.sort(key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows


def _social_signal_score(
    country: str | None,
    now_utc: datetime,
    tokens: tuple[str, ...],
    lookback_hours: int = 96,
) -> tuple[int, float, datetime | None]:
    docs = _recent_social_signals(140)
    cutoff = now_utc - timedelta(hours=lookback_hours)
    count = 0
    max_intensity = 0.0
    latest: datetime | None = None
    for doc in docs:
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = doc.get("timestamp") if isinstance(doc.get("timestamp"), datetime) else parse_dt(doc.get("timestamp"))
        if stamp and stamp < cutoff:
            continue
        text = str(doc.get("text") or "").lower()
        intensity = clamp(safe_float(doc.get("intensity"), 0.0))
        if any(token in text for token in tokens) or (not text and intensity >= 0.72):
            count += 1
            max_intensity = max(max_intensity, intensity)
            if stamp and (latest is None or stamp > latest):
                latest = stamp
    return count, max_intensity, latest


def _seismic_region_key(lat: Any, lon: Any, grid_size: int = 40) -> str | None:
    if lat is None or lon is None:
        return None
    lat_value = safe_float(lat, default=float("nan"))
    lon_value = safe_float(lon, default=float("nan"))
    if lat_value != lat_value or lon_value != lon_value:
        return None
    lat_bucket = int((lat_value + 90.0) // grid_size)
    lon_bucket = int((lon_value + 180.0) // grid_size)
    return f"seismic_{lat_bucket:02d}_{lon_bucket:02d}"

def build_disaster_feature_bundle(country: str | None = None, *, persist: bool = False) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    normalized_country = normalize_country(country) if country else None
    weather_docs = _latest_docs("weather", 260)
    world_state_docs = _recent_world_state(420)
    earthquake_docs = _latest_docs("earthquakes", 2400)

    bundles = [
        _build_flood_features(now_utc, weather_docs, world_state_docs, normalized_country),
        _build_wildfire_features(now_utc, weather_docs, world_state_docs, normalized_country),
        _build_cyclone_features(now_utc, weather_docs, world_state_docs, normalized_country),
        _build_earthquake_features(now_utc, earthquake_docs, normalized_country),
    ]
    if persist:
        persist_disaster_feature_store(bundles, country=normalized_country, context="disaster_feature_builder")
    return bundles


def _build_flood_features(now_utc: datetime, weather_docs: list[dict[str, Any]], world_state_docs: list[dict[str, Any]], country: str | None) -> dict[str, Any]:
    severe_weather_keyword_score = 0.0
    wind_score = 0.0
    cold_wet_score = 0.0
    flood_signal_count = 0
    source_hits = 0
    countries: list[str] = []
    contributors: list[str] = []
    updated_at = now_utc

    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, "country", "data.country", "data_country"))
        if country and doc_country and doc_country != country:
            continue
        text = str(pick_nested(doc, "event", "data.weather", "data_weather", "data.description", default="")).lower()
        wind = safe_float(pick_nested(doc, "wind_speed", "data.wind_speed", "data_wind_speed"))
        temp = safe_float(pick_nested(doc, "temperature", "data.temperature", "data.temp", "data_temperature"))
        stamp = parse_dt(pick_nested(doc, "timestamp", "data_timestamp", "data.date", "collected_at"))
        if stamp:
            updated_at = max(updated_at, stamp)
        if any(token in text for token in ("flood", "heavy rain", "storm", "overflow", "monsoon")):
            severe_weather_keyword_score = max(severe_weather_keyword_score, 1.0)
            contributors.append("severe weather text")
            source_hits += 1
        wind_score = max(wind_score, clamp(wind / 160.0))
        if temp <= 12:
            cold_wet_score = max(cold_wet_score, clamp((12.0 - temp) / 12.0))
        if doc_country:
            countries.append(doc_country)

    satellite_hits = 0
    ocean_hits = 0
    for doc in world_state_docs:
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        category = str(meta.get("category") or "").lower()
        source = str(doc.get("source") or "").lower()
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if stamp and stamp >= now_utc - timedelta(days=5):
            updated_at = max(updated_at, stamp)
        if "flood" in category or "storm" in category:
            flood_signal_count += 1
            contributors.append("world-state flood event")
            source_hits += 1
            if doc_country:
                countries.append(doc_country)
        if source in {"firms", "modis", "viirs"} or "wildfire" in category:
            satellite_hits += 1
        if source in {"noaa_cdo", "eonet", "ocean"} or any(token in category for token in ("cyclone", "hurricane", "typhoon", "storm", "surge")):
            ocean_hits += 1

    social_hits, social_boost, social_ts = _social_signal_score(
        country,
        now_utc,
        ("flood", "flooding", "storm", "overflow", "monsoon", "evacuation"),
        lookback_hours=96,
    )
    if social_hits > 0:
        contributors.append("social flood chatter")
        if social_ts:
            updated_at = max(updated_at, social_ts)

    total_signal_count = flood_signal_count + satellite_hits + ocean_hits + social_hits
    coverage_hits = source_hits + (1 if satellite_hits else 0) + (1 if ocean_hits else 0) + (1 if social_hits else 0)

    return {
        "event_type": "flood",
        "country": country or (max(set(countries), key=countries.count) if countries else "GLB"),
        "lead_time_hours": 24,
        "signal_sources": sorted({"weather_sensors", "satellite_imagery", "ocean_sensors", "social_media_signals"}),
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Increase flood watch coverage for high-rainfall regions and verify river-basin exposure.",
        "updated_at": updated_at.isoformat(),
        "feature_values": {
            "severe_weather_keyword_score": round(max(severe_weather_keyword_score, social_boost), 4),
            "wind_score": round(wind_score, 4),
            "cold_wet_score": round(cold_wet_score, 4),
            "flood_signal_density": round(clamp(total_signal_count / 10.0), 4),
            "source_coverage": round(clamp(coverage_hits / 12.0), 4),
            "recency_score": round(clamp(1.0 - max((now_utc - updated_at).total_seconds(), 0.0) / (72 * 3600)), 4),
        },
    }


def _build_wildfire_features(now_utc: datetime, weather_docs: list[dict[str, Any]], world_state_docs: list[dict[str, Any]], country: str | None) -> dict[str, Any]:
    heat_score = 0.0
    wind_score = 0.0
    smoke_keyword_score = 0.0
    wildfire_signal_count = 0
    dryness_proxy_score = 0.0
    source_hits = 0
    countries: list[str] = []
    contributors: list[str] = []
    updated_at = now_utc

    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, "country", "data.country", "data_country"))
        if country and doc_country and doc_country != country:
            continue
        text = str(pick_nested(doc, "event", "data.weather", "data_weather", "data.description", default="")).lower()
        wind = safe_float(pick_nested(doc, "wind_speed", "data.wind_speed", "data_wind_speed"))
        temp = safe_float(pick_nested(doc, "temperature", "data.temperature", "data.temp", "data_temperature"))
        stamp = parse_dt(pick_nested(doc, "timestamp", "data_timestamp", "data.date", "collected_at"))
        if stamp:
            updated_at = max(updated_at, stamp)
        if temp >= 34:
            heat_score = max(heat_score, clamp((temp - 30.0) / 18.0))
            dryness_proxy_score = max(dryness_proxy_score, clamp((temp - 25.0) / 20.0))
            contributors.append("heat stress")
            source_hits += 1
        if wind >= 30:
            wind_score = max(wind_score, clamp(wind / 120.0))
            contributors.append("wind acceleration")
        if any(token in text for token in ("wildfire", "smoke", "dry", "heatwave")):
            smoke_keyword_score = max(smoke_keyword_score, 1.0)
            contributors.append("wildfire weather text")
            source_hits += 1
        if doc_country:
            countries.append(doc_country)

    satellite_hits = 0
    for doc in world_state_docs:
        source = str(doc.get("source") or "").lower()
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        category = str(meta.get("category") or "").lower()
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if stamp and stamp >= now_utc - timedelta(days=5):
            updated_at = max(updated_at, stamp)
        if source == "firms" or "wildfire" in category:
            wildfire_signal_count += 1
            contributors.append("fire detection signal")
            source_hits += 1
            if doc_country:
                countries.append(doc_country)
        if source in {"firms", "modis", "viirs"} or "wildfire" in category:
            satellite_hits += 1

    social_hits, social_boost, social_ts = _social_signal_score(
        country,
        now_utc,
        ("wildfire", "fire", "smoke", "burn", "evacuation", "heatwave"),
        lookback_hours=96,
    )
    if social_hits > 0:
        contributors.append("social wildfire chatter")
        if social_ts:
            updated_at = max(updated_at, social_ts)

    total_signal_count = wildfire_signal_count + satellite_hits + social_hits
    coverage_hits = source_hits + (1 if satellite_hits else 0) + (1 if social_hits else 0)

    return {
        "event_type": "wildfire",
        "country": country or (max(set(countries), key=countries.count) if countries else "GLB"),
        "lead_time_hours": 18,
        "signal_sources": sorted({"weather_sensors", "satellite_imagery", "social_media_signals"}),
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Prioritize wildfire patrol zones, dry vegetation monitoring, and rapid response readiness.",
        "updated_at": updated_at.isoformat(),
        "feature_values": {
            "heat_score": round(heat_score, 4),
            "wind_score": round(wind_score, 4),
            "smoke_keyword_score": round(max(smoke_keyword_score, social_boost), 4),
            "wildfire_signal_density": round(clamp(total_signal_count / 10.0), 4),
            "dryness_proxy_score": round(dryness_proxy_score, 4),
            "source_coverage": round(clamp(coverage_hits / 12.0), 4),
            "recency_score": round(clamp(1.0 - max((now_utc - updated_at).total_seconds(), 0.0) / (72 * 3600)), 4),
        },
    }


def _build_cyclone_features(now_utc: datetime, weather_docs: list[dict[str, Any]], world_state_docs: list[dict[str, Any]], country: str | None) -> dict[str, Any]:
    storm_keyword_score = 0.0
    wind_score = 0.0
    storm_signal_count = 0
    ocean_proxy_score = 0.0
    pressure_proxy_score = 0.0
    source_hits = 0
    countries: list[str] = []
    contributors: list[str] = []
    updated_at = now_utc

    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, "country", "data.country", "data_country"))
        if country and doc_country and doc_country != country:
            continue
        text = str(pick_nested(doc, "event", "data.weather", "data_weather", "data.description", default="")).lower()
        wind = safe_float(pick_nested(doc, "wind_speed", "data.wind_speed", "data_wind_speed"))
        temp = safe_float(pick_nested(doc, "temperature", "data.temperature", "data.temp", "data_temperature"))
        stamp = parse_dt(pick_nested(doc, "timestamp", "data_timestamp", "data.date", "collected_at"))
        if stamp:
            updated_at = max(updated_at, stamp)
        if wind >= 45:
            wind_score = max(wind_score, clamp(wind / 160.0))
            pressure_proxy_score = max(pressure_proxy_score, clamp(wind / 180.0))
            contributors.append("strong wind field")
            source_hits += 1
        if any(token in text for token in ("cyclone", "hurricane", "typhoon", "tropical storm")):
            storm_keyword_score = max(storm_keyword_score, 1.0)
            ocean_proxy_score = max(ocean_proxy_score, clamp((temp - 24.0) / 12.0))
            contributors.append("cyclone keyword detection")
            source_hits += 1
        if doc_country:
            countries.append(doc_country)

    ocean_hits = 0
    satellite_hits = 0
    for doc in world_state_docs:
        source = str(doc.get("source") or "").lower()
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        category = str(meta.get("category") or "").lower()
        doc_country = normalize_country(doc.get("country"))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if stamp and stamp >= now_utc - timedelta(days=5):
            updated_at = max(updated_at, stamp)
        if "cyclone" in category or "hurricane" in category or "storm" in category or source == "eonet":
            storm_signal_count += 1
            contributors.append("storm track signal")
            source_hits += 1
            if doc_country:
                countries.append(doc_country)
        if source in {"noaa_cdo", "eonet", "ocean"} or any(token in category for token in ("cyclone", "hurricane", "typhoon", "storm", "surge")):
            ocean_hits += 1
            ocean_proxy_score = max(ocean_proxy_score, clamp(safe_float(doc.get("value"), 0.0)))
        if source in {"firms", "modis", "viirs"} or any(token in category for token in ("cyclone", "hurricane", "typhoon", "storm")):
            satellite_hits += 1

    social_hits, social_boost, social_ts = _social_signal_score(
        country,
        now_utc,
        ("cyclone", "hurricane", "typhoon", "storm surge", "landfall", "evacuation"),
        lookback_hours=96,
    )
    if social_hits > 0:
        contributors.append("social storm chatter")
        if social_ts:
            updated_at = max(updated_at, social_ts)

    total_signal_count = storm_signal_count + ocean_hits + satellite_hits + social_hits
    coverage_hits = source_hits + (1 if ocean_hits else 0) + (1 if satellite_hits else 0) + (1 if social_hits else 0)

    return {
        "event_type": "cyclone",
        "country": country or (max(set(countries), key=countries.count) if countries else "GLB"),
        "lead_time_hours": 48,
        "signal_sources": sorted({"weather_sensors", "ocean_sensors", "satellite_imagery", "social_media_signals"}),
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Review coastal readiness, logistics exposure, and evacuation messaging for high-risk zones.",
        "updated_at": updated_at.isoformat(),
        "feature_values": {
            "storm_keyword_score": round(max(storm_keyword_score, social_boost), 4),
            "wind_score": round(wind_score, 4),
            "storm_signal_density": round(clamp(total_signal_count / 10.0), 4),
            "ocean_proxy_score": round(ocean_proxy_score, 4),
            "pressure_proxy_score": round(pressure_proxy_score, 4),
            "source_coverage": round(clamp(coverage_hits / 12.0), 4),
            "recency_score": round(clamp(1.0 - max((now_utc - updated_at).total_seconds(), 0.0) / (72 * 3600)), 4),
        },
    }


def _build_earthquake_features(now_utc: datetime, seismic_docs: list[dict[str, Any]], country: str | None) -> dict[str, Any]:
    seismic_world_docs = _recent_seismic_world_state(2200)
    region_rows: dict[str, list[dict[str, Any]]] = {}

    for doc in seismic_docs:
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if not stamp or stamp < now_utc - timedelta(hours=72):
            continue
        region_key = _seismic_region_key(doc.get("lat"), doc.get("lon"))
        if not region_key:
            continue
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        mag = safe_float(meta.get("mag"), safe_float(doc.get("value"), 0.0) * 8.0)
        region_rows.setdefault(region_key, []).append({
            "ts": stamp,
            "mag": mag,
        })

    for doc in seismic_world_docs:
        stamp = parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if not stamp or stamp < now_utc - timedelta(hours=72):
            continue
        region_key = _seismic_region_key(doc.get("lat"), doc.get("lon"))
        if not region_key:
            continue
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        mag = safe_float(meta.get("mag"), safe_float(doc.get("value"), 0.0) * 8.0)
        region_rows.setdefault(region_key, []).append({
            "ts": stamp,
            "mag": mag,
        })

    dominant_region = "seismic_unknown"
    dominant_rows: list[dict[str, Any]] = []
    best_score = -1.0
    for region_key, rows in region_rows.items():
        weighted_score = sum(max(row["mag"], 0.1) for row in rows)
        if weighted_score > best_score:
            best_score = weighted_score
            dominant_region = region_key
            dominant_rows = rows

    recent_quake_count = 0
    average_magnitude = 0.0
    major_quake_ratio = 0.0
    aftershock_cluster_score = 0.0
    recency_score = 0.0
    contributors: list[str] = []
    updated_at = now_utc
    major_count = 0
    strong_count = 0
    magnitude_sum = 0.0
    max_magnitude = 0.0
    recent_24h_count = 0
    prior_48h_count = 0
    energy_proxy_total = 0.0

    for row in dominant_rows:
        stamp = row["ts"]
        updated_at = max(updated_at, stamp)
        mag = row["mag"]
        if mag <= 0:
            continue
        recent_quake_count += 1
        magnitude_sum += mag
        max_magnitude = max(max_magnitude, mag)
        energy_proxy_total += max(0.0, mag) ** 2
        if stamp >= now_utc - timedelta(hours=24):
            recent_24h_count += 1
        else:
            prior_48h_count += 1
        if mag >= 5.5:
            major_count += 1
            contributors.append("major magnitude concentration")
        if mag >= 4.5:
            strong_count += 1
            contributors.append("strong-event cluster")
        contributors.append("regional seismic sequence")

    social_hits, social_boost, social_ts = _social_signal_score(
        country,
        now_utc,
        ("earthquake", "quake", "tremor", "aftershock", "seismic"),
        lookback_hours=120,
    )

    max_magnitude_score = 0.0
    short_term_acceleration_score = 0.0
    strong_event_density = 0.0
    energy_proxy_score = 0.0
    if recent_quake_count:
        average_magnitude = magnitude_sum / recent_quake_count
        major_quake_ratio = major_count / recent_quake_count
        aftershock_cluster_score = clamp(recent_quake_count / 18.0)
        strong_event_density = clamp(strong_count / 6.0)
        max_magnitude_score = clamp(max(max_magnitude - 4.0, 0.0) / 3.0)
        baseline_rate = prior_48h_count / 2.0
        if baseline_rate <= 0:
            short_term_acceleration_score = clamp(recent_24h_count / 6.0)
        else:
            short_term_acceleration_score = clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
        energy_proxy_score = clamp(energy_proxy_total / 250.0)
        recency_score = clamp(1.0 - max((now_utc - updated_at).total_seconds(), 0.0) / (72 * 3600))
        if max_magnitude >= 5.5:
            contributors.append("high-magnitude precursor")
        if short_term_acceleration_score >= 0.4:
            contributors.append("short-term acceleration")

    if social_hits > 0:
        contributors.append("social seismic chatter")
        recency_score = max(recency_score, social_boost)
        if social_ts:
            updated_at = max(updated_at, social_ts)

    return {
        "event_type": "earthquake",
        "country": country or "GLB",
        "region": dominant_region,
        "lead_time_hours": 12,
        "signal_sources": ["seismic_data", "social_media_signals"],
        "top_contributing_signals": list(dict.fromkeys(contributors))[:6],
        "recommended_action": "Treat this as regional precursor anomaly monitoring, not deterministic prediction, and verify preparedness channels.",
        "updated_at": updated_at.isoformat(),
        "feature_values": {
            "recent_quake_density": round(clamp(recent_quake_count / 18.0), 4),
            "average_magnitude_score": round(clamp(max(average_magnitude - 3.5, 0.0) / 4.0), 4),
            "major_quake_ratio": round(clamp(major_quake_ratio), 4),
            "aftershock_cluster_score": round(aftershock_cluster_score, 4),
            "max_magnitude_score": round(max_magnitude_score, 4),
            "short_term_acceleration_score": round(short_term_acceleration_score, 4),
            "strong_event_density": round(strong_event_density, 4),
            "energy_proxy_score": round(energy_proxy_score, 4),
            "source_coverage": round(clamp((recent_quake_count + social_hits) / 14.0), 4),
            "recency_score": round(recency_score, 4),
        },
    }
