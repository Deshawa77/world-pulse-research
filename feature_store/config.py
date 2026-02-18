import os

BASE_DIR = "feature_store"

GLOBAL_PATH = "data/daily_features.parquet"
COUNTRY_PATH = "data/country_features.parquet"
REALTIME_PATH = "data/hourly_features.parquet"


VERSION_PATH = os.path.join(BASE_DIR, "versions")
REGISTRY_PATH = os.path.join(BASE_DIR, "versions", "registry.json")
