import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

from kafka import TopicPartition

from backend.kafka_client import get_consumer, send_to_kafka
from collectors.country_news import get_country_catalog
from database.mongo import db, write_country_features_v2
from processing.country_incremental_risk import recompute_country_risk
from processing.nlp_analysis import analyze_text, clean_text
from processing.country_signal_fusion import CITY_TO_COUNTRY, COMMON_COUNTRY_ALIASES

RAW_SOURCE_TOPICS = [
    'news_topic', 'gdelt_topic', 'reddit_topic', 'trends_topic', 'weather_topic', 'stocks_topic', 'crypto_topic',
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
            events.append({
                'country': country,
                'timestamp': timestamp.isoformat(),
                'source': 'gdelt' if 'gdelt' in source or topic == 'gdelt_topic' else 'newsapi',
                'topic': topic,
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
    event = {
        'event_id': hashlib.sha256(f"{country_code}:{feature_doc.get('timestamp')}".encode('utf-8')).hexdigest(),
        'country': country_code,
        'timestamp': feature_doc.get('timestamp'),
        'risk': feature_doc.get('global_risk_score'),
        'feature_timestamp': feature_doc.get('timestamp'),
        'source_count': feature_doc.get('source_count', 0),
        'top_topics': feature_doc.get('top_topics', ['no data']),
        'war_state_rules': feature_doc.get('war_state_rules', []),
        'social_unrest_score': feature_doc.get('social_unrest_score', 0.0),
        'google_trends_pressure': feature_doc.get('google_trends_pressure', 0.0),
        'weather_stress': feature_doc.get('weather_stress', 0.0),
        'external_signal_freshness': feature_doc.get('external_signal_freshness', 0.0),
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
