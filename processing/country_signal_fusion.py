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


SOURCE_LOOKBACK_HOURS = {
    'wiki': 24,
    'telegram_public': 24,
    'youtube_trends': 24,
    'trends': 24,
    'weather': 18,
    'mobility': 72,
    'aviation': 24,
    'logistics': 96,
    'economic_behavior': 96,
}


def _latest_docs_for_day(collection_name: str, day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lookback_hours = int(SOURCE_LOOKBACK_HOURS.get(collection_name, 24))
    cutoff = current - timedelta(hours=lookback_hours)
    docs = []
    for doc in db[collection_name].find():
        stamp = _parse_dt(doc.get('timestamp') or doc.get('collected_at') or ((doc.get('data') or {}).get('published_at')) or doc.get('data_timestamp'))
        if stamp and cutoff <= stamp <= current:
            docs.append(doc)
    return docs


def build_country_external_signal_snapshot(day: datetime | None, catalog: dict[str, str]):
    alias_map = _build_alias_map(catalog)
    signals = {
        code: {
            'social_unrest_score': 0.0,
            'google_trends_pressure': 0.0,
            'public_attention_score': 0.0,
            'narrative_velocity_score': 0.0,
            'coordination_risk_score': 0.0,
            'weather_stress': 0.0,
            'mobility_disruption_score': 0.0,
            'aviation_disruption_score': 0.0,
            'logistics_stress_score': 0.0,
            'household_stress_score': 0.0,
            'fuel_price_pressure': 0.0,
            'food_price_pressure': 0.0,
            'labor_stress_score': 0.0,
            'fx_pressure_score': 0.0,
            'remittance_stress_score': 0.0,
            'energy_stress_score': 0.0,
            'external_signal_freshness': 0.0,
            'external_sources': [],
            'attention_points': 0,
            'trend_points': 0,
            'social_points': 0,
            'weather_points': 0,
            'mobility_points': 0,
            'aviation_points': 0,
            'logistics_points': 0,
            'economic_points': 0,
        }
        for code in catalog.keys()
    }
    source_coverage = {'wiki': 0, 'trends': 0, 'telegram_public': 0, 'youtube_public': 0, 'weather': 0, 'mobility': 0, 'aviation': 0, 'logistics': 0, 'economic_behavior': 0}

    wiki_docs = _latest_docs_for_day('wiki', day)
    for doc in wiki_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        article = str(data.get('article') or '')
        if country_code not in signals:
            matched = _match_countries(article, alias_map)
            if not matched:
                continue
        else:
            matched = {country_code}
        views = float(data.get('views') or 0.0)
        delta_ratio = float(data.get('view_delta_ratio') or 0.0)
        attention_strength = min((math.log1p(max(views, 0.0)) / 12.0) + max(delta_ratio, 0.0) * 0.35, 1.0)
        for code in matched:
            entry = signals[code]
            entry['public_attention_score'] = min(1.0, max(entry['public_attention_score'], attention_strength))
            entry['attention_points'] += 1
            if 'wikipedia' not in entry['external_sources']:
                entry['external_sources'].append('wikipedia')
            source_coverage['wiki'] += 1

    telegram_docs = _latest_docs_for_day('telegram_public', day)
    for doc in telegram_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        if country_code not in signals:
            continue
        entry = signals[country_code]
        entry['narrative_velocity_score'] = max(entry['narrative_velocity_score'], float(data.get('narrative_velocity_score') or 0.0))
        entry['coordination_risk_score'] = max(entry['coordination_risk_score'], float(data.get('coordination_risk_score') or 0.0))
        entry['social_unrest_score'] = max(entry['social_unrest_score'], float(data.get('social_unrest_score') or 0.0))
        entry['social_points'] += 1
        if 'telegram_public' not in entry['external_sources']:
            entry['external_sources'].append('telegram_public')
        source_coverage['telegram_public'] += 1

    youtube_docs = _latest_docs_for_day('youtube_trends', day)
    for doc in youtube_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        if country_code not in signals:
            continue
        entry = signals[country_code]
        entry['public_attention_score'] = max(entry['public_attention_score'], float(data.get('public_attention_score') or 0.0))
        entry['narrative_velocity_score'] = max(entry['narrative_velocity_score'], float(data.get('narrative_velocity_score') or 0.0))
        entry['social_points'] += 1
        if 'youtube_public' not in entry['external_sources']:
            entry['external_sources'].append('youtube_public')
        source_coverage['youtube_public'] += 1

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

    mobility_docs = _latest_docs_for_day('mobility', day)
    for doc in mobility_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or data.get('origin_country') or '').strip().upper()
        if country_code not in signals:
            continue
        displaced_people = float(data.get('displaced_people') or 0.0)
        delta_ratio = float(data.get('displacement_delta_ratio') or 0.0)
        mobility_strength = min((math.log1p(max(displaced_people, 0.0)) / 13.0) + max(delta_ratio, 0.0) * 0.2, 1.0)
        entry = signals[country_code]
        entry['mobility_disruption_score'] = max(entry['mobility_disruption_score'], mobility_strength)
        entry['mobility_points'] += 1
        if 'mobility' not in entry['external_sources']:
            entry['external_sources'].append('mobility')
        source_coverage['mobility'] += 1

    aviation_docs = _latest_docs_for_day('aviation', day)
    for doc in aviation_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        if country_code not in signals:
            continue
        aviation_strength = float(data.get('aviation_disruption_score') or 0.0)
        entry = signals[country_code]
        entry['aviation_disruption_score'] = max(entry['aviation_disruption_score'], aviation_strength)
        entry['mobility_disruption_score'] = max(entry['mobility_disruption_score'], aviation_strength)
        entry['aviation_points'] += 1
        if 'aviation' not in entry['external_sources']:
            entry['external_sources'].append('aviation')
        source_coverage['aviation'] += 1

    logistics_docs = _latest_docs_for_day('logistics', day)
    for doc in logistics_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        if country_code not in signals:
            continue
        entry = signals[country_code]
        entry['logistics_stress_score'] = max(entry['logistics_stress_score'], float(data.get('logistics_stress_score') or 0.0))
        entry['mobility_disruption_score'] = max(entry['mobility_disruption_score'], float(data.get('logistics_stress_score') or 0.0) * 0.75)
        entry['logistics_points'] += 1
        if 'logistics' not in entry['external_sources']:
            entry['external_sources'].append('logistics')
        source_coverage['logistics'] += 1

    economic_docs = _latest_docs_for_day('economic_behavior', day)
    for doc in economic_docs:
        data = doc.get('data') or {}
        country_code = str(doc.get('country') or '').strip().upper()
        if country_code not in signals:
            continue
        entry = signals[country_code]
        entry['household_stress_score'] = max(entry['household_stress_score'], float(data.get('household_stress_score') or 0.0))
        entry['fuel_price_pressure'] = max(entry['fuel_price_pressure'], float(data.get('fuel_price_pressure') or 0.0))
        entry['food_price_pressure'] = max(entry['food_price_pressure'], float(data.get('food_price_pressure') or 0.0))
        entry['labor_stress_score'] = max(entry['labor_stress_score'], float(data.get('labor_stress_score') or 0.0))
        entry['fx_pressure_score'] = max(entry['fx_pressure_score'], float(data.get('fx_pressure_score') or 0.0))
        entry['remittance_stress_score'] = max(entry['remittance_stress_score'], float(data.get('remittance_stress_score') or 0.0))
        entry['energy_stress_score'] = max(entry['energy_stress_score'], float(data.get('energy_stress_score') or 0.0))
        entry['economic_points'] += 1
        if 'economic_behavior' not in entry['external_sources']:
            entry['external_sources'].append('economic_behavior')
        source_coverage['economic_behavior'] += 1

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
        contributing = sum(1 for source in ('wikipedia', 'google_trends', 'telegram_public', 'youtube_public', 'weather', 'mobility', 'aviation', 'logistics', 'economic_behavior') if source in entry['external_sources'])
        entry['social_unrest_score'] = round(min(entry['social_unrest_score'], 1.0), 4)
        entry['google_trends_pressure'] = round(min(entry['google_trends_pressure'], 1.0), 4)
        entry['public_attention_score'] = round(min(entry['public_attention_score'], 1.0), 4)
        entry['narrative_velocity_score'] = round(min(entry['narrative_velocity_score'], 1.0), 4)
        entry['coordination_risk_score'] = round(min(entry['coordination_risk_score'], 1.0), 4)
        entry['weather_stress'] = round(min(entry['weather_stress'], 1.0), 4)
        entry['mobility_disruption_score'] = round(min(entry['mobility_disruption_score'], 1.0), 4)
        entry['aviation_disruption_score'] = round(min(entry['aviation_disruption_score'], 1.0), 4)
        entry['logistics_stress_score'] = round(min(entry['logistics_stress_score'], 1.0), 4)
        entry['household_stress_score'] = round(min(entry['household_stress_score'], 1.0), 4)
        entry['fuel_price_pressure'] = round(min(entry['fuel_price_pressure'], 1.0), 4)
        entry['food_price_pressure'] = round(min(entry['food_price_pressure'], 1.0), 4)
        entry['labor_stress_score'] = round(min(entry['labor_stress_score'], 1.0), 4)
        entry['fx_pressure_score'] = round(min(entry['fx_pressure_score'], 1.0), 4)
        entry['remittance_stress_score'] = round(min(entry['remittance_stress_score'], 1.0), 4)
        entry['energy_stress_score'] = round(min(entry['energy_stress_score'], 1.0), 4)
        entry['external_signal_freshness'] = round(contributing / 9.0, 4)

    summary = {
        'source_docs': {
            'wiki': len(wiki_docs),
            'trends': len(trend_docs),
            'telegram_public': len(telegram_docs),
            'youtube_public': len(youtube_docs),
            'weather': len(weather_docs),
            'mobility': len(mobility_docs),
            'aviation': len(aviation_docs),
            'logistics': len(logistics_docs),
            'economic_behavior': len(economic_docs),
        },
        'country_coverage': {
            'wiki': sum(1 for item in signals.values() if item['attention_points'] > 0),
            'trends': sum(1 for item in signals.values() if item['trend_points'] > 0),
            'weather': sum(1 for item in signals.values() if item['weather_points'] > 0),
            'mobility': sum(1 for item in signals.values() if item['mobility_points'] > 0),
            'aviation': sum(1 for item in signals.values() if item['aviation_points'] > 0),
            'economic_behavior': sum(1 for item in signals.values() if item['economic_points'] > 0),
        },
    }
    return signals, summary
