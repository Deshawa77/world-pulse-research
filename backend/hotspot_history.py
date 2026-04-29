from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING

from processing.disaster_hotspot_regions import HOTSPOT_ALERT_BANDS, HOTSPOT_TREND_WINDOWS, iso_now


def ensure_hotspot_indexes(collection, summary_collection=None) -> None:
    collection.create_index([('snapshot_key', ASCENDING)], unique=True)
    collection.create_index([('hazard', ASCENDING), ('region', ASCENDING), ('captured_at', DESCENDING)])
    collection.create_index([('hazard', ASCENDING), ('region_name', ASCENDING), ('captured_at', DESCENDING)])
    collection.create_index([('hazard', ASCENDING), ('hotspot_band', ASCENDING), ('captured_at', DESCENDING)])
    if summary_collection is not None:
        summary_collection.create_index([('hazard', ASCENDING), ('summary_type', ASCENDING), ('bucket_start', DESCENDING), ('region', ASCENDING)])


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _snapshot_key(captured_at: datetime, hazard: str, region: str) -> str:
    bucket = captured_at.replace(minute=(captured_at.minute // 5) * 5, second=0, microsecond=0)
    return f"{hazard}:{region}:{bucket.isoformat()}"


def _normalize_hazard(value: Any) -> str:
    hazard = str(value or 'earthquake').strip().lower()
    return hazard or 'earthquake'


def _history_query(hours: int, hazard: str | None = None) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query: dict[str, Any] = {'captured_at': {'$gte': cutoff.isoformat()}}
    if hazard:
        query['hazard'] = _normalize_hazard(hazard)
    return query


def persist_hotspot_snapshots(collection, hotspots: list[dict[str, Any]], *, captured_at: str | None = None, hazard: str | None = None) -> dict[str, int]:
    captured_dt = _parse_dt(captured_at) or datetime.now(timezone.utc)
    inserted = 0
    updated = 0
    for hotspot in hotspots:
        region = str(hotspot.get('region') or '').strip()
        hazard_name = _normalize_hazard(hazard or hotspot.get('event_type'))
        if not region:
            continue
        doc = {
            'snapshot_key': _snapshot_key(captured_dt, hazard_name, region),
            'captured_at': captured_dt.isoformat(),
            'hazard': hazard_name,
            'event_type': hazard_name,
            'region': region,
            'region_name': hotspot.get('region_name'),
            'region_label': hotspot.get('region_label'),
            'display_label': hotspot.get('display_label'),
            'hotspot_band': hotspot.get('hotspot_band'),
            'activity_trend': hotspot.get('activity_trend'),
            'hotspot_score': hotspot.get('hotspot_score'),
            'hotspot_confidence': hotspot.get('hotspot_confidence'),
            'activity_score': hotspot.get('activity_score'),
            'center_lat': hotspot.get('center_lat'),
            'center_lon': hotspot.get('center_lon'),
            'trend_points': hotspot.get('trend_points') or [],
            'history': hotspot.get('history') or {},
            'signal_sources': hotspot.get('signal_sources') or [],
            'top_contributing_signals': hotspot.get('top_contributing_signals') or [],
            'hotspot_stats': hotspot.get('hotspot_stats') or {},
            'recommended_action': hotspot.get('recommended_action'),
            'lead_time_hours': hotspot.get('lead_time_hours'),
            'confidence': hotspot.get('confidence'),
            'severity_score': hotspot.get('severity_score'),
            'likelihood': hotspot.get('likelihood'),
        }
        result = collection.update_one({'snapshot_key': doc['snapshot_key']}, {'$set': doc}, upsert=True)
        if getattr(result, 'upserted_id', None) is not None:
            inserted += 1
        elif result.modified_count:
            updated += 1
    return {'inserted': inserted, 'updated': updated}


def load_recent_history_lookup(collection, *, hours: int = 72, points_per_region: int = 12, hazard: str | None = None) -> dict[str, list[dict[str, Any]]] | dict[str, dict[str, list[dict[str, Any]]]]:
    docs = collection.find(
        _history_query(hours, hazard=hazard),
        {'_id': 0, 'hazard': 1, 'region': 1, 'captured_at': 1, 'activity_score': 1, 'hotspot_band': 1, 'hotspot_score': 1},
    ).sort('captured_at', ASCENDING)
    by_hazard: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for doc in docs:
        region = str(doc.get('region') or '').strip()
        hazard_name = _normalize_hazard(doc.get('hazard'))
        if not region:
            continue
        by_hazard[hazard_name][region].append({
            'timestamp': doc.get('captured_at'),
            'activity': float(doc.get('activity_score') or doc.get('hotspot_score') or 0.0),
            'band': doc.get('hotspot_band') or 'guarded',
        })
    for hazard_name, region_map in list(by_hazard.items()):
        for region, entries in list(region_map.items()):
            by_hazard[hazard_name][region] = entries[-points_per_region:]
    if hazard:
        return dict(by_hazard.get(_normalize_hazard(hazard), {}))
    return {hazard_name: dict(region_map) for hazard_name, region_map in by_hazard.items()}


def _compute_delta(series: list[dict[str, Any]]) -> float:
    if len(series) < 2:
        return 0.0
    return round(float(series[-1].get('activity') or 0.0) - float(series[0].get('activity') or 0.0), 3)


def build_region_history_payload(collection, region: str, *, hours: int = 72, hazard: str | None = None) -> dict[str, Any]:
    docs = list(collection.find({**_history_query(hours, hazard=hazard), 'region': region}, {'_id': 0}).sort('captured_at', ASCENDING).limit(256))
    hazard_name = _normalize_hazard(hazard or (docs[-1].get('hazard') if docs else 'earthquake'))
    if not docs:
        return {
            'region': region,
            'hazard': hazard_name,
            'status': 'quiet',
            'history': {key: [] for key in HOTSPOT_TREND_WINDOWS},
            'latest': None,
            'delta_badge': {'label': 'quiet', 'delta': 0.0},
            'alert_history': [],
        }
    latest = docs[-1]
    history = {}
    for key, window_hours in HOTSPOT_TREND_WINDOWS.items():
        window_cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        series = [
            {
                'timestamp': row.get('captured_at'),
                'activity': float(row.get('activity_score') or row.get('hotspot_score') or 0.0),
                'band': row.get('hotspot_band') or 'guarded',
                'event_count': float(((row.get('hotspot_stats') or {}).get('event_count')) or ((row.get('hotspot_stats') or {}).get('quake_count')) or ((row.get('hotspot_stats') or {}).get('detection_count')) or 0.0),
                'intensity_peak': float(((row.get('hotspot_stats') or {}).get('intensity_peak')) or ((row.get('hotspot_stats') or {}).get('max_magnitude')) or ((row.get('hotspot_stats') or {}).get('max_temperature')) or 0.0),
                'quake_count': float(((row.get('hotspot_stats') or {}).get('quake_count')) or 0.0),
                'max_magnitude': float(((row.get('hotspot_stats') or {}).get('max_magnitude')) or 0.0),
                'max_temperature': float(((row.get('hotspot_stats') or {}).get('max_temperature')) or 0.0),
            }
            for row in docs
            if (_parse_dt(row.get('captured_at')) or datetime.now(timezone.utc)) >= window_cutoff
        ]
        history[key] = series
    transitions = []
    previous_band = None
    for row in docs:
        band = str(row.get('hotspot_band') or 'guarded')
        if band != previous_band:
            transitions.append({
                'hazard': _normalize_hazard(row.get('hazard')),
                'region': row.get('region'),
                'region_name': row.get('region_name'),
                'region_label': row.get('region_label'),
                'timestamp': row.get('captured_at'),
                'from_band': previous_band,
                'to_band': band,
                'activity': float(row.get('activity_score') or row.get('hotspot_score') or 0.0),
            })
        previous_band = band
    delta_24 = _compute_delta(history.get('24h') or [])
    return {
        'region': region,
        'hazard': hazard_name,
        'region_name': latest.get('region_name'),
        'region_label': latest.get('region_label'),
        'display_label': latest.get('display_label'),
        'status': 'active',
        'history': history,
        'latest': latest,
        'delta_badge': {
            'label': 'up' if delta_24 > 0.08 else 'down' if delta_24 < -0.08 else 'flat',
            'delta': delta_24,
        },
        'alert_history': transitions[-12:],
    }


def build_top_movers(collection, *, hours: int = 24, limit: int = 6, hazard: str | None = None) -> dict[str, list[dict[str, Any]]]:
    docs = list(collection.find(_history_query(hours, hazard=hazard), {'_id': 0, 'hazard': 1, 'region': 1, 'region_name': 1, 'region_label': 1, 'display_label': 1, 'captured_at': 1, 'activity_score': 1, 'hotspot_band': 1}).sort('captured_at', ASCENDING))
    series_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in docs:
        region = str(row.get('region') or '').strip()
        if not region:
            continue
        series_by_region[f"{_normalize_hazard(row.get('hazard'))}:{region}"] .append(row)
    movers = []
    for key, rows in series_by_region.items():
        delta = _compute_delta([{'activity': float(row.get('activity_score') or 0.0)} for row in rows])
        latest = rows[-1]
        movers.append({
            'hazard': _normalize_hazard(latest.get('hazard')),
            'region': latest.get('region'),
            'region_name': latest.get('region_name'),
            'region_label': latest.get('region_label'),
            'display_label': latest.get('display_label'),
            'delta': delta,
            'current_band': latest.get('hotspot_band') or 'guarded',
            'current_activity': float(latest.get('activity_score') or 0.0),
            'latest_timestamp': latest.get('captured_at') or iso_now(),
        })
    movers.sort(key=lambda item: item['delta'], reverse=True)
    return {
        'accelerating_fastest': movers[:limit],
        'cooling_fastest': sorted(movers, key=lambda item: item['delta'])[:limit],
    }


def build_alert_transitions(collection, *, hours: int = 72, limit: int = 20, hazard: str | None = None) -> list[dict[str, Any]]:
    docs = list(collection.find(_history_query(hours, hazard=hazard), {'_id': 0}).sort([('hazard', ASCENDING), ('region', ASCENDING), ('captured_at', ASCENDING)]))
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in docs:
        region = str(row.get('region') or '').strip()
        hazard_name = _normalize_hazard(row.get('hazard'))
        if region:
            by_region[f"{hazard_name}:{region}"] .append(row)
    transitions: list[dict[str, Any]] = []
    for _, rows in by_region.items():
        previous_band = None
        previous_activity = None
        for row in rows:
            band = str(row.get('hotspot_band') or 'guarded')
            activity = float(row.get('activity_score') or row.get('hotspot_score') or 0.0)
            if previous_band is not None and band != previous_band:
                transitions.append({
                    'hazard': _normalize_hazard(row.get('hazard')),
                    'region': row.get('region'),
                    'region_name': row.get('region_name'),
                    'region_label': row.get('region_label'),
                    'timestamp': row.get('captured_at'),
                    'from_band': previous_band,
                    'to_band': band,
                    'delta_activity': round(activity - float(previous_activity or 0.0), 3),
                })
            previous_band = band
            previous_activity = activity
    transitions.sort(key=lambda item: str(item.get('timestamp') or ''), reverse=True)
    return transitions[:limit]


def build_alert_queue(collection, *, hours: int = 24, limit: int = 10, hazard: str | None = None) -> list[dict[str, Any]]:
    docs = list(collection.find(_history_query(hours, hazard=hazard), {'_id': 0}).sort('captured_at', DESCENDING))
    latest_by_region: dict[str, dict[str, Any]] = {}
    for row in docs:
        region = str(row.get('region') or '').strip()
        hazard_name = _normalize_hazard(row.get('hazard'))
        key = f"{hazard_name}:{region}"
        if region and key not in latest_by_region:
            latest_by_region[key] = row
    queue = []
    for row in latest_by_region.values():
        band = str(row.get('hotspot_band') or 'guarded')
        activity = float(row.get('activity_score') or row.get('hotspot_score') or 0.0)
        if band == 'guarded' and activity < 0.3:
            continue
        queue.append({
            'hazard': _normalize_hazard(row.get('hazard')),
            'region': row.get('region'),
            'region_name': row.get('region_name'),
            'region_label': row.get('region_label'),
            'priority_band': band,
            'activity': activity,
            'confidence': float(row.get('hotspot_confidence') or 0.0),
            'timestamp': row.get('captured_at'),
            'signals': row.get('top_contributing_signals') or [],
            'display_label': row.get('display_label'),
            'signal_sources': row.get('signal_sources') or [],
            'top_contributing_signals': row.get('top_contributing_signals') or [],
            'recommended_action': row.get('recommended_action'),
            'lead_time_hours': row.get('lead_time_hours'),
        })
    queue.sort(key=lambda item: (HOTSPOT_ALERT_BANDS.index(str(item.get('priority_band') or 'guarded')), -float(item.get('activity') or 0.0)))
    return queue[:limit]


def summarize_history(summary_collection, history_collection, *, hours: int = 24, hazard: str | None = None) -> dict[str, int]:
    now_dt = datetime.now(timezone.utc)
    bucket_start = (now_dt - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    docs = list(history_collection.find({**_history_query(hours, hazard=hazard), 'captured_at': {'$gte': bucket_start.isoformat()}}, {'_id': 0}).sort('captured_at', ASCENDING))
    if not docs:
        return {'inserted': 0}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in docs:
        region = str(row.get('region') or '').strip()
        hazard_name = _normalize_hazard(row.get('hazard'))
        if region:
            grouped[f"{hazard_name}:{region}"] .append(row)
    inserted = 0
    for _, rows in grouped.items():
        activity_values = [float(row.get('activity_score') or row.get('hotspot_score') or 0.0) for row in rows]
        latest = rows[-1]
        doc = {
            'hazard': _normalize_hazard(latest.get('hazard')),
            'summary_type': 'hourly' if hours <= 24 else 'daily',
            'bucket_start': bucket_start.isoformat(),
            'region': latest.get('region'),
            'region_name': latest.get('region_name'),
            'region_label': latest.get('region_label'),
            'avg_activity': round(sum(activity_values) / len(activity_values), 4),
            'max_activity': round(max(activity_values), 4),
            'max_band': max((row.get('hotspot_band') or 'guarded' for row in rows), key=lambda band: HOTSPOT_ALERT_BANDS.index(str(band or 'guarded'))),
            'sample_count': len(rows),
            'updated_at': iso_now(),
        }
        summary_collection.update_one(
            {'hazard': doc['hazard'], 'summary_type': doc['summary_type'], 'bucket_start': doc['bucket_start'], 'region': doc['region']},
            {'$set': doc},
            upsert=True,
        )
        inserted += 1
    return {'inserted': inserted}


def prune_history(collection, *, retention_days: int = 30) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    result = collection.delete_many({'captured_at': {'$lt': cutoff}})
    return int(result.deleted_count)

