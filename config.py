# config.py
import os

DATA_DIR = "./data"
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# Original feature columns
FEATURE_COLUMNS = [
    "news_sentiment","gdelt_sentiment","crypto_return","crypto_volatility",
    "stock_return","stock_volatility","weather_anomaly"
]

# Extended feature columns for new collectors
EXTENDED_FEATURE_COLUMNS = [
    # Original features
    "news_sentiment","gdelt_sentiment","crypto_return","crypto_volatility",
    "stock_return","stock_volatility","weather_anomaly",
    # Social Media
    "youtube_sentiment","stackoverflow_sentiment","reddit_enhanced_sentiment",
    # Financial
    "alphavantage_sentiment","fmp_financial_health","eod_market_breadth",
    # Crisis & Conflict
    "acled_conflict_intensity","reliefweb_crisis_score",
    # Environmental
    "nasa_environmental_anomaly","openaq_air_quality_index",
    # NLP/AI
    "huggingface_sentiment",

    # Crypto
    "messari_onchain_activity"
]

# Collector configuration
COLLECTOR_CONFIG = {
    "youtube": {"enabled": True, "interval": 300},
    "alphavantage": {"enabled": True, "interval": 300},
    "acled": {"enabled": True, "interval": 600},
    "nasa_earth": {"enabled": True, "interval": 600},
    "huggingface_nlp": {"enabled": True, "interval": 300},
    "stackoverflow": {"enabled": True, "interval": 300},
    "openaq": {"enabled": True, "interval": 600},
    "reliefweb": {"enabled": True, "interval": 300},
    "messari": {"enabled": True, "interval": 300},
    "financialmodelingprep": {"enabled": True, "interval": 300},
    "eodhistorical": {"enabled": True, "interval": 300},
    "reddit_enhanced": {"enabled": True, "interval": 300},
}


# API Rate limits (requests per minute)
API_RATE_LIMITS = {
    "youtube": 100,
    "alphavantage": 5,  # Free tier
    "acled": 100,
    "nasa_earth": 1000,
    "huggingface": 1000,
    "stackoverflow": 300,
    "openaq": 100,
    "reliefweb": 100,
    "messari": 100,
    "financialmodelingprep": 250,
    "eodhistorical": 1000,
    "reddit": 60,
}
