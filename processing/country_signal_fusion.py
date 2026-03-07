import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from database.mongo import db

COMMON_COUNTRY_ALIASES = {
    "USA": {"united states", "united states of america", "usa", "u.s.", "u.s", "america", "american", "washington"},
    "GBR": {"united kingdom", "uk", "britain", "british", "england"},
    "ARE": {"uae", "united arab emirates", "emirati", "abu dhabi", "dubai"},
    "KOR": {"south korea", "republic of korea", "seoul"},
    "PRK": {"north korea", "dprk", "pyongyang"},
    "RUS": {"russia", "russian", "moscow"},
    "IRN": {"iran", "iranian", "tehran"},
    "ISR": {"israel", "israeli", "jerusalem", "tel aviv"},
    "PSE": {"palestine", "gaza", "west bank"},
    "SYR": {"syria", "syrian", "damascus"},
    "IRQ": {"iraq", "iraqi", "baghdad"},
    "SAU": {"saudi arabia", "saudi", "riyadh"},
    "EGY": {"egypt", "egyptian", "cairo"},
    "TUR": {"turkey", "turkish", "ankara"},
    "CHN": {"china", "chinese", "beijing", "shanghai"},
    "JPN": {"japan", "japanese", "tokyo", "osaka"},
    "IND": {"india", "indian", "delhi", "mumbai"},
    "PAK": {"pakistan", "pakistani", "karachi", "lahore"},
    "UKR": {"ukraine", "ukrainian", "kyiv"},
    "CAN": {"canada", "canadian", "toronto", "vancouver", "montreal"},
    "AUS": {"australia", "australian", "sydney", "melbourne", "brisbane", "perth"},
}

CITY_TO_COUNTRY = {
    "new york": "USA", "los angeles": "USA", "chicago": "USA", "houston": "USA", "miami": "USA", "san francisco": "USA",
    "toronto": "CAN", "vancouver": "CAN", "montreal": "CAN",
    "mexico city": "MEX",
    "sao paulo": "BRA", "rio de janeiro": "BRA",
    "buenos aires": "ARG", "lima": "PER", "bogota": "COL", "santiago": "CHL", "caracas": "VEN", "quito": "ECU", "la paz": "BOL", "montevideo": "URY",
    "london": "GBR", "paris": "FRA", "berlin": "DEU", "madrid": "ESP", "rome": "ITA", "amsterdam": "NLD", "brussels": "BEL", "vienna": "AUT", "prague": "CZE", "warsaw": "POL",
    "budapest": "HUN", "stockholm": "SWE", "oslo": "NOR", "copenhagen": "DNK", "helsinki": "FIN", "athens": "GRC", "lisbon": "PRT", "dublin": "IRL", "zurich": "CHE", "moscow": "RUS",
    "cairo": "EGY", "lagos": "NGA", "johannesburg": "ZAF", "cape town": "ZAF", "nairobi": "KEN", "addis ababa": "ETH", "accra": "GHA", "casablanca": "MAR", "algiers": "DZA", "tunis": "TUN",
    "dubai": "ARE", "abu dhabi": "ARE", "doha": "QAT", "riyadh": "SAU", "jeddah": "SAU", "kuwait city": "KWT", "manama": "BHR", "muscat": "OMN", "tehran": "IRN", "jerusalem": "ISR",
    "delhi": "IND", "mumbai": "IND", "bangalore": "IND", "chennai": "IND", "kolkata": "IND", "karachi": "PAK", "lahore": "PAK", "dhaka": "BGD", "colombo": "LKA", "kathmandu": "NPL",
    "tokyo": "JPN", "osaka": "JPN", "seoul": "KOR", "beijing": "CHN", "shanghai": "CHN", "hong kong": "HKG", "taipei": "TWN", "bangkok": "THA", "singapore": "SGP", "kuala lumpur": "MYS",
    "jakarta": "IDN", "manila": "PHL", "hanoi": "VNM", "ho chi minh city": "VNM", "phnom penh": "KHM", "yangon": "MMR",
    "sydney": "AUS", "melbourne": "AUS", "brisbane": "AUS", "perth": "AUS", "auckland": "NZL", "wellington": "NZL",
}

WEATHER_ALERT_TERMS = {
    "storm": 0.55,
    "flood": 0.7,
    "rain": 0.2,
    "snow": 0.25,
    "heat": 0.45,
    "wildfire": 0.8,
    "sand": 0.25,
    "dust": 0.25,
    "hurricane": 0.9,
    "cyclone": 0.9,
    "typhoon": 0.9,
    "thunderstorm": 0.5,
    "extreme": 0.35,
}

SOCIAL_RISK_TERMS = {
    "war": 1.0,
    "attack": 0.9,
    "bomb": 0.85,
    "strike": 0.85,
    "missile": 0.9,
    "protest": 0.65,
    "riot": 0.8,
    "violence": 0.8,
    "conflict": 0.75,
    "military": 0.7,
    "sanction": 0.45,
    "ceasefire": 0.35,
}


def _utc_day_bounds(day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _strip_accents(text: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', text) if not unicodedata.combining(ch))


def _norm(text) -> str:
    return _strip_accents(str(text or '').lower().strip())


def _parse_dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith('Z') and raw[:-1].isdigit() and len(raw[:-1]) == 14:
            return datetime.strptime(raw, '%Y%m%d%H%M%SZ').replace(tzinfo=timezone.utc)
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _contains(text: str, term: str) -> bool:
    t = _norm(term)
    if not t:
        return False
    if len(t) <= 3 and t.isascii() and t.isalpha():
        return re.search(rf'(?<![a-z]){re.escape(t)}(?![a-z])', text) is not None
    return t in text


def _build_alias_map(catalog: dict[str, str]):
    alias_map = {}
    for code, name in catalog.items():
        aliases = {_norm(name)}
        aliases.update(COMMON_COUNTRY_ALIASES.get(code, set()))
        cleaned = _norm(name.replace(',', ' ').replace('-', ' '))
        aliases.add(cleaned)
        if cleaned.startswith('the '):
            aliases.add(cleaned[4:])
        alias_map[code] = {alias for alias in aliases if alias}
    return alias_map


def _match_countries(text: str, alias_map: dict[str, set[str]]):
    norm_text = _norm(text)
    matched = set()
    for code, aliases in alias_map.items():
        if any(_contains(norm_text, alias) for alias in aliases):
            matched.add(code)
    return matched


def _latest_docs_for_day(collection_name: str, day: datetime | None = None):
    start, end = _utc_day_bounds(day)
    docs = []
    for doc in db[collection_name].find():
        stamp = _parse_dt(doc.get('timestamp') or doc.get('collected_at') or ((doc.get('data') or {}).get('published_at')) or doc.get('data_timestamp'))
        if stamp and start <= stamp < end:
            docs.append(doc)
    return docs


def build_country_external_signal_snapshot(day: datetime | None, catalog: dict[str, str]):
    alias_map = _build_alias_map(catalog)
    signals = {
        code: {
            'social_unrest_score': 0.0,
            'google_trends_pressure': 0.0,
            'weather_stress': 0.0,
            'external_signal_freshness': 0.0,
            'external_sources': [],
            'social_posts': 0,
            'trend_points': 0,
            'weather_points': 0,
        }
        for code in catalog.keys()
    }
    source_coverage = {'reddit': 0, 'trends': 0, 'weather': 0}

    reddit_docs = _latest_docs_for_day('reddit', day)
    for doc in reddit_docs:
        data = doc.get('data') or {}
        text = ' '.join([str(data.get('query') or ''), str(data.get('title') or ''), str(data.get('text') or ''), str(data.get('subreddit') or '')])
        matched = _match_countries(text, alias_map)
        if not matched:
            continue
        norm_text = _norm(text)
        keyword_pressure = max((weight for term, weight in SOCIAL_RISK_TERMS.items() if _contains(norm_text, term)), default=0.0)
        score = float(data.get('score') or 0.0)
        social_strength = min((math.log1p(max(score, 0.0)) / 6.0) + keyword_pressure, 1.0)
        for code in matched:
            entry = signals[code]
            entry['social_unrest_score'] = min(1.0, entry['social_unrest_score'] + social_strength * 0.35)
            entry['social_posts'] += 1
            if 'reddit' not in entry['external_sources']:
                entry['external_sources'].append('reddit')
            source_coverage['reddit'] += 1

    trend_docs = _latest_docs_for_day('trends', day)
    for doc in trend_docs:
        data = doc.get('data') or {}
        keyword = str(data.get('keyword') or '')
        matched = _match_countries(keyword, alias_map)
        if not matched:
            continue
        interest = float(data.get('interest') or 0.0)
        trend_strength = min(max(interest, 0.0) / 100.0, 1.0)
        for code in matched:
            entry = signals[code]
            entry['google_trends_pressure'] = min(1.0, entry['google_trends_pressure'] + trend_strength * 0.5)
            entry['trend_points'] += 1
            if 'google_trends' not in entry['external_sources']:
                entry['external_sources'].append('google_trends')
            source_coverage['trends'] += 1

    weather_docs = _latest_docs_for_day('weather', day)
    for doc in weather_docs:
        city = _norm(doc.get('data_city') or '')
        country_code = CITY_TO_COUNTRY.get(city)
        if not country_code or country_code not in signals:
            continue
        temp_norm = float(doc.get('data_temperature_normalized') or 0.5)
        humidity = float(doc.get('data_humidity') or 0.0)
        desc = _norm(doc.get('data_weather') or '')
        temp_stress = min(abs(temp_norm - 0.5) * 1.4, 1.0)
        humidity_stress = 0.25 if humidity >= 90 or humidity <= 15 else 0.0
        condition_stress = max((weight for term, weight in WEATHER_ALERT_TERMS.items() if _contains(desc, term)), default=0.0)
        weather_stress = min(1.0, max(temp_stress, humidity_stress, condition_stress))
        entry = signals[country_code]
        entry['weather_stress'] = max(entry['weather_stress'], weather_stress)
        entry['weather_points'] += 1
        if 'weather' not in entry['external_sources']:
            entry['external_sources'].append('weather')
        source_coverage['weather'] += 1

    for entry in signals.values():
        contributing = sum(1 for source in ('reddit', 'google_trends', 'weather') if source in entry['external_sources'])
        entry['social_unrest_score'] = round(min(entry['social_unrest_score'], 1.0), 4)
        entry['google_trends_pressure'] = round(min(entry['google_trends_pressure'], 1.0), 4)
        entry['weather_stress'] = round(min(entry['weather_stress'], 1.0), 4)
        entry['external_signal_freshness'] = round(contributing / 3.0, 4)

    summary = {
        'source_docs': {
            'reddit': len(reddit_docs),
            'trends': len(trend_docs),
            'weather': len(weather_docs),
        },
        'country_coverage': {
            'reddit': sum(1 for item in signals.values() if item['social_posts'] > 0),
            'trends': sum(1 for item in signals.values() if item['trend_points'] > 0),
            'weather': sum(1 for item in signals.values() if item['weather_points'] > 0),
        },
    }
    return signals, summary
