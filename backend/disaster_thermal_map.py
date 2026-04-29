from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from math import cos, radians, sqrt
from pathlib import Path
from typing import Any

import pandas as pd

from collectors.weather import TOP_100_CITIES
from database.mongo import db
from processing.disaster_feature_builder import clamp, safe_float

ROOT = Path(__file__).resolve().parents[1]
COUNTRY_FEATURES_PATH = ROOT / "data" / "country_features.parquet"

CITY_TO_COUNTRY: dict[str, str] = {
    "New York": "USA",
    "Los Angeles": "USA",
    "Chicago": "USA",
    "Houston": "USA",
    "Toronto": "CAN",
    "Vancouver": "CAN",
    "Mexico City": "MEX",
    "Montreal": "CAN",
    "Miami": "USA",
    "San Francisco": "USA",
    "São Paulo": "BRA",
    "Rio de Janeiro": "BRA",
    "Buenos Aires": "ARG",
    "Lima": "PER",
    "Bogotá": "COL",
    "Santiago": "CHL",
    "Caracas": "VEN",
    "Quito": "ECU",
    "La Paz": "BOL",
    "Montevideo": "URY",
    "London": "GBR",
    "Paris": "FRA",
    "Berlin": "DEU",
    "Madrid": "ESP",
    "Rome": "ITA",
    "Amsterdam": "NLD",
    "Brussels": "BEL",
    "Vienna": "AUT",
    "Prague": "CZE",
    "Warsaw": "POL",
    "Budapest": "HUN",
    "Stockholm": "SWE",
    "Oslo": "NOR",
    "Copenhagen": "DNK",
    "Helsinki": "FIN",
    "Athens": "GRC",
    "Lisbon": "PRT",
    "Dublin": "IRL",
    "Zurich": "CHE",
    "Moscow": "RUS",
    "Cairo": "EGY",
    "Lagos": "NGA",
    "Johannesburg": "ZAF",
    "Cape Town": "ZAF",
    "Nairobi": "KEN",
    "Addis Ababa": "ETH",
    "Accra": "GHA",
    "Casablanca": "MAR",
    "Algiers": "DZA",
    "Tunis": "TUN",
    "Dubai": "ARE",
    "Abu Dhabi": "ARE",
    "Doha": "QAT",
    "Riyadh": "SAU",
    "Jeddah": "SAU",
    "Kuwait City": "KWT",
    "Manama": "BHR",
    "Muscat": "OMN",
    "Tehran": "IRN",
    "Jerusalem": "ISR",
    "Delhi": "IND",
    "Mumbai": "IND",
    "Bangalore": "IND",
    "Chennai": "IND",
    "Kolkata": "IND",
    "Karachi": "PAK",
    "Lahore": "PAK",
    "Dhaka": "BGD",
    "Colombo": "LKA",
    "Kathmandu": "NPL",
    "Tokyo": "JPN",
    "Osaka": "JPN",
    "Seoul": "KOR",
    "Beijing": "CHN",
    "Shanghai": "CHN",
    "Hong Kong": "HKG",
    "Taipei": "TWN",
    "Bangkok": "THA",
    "Singapore": "SGP",
    "Kuala Lumpur": "MYS",
    "Jakarta": "IDN",
    "Manila": "PHL",
    "Hanoi": "VNM",
    "Ho Chi Minh City": "VNM",
    "Phnom Penh": "KHM",
    "Yangon": "MMR",
    "Sydney": "AUS",
    "Melbourne": "AUS",
    "Brisbane": "AUS",
    "Perth": "AUS",
    "Auckland": "NZL",
    "Wellington": "NZL",
}

CITY_COORDS = {
    str(row.get("name") or ""): {
        "lat": float(row.get("lat") or 0.0),
        "lon": float(row.get("lon") or 0.0),
    }
    for row in TOP_100_CITIES
    if str(row.get("name") or "").strip()
}

THERMAL_COLORSCALE = [
    [0.0, "#041126"],
    [0.12, "#0b2e63"],
    [0.26, "#0c7bdc"],
    [0.42, "#1fd3e1"],
    [0.58, "#8ff35a"],
    [0.74, "#ffe45c"],
    [0.88, "#ff7d2f"],
    [1.0, "#f31245"],
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _country_feature_rows() -> dict[str, dict[str, Any]]:
    if not COUNTRY_FEATURES_PATH.exists():
        return {}
    frame = pd.read_parquet(COUNTRY_FEATURES_PATH)
    if frame.empty:
        return {}
    frame = frame.sort_values("timestamp")
    latest = frame.groupby("country", as_index=False).tail(1)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in latest.iterrows():
        code = str(row.get("country") or "").strip().upper()
        if code:
            rows[code] = row.to_dict()
    return rows


def _distance_units(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lon_scale = max(cos(radians((lat_a + lat_b) / 2.0)), 0.35)
    return sqrt((lat_a - lat_b) ** 2 + ((lon_a - lon_b) * lon_scale) ** 2)


def _hazard_heat_boost(hazard: str) -> float:
    if hazard == "wildfire":
        return 8.0
    if hazard == "cyclone":
        return 4.0
    if hazard == "flood":
        return 2.5
    return 1.5


def _load_latest_weather_samples(limit: int = 800) -> list[dict[str, Any]]:
    docs = list(db["weather"].find({}, {"_id": 0}).sort("collected_at", -1).limit(max(limit, 1)))
    latest_by_city: dict[str, dict[str, Any]] = {}
    for doc in docs:
        city = str(doc.get("data_city") or "").strip()
        if not city or city in latest_by_city:
            continue
        coords = CITY_COORDS.get(city)
        country = str(doc.get("data_country") or doc.get("country") or CITY_TO_COUNTRY.get(city) or "").strip().upper()
        if not coords or not country:
            continue
        latest_by_city[city] = {
            "city": city,
            "country": country,
            "lat": float(coords["lat"]),
            "lon": float(coords["lon"]),
            "temperature_c": safe_float(doc.get("data_temperature"), 18.0),
            "wind_kph": safe_float(doc.get("data_wind_speed"), 0.0),
            "humidity_pct": safe_float(doc.get("data_humidity"), 0.0),
            "description": str(doc.get("data_weather") or ""),
            "sample_type": "observed",
        }
    return list(latest_by_city.values())


def _flatten_hotspots(forecast_payload: dict[str, Any] | None, hazard: str | None = None) -> list[dict[str, Any]]:
    hotspot_groups = ((forecast_payload or {}).get("regional_hotspots") or {}) if isinstance(forecast_payload, dict) else {}
    items: list[dict[str, Any]] = []
    for hazard_name, rows in hotspot_groups.items():
        if hazard and hazard_name != hazard:
            continue
        for row in rows or []:
            lat = safe_float(row.get("center_lat"), default=float("nan"))
            lon = safe_float(row.get("center_lon"), default=float("nan"))
            if lat != lat or lon != lon:
                continue
            items.append(
                {
                    "hazard": str(hazard_name),
                    "lat": lat,
                    "lon": lon,
                    "score": safe_float(row.get("hotspot_score") or row.get("activity_score"), 0.0),
                    "confidence": safe_float(row.get("hotspot_confidence") or row.get("confidence"), 0.0),
                    "lead_time_hours": int(row.get("lead_time_hours") or 0),
                    "signal_sources": [str(source) for source in (row.get("signal_sources") or []) if str(source or "").strip()],
                }
            )
    return items


def _build_country_summaries(weather_samples: list[dict[str, Any]], hazard_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_rows = _country_feature_rows()
    country_weather: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in weather_samples:
        country_weather[str(sample.get("country") or "GLB")].append(sample)

    summaries: list[dict[str, Any]] = []
    for country, feature_row in feature_rows.items():
        samples = country_weather.get(country, [])
        avg_temp = sum(safe_float(item.get("temperature_c"), 18.0) for item in samples) / len(samples) if samples else 18.0
        temp_norm = clamp((avg_temp + 10.0) / 55.0)
        risk_norm = clamp(safe_float(feature_row.get("global_risk_score"), 0.0) / 100.0)
        weather_norm = clamp(safe_float(feature_row.get("weather_stress"), safe_float(feature_row.get("weather_anomaly"), 0.0)))
        country_hotspots = [item for item in hazard_points if str(item.get("country") or "") == country]
        hazard_score = max([safe_float(item.get("score"), 0.0) for item in country_hotspots], default=0.0)
        thermal_index = clamp((temp_norm * 0.48) + (risk_norm * 0.34) + (weather_norm * 0.08) + (hazard_score * 0.1))
        center_lat = sum(float(item.get("lat") or 0.0) for item in samples) / len(samples) if samples else None
        center_lon = sum(float(item.get("lon") or 0.0) for item in samples) / len(samples) if samples else None
        summaries.append(
            {
                "country": country,
                "country_name": str(feature_row.get("country_name") or country),
                "avg_temperature_c": round(avg_temp, 2),
                "thermal_index": round(thermal_index, 3),
                "risk_score": round(safe_float(feature_row.get("global_risk_score"), 0.0), 2),
                "weather_stress": round(safe_float(feature_row.get("weather_stress"), 0.0), 3),
                "source_confidence": round(safe_float(feature_row.get("source_confidence"), 0.0), 3),
                "sample_count": len(samples),
                "center_lat": round(center_lat, 3) if center_lat is not None else None,
                "center_lon": round(center_lon, 3) if center_lon is not None else None,
            }
        )
    summaries.sort(key=lambda item: (float(item.get("thermal_index") or 0.0), float(item.get("risk_score") or 0.0)), reverse=True)
    return summaries


def _estimate_temperature(lat: float, risk_score: float, weather_stress: float) -> float:
    latitude_baseline = 31.0 - (abs(lat) * 0.32)
    return round(latitude_baseline + (risk_score * 0.06) + (weather_stress * 4.0), 2)


def _synthetic_country_sample(country: str, focus_lat: float | None, focus_lon: float | None) -> dict[str, Any]:
    features = _country_feature_rows().get(country, {})
    lat = float(focus_lat if focus_lat is not None else 12.0)
    lon = float(focus_lon if focus_lon is not None else 12.0)
    risk_score = safe_float(features.get("global_risk_score"), 25.0)
    weather_stress = safe_float(features.get("weather_stress"), 0.15)
    return {
        "city": str(features.get("country_name") or country),
        "country": country,
        "lat": lat,
        "lon": lon,
        "temperature_c": _estimate_temperature(lat, risk_score, weather_stress),
        "wind_kph": round(12.0 + (risk_score * 0.18), 2),
        "humidity_pct": round(48.0 + (weather_stress * 18.0), 2),
        "description": "modeled thermal sector",
        "sample_type": "modeled",
    }


def _kernel_offsets(country_mode: bool) -> list[tuple[int, int, float]]:
    if country_mode:
        offsets = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                distance = abs(dx) + abs(dy)
                weight = max(0.18, 1.0 - (distance * 0.16))
                offsets.append((dx, dy, weight))
        return offsets
    return [
        (-1, -1, 0.42),
        (-1, 0, 0.58),
        (-1, 1, 0.42),
        (0, -1, 0.58),
        (0, 0, 1.0),
        (0, 1, 0.58),
        (1, -1, 0.42),
        (1, 0, 0.58),
        (1, 1, 0.42),
    ]


def _nearest_hazard(lat: float, lon: float, hazards: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1.0
    for item in hazards:
        distance = _distance_units(lat, lon, safe_float(item.get("lat"), 0.0), safe_float(item.get("lon"), 0.0))
        reach = 20.0 if str(item.get("hazard") or "") in {"flood", "cyclone"} else 14.0
        influence = clamp(1.0 - (distance / reach)) * safe_float(item.get("score"), 0.0)
        if influence > best_score:
            best_score = influence
            best = {**item, "influence": influence}
    return best


def build_disaster_thermal_map(
    forecast_payload: dict[str, Any] | None,
    *,
    country: str | None = None,
    hazard: str | None = None,
    focus_lat: float | None = None,
    focus_lon: float | None = None,
) -> dict[str, Any]:
    weather_samples = _load_latest_weather_samples()
    hazard_points = _flatten_hotspots(forecast_payload, hazard=hazard)
    country_summaries = _build_country_summaries(weather_samples, hazard_points)
    selected_country = str(country or "").strip().upper() or None
    country_mode = bool(selected_country)

    if selected_country:
        samples = [item for item in weather_samples if str(item.get("country") or "") == selected_country]
        if not samples:
            samples = [_synthetic_country_sample(selected_country, focus_lat, focus_lon)]
    else:
        samples = weather_samples

    feature_rows = _country_feature_rows()
    offsets = _kernel_offsets(country_mode)
    step = 1.8 if country_mode else 4.8
    precision = 0.45 if country_mode else 1.2
    cell_rollup: dict[str, dict[str, Any]] = {}

    for sample in samples:
        base_country = str(sample.get("country") or "GLB")
        feature_row = feature_rows.get(base_country, {})
        risk_score = safe_float(feature_row.get("global_risk_score"), 20.0)
        weather_stress = safe_float(feature_row.get("weather_stress"), 0.0)
        base_temp = safe_float(sample.get("temperature_c"), _estimate_temperature(safe_float(sample.get("lat"), 0.0), risk_score, weather_stress))
        base_wind = safe_float(sample.get("wind_kph"), 0.0)
        base_humidity = safe_float(sample.get("humidity_pct"), 0.0)
        lat = safe_float(sample.get("lat"), 0.0)
        lon = safe_float(sample.get("lon"), 0.0)
        nearby_hazards = [item for item in hazard_points if not country_mode or _distance_units(lat, lon, safe_float(item.get("lat"), 0.0), safe_float(item.get("lon"), 0.0)) <= 22.0]

        for dx, dy, weight in offsets:
            cell_lat = lat + (dx * step)
            cell_lon = lon + (dy * step)
            nearest = _nearest_hazard(cell_lat, cell_lon, nearby_hazards)
            hazard_pressure = safe_float((nearest or {}).get("influence"), 0.0)
            hazard_name = str((nearest or {}).get("hazard") or hazard or "thermal")
            hazard_confidence = safe_float((nearest or {}).get("confidence"), 0.0)
            hazard_lead = int((nearest or {}).get("lead_time_hours") or 0)
            hazard_sources = [str(source) for source in ((nearest or {}).get("signal_sources") or []) if str(source or "").strip()]
            adjusted_temp = base_temp - ((abs(dx) + abs(dy)) * (0.9 if country_mode else 1.4)) + (_hazard_heat_boost(hazard_name) * hazard_pressure)
            temp_norm = clamp((adjusted_temp + 10.0) / 55.0)
            thermal_index = clamp((temp_norm * 0.7) + (hazard_pressure * 0.3))
            key_lat = round(cell_lat / precision) * precision
            key_lon = round(cell_lon / precision) * precision
            key = f"{base_country}:{round(key_lat, 3)}:{round(key_lon, 3)}"
            bucket = cell_rollup.setdefault(
                key,
                {
                    "country": base_country,
                    "lat": key_lat,
                    "lon": key_lon,
                    "temperature_sum": 0.0,
                    "thermal_sum": 0.0,
                    "hazard_sum": 0.0,
                    "wind_sum": 0.0,
                    "humidity_sum": 0.0,
                    "confidence_sum": 0.0,
                    "risk_score": risk_score,
                    "weather_stress": weather_stress,
                    "lead_time_hours": 0,
                    "sample_weight": 0.0,
                    "sample_types": set(),
                    "signal_sources": set(),
                    "active_hazard": hazard_name,
                    "city_anchor": str(sample.get("city") or ""),
                },
            )
            bucket["temperature_sum"] += adjusted_temp * weight
            bucket["thermal_sum"] += thermal_index * weight
            bucket["hazard_sum"] += hazard_pressure * weight
            bucket["wind_sum"] += base_wind * weight
            bucket["humidity_sum"] += base_humidity * weight
            bucket["confidence_sum"] += max(0.52, hazard_confidence) * weight
            bucket["sample_weight"] += weight
            bucket["sample_types"].add(str(sample.get("sample_type") or "observed"))
            for source in hazard_sources or ["weather_sensors"]:
                bucket["signal_sources"].add(source)
            if hazard_pressure >= safe_float(bucket.get("hazard_sum"), 0.0):
                bucket["active_hazard"] = hazard_name
                bucket["lead_time_hours"] = max(int(bucket.get("lead_time_hours") or 0), hazard_lead)

    cells: list[dict[str, Any]] = []
    sorted_buckets = sorted(cell_rollup.values(), key=lambda item: safe_float(item.get("thermal_sum"), 0.0), reverse=True)
    for index, bucket in enumerate(sorted_buckets, start=1):
        weight = max(safe_float(bucket.get("sample_weight"), 1.0), 0.01)
        avg_temp = safe_float(bucket.get("temperature_sum"), 0.0) / weight
        thermal_index = clamp(safe_float(bucket.get("thermal_sum"), 0.0) / weight)
        hazard_pressure = clamp(safe_float(bucket.get("hazard_sum"), 0.0) / weight)
        cells.append(
            {
                "cell_id": f"{bucket['country']}-cell-{index:03d}",
                "country": bucket["country"],
                "lat": round(safe_float(bucket.get("lat"), 0.0), 3),
                "lon": round(safe_float(bucket.get("lon"), 0.0), 3),
                "sector_label": f"Sector {index:02d}",
                "district_label": f"Sector {index:02d}",
                "temperature_c": round(avg_temp, 2),
                "thermal_index": round(thermal_index, 3),
                "hazard_pressure": round(hazard_pressure, 3),
                "confidence": round(clamp(safe_float(bucket.get("confidence_sum"), 0.0) / weight), 3),
                "risk_score": round(safe_float(bucket.get("risk_score"), 0.0), 2),
                "weather_stress": round(safe_float(bucket.get("weather_stress"), 0.0), 3),
                "lead_time_hours": int(bucket.get("lead_time_hours") or 0),
                "wind_kph": round(safe_float(bucket.get("wind_sum"), 0.0) / weight, 2),
                "humidity_pct": round(safe_float(bucket.get("humidity_sum"), 0.0) / weight, 2),
                "active_hazard": str(bucket.get("active_hazard") or "thermal"),
                "signal_sources": sorted(str(source) for source in bucket.get("signal_sources") or []),
                "sample_type": "observed" if "observed" in (bucket.get("sample_types") or set()) else "modeled",
                "city_anchor": str(bucket.get("city_anchor") or ""),
            }
        )

    limit = 60 if country_mode else 260
    cells = cells[:limit]
    if selected_country:
        cells = [item for item in cells if item.get("country") == selected_country][:60]

    focus_cells = cells if selected_country else sorted(cells, key=lambda item: float(item.get("thermal_index") or 0.0), reverse=True)[:36]
    if selected_country and not focus_cells:
        focus_cells = cells[:24]

    if focus_cells:
        center_lat = sum(float(item.get("lat") or 0.0) for item in focus_cells) / len(focus_cells)
        center_lon = sum(float(item.get("lon") or 0.0) for item in focus_cells) / len(focus_cells)
        peak_temp = max([safe_float(item.get("temperature_c"), 0.0) for item in focus_cells], default=0.0)
        avg_temp = sum(safe_float(item.get("temperature_c"), 0.0) for item in focus_cells) / len(focus_cells)
        peak_thermal = max([safe_float(item.get("thermal_index"), 0.0) for item in focus_cells], default=0.0)
        avg_hazard = sum(safe_float(item.get("hazard_pressure"), 0.0) for item in focus_cells) / len(focus_cells)
        focus = {
            "center_lat": round(center_lat, 3),
            "center_lon": round(center_lon, 3),
            "avg_temperature_c": round(avg_temp, 2),
            "peak_temperature_c": round(peak_temp, 2),
            "peak_thermal_index": round(peak_thermal, 3),
            "avg_hazard_pressure": round(avg_hazard, 3),
            "district_count": len(focus_cells),
            "zoom_scale": 3.2 if selected_country else 1.0,
        }
    else:
        focus = {
            "center_lat": focus_lat,
            "center_lon": focus_lon,
            "avg_temperature_c": None,
            "peak_temperature_c": None,
            "peak_thermal_index": None,
            "avg_hazard_pressure": None,
            "district_count": 0,
            "zoom_scale": 3.0 if selected_country else 1.0,
        }

    if selected_country:
        top_country_summary = next((item for item in country_summaries if item.get("country") == selected_country), None)
        if top_country_summary:
            focus["country_risk_score"] = top_country_summary.get("risk_score")
            focus["source_confidence"] = top_country_summary.get("source_confidence")

    return {
        "generated_at": _now_iso(),
        "selected_country": selected_country,
        "hazard_filter": hazard or "all",
        "colorscale": THERMAL_COLORSCALE,
        "countries": country_summaries,
        "cells": cells,
        "focus": focus,
    }
