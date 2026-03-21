import hashlib
import math
import json
import os
import time
from datetime import datetime, timedelta, timezone

from backend.kafka_client import get_consumer, send_to_kafka
from collectors.country_news import get_country_catalog
from database.mongo import db, write_country_features_v2
from processing.country_incremental_risk import recompute_country_risk
from processing.nlp_analysis import analyze_text, clean_text
from processing.country_signal_fusion import CITY_TO_COUNTRY, COMMON_COUNTRY_ALIASES
from processing.spillover_graph import load_country_spillover_map
from processing.signal_taxonomy import build_signal_metadata

RAW_SOURCE_TOPICS = [
    'news_topic', 'gdelt_topic', 'reddit_topic', 'trends_topic', 'weather_topic', 'stocks_topic', 'crypto_topic', 'wiki_pageviews', 'wiki', 'telegram_public_topic', 'telegram_public', 'youtube_trends_topic', 'youtube_trends', 'mobility_topic', 'mobility', 'aviation_topic', 'aviation', 'logistics_topic', 'logistics', 'economic_behavior_topic', 'economic_behavior', 'worldbank_behavior_topic', 'worldbank_behavior', 'energy_stress_topic', 'energy_stress',
    'news', 'media', 'trends', 'weather', 'stocks', 'crypto',
]
NORMALIZED_TOPIC = 'country_source_events'
UPDATE_TOPIC = 'country_risk_updates'
DLQ_TOPIC = 'country_risk_dlq'
CONSUMER_GROUP = 'country-risk-events-v1'
RISK_CONSUMER_GROUP = 'country-risk-updates-v1'
SERVICE_NAME = 'country_risk_stream'


def _utc_day_bounds(day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _normalize_text(value):
    return str(value or '').strip().lower()


def _parse_timestamp(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return datetime.now(timezone.utc)
    raw = str(value).strip()
    if not raw:
        return datetime.now(timezone.utc)
    try:
        if raw.endswith('Z') and raw[:-1].isdigit() and len(raw[:-1]) == 14:
            return datetime.strptime(raw, '%Y%m%d%H%M%SZ').replace(tzinfo=timezone.utc)
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _build_alias_map():
    catalog = get_country_catalog()
    alias_map = {}
    for code, name in catalog.items():
        aliases = {_normalize_text(name)}
        aliases.update({_normalize_text(v) for v in COMMON_COUNTRY_ALIASES.get(code, set())})
        alias_map[code] = {alias for alias in aliases if alias}
    return alias_map


ALIAS_MAP = _build_alias_map()
STOCK_COUNTRY_MAP = {
    'AAPL': 'USA', 'MSFT': 'USA', 'GOOGL': 'USA', 'AMZN': 'USA', 'TSLA': 'USA',
    'NVDA': 'USA', 'META': 'USA', 'SPY': 'USA',
}
CRYPTO_COUNTRY_MAP = {
    'bitcoin': 'USA',
    'ethereum': 'USA',
}

COUNTRY_SPILLOVER_MAP = load_country_spillover_map()

COUNTRY_RISK_DELTA_FIELDS = (
    'direct_behavior_score', 'contextual_pressure_score', 'evidence_quality_score', 'social_unrest_score', 'google_trends_pressure',
    'public_attention_score', 'narrative_velocity_score', 'coordination_risk_score', 'mobility_disruption_score', 'aviation_disruption_score',
    'logistics_stress_score', 'household_stress_score', 'fuel_price_pressure', 'food_price_pressure', 'labor_stress_score', 'fx_pressure_score',
    'remittance_stress_score', 'energy_stress_score', 'weather_stress',
)


def _safe_float(value):
    try:
        number = float(value or 0.0)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _risk_trend_direction(delta_24h, delta_7d):
    reference = delta_24h if abs(delta_24h) >= 0.75 else delta_7d
    if reference >= 0.75:
        return 'worsening'
    if reference <= -0.75:
        return 'improving'
    return 'stable'


def _compute_country_deltas(country_code):
    docs = list(db.country_features.find({'country': country_code, 'mode': 'online'}).sort('timestamp', -1).limit(8))
    if not docs:
        return 0.0, 0.0, 'stable', []
    ordered = sorted(docs, key=lambda d: _parse_timestamp(d.get('timestamp')))
    latest = ordered[-1].get('features', {}) if isinstance(ordered[-1].get('features'), dict) else {}
    previous = ordered[-2].get('features', {}) if len(ordered) >= 2 and isinstance(ordered[-2].get('features'), dict) else latest
    earliest = ordered[0].get('features', {}) if isinstance(ordered[0].get('features'), dict) else latest
    latest_risk = _safe_float(latest.get('global_risk_score'))
    previous_risk = _safe_float(previous.get('global_risk_score'))
    earliest_risk = _safe_float(earliest.get('global_risk_score'))
    delta_24h = round(latest_risk - previous_risk, 2)
    delta_7d = round(latest_risk - earliest_risk, 2)
    contributors = []
    for field in COUNTRY_RISK_DELTA_FIELDS:
        current_value = _safe_float(latest.get(field))
        previous_value = _safe_float(previous.get(field))
        delta = current_value - previous_value
        if abs(delta) < 0.25:
            continue
        contributors.append({
            'feature': field,
            'value': round(current_value, 4),
            'delta': round(delta, 4),
            'contribution': round(delta / 100.0, 4),
        })
    contributors.sort(key=lambda item: abs(_safe_float(item.get('delta'))), reverse=True)
    return delta_24h, delta_7d, _risk_trend_direction(delta_24h, delta_7d), contributors[:4]


def _spillover_links(country_code):
    spillovers = []
    for item in COUNTRY_SPILLOVER_MAP.get(country_code, []):
        neighbor = db.country_features.find_one({'country': item['country'], 'mode': 'online'}, sort=[('timestamp', -1)])
        features = neighbor.get('features', {}) if isinstance((neighbor or {}).get('features'), dict) else {}
        if not neighbor:
            continue
        spillovers.append({
            'country': item['country'],
            'risk': round(_safe_float(features.get('global_risk_score')), 2),
            'relationship': item['relationship'],
        })
    spillovers.sort(key=lambda item: _safe_float(item.get('risk')), reverse=True)
    return spillovers[:4]


def _match_countries(text):
    norm_text = _normalize_text(text)
    matched = set()
    for code, aliases in ALIAS_MAP.items():
        if any(alias and alias in norm_text for alias in aliases):
            matched.add(code)
    return matched


def _event_id(topic, country, timestamp, source, payload):
    raw = json.dumps({'topic': topic, 'country': country, 'timestamp': timestamp, 'source': source, 'payload': payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _enrich_sentiment(title, description=''):
    text = f"{title or ''}. {description or ''}".strip()
    if not text:
        return None
    try:
        cleaned = clean_text(text)
        analysis = analyze_text(cleaned)
        sentiment = analysis.get('sentiment') if isinstance(analysis, dict) else None
        compound = None
        if isinstance(sentiment, dict):
            compound = sentiment.get('vader', {}).get('compound')
        if compound is None and isinstance(analysis, dict):
            compound = analysis.get('compound')
        return {'vader': {'compound': float(compound or 0.0)}}
    except Exception:
        return {'vader': {'compound': 0.0}}


def normalize_record(topic, record):
    source = str(record.get('source') or topic).lower()
    events = []

    if topic in {'news_topic', 'news', 'media', 'gdelt_topic'}:
        data = record.get('data') or {}
        title = data.get('title') or ''
        description = data.get('description') or ''
        timestamp = _parse_timestamp(data.get('published_at') or record.get('collected_at'))
        countries = _match_countries(' '.join([str(data.get('query') or ''), str(title), str(description)]))
        for country in countries:
            payload = {
                'title': title,
                'description': description,
                'url': data.get('url'),
                'language': data.get('language'),
                'published_at': timestamp.isoformat(),
                'query': data.get('query'),
                'sentiment': data.get('sentiment') or _enrich_sentiment(title, description),
            }
            normalized_source = 'gdelt' if 'gdelt' in source or topic == 'gdelt_topic' else 'newsapi'
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': normalized_source,
                'topic': topic,
                **build_signal_metadata(
                    source=normalized_source,
                    observed_at=timestamp,
                    language=payload.get('language'),
                    confidence=0.72 if normalized_source == 'newsapi' else 0.78,
                    coverage_weight=1.0,
                ),
                'payload': payload,
            })

    elif topic in {'reddit_topic'}:
        data = record.get('data') or {}
        title = data.get('title') or ''
        text = data.get('text') or ''
        timestamp = _parse_timestamp(data.get('created_utc') or record.get('collected_at'))
        countries = _match_countries(' '.join([str(data.get('query') or ''), str(title), str(text), str(data.get('subreddit') or '')]))
        for country in countries:
            payload = {
                'title': title,
                'description': text,
                'score': float(data.get('score') or 0.0),
                'subreddit': data.get('subreddit'),
                'url': data.get('url'),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'reddit',
                'topic': topic,
                **build_signal_metadata(
                    source='reddit',
                    observed_at=timestamp,
                    language='en',
                    confidence=0.55,
                    coverage_weight=0.65,
                ),
                'payload': payload,
            })

    elif topic in {'telegram_public_topic', 'telegram_public'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp'))
            payload = {
                'post_count': int(data.get('post_count') or 0),
                'unique_channels': int(data.get('unique_channels') or 0),
                'narrative_velocity_score': float(data.get('narrative_velocity_score') or 0.0),
                'coordination_risk_score': float(data.get('coordination_risk_score') or 0.0),
                'social_unrest_score': float(data.get('social_unrest_score') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'telegram_public',
                'topic': topic,
                **build_signal_metadata(source='telegram_public', observed_at=timestamp, language='und', confidence=0.62, coverage_weight=0.55),
                'payload': payload,
            })

    elif topic in {'youtube_trends_topic', 'youtube_trends'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp'))
            payload = {
                'video_count': int(data.get('video_count') or 0),
                'unique_channels': int(data.get('unique_channels') or 0),
                'public_attention_score': float(data.get('public_attention_score') or 0.0),
                'narrative_velocity_score': float(data.get('narrative_velocity_score') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'youtube_public',
                'topic': topic,
                **build_signal_metadata(source='youtube_public', observed_at=timestamp, language='und', confidence=0.64, coverage_weight=0.58),
                'payload': payload,
            })

    elif topic in {'wiki_pageviews', 'wiki'}:
        data = record.get('data') or {}
        article = str(data.get('article') or data.get('title') or '')
        timestamp = _parse_timestamp(record.get('collected_at') or data.get('date'))
        explicit_country = str(record.get('country') or '').strip().upper()
        countries = {explicit_country} if explicit_country else _match_countries(article)
        for country in countries:
            payload = {
                'article': article,
                'views': float(data.get('views') or 0.0),
                'previous_views': float(data.get('previous_views') or 0.0),
                'view_delta_ratio': float(data.get('view_delta_ratio') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'wikipedia',
                'topic': topic,
                **build_signal_metadata(
                    source='wikipedia',
                    observed_at=timestamp,
                    language='en',
                    confidence=0.66,
                    coverage_weight=0.75,
                ),
                'payload': payload,
            })

    elif topic in {'aviation_topic', 'aviation'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp') or data.get('snapshot_at'))
            payload = {
                'aircraft_count': float(data.get('aircraft_count') or 0.0),
                'on_ground_count': float(data.get('on_ground_count') or 0.0),
                'avg_velocity_mps': float(data.get('avg_velocity_mps') or 0.0),
                'aviation_disruption_score': float(data.get('aviation_disruption_score') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'opensky',
                'topic': topic,
                **build_signal_metadata(
                    source='opensky',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.71,
                    coverage_weight=0.72,
                ),
                'payload': payload,
            })

    elif topic in {'mobility_topic', 'mobility'}:
        data = record.get('data') or {}
        country = str(record.get('country') or data.get('origin_country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp') or data.get('year'))
            payload = {
                'year': int(data.get('year') or 0),
                'origin_country': country,
                'host_country': data.get('host_country'),
                'displaced_people': float(data.get('displaced_people') or 0.0),
                'previous_displaced_people': float(data.get('previous_displaced_people') or 0.0) if data.get('previous_displaced_people') not in (None, '') else 0.0,
                'displacement_delta_ratio': float(data.get('displacement_delta_ratio') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'unhcr_idmc',
                'topic': topic,
                **build_signal_metadata(
                    source='unhcr_idmc',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.82,
                    coverage_weight=0.88,
                ),
                'payload': payload,
            })

    elif topic in {'logistics_topic', 'logistics'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp'))
            payload = {
                'logistics_stress_score': float(data.get('logistics_stress_score') or 0.0),
                'logistics_performance': float(data.get('logistics_performance') or 0.0),
                'container_port_traffic': float(data.get('container_port_traffic') or 0.0),
                'air_freight': float(data.get('air_freight') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'logistics',
                'topic': topic,
                **build_signal_metadata(source='logistics', observed_at=timestamp, language='und', confidence=0.68, coverage_weight=0.62),
                'payload': payload,
            })

    elif topic in {'economic_behavior_topic', 'economic_behavior'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp') or data.get('fuel_price_date') or data.get('food_price_date'))
            payload = {
                'household_stress_score': float(data.get('household_stress_score') or 0.0),
                'fuel_price_pressure': float(data.get('fuel_price_pressure') or 0.0),
                'food_price_pressure': float(data.get('food_price_pressure') or 0.0),
                'labor_stress_score': float(data.get('labor_stress_score') or 0.0),
                'fx_pressure_score': float(data.get('fx_pressure_score') or 0.0),
                'remittance_stress_score': float(data.get('remittance_stress_score') or 0.0),
                'energy_stress_score': float(data.get('energy_stress_score') or 0.0),
                'inflation_rate': float(data.get('inflation_rate') or 0.0),
                'unemployment_rate': float(data.get('unemployment_rate') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'economic_behavior',
                'topic': topic,
                **build_signal_metadata(
                    source='economic_behavior',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.76,
                    coverage_weight=0.8,
                    signal_domain='economic_behavior',
                    signal_type='household_labor_pressure',
                    signal_class='direct',
                    source_tier='public_institution',
                ),
                'payload': payload,
            })

    elif topic in {'worldbank_behavior_topic', 'worldbank_behavior'}:
        data = record.get('data') or {}
        country = str(record.get('country') or '').strip().upper()
        if country:
            timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp'))
            payload = {
                'household_stress_score': 0.0,
                'fuel_price_pressure': 0.0,
                'food_price_pressure': 0.0,
                'labor_stress_score': 0.0,
                'fx_pressure_score': 0.0,
                'remittance_stress_score': float(data.get('remittance_stress_score') or 0.0),
                'energy_stress_score': float(data.get('energy_dependency_score') or 0.0),
                'inflation_rate': float(data.get('inflation_rate') or 0.0),
                'unemployment_rate': float(data.get('unemployment_rate') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'economic_behavior',
                'topic': topic,
                **build_signal_metadata(
                    source='economic_behavior',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.79,
                    coverage_weight=0.72,
                    signal_domain='economic_behavior',
                    signal_type='remittance_energy_pressure',
                    signal_class='direct',
                    source_tier='public_institution',
                ),
                'payload': payload,
            })

    elif topic in {'energy_stress_topic', 'energy_stress'}:
        data = record.get('data') or {}
        timestamp = _parse_timestamp(record.get('collected_at') or record.get('timestamp') or data.get('fuel_price_date') or data.get('energy_price_date'))
        for country in get_country_catalog().keys():
            payload = {
                'household_stress_score': 0.0,
                'fuel_price_pressure': float(data.get('fuel_price_pressure') or 0.0),
                'food_price_pressure': 0.0,
                'labor_stress_score': 0.0,
                'fx_pressure_score': 0.0,
                'remittance_stress_score': 0.0,
                'energy_stress_score': float(data.get('energy_stress_score') or 0.0),
                'inflation_rate': 0.0,
                'unemployment_rate': 0.0,
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'economic_behavior',
                'topic': topic,
                **build_signal_metadata(
                    source='economic_behavior',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.74,
                    coverage_weight=0.66,
                    signal_domain='economic_behavior',
                    signal_type='energy_cost_pressure',
                    signal_class='contextual',
                    source_tier='public_institution',
                ),
                'payload': payload,
            })

    elif topic in {'trends_topic', 'trends'}:
        data = record.get('data') or {}
        keyword = str(data.get('keyword') or '')
        timestamp = _parse_timestamp(data.get('date') or record.get('collected_at'))
        countries = _match_countries(keyword)
        for country in countries:
            payload = {
                'keyword': keyword,
                'interest': int(data.get('interest') or 0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'google_trends',
                'topic': topic,
                **build_signal_metadata(
                    source='google_trends',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.68,
                    coverage_weight=0.85,
                ),
                'payload': payload,
            })

    elif topic in {'weather_topic', 'weather'}:
        city = _normalize_text(record.get('data_city'))
        country = CITY_TO_COUNTRY.get(city)
        if country:
            timestamp = _parse_timestamp(record.get('data_timestamp') or record.get('collected_at'))
            payload = {
                'city': record.get('data_city'),
                'temperature': float(record.get('data_temperature') or 0.0),
                'temperature_normalized': float(record.get('data_temperature_normalized') or 0.0),
                'humidity': float(record.get('data_humidity') or 0.0),
                'weather': record.get('data_weather'),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'weather',
                'topic': topic,
                **build_signal_metadata(
                    source='weather',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.81,
                    coverage_weight=0.9,
                ),
                'payload': payload,
            })

    elif topic in {'stocks_topic', 'stocks'}:
        symbol = str(record.get('data_symbol') or '').upper().strip()
        country = STOCK_COUNTRY_MAP.get(symbol)
        if country:
            timestamp = _parse_timestamp(record.get('data_datetime') or record.get('collected_at'))
            payload = {
                'symbol': symbol,
                'close': float(record.get('data_close') or 0.0),
                'volume': float(record.get('data_volume') or 0.0),
                'close_normalized': float(record.get('data_close_normalized') or 0.0),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'stocks',
                'topic': topic,
                **build_signal_metadata(
                    source='stocks',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.84,
                    coverage_weight=0.7,
                ),
                'payload': payload,
            })

    elif topic in {'crypto_topic', 'crypto'}:
        coin_id = str(record.get('data_coin_id') or '').lower().strip()
        country = CRYPTO_COUNTRY_MAP.get(coin_id)
        if country:
            timestamp = _parse_timestamp(record.get('data_timestamp') or record.get('collected_at'))
            payload = {
                'coin_id': coin_id,
                'price': float(record.get('data_price') or 0.0),
                'vs_currency': record.get('data_vs_currency'),
            }
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'crypto',
                'topic': topic,
                **build_signal_metadata(
                    source='crypto',
                    observed_at=timestamp,
                    language='und',
                    confidence=0.76,
                    coverage_weight=0.65,
                ),
                'payload': payload,
            })

    normalized = []
    for event in events:
        event['event_id'] = _event_id(topic, event['country'], event['timestamp'], event['source'], event['payload'])
        event['event_date'] = event['timestamp'][:10]
        normalized.append(event)
    return normalized


def _store_country_side_effects(event):
    source = event.get('source')
    payload = event.get('payload') or {}
    country = event.get('country')
    timestamp = _parse_timestamp(event.get('timestamp'))

    if source in {'newsapi', 'gdelt'}:
        db.country_news.update_one(
            {'event_id': event['event_id']},
            {'$setOnInsert': {
                'event_id': event['event_id'],
                'source': source,
                'category': 'global_news',
                'country': country,
                'country_name': get_country_catalog().get(country, country),
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'signal_domain': event.get('signal_domain'),
                'signal_type': event.get('signal_type'),
                'signal_class': event.get('signal_class'),
                'source_tier': event.get('source_tier'),
                'geo_scope': event.get('geo_scope'),
                'language': event.get('language'),
                'observed_at': event.get('observed_at'),
                'ingested_at': event.get('ingested_at'),
                'confidence': event.get('confidence'),
                'coverage_weight': event.get('coverage_weight'),
                'data': {
                    'title': payload.get('title'),
                    'description': payload.get('description'),
                    'url': payload.get('url'),
                    'language': payload.get('language'),
                    'published_at': payload.get('published_at'),
                    'query': payload.get('query'),
                    'sentiment': payload.get('sentiment'),
                },
                'timestamp': timestamp,
            }},
            upsert=True,
        )


def _update_rollup(event):
    event_date = event['event_date']
    country = event['country']
    source = event['source']
    payload = event.get('payload') or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        '$setOnInsert': {'country': country, 'event_date': event_date, 'created_at': now_iso},
        '$set': {'updated_at': now_iso},
        '$addToSet': {'sources': source, 'event_ids': event['event_id']},
        '$inc': {f'counts.{source}': 1, 'total_events': 1},
        '$max': {'last_event_timestamp': event['timestamp']},
    }
    if source == 'reddit':
        score = min((payload.get('score') or 0.0) / 1000.0, 1.0)
        update['$max']['social_unrest_score'] = round(score, 4)
    elif source == 'google_trends':
        update['$max']['google_trends_pressure'] = round(min((payload.get('interest') or 0) / 100.0, 1.0), 4)
    elif source == 'wikipedia':
        views = float(payload.get('views') or 0.0)
        delta_ratio = max(float(payload.get('view_delta_ratio') or 0.0), 0.0)
        attention_score = min((math.log1p(max(views, 0.0)) / 12.0) + (delta_ratio * 0.35), 1.0)
        update['$max']['public_attention_score'] = round(attention_score, 4)
    elif source == 'telegram_public':
        update['$max']['narrative_velocity_score'] = round(min(max(float(payload.get('narrative_velocity_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['coordination_risk_score'] = round(min(max(float(payload.get('coordination_risk_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['social_unrest_score'] = round(min(max(float(payload.get('social_unrest_score') or 0.0), 0.0), 1.0), 4)
    elif source == 'youtube_public':
        update['$max']['public_attention_score'] = round(min(max(float(payload.get('public_attention_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['narrative_velocity_score'] = round(min(max(float(payload.get('narrative_velocity_score') or 0.0), 0.0), 1.0), 4)
    elif source == 'opensky':
        aviation_score = min(max(float(payload.get('aviation_disruption_score') or 0.0), 0.0), 1.0)
        update['$max']['aviation_disruption_score'] = round(aviation_score, 4)
        update['$max']['mobility_disruption_score'] = round(max(update['$max'].get('mobility_disruption_score', 0.0), aviation_score), 4)
    elif source == 'unhcr_idmc':
        displaced_people = float(payload.get('displaced_people') or 0.0)
        delta_ratio = max(float(payload.get('displacement_delta_ratio') or 0.0), 0.0)
        mobility_score = min((math.log1p(max(displaced_people, 0.0)) / 13.0) + (delta_ratio * 0.2), 1.0)
        update['$max']['mobility_disruption_score'] = round(mobility_score, 4)
    elif source == 'economic_behavior':
        update['$max']['household_stress_score'] = round(min(max(float(payload.get('household_stress_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['fuel_price_pressure'] = round(min(max(float(payload.get('fuel_price_pressure') or 0.0), 0.0), 1.0), 4)
        update['$max']['food_price_pressure'] = round(min(max(float(payload.get('food_price_pressure') or 0.0), 0.0), 1.0), 4)
        update['$max']['labor_stress_score'] = round(min(max(float(payload.get('labor_stress_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['fx_pressure_score'] = round(min(max(float(payload.get('fx_pressure_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['remittance_stress_score'] = round(min(max(float(payload.get('remittance_stress_score') or 0.0), 0.0), 1.0), 4)
        update['$max']['energy_stress_score'] = round(min(max(float(payload.get('energy_stress_score') or 0.0), 0.0), 1.0), 4)
    elif source == 'logistics':
        update['$max']['logistics_stress_score'] = round(min(max(float(payload.get('logistics_stress_score') or 0.0), 0.0), 1.0), 4)
    elif source == 'weather':
        update['$max']['weather_stress'] = round(min(abs((payload.get('temperature_normalized') or 0.5) - 0.5) * 1.4, 1.0), 4)
    elif source == 'stocks':
        update['$max']['stock_pressure'] = round(min(abs(payload.get('close_normalized') or 0.0), 1.0), 4)
    elif source == 'crypto':
        price = float(payload.get('price') or 0.0)
        update['$max']['crypto_pressure'] = round(min(price / 100000.0, 1.0), 4)
    db.country_signal_rollups.update_one({'country': country, 'event_date': event_date}, update, upsert=True)


def _mark_processed(event_id, stage):
    db.kafka_event_state.update_one(
        {'event_id': event_id, 'stage': stage},
        {'$setOnInsert': {'event_id': event_id, 'stage': stage, 'processed_at': datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


def _already_processed(event_id, stage):
    return db.kafka_event_state.find_one({'event_id': event_id, 'stage': stage}) is not None


def _publish_risk_update(country_code):
    feature_doc = recompute_country_risk(country_code)
    delta_24h, delta_7d, trend_direction, change_contributors = _compute_country_deltas(country_code)
    spillover_links = _spillover_links(country_code)
    event = {
        'event_id': hashlib.sha256(f"{country_code}:{feature_doc.get('timestamp')}".encode('utf-8')).hexdigest(),
        'country': country_code,
        'timestamp': feature_doc.get('timestamp'),
        'risk': feature_doc.get('global_risk_score'),
        'feature_timestamp': feature_doc.get('timestamp'),
        'source_count': feature_doc.get('source_count', 0),
        'top_topics': feature_doc.get('top_topics', ['no data']),
        'war_state_rules': feature_doc.get('war_state_rules', []),
        'risk_delta_24h': delta_24h,
        'risk_delta_7d': delta_7d,
        'risk_trend_direction': trend_direction,
        'score_change_contributors': change_contributors,
        'spillover_links': spillover_links,
        'social_unrest_score': feature_doc.get('social_unrest_score', 0.0),
        'google_trends_pressure': feature_doc.get('google_trends_pressure', 0.0),
        'public_attention_score': feature_doc.get('public_attention_score', 0.0),
        'narrative_velocity_score': feature_doc.get('narrative_velocity_score', 0.0),
        'coordination_risk_score': feature_doc.get('coordination_risk_score', 0.0),
        'mobility_disruption_score': feature_doc.get('mobility_disruption_score', 0.0),
        'aviation_disruption_score': feature_doc.get('aviation_disruption_score', 0.0),
        'logistics_stress_score': feature_doc.get('logistics_stress_score', 0.0),
        'household_stress_score': feature_doc.get('household_stress_score', 0.0),
        'fuel_price_pressure': feature_doc.get('fuel_price_pressure', 0.0),
        'food_price_pressure': feature_doc.get('food_price_pressure', 0.0),
        'labor_stress_score': feature_doc.get('labor_stress_score', 0.0),
        'fx_pressure_score': feature_doc.get('fx_pressure_score', 0.0),
        'remittance_stress_score': feature_doc.get('remittance_stress_score', 0.0),
        'energy_stress_score': feature_doc.get('energy_stress_score', 0.0),
        'weather_stress': feature_doc.get('weather_stress', 0.0),
        'external_signal_freshness': feature_doc.get('external_signal_freshness', 0.0),
        'direct_behavior_score': feature_doc.get('direct_behavior_score', 0.0),
        'contextual_pressure_score': feature_doc.get('contextual_pressure_score', 0.0),
        'evidence_quality_score': feature_doc.get('evidence_quality_score', 0.0),
        'validated_today': True if feature_doc.get('top_topics') != ['no data'] or feature_doc.get('war_state_rules') else False,
        'data_quality': 'verified' if feature_doc.get('top_topics') != ['no data'] or feature_doc.get('war_state_rules') else 'unknown',
    }
    send_to_kafka(UPDATE_TOPIC, event, key=country_code)
    db.service_status.update_one({'service': SERVICE_NAME}, {'$set': {'last_country_update': event['timestamp'], 'last_country': country_code, 'last_risk_event_id': event['event_id']}}, upsert=True)
    return event


def process_raw_message(record, topic):
    normalized_events = normalize_record(topic, record)
    results = []
    for event in normalized_events:
        if _already_processed(event['event_id'], 'normalized'):
            continue
        db.country_source_events.update_one({'event_id': event['event_id']}, {'$setOnInsert': event}, upsert=True)
        _mark_processed(event['event_id'], 'normalized')
        _store_country_side_effects(event)
        send_to_kafka(NORMALIZED_TOPIC, event, key=event['country'])
        results.append(event)
    return results


def process_country_event(event):
    if _already_processed(event['event_id'], 'risk'):
        return None
    _update_rollup(event)
    risk_event = _publish_risk_update(event['country'])
    _mark_processed(event['event_id'], 'risk')
    return risk_event


def _send_dlq(stage, topic, record, error):
    event = {
        'stage': stage,
        'topic': topic,
        'record': record,
        'error': str(error),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    send_to_kafka(DLQ_TOPIC, event)
    db.country_risk_dlq.insert_one(event)


def _update_service_status(**fields):
    payload = {'updated_at': datetime.now(timezone.utc).isoformat(), **fields}
    db.service_status.update_one({'service': SERVICE_NAME}, {'$set': payload}, upsert=True)


def _consumer_lag_snapshot(consumer):
    lag = {}
    try:
        partitions = consumer.assignment()
        end_offsets = consumer.end_offsets(partitions)
        for partition in partitions:
            end_offset = end_offsets.get(partition, 0)
            current = consumer.position(partition)
            lag[f'{partition.topic}:{partition.partition}'] = max(end_offset - current, 0)
    except Exception:
        pass
    return lag


def run_normalizer_loop():
    consumer = get_consumer(RAW_SOURCE_TOPICS, group_id=CONSUMER_GROUP, auto_offset_reset='latest', enable_auto_commit=True, consumer_timeout_ms=1000)
    _update_service_status(normalizer_started_at=datetime.now(timezone.utc).isoformat(), raw_topics=RAW_SOURCE_TOPICS)
    while True:
        processed = 0
        for message in consumer:
            try:
                process_raw_message(message.value, message.topic)
                processed += 1
            except Exception as exc:
                _send_dlq('normalize', message.topic, message.value, exc)
        _update_service_status(normalized_events_processed=processed, kafka_lag=_consumer_lag_snapshot(consumer))
        time.sleep(1)


def run_risk_loop():
    consumer = get_consumer(NORMALIZED_TOPIC, group_id=RISK_CONSUMER_GROUP, auto_offset_reset='latest', enable_auto_commit=True, consumer_timeout_ms=1000)
    _update_service_status(risk_consumer_started_at=datetime.now(timezone.utc).isoformat(), normalized_topic=NORMALIZED_TOPIC)
    while True:
        processed = 0
        for message in consumer:
            try:
                process_country_event(message.value)
                processed += 1
            except Exception as exc:
                _send_dlq('risk', message.topic, message.value, exc)
        _update_service_status(risk_events_processed=processed, risk_kafka_lag=_consumer_lag_snapshot(consumer))
        time.sleep(1)


def country_risk_stream_health():
    doc = db.service_status.find_one({'service': SERVICE_NAME}, {'_id': 0}) or {'service': SERVICE_NAME, 'status': 'missing'}
    today = datetime.now(timezone.utc).date().isoformat()
    doc['today_rollups'] = db.country_signal_rollups.count_documents({'event_date': today})
    doc['today_normalized_events'] = db.country_source_events.count_documents({'event_date': today})
    return doc
