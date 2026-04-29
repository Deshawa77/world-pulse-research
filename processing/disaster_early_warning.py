from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import log1p
from typing import Any

from machine_learning.disaster_models import predict_hazard_forecast
from processing.cyclone_tracker import compute_cyclone_tracker
from processing.seismic_anomaly import compute_seismic_anomaly_scoring
from processing.disaster_feature_builder import (
    _latest_docs,
    _recent_seismic_world_state,
    _recent_world_state,
    _seismic_region_key,
    build_disaster_feature_bundle,
    clamp,
    normalize_country,
    parse_dt,
    pick_nested,
    safe_float,
)
from processing.disaster_hotspot_regions import (
    HOTSPOT_ALERT_BANDS,
    HOTSPOT_TREND_WINDOWS,
    build_region_metadata,
)

DISASTER_SOURCE_FAMILIES = [
    'satellite_imagery',
    'seismic_data',
    'weather_sensors',
    'ocean_sensors',
    'social_media_signals',
]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


FLOOD_MONITOR_THRESHOLD = _env_float("PLANETARY_FLOOD_MONITOR_THRESHOLD", 0.33)
FLOOD_ACTIVE_THRESHOLD = _env_float("PLANETARY_FLOOD_ACTIVE_THRESHOLD", 0.5)
FLOOD_CRITICAL_THRESHOLD = _env_float("PLANETARY_FLOOD_CRITICAL_THRESHOLD", 0.68)
CYCLONE_MONITOR_THRESHOLD = _env_float("PLANETARY_CYCLONE_MONITOR_THRESHOLD", 0.33)
CYCLONE_ACTIVE_THRESHOLD = _env_float("PLANETARY_CYCLONE_ACTIVE_THRESHOLD", 0.5)
CYCLONE_CRITICAL_THRESHOLD = _env_float("PLANETARY_CYCLONE_CRITICAL_THRESHOLD", 0.68)


def _source_family_for_row(source: str, event_type: str) -> str:
    src = str(source or '').lower().strip()
    evt = str(event_type or '').lower().strip()
    if src in {'firms', 'modis', 'viirs'}:
        return 'satellite_imagery'
    if src in {'usgs'} or evt == 'earthquake':
        return 'seismic_data'
    if src in {'reddit', 'telegram_public', 'youtube_trends', 'youtube_public', 'twitter', 'x'}:
        return 'social_media_signals'
    if src in {'eonet', 'ocean', 'noaa', 'noaa_cdo'} or evt == 'cyclone':
        return 'ocean_sensors'
    return 'weather_sensors'


def _source_families_from_rows(
    rows: list[dict[str, Any]],
    event_type: str,
    include: set[str] | None = None,
) -> list[str]:
    families = {
        _source_family_for_row(str(row.get('source') or ''), event_type)
        for row in rows
    }
    if include:
        families.update(include)
    return sorted({family for family in families if family})

def _region_key(lat: float, lon: float, prefix: str, grid_size: int) -> str | None:
    if lat != lat or lon != lon:
        return None
    lat_bucket = int((lat + 90.0) // grid_size)
    lon_bucket = int((lon + 180.0) // grid_size)
    return f"{prefix}_{lat_bucket:02d}_{lon_bucket:02d}"


def _build_hotspot_trend_from_rows(
    rows: list[dict[str, Any]],
    now_utc: datetime,
    *,
    activity_fn,
    rising_threshold: float,
    cooling_threshold: float,
) -> tuple[list[float], str]:
    windows: list[float] = []
    for hours_back in range(30, -1, -6):
        window_end = now_utc - timedelta(hours=hours_back)
        window_start = window_end - timedelta(hours=6)
        window_rows = [row for row in rows if window_start < row['ts'] <= window_end]
        windows.append(round(clamp(activity_fn(window_rows)), 3))

    if len(windows) >= 2 and windows[-1] >= windows[0] + rising_threshold:
        trend = 'accelerating'
    elif len(windows) >= 2 and windows[-1] <= windows[0] - cooling_threshold:
        trend = 'cooling'
    else:
        trend = 'steady'
    return windows, trend


def _build_seismic_window_activity(window_rows: list[dict[str, Any]]) -> float:
    count_component = min(len(window_rows) / 6.0, 1.0)
    max_mag = max([safe_float(row.get('mag')) for row in window_rows], default=0.0)
    magnitude_component = clamp(max(max_mag - 3.0, 0.0) / 3.0)
    return 0.6 * count_component + 0.4 * magnitude_component


def _build_wildfire_window_activity(window_rows: list[dict[str, Any]]) -> float:
    detections = sum(1 for row in window_rows if row.get('source') == 'firms' or row.get('detected'))
    heat_peak = max([safe_float(row.get('heat')) for row in window_rows], default=0.0)
    wind_peak = max([safe_float(row.get('wind')) for row in window_rows], default=0.0)
    dryness_peak = max([safe_float(row.get('dryness')) for row in window_rows], default=0.0)
    count_component = clamp(detections / 8.0)
    heat_component = clamp(max(heat_peak - 28.0, 0.0) / 18.0)
    wind_component = clamp(wind_peak / 70.0)
    dryness_component = clamp(dryness_peak)
    return 0.38 * count_component + 0.26 * heat_component + 0.18 * wind_component + 0.18 * dryness_component


def _build_flood_window_activity(window_rows: list[dict[str, Any]]) -> float:
    detections = sum(1 for row in window_rows if row.get('detected'))
    rain_peak = max([safe_float(row.get('rain')) for row in window_rows], default=0.0)
    wind_peak = max([safe_float(row.get('wind')) for row in window_rows], default=0.0)
    surge_peak = max([safe_float(row.get('surge')) for row in window_rows], default=0.0)
    return 0.38 * clamp(detections / 8.0) + 0.28 * clamp(rain_peak / 120.0) + 0.18 * clamp(wind_peak / 80.0) + 0.16 * clamp(surge_peak)


def _build_cyclone_window_activity(window_rows: list[dict[str, Any]]) -> float:
    detections = sum(1 for row in window_rows if row.get('detected'))
    wind_peak = max([safe_float(row.get('wind')) for row in window_rows], default=0.0)
    ocean_peak = max([safe_float(row.get('ocean')) for row in window_rows], default=0.0)
    pressure_peak = max([safe_float(row.get('pressure_score')) for row in window_rows], default=0.0)
    return 0.34 * clamp(detections / 8.0) + 0.32 * clamp(wind_peak / 120.0) + 0.18 * clamp(ocean_peak) + 0.16 * clamp(pressure_peak)


def _derive_window_series(rows: list[dict[str, Any]], now_utc: datetime, hours: int, *, hazard: str) -> list[dict[str, Any]]:
    bucket_hours = 6 if hours > 6 else 1
    count = max(2, hours // bucket_hours)
    series: list[dict[str, Any]] = []
    for idx in range(count):
        window_end = now_utc - timedelta(hours=(count - idx - 1) * bucket_hours)
        window_start = window_end - timedelta(hours=bucket_hours)
        window_rows = [row for row in rows if window_start < row['ts'] <= window_end]
        if hazard == 'wildfire':
            activity = _build_wildfire_window_activity(window_rows)
            peak_value = max([safe_float(row.get('heat')) for row in window_rows], default=0.0)
            event_count = sum(1 for row in window_rows if row.get('source') == 'firms' or row.get('detected'))
            series.append({
                'timestamp': window_end.isoformat(),
                'activity': round(clamp(activity), 3),
                'band': 'active' if activity >= 0.55 else 'monitor' if activity >= 0.35 else 'guarded',
                'event_count': event_count,
                'intensity_peak': round(peak_value, 3),
                'max_temperature': round(peak_value, 3),
            })
        elif hazard == 'flood':
            activity = _build_flood_window_activity(window_rows)
            peak_value = max([safe_float(row.get('rain')) for row in window_rows], default=0.0)
            event_count = sum(1 for row in window_rows if row.get('detected'))
            series.append({
                'timestamp': window_end.isoformat(),
                'activity': round(clamp(activity), 3),
                'band': 'active' if activity >= 0.55 else 'monitor' if activity >= 0.35 else 'guarded',
                'event_count': event_count,
                'intensity_peak': round(peak_value, 3),
                'rainfall_peak': round(peak_value, 3),
            })
        elif hazard == 'cyclone':
            activity = _build_cyclone_window_activity(window_rows)
            peak_value = max([safe_float(row.get('wind')) for row in window_rows], default=0.0)
            event_count = sum(1 for row in window_rows if row.get('detected'))
            series.append({
                'timestamp': window_end.isoformat(),
                'activity': round(clamp(activity), 3),
                'band': 'active' if activity >= 0.55 else 'monitor' if activity >= 0.35 else 'guarded',
                'event_count': event_count,
                'intensity_peak': round(peak_value, 3),
                'max_wind_speed': round(peak_value, 3),
            })
        else:
            max_mag = max([safe_float(row.get('mag')) for row in window_rows], default=0.0)
            event_count = len(window_rows)
            score = _build_seismic_window_activity(window_rows)
            series.append({
                'timestamp': window_end.isoformat(),
                'activity': round(clamp(score), 3),
                'band': 'active' if score >= 0.55 else 'monitor' if score >= 0.35 else 'guarded',
                'event_count': event_count,
                'intensity_peak': round(max_mag, 3),
                'quake_count': event_count,
                'max_magnitude': round(max_mag, 3),
            })
    return series


def _history_feature_summary(history_points: list[dict[str, Any]]) -> dict[str, float]:
    if not history_points:
        return {
            'history_avg_activity': 0.0,
            'history_max_activity': 0.0,
            'history_recent_delta': 0.0,
        }
    activity_values = [safe_float(point.get('activity')) for point in history_points]
    recent_delta = 0.0
    if len(activity_values) >= 2:
        recent_delta = activity_values[-1] - activity_values[0]
    return {
        'history_avg_activity': round(sum(activity_values) / len(activity_values), 4),
        'history_max_activity': round(max(activity_values), 4),
        'history_recent_delta': round(recent_delta, 4),
    }


def _build_seismic_hotspot_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    recent_quake_count = len([row for row in rows if row['mag'] > 0])
    magnitude_sum = sum(row['mag'] for row in rows if row['mag'] > 0)
    major_count = sum(1 for row in rows if row['mag'] >= 5.5)
    strong_count = sum(1 for row in rows if row['mag'] >= 4.5)
    max_mag = max([row['mag'] for row in rows], default=0.0)
    energy_proxy_total = sum(max(0.0, row['mag']) ** 2 for row in rows)
    recent_24h_count = sum(1 for row in rows if row['ts'] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in rows if row['ts'] < now_utc - timedelta(hours=24))
    latest_signal = max([row['ts'] for row in rows], default=None)

    avg_mag = magnitude_sum / recent_quake_count if recent_quake_count else 0.0
    major_ratio = major_count / recent_quake_count if recent_quake_count else 0.0
    strong_event_density = clamp(strong_count / 6.0) if recent_quake_count else 0.0
    max_magnitude_score = clamp(max(max_mag - 4.0, 0.0) / 3.0) if recent_quake_count else 0.0
    baseline_rate = prior_48h_count / 2.0
    if recent_quake_count:
        if baseline_rate <= 0:
            short_term_acceleration_score = clamp(recent_24h_count / 6.0)
        else:
            short_term_acceleration_score = clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    else:
        short_term_acceleration_score = 0.0
    energy_proxy_score = clamp(energy_proxy_total / 250.0) if recent_quake_count else 0.0
    recency_score = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (72 * 3600))) if latest_signal else 0.0

    coord_rows = [row for row in rows if row.get('lat') == row.get('lat') and row.get('lon') == row.get('lon')]
    center_lat = sum(float(row['lat']) for row in coord_rows) / len(coord_rows) if coord_rows else 0.0
    center_lon = sum(float(row['lon']) for row in coord_rows) / len(coord_rows) if coord_rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard='earthquake')
    trend_points, trend_direction = _build_hotspot_trend_from_rows(rows, now_utc, activity_fn=_build_seismic_window_activity, rising_threshold=0.18, cooling_threshold=0.12)
    history_summary = _history_feature_summary(history_points or [])

    return {
        'event_type': 'earthquake',
        'country': 'GLB',
        'region': region,
        **metadata,
        'center_lat': round(center_lat, 3),
        'center_lon': round(center_lon, 3),
        'lead_time_hours': 12,
        'signal_sources': _source_families_from_rows(rows, 'earthquake', include={'seismic_data'}),
        'top_contributing_signals': ['regional seismic sequence', 'hotspot clustering'],
        'recommended_action': 'Review readiness for this active seismic region and monitor the next 12 hours closely.',
        'updated_at': latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        'feature_values': {
            'recent_quake_density': round(clamp(recent_quake_count / 18.0), 4),
            'average_magnitude_score': round(clamp(max(avg_mag - 3.5, 0.0) / 4.0), 4),
            'major_quake_ratio': round(clamp(major_ratio), 4),
            'aftershock_cluster_score': round(clamp(recent_quake_count / 18.0), 4),
            'max_magnitude_score': round(max_magnitude_score, 4),
            'short_term_acceleration_score': round(short_term_acceleration_score, 4),
            'strong_event_density': round(strong_event_density, 4),
            'energy_proxy_score': round(energy_proxy_score, 4),
            'source_coverage': round(clamp(recent_quake_count / 12.0), 4),
            'recency_score': round(recency_score, 4),
            **history_summary,
        },
        'hotspot_stats': {
            'event_count': recent_quake_count,
            'intensity_peak': round(max_mag, 3),
            'quake_count': recent_quake_count,
            'max_magnitude': round(max_mag, 3),
            'strong_event_count': strong_count,
            'major_event_count': major_count,
            'recent_24h_count': recent_24h_count,
        },
        'activity_trend': trend_direction,
        'trend_points': trend_points,
        'history': {
            key: _derive_window_series(rows, now_utc, hours, hazard='earthquake')
            for key, hours in HOTSPOT_TREND_WINDOWS.items()
        },
    }


def _extract_hotspot_coordinate(doc: dict[str, Any]) -> tuple[float, float] | None:
    lat = safe_float(pick_nested(doc, 'lat', 'latitude', 'meta.lat', 'meta.latitude', 'data.lat', 'data.latitude'), default=float('nan'))
    lon = safe_float(pick_nested(doc, 'lon', 'longitude', 'meta.lon', 'meta.longitude', 'data.lon', 'data.longitude'), default=float('nan'))
    if lat != lat or lon != lon:
        return None
    return lat, lon


def _build_wildfire_hotspot_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    detection_count = sum(1 for row in rows if row.get('source') == 'firms' or row.get('detected'))
    weather_trigger_count = sum(1 for row in rows if row.get('source') == 'weather')
    smoke_signal_count = sum(1 for row in rows if row.get('smoke'))
    max_temperature = max([safe_float(row.get('heat')) for row in rows], default=0.0)
    max_wind_speed = max([safe_float(row.get('wind')) for row in rows], default=0.0)
    max_dryness = max([safe_float(row.get('dryness')) for row in rows], default=0.0)
    multi_source_overlap = len({str(row.get('source') or '') for row in rows if row.get('source')})
    recent_24h_count = sum(1 for row in rows if row['ts'] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in rows if row['ts'] < now_utc - timedelta(hours=24))
    latest_signal = max([row['ts'] for row in rows], default=None)

    heat_score = clamp(max(max_temperature - 28.0, 0.0) / 18.0)
    wind_score = clamp(max_wind_speed / 70.0)
    dryness_score = clamp(max_dryness)
    signal_density = clamp(detection_count / 10.0)
    overlap_score = clamp((multi_source_overlap - 1.0) / 2.0)
    baseline_rate = prior_48h_count / 2.0
    if detection_count or weather_trigger_count:
        if baseline_rate <= 0:
            acceleration_score = clamp(recent_24h_count / 8.0)
        else:
            acceleration_score = clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    else:
        acceleration_score = 0.0
    recency_score = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (96 * 3600))) if latest_signal else 0.0

    coord_rows = [row for row in rows if row.get('lat') == row.get('lat') and row.get('lon') == row.get('lon')]
    center_lat = sum(float(row['lat']) for row in coord_rows) / len(coord_rows) if coord_rows else 0.0
    center_lon = sum(float(row['lon']) for row in coord_rows) / len(coord_rows) if coord_rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard='wildfire')
    trend_points, trend_direction = _build_hotspot_trend_from_rows(rows, now_utc, activity_fn=_build_wildfire_window_activity, rising_threshold=0.14, cooling_threshold=0.1)
    history_summary = _history_feature_summary(history_points or [])

    countries = [str(row.get('country') or '').upper() for row in rows if row.get('country')]
    return {
        'event_type': 'wildfire',
        'country': max(set(countries), key=countries.count) if countries else 'GLB',
        'region': region,
        **metadata,
        'center_lat': round(center_lat, 3),
        'center_lon': round(center_lon, 3),
        'lead_time_hours': 18,
        'signal_sources': _source_families_from_rows(rows, 'wildfire', include={'weather_sensors', 'satellite_imagery'}),
        'top_contributing_signals': ['fire detection clustering', 'heat stress', 'wind alignment', 'dryness persistence'][:4],
        'recommended_action': 'Stage wildfire patrols, review suppression capacity, and verify near-term weather escalation in this region.',
        'updated_at': latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        'feature_values': {
            'heat_score': round(heat_score, 4),
            'wind_score': round(wind_score, 4),
            'smoke_keyword_score': round(clamp(smoke_signal_count / 4.0), 4),
            'wildfire_signal_density': round(signal_density, 4),
            'dryness_proxy_score': round(dryness_score, 4),
            'source_coverage': round(clamp(multi_source_overlap / 3.0), 4),
            'multi_source_overlap_score': round(overlap_score, 4),
            'heat_persistence_score': round(clamp((recent_24h_count + weather_trigger_count) / 10.0), 4),
            'wind_alignment_score': round(clamp((max_wind_speed / 50.0) * max(heat_score, 0.4)), 4),
            'short_term_acceleration_score': round(acceleration_score, 4),
            'recency_score': round(recency_score, 4),
            **history_summary,
        },
        'hotspot_stats': {
            'event_count': detection_count,
            'intensity_peak': round(max_temperature, 3),
            'detection_count': detection_count,
            'weather_trigger_count': weather_trigger_count,
            'smoke_signal_count': smoke_signal_count,
            'max_temperature': round(max_temperature, 3),
            'max_wind_speed': round(max_wind_speed, 3),
            'cross_source_hits': multi_source_overlap,
            'recent_24h_count': recent_24h_count,
        },
        'activity_trend': trend_direction,
        'trend_points': trend_points,
        'history': {
            key: _derive_window_series(rows, now_utc, hours, hazard='wildfire')
            for key, hours in HOTSPOT_TREND_WINDOWS.items()
        },
    }



def _build_flood_hotspot_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    detection_count = sum(1 for row in rows if row.get('detected'))
    rain_peak = max([safe_float(row.get('rain')) for row in rows], default=0.0)
    wind_peak = max([safe_float(row.get('wind')) for row in rows], default=0.0)
    surge_peak = max([safe_float(row.get('surge')) for row in rows], default=0.0)
    source_overlap = len({str(row.get('source') or '') for row in rows if row.get('source')})
    recent_24h_count = sum(1 for row in rows if row['ts'] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in rows if row['ts'] < now_utc - timedelta(hours=24))
    baseline_rate = prior_48h_count / 2.0
    acceleration = clamp(recent_24h_count / 8.0) if baseline_rate <= 0 else clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    latest_signal = max([row['ts'] for row in rows], default=None)
    recency = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (96 * 3600))) if latest_signal else 0.0
    center_lat = sum(float(row['lat']) for row in rows) / len(rows) if rows else 0.0
    center_lon = sum(float(row['lon']) for row in rows) / len(rows) if rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard='flood')
    trend_points, trend_direction = _build_hotspot_trend_from_rows(rows, now_utc, activity_fn=_build_flood_window_activity, rising_threshold=0.13, cooling_threshold=0.1)
    history_summary = _history_feature_summary(history_points or [])
    countries = [str(row.get('country') or '').upper() for row in rows if row.get('country')]
    return {
        'event_type': 'flood',
        'country': max(set(countries), key=countries.count) if countries else 'GLB',
        'region': region,
        **metadata,
        'center_lat': round(center_lat, 3),
        'center_lon': round(center_lon, 3),
        'lead_time_hours': 24,
        'signal_sources': _source_families_from_rows(rows, 'flood', include={'weather_sensors', 'ocean_sensors', 'satellite_imagery'}),
        'top_contributing_signals': ['rainfall clustering', 'flood event detections', 'wind-driven runoff'],
        'recommended_action': 'Review exposed basins, river watches, and urban drainage readiness in this flood-prone region.',
        'updated_at': latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        'feature_values': {
            'rainfall_score': round(clamp(rain_peak / 120.0), 4),
            'wind_score': round(clamp(wind_peak / 80.0), 4),
            'surge_proxy_score': round(clamp(surge_peak), 4),
            'flood_signal_density': round(clamp(detection_count / 10.0), 4),
            'source_coverage': round(clamp(source_overlap / 3.0), 4),
            'multi_source_overlap_score': round(clamp((source_overlap - 1.0) / 2.0), 4),
            'short_term_acceleration_score': round(acceleration, 4),
            'recency_score': round(recency, 4),
            **history_summary,
        },
        'hotspot_stats': {
            'event_count': detection_count,
            'intensity_peak': round(rain_peak, 3),
            'flood_detection_count': detection_count,
            'max_rainfall': round(rain_peak, 3),
            'max_wind_speed': round(wind_peak, 3),
            'surge_proxy': round(surge_peak, 3),
            'cross_source_hits': source_overlap,
            'recent_24h_count': recent_24h_count,
        },
        'activity_trend': trend_direction,
        'trend_points': trend_points,
        'history': {
            key: _derive_window_series(rows, now_utc, hours, hazard='flood')
            for key, hours in HOTSPOT_TREND_WINDOWS.items()
        },
    }


def _build_cyclone_hotspot_bundle(
    region: str,
    rows: list[dict[str, Any]],
    now_utc: datetime,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    detection_count = sum(1 for row in rows if row.get('detected'))
    wind_peak = max([safe_float(row.get('wind')) for row in rows], default=0.0)
    ocean_peak = max([safe_float(row.get('ocean')) for row in rows], default=0.0)
    pressure_peak = max([safe_float(row.get('pressure_score')) for row in rows], default=0.0)
    source_overlap = len({str(row.get('source') or '') for row in rows if row.get('source')})
    recent_24h_count = sum(1 for row in rows if row['ts'] >= now_utc - timedelta(hours=24))
    prior_48h_count = sum(1 for row in rows if row['ts'] < now_utc - timedelta(hours=24))
    baseline_rate = prior_48h_count / 2.0
    acceleration = clamp(recent_24h_count / 8.0) if baseline_rate <= 0 else clamp((recent_24h_count - baseline_rate) / max(baseline_rate, 1.0))
    latest_signal = max([row['ts'] for row in rows], default=None)
    recency = clamp(1.0 - ((now_utc - latest_signal).total_seconds() / (96 * 3600))) if latest_signal else 0.0
    center_lat = sum(float(row['lat']) for row in rows) / len(rows) if rows else 0.0
    center_lon = sum(float(row['lon']) for row in rows) / len(rows) if rows else 0.0
    metadata = build_region_metadata(center_lat, center_lon, hazard='cyclone')
    trend_points, trend_direction = _build_hotspot_trend_from_rows(rows, now_utc, activity_fn=_build_cyclone_window_activity, rising_threshold=0.12, cooling_threshold=0.09)
    history_summary = _history_feature_summary(history_points or [])
    countries = [str(row.get('country') or '').upper() for row in rows if row.get('country')]
    return {
        'event_type': 'cyclone',
        'country': max(set(countries), key=countries.count) if countries else 'GLB',
        'region': region,
        **metadata,
        'center_lat': round(center_lat, 3),
        'center_lon': round(center_lon, 3),
        'lead_time_hours': 30,
        'signal_sources': _source_families_from_rows(rows, 'cyclone', include={'weather_sensors', 'ocean_sensors', 'satellite_imagery'}),
        'top_contributing_signals': ['storm track clustering', 'wind field intensification', 'ocean heat support'],
        'recommended_action': 'Review tropical storm readiness, logistics staging, and near-coast exposure for this basin.',
        'updated_at': latest_signal.isoformat() if latest_signal else now_utc.isoformat(),
        'feature_values': {
            'wind_score': round(clamp(wind_peak / 120.0), 4),
            'ocean_proxy_score': round(clamp(ocean_peak), 4),
            'pressure_proxy_score': round(clamp(pressure_peak), 4),
            'storm_signal_density': round(clamp(detection_count / 10.0), 4),
            'source_coverage': round(clamp(source_overlap / 3.0), 4),
            'multi_source_overlap_score': round(clamp((source_overlap - 1.0) / 2.0), 4),
            'short_term_acceleration_score': round(acceleration, 4),
            'recency_score': round(recency, 4),
            **history_summary,
        },
        'hotspot_stats': {
            'event_count': detection_count,
            'intensity_peak': round(wind_peak, 3),
            'storm_detection_count': detection_count,
            'max_wind_speed': round(wind_peak, 3),
            'ocean_heat_proxy': round(ocean_peak, 3),
            'pressure_proxy': round(pressure_peak, 3),
            'cross_source_hits': source_overlap,
            'recent_24h_count': recent_24h_count,
        },
        'activity_trend': trend_direction,
        'trend_points': trend_points,
        'history': {
            key: _derive_window_series(rows, now_utc, hours, hazard='cyclone')
            for key, hours in HOTSPOT_TREND_WINDOWS.items()
        },
    }


def _calibrate_seismic_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get('hotspot_stats') or {}
    features = item.get('feature_values') or {}

    quake_count = safe_float(stats.get('quake_count'))
    max_mag = safe_float(stats.get('max_magnitude'))
    strong_count = safe_float(stats.get('strong_event_count'))
    major_count = safe_float(stats.get('major_event_count'))
    count_component = clamp(log1p(quake_count) / log1p(500.0))
    magnitude_component = clamp(max_mag / 7.0)
    strong_component = clamp(strong_count / 12.0)
    major_component = clamp(major_count / 3.0)
    acceleration_component = clamp(safe_float(features.get('short_term_acceleration_score')))
    recency_component = clamp(safe_float(features.get('recency_score')))
    history_avg_component = clamp(safe_float(features.get('history_avg_activity')))
    history_delta_component = clamp((safe_float(features.get('history_recent_delta')) + 1.0) / 2.0)

    hotspot_score = clamp(
        0.18 * count_component
        + 0.24 * magnitude_component
        + 0.12 * strong_component
        + 0.14 * major_component
        + 0.10 * acceleration_component
        + 0.10 * recency_component
        + 0.07 * history_avg_component
        + 0.05 * history_delta_component
    )
    hotspot_confidence = clamp(
        0.35
        + 0.22 * count_component
        + 0.18 * recency_component
        + 0.10 * strong_component
        + 0.10 * major_component
        + 0.05 * history_avg_component
    )

    if hotspot_score >= 0.75:
        hotspot_band = 'critical'
    elif hotspot_score >= 0.55:
        hotspot_band = 'active'
    elif hotspot_score >= 0.35:
        hotspot_band = 'monitor'
    else:
        hotspot_band = 'guarded'

    return {
        **item,
        'activity_score': round(hotspot_score, 3),
        'hotspot_score': round(hotspot_score, 3),
        'hotspot_confidence': round(hotspot_confidence, 3),
        'hotspot_band': hotspot_band,
    }


def _calibrate_wildfire_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get('hotspot_stats') or {}
    features = item.get('feature_values') or {}

    detection_component = clamp(log1p(safe_float(stats.get('detection_count'))) / log1p(60.0))
    heat_component = clamp(safe_float(features.get('heat_score')))
    wind_component = clamp(safe_float(features.get('wind_score')))
    dryness_component = clamp(safe_float(features.get('dryness_proxy_score')))
    overlap_component = clamp(safe_float(features.get('multi_source_overlap_score')))
    acceleration_component = clamp(safe_float(features.get('short_term_acceleration_score')))
    recency_component = clamp(safe_float(features.get('recency_score')))
    history_avg_component = clamp(safe_float(features.get('history_avg_activity')))
    history_delta_component = clamp((safe_float(features.get('history_recent_delta')) + 1.0) / 2.0)

    hotspot_score = clamp(
        0.22 * detection_component
        + 0.18 * heat_component
        + 0.14 * wind_component
        + 0.14 * dryness_component
        + 0.12 * overlap_component
        + 0.08 * acceleration_component
        + 0.07 * recency_component
        + 0.03 * history_avg_component
        + 0.02 * history_delta_component
    )
    hotspot_confidence = clamp(
        0.32
        + 0.18 * detection_component
        + 0.16 * overlap_component
        + 0.14 * recency_component
        + 0.12 * heat_component
        + 0.08 * dryness_component
    )

    if hotspot_score >= 0.72:
        hotspot_band = 'critical'
    elif hotspot_score >= 0.54:
        hotspot_band = 'active'
    elif hotspot_score >= 0.34:
        hotspot_band = 'monitor'
    else:
        hotspot_band = 'guarded'

    return {
        **item,
        'activity_score': round(hotspot_score, 3),
        'hotspot_score': round(hotspot_score, 3),
        'hotspot_confidence': round(hotspot_confidence, 3),
        'hotspot_band': hotspot_band,
    }



def _calibrate_flood_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get('hotspot_stats') or {}
    features = item.get('feature_values') or {}
    detection_component = clamp(log1p(safe_float(stats.get('flood_detection_count'))) / log1p(60.0))
    rainfall_component = clamp(safe_float(features.get('rainfall_score')))
    wind_component = clamp(safe_float(features.get('wind_score')))
    surge_component = clamp(safe_float(features.get('surge_proxy_score')))
    overlap_component = clamp(safe_float(features.get('multi_source_overlap_score')))
    acceleration_component = clamp(safe_float(features.get('short_term_acceleration_score')))
    recency_component = clamp(safe_float(features.get('recency_score')))
    history_avg_component = clamp(safe_float(features.get('history_avg_activity')))
    history_delta_component = clamp((safe_float(features.get('history_recent_delta')) + 1.0) / 2.0)
    source_coverage_component = clamp(safe_float(features.get('source_coverage')))
    calibration_penalty = 0.0
    calibration_notes: list[str] = []
    if overlap_component < 0.2 and source_coverage_component < 0.45:
        calibration_penalty += 0.08
        calibration_notes.append('low_cross_source_overlap')
    if recency_component < 0.35:
        calibration_penalty += 0.05
        calibration_notes.append('stale_signal_window')
    if rainfall_component < 0.35 and detection_component < 0.3:
        calibration_penalty += 0.05
        calibration_notes.append('weak_rainfall_confirmation')
    hotspot_score = clamp(0.22 * detection_component + 0.2 * rainfall_component + 0.14 * wind_component + 0.12 * surge_component + 0.12 * overlap_component + 0.08 * acceleration_component + 0.08 * recency_component + 0.02 * history_avg_component + 0.02 * history_delta_component - calibration_penalty)
    hotspot_confidence = clamp(0.34 + 0.18 * detection_component + 0.16 * rainfall_component + 0.14 * recency_component + 0.08 * overlap_component + 0.06 * source_coverage_component - (calibration_penalty * 0.7))
    hotspot_band = (
        'critical' if hotspot_score >= FLOOD_CRITICAL_THRESHOLD
        else 'active' if hotspot_score >= FLOOD_ACTIVE_THRESHOLD
        else 'monitor' if hotspot_score >= FLOOD_MONITOR_THRESHOLD
        else 'guarded'
    )
    calibration_status = 'well_correlated' if calibration_penalty <= 0.01 else 'guarded' if calibration_penalty <= 0.08 else 'thin_corroboration'
    return {
        **item,
        'activity_score': round(hotspot_score, 3),
        'hotspot_score': round(hotspot_score, 3),
        'hotspot_confidence': round(hotspot_confidence, 3),
        'hotspot_band': hotspot_band,
        'calibration_status': calibration_status,
        'calibration_adjustments': {
            'penalty': round(calibration_penalty, 4),
            'notes': calibration_notes,
            'thresholds': {
                'monitor': round(FLOOD_MONITOR_THRESHOLD, 4),
                'active': round(FLOOD_ACTIVE_THRESHOLD, 4),
                'critical': round(FLOOD_CRITICAL_THRESHOLD, 4),
            },
        },
    }


def _calibrate_cyclone_hotspot_score(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get('hotspot_stats') or {}
    features = item.get('feature_values') or {}
    detection_component = clamp(log1p(safe_float(stats.get('storm_detection_count'))) / log1p(60.0))
    wind_component = clamp(safe_float(features.get('wind_score')))
    ocean_component = clamp(safe_float(features.get('ocean_proxy_score')))
    pressure_component = clamp(safe_float(features.get('pressure_proxy_score')))
    overlap_component = clamp(safe_float(features.get('multi_source_overlap_score')))
    acceleration_component = clamp(safe_float(features.get('short_term_acceleration_score')))
    recency_component = clamp(safe_float(features.get('recency_score')))
    history_avg_component = clamp(safe_float(features.get('history_avg_activity')))
    history_delta_component = clamp((safe_float(features.get('history_recent_delta')) + 1.0) / 2.0)
    source_coverage_component = clamp(safe_float(features.get('source_coverage')))
    calibration_penalty = 0.0
    calibration_notes: list[str] = []
    if overlap_component < 0.2 and source_coverage_component < 0.45:
        calibration_penalty += 0.08
        calibration_notes.append('low_cross_source_overlap')
    if wind_component < 0.38 and pressure_component < 0.42:
        calibration_penalty += 0.06
        calibration_notes.append('weak_wind_pressure_alignment')
    if recency_component < 0.35:
        calibration_penalty += 0.05
        calibration_notes.append('stale_signal_window')
    hotspot_score = clamp(0.2 * detection_component + 0.22 * wind_component + 0.14 * ocean_component + 0.12 * pressure_component + 0.12 * overlap_component + 0.08 * acceleration_component + 0.08 * recency_component + 0.02 * history_avg_component + 0.02 * history_delta_component - calibration_penalty)
    hotspot_confidence = clamp(0.34 + 0.18 * detection_component + 0.16 * wind_component + 0.14 * recency_component + 0.08 * ocean_component + 0.06 * source_coverage_component - (calibration_penalty * 0.7))
    hotspot_band = (
        'critical' if hotspot_score >= CYCLONE_CRITICAL_THRESHOLD
        else 'active' if hotspot_score >= CYCLONE_ACTIVE_THRESHOLD
        else 'monitor' if hotspot_score >= CYCLONE_MONITOR_THRESHOLD
        else 'guarded'
    )
    calibration_status = 'well_correlated' if calibration_penalty <= 0.01 else 'guarded' if calibration_penalty <= 0.08 else 'thin_corroboration'
    return {
        **item,
        'activity_score': round(hotspot_score, 3),
        'hotspot_score': round(hotspot_score, 3),
        'hotspot_confidence': round(hotspot_confidence, 3),
        'hotspot_band': hotspot_band,
        'calibration_status': calibration_status,
        'calibration_adjustments': {
            'penalty': round(calibration_penalty, 4),
            'notes': calibration_notes,
            'thresholds': {
                'monitor': round(CYCLONE_MONITOR_THRESHOLD, 4),
                'active': round(CYCLONE_ACTIVE_THRESHOLD, 4),
                'critical': round(CYCLONE_CRITICAL_THRESHOLD, 4),
            },
        },
    }


def _transition_priority(band: str) -> int:
    try:
        return HOTSPOT_ALERT_BANDS.index(str(band or 'guarded').lower())
    except ValueError:
        return len(HOTSPOT_ALERT_BANDS) - 1


def build_regional_seismic_hotspots(
    limit: int = 5,
    history_lookup: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    docs = _recent_seismic_world_state(2400)
    region_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        stamp = parse_dt(doc.get('timestamp_utc') or doc.get('timestamp'))
        if not stamp or stamp < now_utc - timedelta(hours=72):
            continue
        region = _seismic_region_key(doc.get('lat'), doc.get('lon'))
        if not region:
            continue
        meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
        mag = safe_float(meta.get('mag'), safe_float(doc.get('value'), 0.0) * 8.0)
        lat = safe_float(doc.get('lat'))
        lon = safe_float(doc.get('lon'))
        region_rows[region].append({'ts': stamp, 'mag': mag, 'lat': lat, 'lon': lon})

    hotspots = []
    for region, rows in region_rows.items():
        history_points = (history_lookup or {}).get(region) or []
        bundle = _build_seismic_hotspot_bundle(region, rows, now_utc, history_points=history_points)
        scored = predict_hazard_forecast(bundle)
        hotspots.append(_calibrate_seismic_hotspot_score(scored))

    hotspots.sort(
        key=lambda item: (
            float(item.get('hotspot_score') or 0.0),
            safe_float((item.get('hotspot_stats') or {}).get('max_magnitude')),
            safe_float((item.get('hotspot_stats') or {}).get('quake_count')),
            _transition_priority(str(item.get('hotspot_band') or 'guarded')),
        ),
        reverse=True,
    )
    return hotspots[:limit]


def build_regional_wildfire_hotspots(
    limit: int = 5,
    history_lookup: dict[str, list[dict[str, Any]]] | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    weather_docs = _latest_docs('weather', 320)
    world_state_docs = _recent_world_state(900)
    region_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, 'country', 'data.country', 'data_country'))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(pick_nested(doc, 'timestamp', 'data_timestamp', 'data.date', 'collected_at'))
        if not stamp or stamp < now_utc - timedelta(hours=96):
            continue
        coords = _extract_hotspot_coordinate(doc)
        if not coords:
            continue
        lat, lon = coords
        temp = safe_float(pick_nested(doc, 'temperature', 'data.temperature', 'data.temp', 'data_temperature'))
        wind = safe_float(pick_nested(doc, 'wind_speed', 'data.wind_speed', 'data_wind_speed'))
        text = str(pick_nested(doc, 'event', 'data.weather', 'data_weather', 'data.description', default='')).lower()
        smoke = any(token in text for token in ('wildfire', 'smoke', 'heatwave'))
        dry = any(token in text for token in ('dry', 'drought', 'arid', 'heatwave'))
        signal_strength = clamp(max(max(temp - 28.0, 0.0) / 18.0, wind / 70.0, 1.0 if smoke else 0.0, 0.8 if dry else 0.0))
        if signal_strength < 0.4:
            continue
        region = _region_key(lat, lon, 'wildfire', 20)
        if not region:
            continue
        region_rows[region].append({
            'ts': stamp,
            'lat': lat,
            'lon': lon,
            'heat': temp,
            'wind': wind,
            'dryness': clamp(max(max(temp - 25.0, 0.0) / 20.0, 1.0 if dry else 0.0)),
            'signal_strength': signal_strength,
            'source': 'weather',
            'country': doc_country,
            'smoke': smoke,
            'detected': smoke or dry,
        })

    for doc in world_state_docs:
        source = str(doc.get('source') or '').lower()
        meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
        category = str(meta.get('category') or '').lower()
        doc_country = normalize_country(doc.get('country'))
        if country and doc_country and doc_country != country:
            continue
        if source != 'firms' and 'wildfire' not in category and 'fire' not in category:
            continue
        stamp = parse_dt(doc.get('timestamp_utc') or doc.get('timestamp'))
        if not stamp or stamp < now_utc - timedelta(hours=96):
            continue
        coords = _extract_hotspot_coordinate(doc)
        if not coords:
            continue
        lat, lon = coords
        region = _region_key(lat, lon, 'wildfire', 20)
        if not region:
            continue
        temp = safe_float(meta.get('temperature'), safe_float(doc.get('value')) * 50.0)
        region_rows[region].append({
            'ts': stamp,
            'lat': lat,
            'lon': lon,
            'heat': max(temp, 32.0),
            'wind': safe_float(meta.get('wind_speed')),
            'dryness': clamp(max((max(temp, 32.0) - 25.0) / 20.0, 0.6)),
            'signal_strength': clamp(max((max(temp, 32.0) - 28.0) / 18.0, 0.7)),
            'source': source or 'world_state',
            'country': doc_country,
            'smoke': 'smoke' in category,
            'detected': True,
        })

    hotspots = []
    for region, rows in region_rows.items():
        history_points = (history_lookup or {}).get(region) or []
        bundle = _build_wildfire_hotspot_bundle(region, rows, now_utc, history_points=history_points)
        scored = predict_hazard_forecast(bundle)
        hotspots.append(_calibrate_wildfire_hotspot_score(scored))

    hotspots.sort(
        key=lambda item: (
            float(item.get('hotspot_score') or 0.0),
            safe_float((item.get('hotspot_stats') or {}).get('max_temperature')),
            safe_float((item.get('hotspot_stats') or {}).get('detection_count')),
            _transition_priority(str(item.get('hotspot_band') or 'guarded')),
        ),
        reverse=True,
    )
    return hotspots[:limit]



def build_regional_flood_hotspots(
    limit: int = 5,
    history_lookup: dict[str, list[dict[str, Any]]] | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    weather_docs = _latest_docs('weather', 320)
    world_state_docs = _recent_world_state(900)
    region_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, 'country', 'data.country', 'data_country'))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(pick_nested(doc, 'timestamp', 'data_timestamp', 'data.date', 'collected_at'))
        coords = _extract_hotspot_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=96) or not coords:
            continue
        lat, lon = coords
        wind = safe_float(pick_nested(doc, 'wind_speed', 'data.wind_speed', 'data_wind_speed'))
        rain = safe_float(pick_nested(doc, 'precipitation', 'data.precipitation', 'rainfall', 'data.rainfall'))
        text_value = str(pick_nested(doc, 'event', 'data.weather', 'data_weather', 'data.description', default='')).lower()
        detected = any(token in text_value for token in ('flood', 'heavy rain', 'storm', 'overflow', 'monsoon')) or rain >= 35 or wind >= 30
        if not detected:
            continue
        region = _region_key(lat, lon, 'flood', 18)
        if not region:
            continue
        region_rows[region].append({'ts': stamp, 'lat': lat, 'lon': lon, 'rain': max(rain, 30.0 if 'heavy rain' in text_value else 0.0), 'wind': wind, 'surge': clamp(max(wind / 80.0, 0.6 if 'storm' in text_value or 'monsoon' in text_value else 0.0)), 'source': 'weather', 'country': doc_country, 'detected': True})
    for doc in world_state_docs:
        source = str(doc.get('source') or '').lower()
        meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
        category = str(meta.get('category') or '').lower()
        doc_country = normalize_country(doc.get('country'))
        if country and doc_country and doc_country != country:
            continue
        if 'flood' not in category and 'storm' not in category and source not in {'eonet'}:
            continue
        stamp = parse_dt(doc.get('timestamp_utc') or doc.get('timestamp'))
        coords = _extract_hotspot_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=96) or not coords:
            continue
        lat, lon = coords
        region = _region_key(lat, lon, 'flood', 18)
        if not region:
            continue
        value = safe_float(doc.get('value'))
        region_rows[region].append({'ts': stamp, 'lat': lat, 'lon': lon, 'rain': max(40.0, value * 80.0), 'wind': safe_float(meta.get('wind_speed'), 22.0), 'surge': clamp(max(0.7, value)), 'source': source or 'world_state', 'country': doc_country, 'detected': True})
    hotspots = []
    for region, rows in region_rows.items():
        bundle = _build_flood_hotspot_bundle(region, rows, now_utc, history_points=(history_lookup or {}).get(region) or [])
        hotspots.append(_calibrate_flood_hotspot_score(predict_hazard_forecast(bundle)))
    hotspots.sort(key=lambda item: (float(item.get('hotspot_score') or 0.0), safe_float((item.get('hotspot_stats') or {}).get('max_rainfall')), safe_float((item.get('hotspot_stats') or {}).get('flood_detection_count')), _transition_priority(str(item.get('hotspot_band') or 'guarded'))), reverse=True)
    return hotspots[:limit]


def build_regional_cyclone_hotspots(
    limit: int = 5,
    history_lookup: dict[str, list[dict[str, Any]]] | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    weather_docs = _latest_docs('weather', 320)
    world_state_docs = _recent_world_state(900)
    region_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in weather_docs:
        doc_country = normalize_country(pick_nested(doc, 'country', 'data.country', 'data_country'))
        if country and doc_country and doc_country != country:
            continue
        stamp = parse_dt(pick_nested(doc, 'timestamp', 'data_timestamp', 'data.date', 'collected_at'))
        coords = _extract_hotspot_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=96) or not coords:
            continue
        lat, lon = coords
        wind = safe_float(pick_nested(doc, 'wind_speed', 'data.wind_speed', 'data_wind_speed'))
        temp = safe_float(pick_nested(doc, 'temperature', 'data.temperature', 'data.temp', 'data_temperature'))
        text_value = str(pick_nested(doc, 'event', 'data.weather', 'data_weather', 'data.description', default='')).lower()
        detected = any(token in text_value for token in ('cyclone', 'hurricane', 'typhoon', 'tropical storm')) or wind >= 45
        if not detected:
            continue
        region = _region_key(lat, lon, 'cyclone', 22)
        if not region:
            continue
        region_rows[region].append({'ts': stamp, 'lat': lat, 'lon': lon, 'wind': max(wind, 45.0), 'ocean': clamp(max((temp - 26.0) / 8.0, 0.45 if 'tropical' in text_value else 0.0)), 'pressure_score': clamp(max(wind / 120.0, 0.55 if 'hurricane' in text_value or 'typhoon' in text_value else 0.0)), 'source': 'weather', 'country': doc_country, 'detected': True})
    for doc in world_state_docs:
        source = str(doc.get('source') or '').lower()
        meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
        category = str(meta.get('category') or '').lower()
        doc_country = normalize_country(doc.get('country'))
        if country and doc_country and doc_country != country:
            continue
        if 'cyclone' not in category and 'hurricane' not in category and 'storm' not in category and source not in {'eonet'}:
            continue
        stamp = parse_dt(doc.get('timestamp_utc') or doc.get('timestamp'))
        coords = _extract_hotspot_coordinate(doc)
        if not stamp or stamp < now_utc - timedelta(hours=96) or not coords:
            continue
        lat, lon = coords
        region = _region_key(lat, lon, 'cyclone', 22)
        if not region:
            continue
        value = safe_float(doc.get('value'))
        region_rows[region].append({'ts': stamp, 'lat': lat, 'lon': lon, 'wind': max(55.0, value * 100.0), 'ocean': clamp(max(0.55, safe_float(meta.get('ocean_heat'), 0.0))), 'pressure_score': clamp(max(0.6, value)), 'source': source or 'world_state', 'country': doc_country, 'detected': True})
    hotspots = []
    for region, rows in region_rows.items():
        bundle = _build_cyclone_hotspot_bundle(region, rows, now_utc, history_points=(history_lookup or {}).get(region) or [])
        hotspots.append(_calibrate_cyclone_hotspot_score(predict_hazard_forecast(bundle)))
    hotspots.sort(key=lambda item: (float(item.get('hotspot_score') or 0.0), safe_float((item.get('hotspot_stats') or {}).get('max_wind_speed')), safe_float((item.get('hotspot_stats') or {}).get('storm_detection_count')), _transition_priority(str(item.get('hotspot_band') or 'guarded'))), reverse=True)
    return hotspots[:limit]


def compute_disaster_early_warning(
    country: str | None = None,
    limit: int = 6,
    history_lookup: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    normalized_country = normalize_country(country) if country else None

    feature_bundles = build_disaster_feature_bundle(normalized_country, persist=True)
    forecasts = [predict_hazard_forecast(bundle) for bundle in feature_bundles]
    earthquake_history = (history_lookup or {}).get('earthquake') or {}
    wildfire_history = (history_lookup or {}).get('wildfire') or {}
    flood_history = (history_lookup or {}).get('flood') or {}
    cyclone_history = (history_lookup or {}).get('cyclone') or {}
    seismic_anomaly = compute_seismic_anomaly_scoring(country=normalized_country, limit=5, history_lookup=earthquake_history)
    earthquake_hotspots = (seismic_anomaly.get('regional_hotspots') or []) or build_regional_seismic_hotspots(limit=5, history_lookup=earthquake_history)
    wildfire_hotspots = build_regional_wildfire_hotspots(limit=5, history_lookup=wildfire_history, country=normalized_country)
    flood_hotspots = build_regional_flood_hotspots(limit=5, history_lookup=flood_history, country=normalized_country)
    cyclone_tracker = compute_cyclone_tracker(country=normalized_country, limit=5, history_lookup=cyclone_history)
    cyclone_hotspots = (cyclone_tracker.get('regional_hotspots') or []) or build_regional_cyclone_hotspots(limit=5, history_lookup=cyclone_history, country=normalized_country)
    seismic_forecasts = seismic_anomaly.get('forecasts') or []
    if seismic_forecasts:
        forecasts = [item for item in forecasts if str(item.get('event_type') or '') != 'earthquake']
        forecasts.append(seismic_forecasts[0])
    cyclone_tracker_forecasts = cyclone_tracker.get('forecasts') or []
    if cyclone_tracker_forecasts:
        forecasts = [item for item in forecasts if str(item.get('event_type') or '') != 'cyclone']
        forecasts.append(cyclone_tracker_forecasts[0])
    for hazard_name, hotspots in {
        'earthquake': earthquake_hotspots,
        'wildfire': wildfire_hotspots,
        'flood': flood_hotspots,
        'cyclone': cyclone_hotspots,
    }.items():
        if not hotspots:
            continue
        for forecast in forecasts:
            if forecast.get('event_type') == hazard_name:
                forecast['region'] = hotspots[0].get('region')
                forecast['region_name'] = hotspots[0].get('region_name')
                forecast['regional_hotspots_count'] = len(hotspots)
                break

    forecasts.sort(
        key=lambda item: (
            float(item.get('severity_score') or 0.0),
            float(item.get('likelihood') or 0.0),
            float(item.get('confidence') or 0.0),
        ),
        reverse=True,
    )
    forecasts = forecasts[:limit]

    source_families = sorted({
        str(source)
        for item in forecasts
        for source in (item.get('signal_sources') or [])
        if source
    }) or DISASTER_SOURCE_FAMILIES

    warning_count = sum(1 for item in forecasts if float(item.get('severity_score') or 0.0) >= 0.65)
    watch_count = sum(1 for item in forecasts if 0.4 <= float(item.get('severity_score') or 0.0) < 0.65)
    max_updated_at = max((str(item.get('updated_at') or now_utc.isoformat()) for item in forecasts), default=now_utc.isoformat())

    return {
        'generated_at': now_utc.isoformat(),
        'country': normalized_country or 'GLB',
        'source_families': source_families,
        'summary': {
            'critical_or_high_count': warning_count,
            'watch_count': watch_count,
            'top_hazard': forecasts[0]['event_type'] if forecasts else None,
            'top_seismic_region': earthquake_hotspots[0].get('region') if earthquake_hotspots else None,
            'top_seismic_region_name': earthquake_hotspots[0].get('region_name') if earthquake_hotspots else None,
            'top_wildfire_region': wildfire_hotspots[0].get('region') if wildfire_hotspots else None,
            'top_wildfire_region_name': wildfire_hotspots[0].get('region_name') if wildfire_hotspots else None,
            'top_flood_region': flood_hotspots[0].get('region') if flood_hotspots else None,
            'top_flood_region_name': flood_hotspots[0].get('region_name') if flood_hotspots else None,
            'top_cyclone_region': cyclone_hotspots[0].get('region') if cyclone_hotspots else None,
            'top_cyclone_region_name': cyclone_hotspots[0].get('region_name') if cyclone_hotspots else None,
        },
        'forecasts': forecasts,
        'regional_hotspots': {
            'earthquake': earthquake_hotspots,
            'wildfire': wildfire_hotspots,
            'flood': flood_hotspots,
            'cyclone': cyclone_hotspots,
        },
        'seismic_anomaly': seismic_anomaly,
        'cyclone_tracker': cyclone_tracker,
        'method': 'feature-builder plus hazard-specific runtime models with dedicated seismic anomaly scoring and cyclone tracking',
        'notes': [
            'This version fuses weather sensors, seismic feeds, satellite imagery proxies, ocean signals, and social media indicators from existing collections.',
            'Hazard-specific logistic models run at inference time with conservative weighted fallback if sklearn is unavailable.',
            'Earthquake output remains anomaly likelihood, not deterministic prediction.',
            'Regional hotspot layers expose seismic, wildfire, flood, and cyclone clusters through one shared hotspot system.',
            'Cyclone output is now enriched by a dedicated tracker that adds storm-path continuity and intensity outlook signals.',
            'Earthquake output is now enriched by a dedicated anomaly scorer that emphasizes swarm frequency, aftershock bursts, and conservative operator guardrails.',
            'Hotspot ordering uses hazard-specific calibrated activity scores rather than the main classifiers alone.',
            'Persisted hotspot history is incorporated when available to stabilize trend and alert scoring across refreshes.',
        ],
        'last_updated': max_updated_at,
    }


