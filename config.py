# config.py
import os

DATA_DIR = "./data"
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")
FEATURE_COLUMNS = [
    "news_sentiment","gdelt_sentiment","crypto_return","crypto_volatility",
    "stock_return","stock_volatility","weather_anomaly"
]
