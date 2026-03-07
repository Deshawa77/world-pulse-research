from datetime import datetime, timezone

from collectors.country_news import get_country_catalog
from database.mongo import db, write_country_features_v2
from processing.country_daily_risk import (
    _apply_conflict_overlay,
    _apply_external_signal_overlay,
    _apply_war_state_floor,
    _compute_conflict_indicators,
    _compute_regional_escalation,
    _detect_open_war_states,
    _extract_topics,
    _load_today_country_news,
    _neutral_feature_defaults,
    _score_country,
    _sentiment_values,
)
from feature_store.load_models import load_all_models


DEFAULT_EXTERNAL_SIGNALS = {
    'social_unrest_score': 0.0,
    'google_trends_pressure': 0.0,
    'weather_stress': 0.0,
    'external_signal_freshness': 0.0,
    'external_sources': [],
}


def _load_daily_rollups(day: datetime | None = None):
    target_day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    docs = list(db.country_signal_rollups.find({'event_date': target_day}))
    rollups = {}
    for doc in docs:
        rollups[doc.get('country')] = {
            'social_unrest_score': float(doc.get('social_unrest_score', 0.0) or 0.0),
            'google_trends_pressure': float(doc.get('google_trends_pressure', 0.0) or 0.0),
            'weather_stress': float(doc.get('weather_stress', 0.0) or 0.0),
            'external_signal_freshness': round(min(len(doc.get('sources', [])) / 3.0, 1.0), 4),
            'external_sources': list(doc.get('sources', [])),
        }
    return rollups


def recompute_country_risk(country_code: str, day: datetime | None = None, mode: str = 'online'):
    target_day = day or datetime.now(timezone.utc)
    grouped_news = _load_today_country_news(target_day)
    catalog = get_country_catalog()
    if country_code not in catalog:
        raise ValueError(f'Unknown country code: {country_code}')

    indicators_by_country = {
        code: _compute_conflict_indicators(code, grouped_news.get(code, []), target_day)
        for code in catalog.keys()
    }
    war_state_results = _detect_open_war_states(grouped_news)
    rollups = _load_daily_rollups(target_day)
    external_signals = rollups.get(country_code, DEFAULT_EXTERNAL_SIGNALS)

    country_docs = grouped_news.get(country_code, [])
    sentiments = _sentiment_values(country_docs)
    topics = _extract_topics(country_docs)
    news_mean = round(sum(sentiments) / len(sentiments), 5) if sentiments else 0.0
    features = {
        **_neutral_feature_defaults(),
        'news_sentiment': news_mean,
        'gdelt_sentiment': news_mean,
        'weather_anomaly': float(external_signals.get('weather_stress', 0.0) or 0.0),
    }
    models = load_all_models()
    base_risk_score = _score_country(models, features)
    conflict_indicators = indicators_by_country[country_code]
    regional_escalation, triggered_regions = _compute_regional_escalation(country_code, indicators_by_country)
    risk_score = _apply_conflict_overlay(base_risk_score, conflict_indicators, regional_escalation)
    risk_score = _apply_external_signal_overlay(risk_score, external_signals)
    risk_score, war_state_rules = _apply_war_state_floor(country_code, risk_score, conflict_indicators, regional_escalation, war_state_results)

    feature_doc = {
        **features,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'global_risk_score': risk_score,
        'base_model_risk_score': base_risk_score,
        'top_topics': topics,
        'country_name': catalog[country_code],
        'source': 'country_risk_stream_incremental',
        'source_count': len(country_docs),
        'conflict_headline_count': conflict_indicators['conflict_headline_count'],
        'weighted_keyword_severity': conflict_indicators['weighted_keyword_severity'],
        'source_confidence': conflict_indicators['source_confidence'],
        'recency_weight': conflict_indicators['recency_weight'],
        'regional_escalation': round(regional_escalation, 4),
        'regional_escalation_regions': triggered_regions,
        'social_unrest_score': float(external_signals.get('social_unrest_score', 0.0) or 0.0),
        'google_trends_pressure': float(external_signals.get('google_trends_pressure', 0.0) or 0.0),
        'weather_stress': float(external_signals.get('weather_stress', 0.0) or 0.0),
        'external_signal_freshness': float(external_signals.get('external_signal_freshness', 0.0) or 0.0),
        'external_sources': list(external_signals.get('external_sources', [])),
        'war_state_rules': war_state_rules,
        'risk_category': 'HIGH' if risk_score >= 70 else 'MEDIUM' if risk_score >= 40 else 'LOW',
    }
    write_country_features_v2(country_code, feature_doc, mode=mode)
    return feature_doc
