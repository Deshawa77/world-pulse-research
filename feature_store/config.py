import os

BASE_DIR = "feature_store"

GLOBAL_PATH = os.path.join(BASE_DIR, "global", "features.parquet")
COUNTRY_PATH = os.path.join(BASE_DIR, "country", "features.parquet")
REALTIME_PATH = os.path.join(BASE_DIR, "realtime", "features.parquet")

VERSION_PATH = os.path.join(BASE_DIR, "versions")
REGISTRY_PATH = os.path.join(BASE_DIR, "versions", "registry.json")
