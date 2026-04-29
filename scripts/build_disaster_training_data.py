from __future__ import annotations

import argparse
import csv
import random
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.mongo import db
from processing.disaster_feature_builder import clamp, normalize_country, parse_dt, pick_nested, safe_float

OUTPUT_PATH = ROOT / 'data' / 'disaster_training_data.csv'
LOOKBACK_HOURS = 72
REAL_ROWS_PER_HAZARD = 700
RANDOM_SEED = 42

FIELDS = [
    'hazard',
    'severe_weather_keyword_score','wind_score','cold_wet_score','flood_signal_density','source_coverage','recency_score',
    'heat_score','smoke_keyword_score','wildfire_signal_density','dryness_proxy_score',
    'storm_keyword_score','storm_signal_density','ocean_proxy_score','pressure_proxy_score',
    'recent_quake_density','average_magnitude_score','major_quake_ratio','aftershock_cluster_score','max_magnitude_score','short_term_acceleration_score','strong_event_density','energy_proxy_score',
    'target_alert'
]


def _weather_rows() -> list[dict[str, Any]]:
    rows = []
    for doc in db['weather'].find({}, {'country': 1, 'data_country': 1, 'data.weather': 1, 'data.temperature': 1, 'data.temp': 1, 'data.wind_speed': 1, 'data_timestamp': 1, 'data.date': 1, 'data_weather': 1, 'data_temperature': 1, 'data_wind_speed': 1, 'collected_at': 1}):
        ts = parse_dt(pick_nested(doc, 'timestamp', 'data_timestamp', 'data.date', 'collected_at'))
        if not ts:
            continue
        rows.append({
            'ts': ts,
            'country': normalize_country(pick_nested(doc, 'country', 'data.country', 'data_country')),
            'text': str(pick_nested(doc, 'event', 'data.weather', 'data_weather', 'data.description', default='')).lower(),
            'wind': safe_float(pick_nested(doc, 'wind_speed', 'data.wind_speed', 'data_wind_speed')),
            'temp': safe_float(pick_nested(doc, 'temperature', 'data.temperature', 'data.temp', 'data_temperature')),
        })
    rows.sort(key=lambda item: item['ts'])
    return rows


def _world_state_rows() -> list[dict[str, Any]]:
    rows = []
    for doc in db['world_state_signals'].find({}, {'country': 1, 'source': 1, 'signal_type': 1, 'timestamp_utc': 1, 'timestamp': 1, 'value': 1, 'meta': 1, 'lat': 1, 'lon': 1}):
        ts = parse_dt(doc.get('timestamp_utc') or doc.get('timestamp'))
        if not ts:
            continue
        meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
        rows.append({
            'ts': ts,
            'country': normalize_country(doc.get('country')),
            'source': str(doc.get('source') or '').lower(),
            'signal_type': str(doc.get('signal_type') or '').lower(),
            'category': str(meta.get('category') or '').lower(),
            'value': safe_float(doc.get('value')),
            'meta': meta,
            'lat': doc.get('lat'),
            'lon': doc.get('lon'),
        })
    rows.sort(key=lambda item: item['ts'])
    return rows


def _seismic_region_key(lat: Any, lon: Any, grid_size: int = 40) -> str | None:
    if lat is None or lon is None:
        return None
    lat_value = safe_float(lat, default=float('nan'))
    lon_value = safe_float(lon, default=float('nan'))
    if lat_value != lat_value or lon_value != lon_value:
        return None
    lat_bucket = int((lat_value + 90.0) // grid_size)
    lon_bucket = int((lon_value + 180.0) // grid_size)
    return f'seismic_{lat_bucket:02d}_{lon_bucket:02d}'


def _seismic_rows(ws_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in ws_rows:
        if row['source'] != 'usgs':
            continue
        region = _seismic_region_key(row.get('lat'), row.get('lon'))
        if not region:
            continue
        mag = safe_float((row.get('meta') or {}).get('mag'), safe_float(row.get('value'), 0.0) * 8.0)
        rows.append({'ts': row['ts'], 'region': region, 'mag': mag})
    rows.sort(key=lambda item: item['ts'])
    return rows


def _times(rows: list[dict[str, Any]]) -> list[datetime]:
    return [row['ts'] for row in rows]


def _slice(rows: list[dict[str, Any]], times: list[datetime], start: datetime, end: datetime) -> list[dict[str, Any]]:
    return rows[bisect_left(times, start):bisect_right(times, end)]


def _compute_flood(anchor: datetime, weather_rows: list[dict[str, Any]], weather_times: list[datetime], ws_rows: list[dict[str, Any]], ws_times: list[datetime]) -> tuple[dict[str, float], int]:
    hist_weather = _slice(weather_rows, weather_times, anchor - timedelta(hours=LOOKBACK_HOURS), anchor)
    hist_ws = _slice(ws_rows, ws_times, anchor - timedelta(days=5), anchor)
    future_ws = _slice(ws_rows, ws_times, anchor, anchor + timedelta(hours=24))
    future_weather = _slice(weather_rows, weather_times, anchor, anchor + timedelta(hours=24))

    severe_weather_keyword_score = 0.0
    wind_score = 0.0
    cold_wet_score = 0.0
    flood_signal_count = 0
    source_hits = 0
    latest_signal = None

    for row in hist_weather:
        if any(token in row['text'] for token in ('flood', 'heavy rain', 'storm', 'overflow', 'monsoon')):
            severe_weather_keyword_score = 1.0
            source_hits += 1
            latest_signal = row['ts']
        wind_score = max(wind_score, clamp(row['wind'] / 160.0))
        if row['temp'] <= 12:
            cold_wet_score = max(cold_wet_score, clamp((12.0 - row['temp']) / 12.0))

    for row in hist_ws:
        if 'flood' in row['category'] or 'storm' in row['category']:
            flood_signal_count += 1
            source_hits += 1
            latest_signal = row['ts']

    label = int(
        any('flood' in row['category'] or 'storm' in row['category'] for row in future_ws)
        or any(any(token in row['text'] for token in ('flood', 'heavy rain', 'storm', 'overflow', 'monsoon')) for row in future_weather)
    )
    recency_score = clamp(1.0 - ((anchor - latest_signal).total_seconds() / (72 * 3600))) if latest_signal else 0.0
    return {
        'severe_weather_keyword_score': round(severe_weather_keyword_score, 4),
        'wind_score': round(wind_score, 4),
        'cold_wet_score': round(cold_wet_score, 4),
        'flood_signal_density': round(clamp(flood_signal_count / 8.0), 4),
        'source_coverage': round(clamp(source_hits / 10.0), 4),
        'recency_score': round(recency_score, 4),
    }, label


def _compute_wildfire(anchor: datetime, weather_rows: list[dict[str, Any]], weather_times: list[datetime], ws_rows: list[dict[str, Any]], ws_times: list[datetime]) -> tuple[dict[str, float], int]:
    hist_weather = _slice(weather_rows, weather_times, anchor - timedelta(hours=LOOKBACK_HOURS), anchor)
    hist_ws = _slice(ws_rows, ws_times, anchor - timedelta(days=5), anchor)
    future_ws = _slice(ws_rows, ws_times, anchor, anchor + timedelta(hours=18))
    future_weather = _slice(weather_rows, weather_times, anchor, anchor + timedelta(hours=18))

    heat_score = 0.0
    wind_score = 0.0
    smoke_keyword_score = 0.0
    wildfire_signal_count = 0
    dryness_proxy_score = 0.0
    source_hits = 0
    latest_signal = None

    for row in hist_weather:
        if row['temp'] >= 34:
            heat_score = max(heat_score, clamp((row['temp'] - 30.0) / 18.0))
            dryness_proxy_score = max(dryness_proxy_score, clamp((row['temp'] - 25.0) / 20.0))
            source_hits += 1
            latest_signal = row['ts']
        if row['wind'] >= 30:
            wind_score = max(wind_score, clamp(row['wind'] / 120.0))
        if any(token in row['text'] for token in ('wildfire', 'smoke', 'dry', 'heatwave')):
            smoke_keyword_score = 1.0
            source_hits += 1
            latest_signal = row['ts']

    for row in hist_ws:
        if row['source'] == 'firms' or 'wildfire' in row['category']:
            wildfire_signal_count += 1
            source_hits += 1
            latest_signal = row['ts']

    label = int(
        any(row['source'] == 'firms' or 'wildfire' in row['category'] for row in future_ws)
        or any(any(token in row['text'] for token in ('wildfire', 'smoke', 'dry', 'heatwave')) for row in future_weather)
    )
    recency_score = clamp(1.0 - ((anchor - latest_signal).total_seconds() / (72 * 3600))) if latest_signal else 0.0
    return {
        'heat_score': round(heat_score, 4),
        'wind_score': round(wind_score, 4),
        'smoke_keyword_score': round(smoke_keyword_score, 4),
        'wildfire_signal_density': round(clamp(wildfire_signal_count / 8.0), 4),
        'dryness_proxy_score': round(dryness_proxy_score, 4),
        'source_coverage': round(clamp(source_hits / 10.0), 4),
        'recency_score': round(recency_score, 4),
    }, label


def _compute_cyclone(anchor: datetime, weather_rows: list[dict[str, Any]], weather_times: list[datetime], ws_rows: list[dict[str, Any]], ws_times: list[datetime]) -> tuple[dict[str, float], int]:
    hist_weather = _slice(weather_rows, weather_times, anchor - timedelta(hours=LOOKBACK_HOURS), anchor)
    hist_ws = _slice(ws_rows, ws_times, anchor - timedelta(days=5), anchor)
    future_ws = _slice(ws_rows, ws_times, anchor, anchor + timedelta(hours=48))
    future_weather = _slice(weather_rows, weather_times, anchor, anchor + timedelta(hours=48))

    storm_keyword_score = 0.0
    wind_score = 0.0
    storm_signal_count = 0
    ocean_proxy_score = 0.0
    pressure_proxy_score = 0.0
    source_hits = 0
    latest_signal = None

    for row in hist_weather:
        if row['wind'] >= 45:
            wind_score = max(wind_score, clamp(row['wind'] / 160.0))
            pressure_proxy_score = max(pressure_proxy_score, clamp(row['wind'] / 180.0))
            source_hits += 1
            latest_signal = row['ts']
        if any(token in row['text'] for token in ('cyclone', 'hurricane', 'typhoon', 'tropical storm', 'storm')):
            storm_keyword_score = 1.0
            ocean_proxy_score = max(ocean_proxy_score, clamp((row['temp'] - 24.0) / 12.0))
            source_hits += 1
            latest_signal = row['ts']

    for row in hist_ws:
        if 'cyclone' in row['category'] or 'hurricane' in row['category'] or 'severe storms' in row['category'] or 'storm' in row['category']:
            storm_signal_count += 1
            source_hits += 1
            latest_signal = row['ts']

    label = int(
        any('cyclone' in row['category'] or 'hurricane' in row['category'] or 'severe storms' in row['category'] or 'storm' in row['category'] for row in future_ws)
        or any(any(token in row['text'] for token in ('cyclone', 'hurricane', 'typhoon', 'tropical storm', 'storm')) for row in future_weather)
    )
    recency_score = clamp(1.0 - ((anchor - latest_signal).total_seconds() / (72 * 3600))) if latest_signal else 0.0
    return {
        'storm_keyword_score': round(storm_keyword_score, 4),
        'wind_score': round(wind_score, 4),
        'storm_signal_density': round(clamp(storm_signal_count / 8.0), 4),
        'ocean_proxy_score': round(ocean_proxy_score, 4),
        'pressure_proxy_score': round(pressure_proxy_score, 4),
        'source_coverage': round(clamp(source_hits / 10.0), 4),
        'recency_score': round(recency_score, 4),
    }, label


def _compute_earthquake(anchor: datetime, region: str, seismic_rows: list[dict[str, Any]], seismic_times: list[datetime]) -> tuple[dict[str, float], int]:
    hist_rows = [row for row in _slice(seismic_rows, seismic_times, anchor - timedelta(hours=72), anchor) if row['region'] == region]
    future_rows = [row for row in _slice(seismic_rows, seismic_times, anchor, anchor + timedelta(hours=12)) if row['region'] == region]

    recent_quake_count = len([row for row in hist_rows if row['mag'] > 0])
    magnitude_sum = sum(row['mag'] for row in hist_rows if row['mag'] > 0)
    major_count = sum(1 for row in hist_rows if row['mag'] >= 5.5)
    strong_count = sum(1 for row in hist_rows if row['mag'] >= 4.5)
    max_mag = max([row['mag'] for row in hist_rows], default=0.0)
    energy_proxy_total = sum(max(0.0, row['mag']) ** 2 for row in hist_rows)
    recent_24h_count = sum(1 for row in hist_rows if row['ts'] >= anchor - timedelta(hours=24))
    prior_48h_count = sum(1 for row in hist_rows if row['ts'] < anchor - timedelta(hours=24))
    latest_signal = max([row['ts'] for row in hist_rows], default=None)

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
    recency_score = clamp(1.0 - ((anchor - latest_signal).total_seconds() / (72 * 3600))) if latest_signal else 0.0

    future_max_mag = max([row['mag'] for row in future_rows], default=0.0)
    future_major_count = sum(1 for row in future_rows if row['mag'] >= 3.0)
    future_strong_count = sum(1 for row in future_rows if row['mag'] >= 2.5)
    label = int(
        future_max_mag >= 3.0
        or (future_max_mag >= 2.7 and future_strong_count >= 2)
        or future_major_count >= 2
    )

    return {
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
    }, label


def _base_row(hazard: str) -> dict[str, Any]:
    row = {field: 0.0 for field in FIELDS}
    row['hazard'] = hazard
    return row


def _sample_anchors(times: list[datetime], max_rows: int) -> list[datetime]:
    if not times:
        return []
    if len(times) <= max_rows:
        return times
    step = max(1, len(times) // max_rows)
    sampled = times[::step]
    return sampled[:max_rows]


def build_dataset(output_path: Path = OUTPUT_PATH, rows_per_hazard: int = REAL_ROWS_PER_HAZARD) -> dict[str, Any]:
    random.seed(RANDOM_SEED)
    weather_rows = _weather_rows()
    ws_rows = _world_state_rows()
    seismic_rows = _seismic_rows(ws_rows)
    weather_times = _times(weather_rows)
    ws_times = _times(ws_rows)
    seismic_times = _times(seismic_rows)

    hazard_anchor_times = {
        'flood': _sample_anchors(weather_times + ws_times, rows_per_hazard * 2),
        'wildfire': _sample_anchors(weather_times + ws_times, rows_per_hazard * 2),
        'cyclone': _sample_anchors(weather_times + ws_times, rows_per_hazard * 2),
        'earthquake': _sample_anchors(seismic_times, rows_per_hazard * 4),
    }

    rows = []
    summary: dict[str, Any] = {}
    for hazard, anchors in hazard_anchor_times.items():
        anchors = sorted(anchors)
        positives = []
        negatives = []
        for anchor in anchors:
            if hazard == 'flood':
                features, label = _compute_flood(anchor, weather_rows, weather_times, ws_rows, ws_times)
            elif hazard == 'wildfire':
                features, label = _compute_wildfire(anchor, weather_rows, weather_times, ws_rows, ws_times)
            elif hazard == 'cyclone':
                features, label = _compute_cyclone(anchor, weather_rows, weather_times, ws_rows, ws_times)
            else:
                candidate_region_rows = [row for row in _slice(seismic_rows, seismic_times, anchor - timedelta(hours=6), anchor + timedelta(hours=1))]
                if not candidate_region_rows:
                    continue
                region_counts: dict[str, int] = {}
                for seismic_row in candidate_region_rows:
                    region_counts[seismic_row['region']] = region_counts.get(seismic_row['region'], 0) + 1
                region = max(region_counts, key=region_counts.get)
                features, label = _compute_earthquake(anchor, region, seismic_rows, seismic_times)
            row = _base_row(hazard)
            row.update(features)
            row['target_alert'] = int(label)
            if label:
                positives.append(row)
            else:
                negatives.append(row)

        target_each = min(len(positives), len(negatives), rows_per_hazard // 2)
        if target_each == 0:
            target_each = min(rows_per_hazard, len(positives) + len(negatives))
            selected = (positives + negatives)[:target_each]
        else:
            random.shuffle(positives)
            random.shuffle(negatives)
            selected = positives[:target_each] + negatives[:target_each]
        random.shuffle(selected)
        rows.extend(selected)
        summary[hazard] = {
            'anchors_examined': len(anchors),
            'rows_written': len(selected),
            'positive_rows_available': len(positives),
            'negative_rows_available': len(negatives),
            'positive_rows_written': sum(1 for row in selected if row['target_alert'] == 1),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return {
        'output_path': str(output_path),
        'total_rows': len(rows),
        'hazards': summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Build historical disaster training data from real project sources')
    parser.add_argument('--output', default=str(OUTPUT_PATH))
    parser.add_argument('--rows-per-hazard', type=int, default=REAL_ROWS_PER_HAZARD)
    args = parser.parse_args()
    result = build_dataset(Path(args.output), rows_per_hazard=args.rows_per_hazard)
    print(result)


if __name__ == '__main__':
    main()




