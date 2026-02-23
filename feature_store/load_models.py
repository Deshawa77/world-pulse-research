import os
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from feature_store.model_registry import register_model, promote_model, list_models

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly",
]

LOCAL_MODELS = {
    "gb_model": os.path.join(MODELS_DIR, "gb_model.pkl"),
    "logistic_model": os.path.join(MODELS_DIR, "logistic_model.pkl"),
    "rf_model": os.path.join(MODELS_DIR, "rf_model.pkl"),
}

FEATURE_CSV_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "data", "hourly_features.csv"),
    os.path.join(PROJECT_ROOT, "hourly_features.csv"),
]


def _load_training_frame() -> pd.DataFrame:
    for path in FEATURE_CSV_CANDIDATES:
        if os.path.exists(path):
            df = pd.read_csv(path)
            required = set(FEATURE_COLUMNS + ["global_risk_score"])
            if required.issubset(set(df.columns)):
                return df
    raise FileNotFoundError("No valid hourly features CSV found for model bootstrap")


def _bootstrap_local_models_if_missing() -> None:
    missing = [name for name, path in LOCAL_MODELS.items() if not os.path.exists(path)]
    if not missing:
        return

    os.makedirs(MODELS_DIR, exist_ok=True)
    df = _load_training_frame().copy()
    df = df.dropna(subset=FEATURE_COLUMNS + ["global_risk_score"])
    if len(df) < 10:
        raise FileNotFoundError("Insufficient feature rows to bootstrap local models (need at least 10)")

    X = df[FEATURE_COLUMNS].astype(float)
    cutoff = float(df["global_risk_score"].median())
    y = (df["global_risk_score"].astype(float) >= cutoff).astype(int)

    if y.nunique() < 2:
        order = df["global_risk_score"].astype(float).rank(method="first")
        y = (order >= order.median()).astype(int)

    models_to_train = {
        "gb_model": GradientBoostingClassifier(random_state=42),
        "rf_model": RandomForestClassifier(n_estimators=250, random_state=42, n_jobs=-1),
        "logistic_model": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    }

    for name in missing:
        model = models_to_train[name]
        model.fit(X, y)
        joblib.dump(model, LOCAL_MODELS[name])
        print(f"Bootstrapped local model: {LOCAL_MODELS[name]}")


def load_all_models():
    """
    Loads all models, auto-registering missing ones.
    Only gb_model is promoted to production; others stay in staging.
    """
    _bootstrap_local_models_if_missing()

    loaded_models = {}
    registry_metadata = list_models()

    for name, path in LOCAL_MODELS.items():
        found_version = None
        for version, info in registry_metadata.items():
            if name in version:
                found_version = version
                break

        if not found_version:
            if os.path.exists(path):
                version = f"auto_{name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                try:
                    stage = "production" if name == "gb_model" else "staging"
                    register_model(path, version=version, metrics={"bootstrap": True}, stage=stage)
                    if stage == "production":
                        promote_model(version)
                    found_version = version
                    print(f"Auto-registered {name} in {stage}")
                except Exception as e:
                    print(f"Failed to register {name}: {e}")
                    continue
            else:
                print(f"Local model file not found: {path}")
                continue

        model_file = list_models()[found_version]["file"]
        if os.path.exists(model_file):
            loaded_models[name] = joblib.load(model_file)
            print(f"Loaded {name} from {model_file}")
        else:
            print(f"Model file missing in registry for {name}")

    if not loaded_models:
        raise FileNotFoundError("No models could be loaded from registry or local files")

    return loaded_models
