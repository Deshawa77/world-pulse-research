import math
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from collectors.country_news import get_country_catalog, refresh_country_news
from config import FEATURE_COLUMNS
from database.mongo import db, get_latest_global_features, write_country_features_v2
from processing.country_risk_validation import latest_country_risk_validation
from processing.country_signal_fusion import build_country_external_signal_snapshot
from processing.global_mood import augment_country_mood_fields
from feature_store.feature_store import FeatureStore
from feature_store.load_models import load_all_models
from processing.sentiment_features import extract_sentiment_signal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTRY_FEATURE_CSV = os.path.join(PROJECT_ROOT, "data", "country_features.csv")
STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "over", "under", "after",
    "amid", "near", "new", "more", "than", "have", "has", "had", "its", "their", "your",
    "today", "latest", "breaking", "update", "global", "country", "republic", "state",
    "del", "della", "delle", "degli", "dall", "dalla", "dalle", "agli", "alla", "nelle",
    "des", "dans", "avec", "pour", "plus", "moins", "contre", "apres", "apr?s", "une", "les",
    "las", "los", "para", "como", "sobre", "tras", "ante", "desde", "entre", "contra",
    "dos", "das", "com", "sem", "sobre", "apos", "ap?s", "mais", "menos",
    "der", "die", "das", "und", "mit", "bei", "nach", "uber", "?ber", "den", "dem",
    "iran", "iranian", "iraniana", "iraniano", "irani", "states", "state", "united",
}
CONFLICT_KEYWORDS = {
    "war": 1.0,
    "attack": 0.9,
    "attacks": 0.9,
    "strike": 0.95,
    "strikes": 0.95,
    "missile": 0.95,
    "missiles": 0.95,
    "military": 0.8,
    "navy": 0.75,
    "airstrike": 1.0,
    "airstrikes": 1.0,
    "bomb": 0.9,
    "bombing": 1.0,
    "drone": 0.8,
    "drones": 0.8,
    "artillery": 0.9,
    "troops": 0.8,
    "clash": 0.8,
    "clashes": 0.8,
    "conflict": 0.75,
    "offensive": 0.9,
    "retaliation": 0.85,
    "retaliatory": 0.85,
    "invasion": 1.0,
    "siege": 1.0,
    "rocket": 0.9,
    "rockets": 0.9,
    "explosion": 0.8,
    "explosions": 0.8,
    "destroyed": 0.8,
    "sanctions": 0.45,
    "ceasefire": 0.55,
    "nuclear": 0.75,
    "guerra": 1.0,
    "ataque": 0.9,
    "ataques": 0.9,
    "attacco": 0.9,
    "attacchi": 0.9,
    "attaque": 0.9,
    "attaques": 0.9,
    "angriff": 0.9,
    "angriffe": 0.9,
    "krieg": 1.0,
    "frappe": 0.95,
    "frappes": 0.95,
    "militare": 0.8,
    "militar": 0.8,
    "missili": 0.95,
    "misil": 0.95,
    "misiles": 0.95,
    "rakete": 0.95,
    "raketen": 0.95,
    "marina": 0.75,
    "navi": 0.75,
    "affondate": 0.85,
    "affondato": 0.85,
    "distrutta": 0.8,
    "distrutto": 0.8,
    "?????": 1.0,
    "?????": 0.9,
    "?????": 0.9,
    "????": 0.95,
    "?????": 0.95,
    "??????": 0.95,
    "??????": 0.95,
    "???????": 0.8,
    "???????": 0.95,
    "?????????": 1.0,
    "?????": 1.0,
    "?????": 0.9,
    "?????": 0.95,
    "??????": 0.95,
    "????????": 0.8,
    "???": 1.0,
    "????": 0.9,
    "????": 0.95,
    "?????": 0.95,
    "?????": 0.95,
    "??????": 0.95,
    "?????": 0.8,
    "???": 0.95,
    "???": 1.0,
    "????": 0.9,
    "????": 0.95,
    "?????": 0.8,
    "????": 0.85,
    "?????": 1.0,
    "?????": 0.9,
    "??????": 0.9,
    "???": 0.95,
    "?????": 0.95,
    "????": 0.8,
}
TOPIC_TRANSLATIONS = {
    "guerra": "war",
    "krieg": "war",
    "?????": "war",
    "?????": "war",
    "???": "war",
    "???": "war",
    "?????": "war",
    "attacco": "attack",
    "attacchi": "attack",
    "attaque": "attack",
    "attaques": "attack",
    "ataque": "attack",
    "ataques": "attack",
    "?????": "attack",
    "?????": "attack",
    "?????": "attack",
    "??????": "attack",
    "????": "attack",
    "????": "attack",
    "frappe": "strike",
    "frappes": "strike",
    "????": "strike",
    "?????": "strike",
    "?????": "strike",
    "????": "strike",
    "?????": "strike",
    "missili": "missile",
    "misil": "missile",
    "misiles": "missile",
    "rakete": "missile",
    "raketen": "missile",
    "??????": "missile",
    "??????": "missile",
    "??????": "missile",
    "?????": "missile",
    "??????": "missile",
    "????": "missile",
    "???": "missile",
    "?????": "missile",
    "militare": "military",
    "militar": "military",
    "???????": "military",
    "????????": "military",
    "?????": "military",
    "?????": "military",
    "????": "military",
    "marina": "navy",
    "navi": "ships",
    "affondate": "sunk",
    "affondato": "sunk",
    "distrutta": "destroyed",
    "distrutto": "destroyed",
    "iraniana": "iran",
    "iraniano": "iran",
}
HOTSPOT_REGIONS = {
    "middle_east_conflict": {"IRN", "IRQ", "ISR", "LBN", "SYR", "JOR", "YEM", "SAU", "ARE", "QAT", "KWT", "OMN", "BHR", "EGY", "TUR"},
    "eastern_europe_conflict": {"UKR", "RUS", "BLR", "POL", "ROU", "MDA", "LVA", "LTU", "EST"},
    "south_asia_tension": {"IND", "PAK", "AFG", "IRN", "CHN"},
}
WAR_TRIGGER_TERMS = {
    "strike", "strikes", "attack", "attacks", "airstrike", "airstrikes", "missile", "missiles",
    "rocket", "rockets", "bombing", "bomb", "drone", "drones", "retaliation", "offensive",
    "war", "guerra", "krieg", "attacco", "attacchi", "attaque", "attaques", "frappe",
    "frappes", "missili", "misiles", "rakete", "raketen", "marina", "affondate", "distrutta",
}
WAR_STATE_RULES = [
    {
        "name": "us_iran_israel_open_war",
        "belligerents": {"IRN", "USA", "ISR"},
        "regional": {"IRQ", "SYR", "JOR", "LBN", "SAU", "ARE", "QAT", "KWT", "OMN", "BHR", "EGY", "YEM", "TUR"},
        "aliases": {
            "IRN": ["iran", "iranian", "iraniana", "iraniano", "iraniani", "irani"],
            "USA": ["united states", "u.s.", "u.s", "us ", "usa", "american", "americans", "washington", "trump"],
            "ISR": ["israel", "israeli", "israeli", "israeliana", "tel aviv", "idf"],
            "IRQ": ["iraq", "iraqi", "baghdad"],
            "SYR": ["syria", "syrian", "damascus"],
            "JOR": ["jordan", "jordanian", "amman"],
            "LBN": ["lebanon", "lebanese", "beirut"],
            "SAU": ["saudi", "saudi arabia", "riyadh"],
            "ARE": ["uae", "united arab emirates", "emirati", "abu dhabi", "dubai"],
            "QAT": ["qatar", "qatari", "doha"],
            "KWT": ["kuwait", "kuwaiti"],
            "OMN": ["oman", "omani"],
            "BHR": ["bahrain", "bahraini"],
            "EGY": ["egypt", "egyptian", "cairo"],
            "YEM": ["yemen", "yemeni", "houthi", "houthis", "sanaa"],
            "TUR": ["turkey", "turkish", "ankara"],
        },
        "belligerent_floor": 85.0,
        "regional_floor": 72.0,
    },
]
fs = FeatureStore()


def _utc_day_bounds(day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _neutral_feature_defaults():
    return {col: 0.0 for col in FEATURE_COLUMNS}


def _parse_article_timestamp(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z") and raw[:-1].isdigit() and len(raw[:-1]) == 14:
            return datetime.strptime(raw, "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _article_text(doc):
    data = doc.get("data") or {}
    title = str(data.get("title") or "")
    description = str(data.get("description") or "")
    return f"{title}. {description}".strip()


def _strip_accents(text):
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _normalized_text_variants(text):
    raw = str(text or "").lower()
    folded = _strip_accents(raw)
    return {variant for variant in {raw, folded} if variant}


def _tokenize_text(text):
    tokens = []
    for variant in _normalized_text_variants(text):
        tokens.extend(re.findall(r"[^\W\d_]{3,}", variant, flags=re.UNICODE))
    return tokens


def _contains_term(text_variants, term):
    normalized_term = _strip_accents(str(term or '').lower().strip())
    if not normalized_term:
        return False
    for variant in text_variants:
        if len(normalized_term) <= 3 and normalized_term.isascii() and normalized_term.isalpha():
            if re.search(rf"(?<![a-z]){re.escape(normalized_term)}(?![a-z])", variant):
                return True
        elif normalized_term in variant:
            return True
    return False


def _document_actor_mentions(doc, aliases):
    text_variants = _normalized_text_variants(_article_text(doc))
    mentioned = set()
    for code, alias_list in aliases.items():
        if any(_contains_term(text_variants, alias) for alias in alias_list):
            mentioned.add(code)
    country_code = doc.get('country')
    if country_code in aliases:
        mentioned.add(country_code)
    return mentioned, text_variants


def _canonicalize_topic(token):
    normalized = _strip_accents(str(token).lower().strip())
    return TOPIC_TRANSLATIONS.get(normalized, normalized)


def _sentiment_values(country_docs):
    values = []
    for doc in country_docs:
        compound = extract_sentiment_signal(doc)
        if compound is None:
            continue
        try:
            values.append(float(compound))
        except Exception:
            continue
    return values


def _article_dedupe_key(doc):
    data = doc.get("data") or {}
    url = str(data.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = _strip_accents(str(data.get("title") or "").lower())
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        return None
    published = str(data.get("published_at") or doc.get("timestamp") or "")[:10]
    return f"title:{title}|{published}"


def _dedupe_country_docs(country_docs):
    deduped = []
    seen = set()
    for doc in country_docs:
        dedupe_key = _article_dedupe_key(doc)
        if dedupe_key and dedupe_key in seen:
            continue
        if dedupe_key:
            seen.add(dedupe_key)
        deduped.append(doc)
    return deduped


def _source_reliability_score(source_label):
    label = f" {str(source_label or '').strip().lower()} "
    hints = {
        "reuters": 0.98,
        "associated press": 0.97,
        " ap ": 0.95,
        "bbc": 0.93,
        "financial times": 0.92,
        "bloomberg": 0.94,
        "washington post": 0.9,
        "new york times": 0.92,
        "the guardian": 0.88,
        "al jazeera": 0.88,
        "france 24": 0.87,
        "dw": 0.86,
        "euronews": 0.85,
        "cnn": 0.82,
        "newsapi": 0.74,
        "gdelt": 0.78,
        "globenewswire": 0.55,
        "pr newswire": 0.55,
    }
    for token, score in hints.items():
        if token in label:
            return score
    return 0.72


def _compute_source_profile(country_docs):
    source_ids = []
    reliability_scores = []
    for doc in country_docs:
        data = doc.get("data") or {}
        source_label = str(data.get("source_name") or doc.get("source") or "unknown").strip().lower()
        source_ids.append(source_label)
        reliability_scores.append(_source_reliability_score(source_label))
    distinct_sources = len({source_id for source_id in source_ids if source_id})
    source_diversity_score = min(distinct_sources / 4.0, 1.0)
    source_reliability_score = float(np.mean(reliability_scores)) if reliability_scores else 0.72
    return round(source_diversity_score, 4), round(source_reliability_score, 4)


def _extract_topics(country_docs, top_n=5):
    counter = Counter()
    for doc in country_docs:
        title = str((doc.get("data") or {}).get("title") or "")
        for token in _tokenize_text(title):
            canonical = _canonicalize_topic(token)
            if len(canonical) < 4 or canonical in STOPWORDS:
                continue
            counter[canonical] += 1
    if not counter:
        return ["no data"]
    return [token for token, _ in counter.most_common(top_n)]


def _score_country(models, features):
    row = {}
    for col in FEATURE_COLUMNS:
        value = features.get(col, 0.0)
        row[col] = 0.0 if value is None else float(value)
    X = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    probs = [m.predict_proba(X)[0, 1] for m in models.values() if hasattr(m, "predict_proba")]
    if not probs:
        return 50.0
    return round(float(np.mean(probs) * 100), 2)


def _compute_conflict_indicators(country_code, country_docs, day):
    start, end = _utc_day_bounds(day)
    now = datetime.now(timezone.utc)
    conflict_count = 0
    severity_points = 0.0
    max_severity = 0.0
    recency_scores = []

    for doc in country_docs:
        text_variants = _normalized_text_variants(_article_text(doc))
        article_severity = 0.0
        matched = False
        for keyword, weight in CONFLICT_KEYWORDS.items():
            if any(keyword in variant for variant in text_variants):
                matched = True
                article_severity += weight
                max_severity = max(max_severity, weight)
        if matched:
            conflict_count += 1
            severity_points += article_severity

        published_at = _parse_article_timestamp((doc.get("data") or {}).get("published_at") or doc.get("timestamp"))
        if published_at and start <= published_at < end:
            age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
            recency_scores.append(max(0.0, 1.0 - (age_hours / 24.0)))

    source_count = len(country_docs)
    source_confidence = min(source_count / 5.0, 1.0)
    weighted_keyword_severity = min(severity_points / max(source_count, 1), 3.0) / 3.0
    recency_weight = float(np.mean(recency_scores)) if recency_scores else 0.0

    return {
        "conflict_headline_count": conflict_count,
        "weighted_keyword_severity": round(weighted_keyword_severity, 4),
        "source_confidence": round(source_confidence, 4),
        "recency_weight": round(recency_weight, 4),
        "max_keyword_severity": round(max_severity, 4),
    }


def _detect_open_war_states(grouped_news):
    results = {}
    all_docs = [doc for docs in grouped_news.values() for doc in docs]
    for rule in WAR_STATE_RULES:
        actor_hits = {code: 0 for code in set(rule["belligerents"]) | set(rule["regional"])}
        direct_pair_hits = 0
        conflict_docs = 0
        belligerent_mentions = set()
        for doc in all_docs:
            mentioned, text_variants = _document_actor_mentions(doc, rule["aliases"])
            if not mentioned:
                continue
            has_war_signal = any(_contains_term(text_variants, term) for term in WAR_TRIGGER_TERMS)
            if not has_war_signal:
                continue
            conflict_docs += 1
            for code in mentioned:
                actor_hits[code] = actor_hits.get(code, 0) + 1
            belligerent_in_doc = mentioned & set(rule["belligerents"])
            belligerent_mentions.update(belligerent_in_doc)
            if len(belligerent_in_doc) >= 2:
                direct_pair_hits += 1

        belligerent_hit_count = sum(1 for code in rule["belligerents"] if actor_hits.get(code, 0) > 0)
        triggered = (
            direct_pair_hits >= 1
            or belligerent_hit_count >= 2
            or (conflict_docs >= 2 and len(belligerent_mentions) >= 2)
        )
        if triggered:
            active_belligerents = set(rule["belligerents"])
            active_regional = {code for code in rule["regional"] if actor_hits.get(code, 0) > 0}
        else:
            active_belligerents = set()
            active_regional = set()

        results[rule["name"]] = {
            "triggered": triggered,
            "actor_hits": actor_hits,
            "direct_pair_hits": direct_pair_hits,
            "conflict_docs": conflict_docs,
            "active_belligerents": active_belligerents,
            "active_regional": active_regional,
            "belligerent_floor": rule["belligerent_floor"],
            "regional_floor": rule["regional_floor"],
        }
    return results


def _apply_war_state_floor(country_code, score, local_indicators, regional_escalation, war_state_results):
    adjusted = score
    active_rules = []
    local_has_conflict = (
        local_indicators.get("conflict_headline_count", 0) > 0
        or local_indicators.get("weighted_keyword_severity", 0.0) >= 0.2
    )
    for rule_name, result in war_state_results.items():
        if not result.get("triggered"):
            continue
        if country_code in result.get("active_belligerents", set()):
            adjusted = max(adjusted, result.get("belligerent_floor", 85.0))
            active_rules.append(f"{rule_name}:belligerent")
        elif country_code in result.get("active_regional", set()) and (
            local_has_conflict or regional_escalation >= 0.2
        ):
            adjusted = max(adjusted, result.get("regional_floor", 72.0))
            active_rules.append(f"{rule_name}:regional")
    return round(min(adjusted, 100.0), 2), active_rules


def _compute_regional_escalation(country_code, indicators_by_country):
    escalation = 0.0
    triggered_regions = []
    for region_name, members in HOTSPOT_REGIONS.items():
        if country_code not in members:
            continue
        neighboring_conflict = [
            indicators_by_country.get(member, {})
            for member in members
            if member != country_code
        ]
        high_signal_neighbors = sum(
            1
            for item in neighboring_conflict
            if (item.get("conflict_headline_count", 0) >= 2 or item.get("weighted_keyword_severity", 0.0) >= 0.45)
        )
        if high_signal_neighbors:
            escalation += min(0.12 + (0.04 * high_signal_neighbors), 0.28)
            triggered_regions.append(region_name)
    return min(escalation, 0.35), triggered_regions


def _apply_external_signal_overlay(score, external_signals):
    social_unrest_score = float(external_signals.get("social_unrest_score", 0.0) or 0.0)
    google_trends_pressure = float(external_signals.get("google_trends_pressure", 0.0) or 0.0)
    weather_stress = float(external_signals.get("weather_stress", 0.0) or 0.0)
    external_signal_freshness = float(external_signals.get("external_signal_freshness", 0.0) or 0.0)

    overlay = (
        social_unrest_score * 10.0
        + google_trends_pressure * 8.0
        + weather_stress * 12.0
        + external_signal_freshness * 4.0
    )
    return round(min(score + overlay, 100.0), 2)


def _apply_conflict_overlay(base_score, indicators, regional_escalation):
    conflict_headline_count = indicators.get("conflict_headline_count", 0)
    weighted_keyword_severity = indicators.get("weighted_keyword_severity", 0.0)
    source_confidence = indicators.get("source_confidence", 0.0)
    recency_weight = indicators.get("recency_weight", 0.0)

    conflict_count_factor = min(conflict_headline_count / 4.0, 1.0)
    evidence_strength = max(conflict_count_factor, weighted_keyword_severity)
    source_boost = source_confidence * evidence_strength
    recency_boost = recency_weight * evidence_strength

    overlay = (
        conflict_count_factor * 24.0
        + weighted_keyword_severity * 22.0
        + source_boost * 12.0
        + recency_boost * 10.0
        + regional_escalation * 18.0
    )
    adjusted = base_score + overlay

    if conflict_headline_count >= 3 and weighted_keyword_severity >= 0.55:
        adjusted = max(adjusted, 78.0)
    elif conflict_headline_count >= 2 and weighted_keyword_severity >= 0.4:
        adjusted = max(adjusted, 68.0)

    return round(min(adjusted, 100.0), 2)


def _load_today_country_news(day: datetime | None = None):
    start, end = _utc_day_bounds(day)
    docs = list(db.country_news.find({"timestamp": {"$gte": start, "$lt": end}}))
    grouped = {}
    for doc in docs:
        grouped.setdefault(doc.get("country"), []).append(doc)
    return grouped


def build_daily_country_features(day: datetime | None = None, ensure_fresh_news: bool = True, max_records: int = 4, batch_size: int = 50):
    target_day = day or datetime.now(timezone.utc)
    refresh_summary = None
    if ensure_fresh_news:
        refresh_summary = refresh_country_news(day=target_day, max_records=max_records, batch_size=batch_size)

    grouped_news = {country: _dedupe_country_docs(docs) for country, docs in _load_today_country_news(target_day).items()}
    neutral_defaults = _neutral_feature_defaults()
    models = load_all_models()
    catalog = get_country_catalog()
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    indicators_by_country = {
        country_code: _compute_conflict_indicators(country_code, grouped_news.get(country_code, []), target_day)
        for country_code in catalog.keys()
    }
    external_signals_by_country, external_signal_summary = build_country_external_signal_snapshot(target_day, catalog)
    war_state_results = _detect_open_war_states(grouped_news)
    latest_validation = latest_country_risk_validation()

    rows = []
    summary = {
        "target_countries": len(catalog),
        "written": 0,
        "with_news": 0,
        "without_news": [],
        "refresh": refresh_summary,
        "external_signals": external_signal_summary,
        "latest_validation_status": latest_validation.get("status"),
        "latest_validation_sample_count": int(latest_validation.get("sample_count", 0) or 0),
    }
    for country_code, country_name in catalog.items():
        country_docs = grouped_news.get(country_code, [])
        source_diversity_score, source_reliability_score = _compute_source_profile(country_docs)
        sentiments = _sentiment_values(country_docs)
        topics = _extract_topics(country_docs)
        news_mean = round(float(np.mean(sentiments)), 5) if sentiments else 0.0
        gdelt_mean = news_mean
        external_signals = external_signals_by_country.get(country_code, {})
        features = {
            **neutral_defaults,
            "news_sentiment": news_mean,
            "gdelt_sentiment": gdelt_mean,
            "weather_anomaly": float(external_signals.get("weather_stress", 0.0) or 0.0),
        }
        base_risk_score = _score_country(models, features)
        conflict_indicators = indicators_by_country[country_code]
        regional_escalation, triggered_regions = _compute_regional_escalation(country_code, indicators_by_country)
        risk_score = _apply_conflict_overlay(base_risk_score, conflict_indicators, regional_escalation)
        risk_score = _apply_external_signal_overlay(risk_score, external_signals)
        risk_score, war_state_rules = _apply_war_state_floor(country_code, risk_score, conflict_indicators, regional_escalation, war_state_results)
        feature_doc = {
            **features,
            "timestamp": timestamp_iso,
            "global_risk_score": risk_score,
            "base_model_risk_score": base_risk_score,
            "top_topics": topics,
            "country_name": country_name,
            "source": "country_news_multi_source_daily",
            "source_count": len(country_docs),
            "source_diversity_score": source_diversity_score,
            "source_reliability_score": source_reliability_score,
            "conflict_headline_count": conflict_indicators["conflict_headline_count"],
            "weighted_keyword_severity": conflict_indicators["weighted_keyword_severity"],
            "source_confidence": conflict_indicators["source_confidence"],
            "recency_weight": conflict_indicators["recency_weight"],
            "regional_escalation": round(regional_escalation, 4),
            "regional_escalation_regions": triggered_regions,
            "social_unrest_score": float(external_signals.get("social_unrest_score", 0.0) or 0.0),
            "google_trends_pressure": float(external_signals.get("google_trends_pressure", 0.0) or 0.0),
            "weather_stress": float(external_signals.get("weather_stress", 0.0) or 0.0),
            "external_signal_freshness": float(external_signals.get("external_signal_freshness", 0.0) or 0.0),
            "external_sources": list(external_signals.get("external_sources", [])),
            "war_state_rules": war_state_rules,
            "risk_category": "HIGH" if risk_score >= 70 else "MEDIUM" if risk_score >= 40 else "LOW",
        }
        augment_country_mood_fields(country_code, feature_doc, mode="online")
        write_country_features_v2(country_code, feature_doc, mode="online")
        rows.append({
            "country": country_code,
            "timestamp": timestamp_iso,
            **{col: feature_doc[col] for col in FEATURE_COLUMNS},
            "global_risk_score": risk_score,
            "base_model_risk_score": base_risk_score,
            "top_topics": topics,
            "country_name": country_name,
            "source_count": len(country_docs),
            "source_diversity_score": source_diversity_score,
            "source_reliability_score": source_reliability_score,
            "country_mood_score": feature_doc["country_mood_score"],
            "country_mood_baseline": feature_doc["country_mood_baseline"],
            "country_mood_sentiment_delta": feature_doc["country_mood_sentiment_delta"],
            "country_mood_sentiment_zscore": feature_doc["country_mood_sentiment_zscore"],
            "conflict_headline_count": conflict_indicators["conflict_headline_count"],
            "weighted_keyword_severity": conflict_indicators["weighted_keyword_severity"],
            "source_confidence": conflict_indicators["source_confidence"],
            "recency_weight": conflict_indicators["recency_weight"],
            "regional_escalation": round(regional_escalation, 4),
            "social_unrest_score": float(external_signals.get("social_unrest_score", 0.0) or 0.0),
            "google_trends_pressure": float(external_signals.get("google_trends_pressure", 0.0) or 0.0),
            "weather_stress": float(external_signals.get("weather_stress", 0.0) or 0.0),
            "external_signal_freshness": float(external_signals.get("external_signal_freshness", 0.0) or 0.0),
            "war_state_rules": war_state_rules,
            "source": "country_news_multi_source_daily",
        })
        summary["written"] += 1
        if country_docs:
            summary["with_news"] += 1
        else:
            summary["without_news"].append(country_code)

    df = pd.DataFrame(rows)
    if not df.empty:
        write_cols = [
            "country", "timestamp", *FEATURE_COLUMNS, "global_risk_score", "base_model_risk_score", "top_topics",
            "country_name", "source_count", "source_diversity_score", "source_reliability_score", "country_mood_score", "country_mood_baseline", "country_mood_sentiment_delta", "country_mood_sentiment_zscore", "conflict_headline_count", "weighted_keyword_severity",
            "source_confidence", "recency_weight", "regional_escalation", "social_unrest_score",
            "google_trends_pressure", "weather_stress", "external_signal_freshness", "war_state_rules", "source"
        ]
        fs.write_country(df[write_cols])
        df.to_csv(COUNTRY_FEATURE_CSV, index=False)
    return summary


def country_daily_refresh_if_due(day: datetime | None = None, max_records: int = 4, batch_size: int = 50):
    result = build_daily_country_features(day=day, ensure_fresh_news=True, max_records=max_records, batch_size=batch_size)
    result["skipped"] = False
    return result


if __name__ == "__main__":
    print(build_daily_country_features())


