from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from pymongo import DESCENDING
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from database.mongo import db
from feature_store.model_registry import promote_model, register_model
from machine_learning.prediction_schema import (
    DEFAULT_PREDICTION_FEATURES,
    PREDICTION_SCHEMA_VERSION,
    extract_feature_vector,
)

DEFAULT_MODE = "online"
DEFAULT_LIMIT = 5000
DEFAULT_MIN_ROWS = 250
DEFAULT_TRAIN_FRACTION = 0.8


@dataclass
class TrainingResult:
    version: str
    metrics: dict[str, Any]
    feature_names: list[str]
    schema_version: str


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _iter_feature_docs(mode: str = DEFAULT_MODE, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    docs = list(
        db.global_features.find({"mode": mode}, {"features": 1, "timestamp": 1, "mode": 1})
        .sort([("timestamp", DESCENDING), ("_id", DESCENDING)])
        .limit(max(10, limit))
    )
    return list(reversed(docs))


def _build_training_frame(mode: str = DEFAULT_MODE, limit: int = DEFAULT_LIMIT) -> pd.DataFrame:
    docs = _iter_feature_docs(mode=mode, limit=limit)
    rows: list[dict[str, Any]] = []

    for current_doc, next_doc in zip(docs, docs[1:]):
        current_features = (current_doc or {}).get("features") or {}
        next_features = (next_doc or {}).get("features") or {}
        feature_vector = extract_feature_vector(current_features, DEFAULT_PREDICTION_FEATURES)
        target_score = max(
            _safe_float(next_features.get("global_risk_score"), 0.0),
            _safe_float(next_features.get("forecast_risk_score"), 0.0),
        )
        rows.append({
            "timestamp": current_doc.get("timestamp"),
            **{name: feature_vector[idx] for idx, name in enumerate(DEFAULT_PREDICTION_FEATURES)},
            "target_score": target_score,
        })

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("No global feature rows available for expanded prediction training")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return frame


def _build_candidate_models() -> dict[str, Pipeline]:
    return {
        "expanded_gb_reg": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", GradientBoostingRegressor(random_state=42)),
        ]),
        "expanded_rf_reg": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(n_estimators=300, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=-1)),
        ]),
        "expanded_ridge_reg": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0, random_state=42)),
        ]),
    }


def _evaluate_model(model: Pipeline, x_train: pd.DataFrame, y_train: pd.Series, x_test: pd.DataFrame, y_test: pd.Series) -> dict[str, Any]:
    fitted = model.fit(x_train, y_train)
    predictions = np.clip(fitted.predict(x_test), 0.0, 100.0)
    return {
        "pipeline": fitted,
        "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
        "mae": float(mean_absolute_error(y_test, predictions)),
        "r2": float(r2_score(y_test, predictions)),
        "mean_prediction": float(np.mean(predictions)),
    }


def train_and_register_expanded_model(mode: str = DEFAULT_MODE, limit: int = DEFAULT_LIMIT, promote: bool = True) -> TrainingResult:
    frame = _build_training_frame(mode=mode, limit=limit)
    if len(frame) < DEFAULT_MIN_ROWS:
        raise RuntimeError(f"Need at least {DEFAULT_MIN_ROWS} rows for expanded training; found {len(frame)}")

    x = frame[DEFAULT_PREDICTION_FEATURES].copy()
    y = frame["target_score"].astype(float)

    split_idx = max(int(len(frame) * DEFAULT_TRAIN_FRACTION), DEFAULT_MIN_ROWS - 1)
    split_idx = min(split_idx, len(frame) - 1)
    x_train = x.iloc[:split_idx]
    y_train = y.iloc[:split_idx]
    x_test = x.iloc[split_idx:]
    y_test = y.iloc[split_idx:]

    if x_test.empty or y_test.empty:
        raise RuntimeError("Expanded training split left no validation rows; need more global feature history")

    candidates = _build_candidate_models()
    evaluated: dict[str, dict[str, Any]] = {}
    for name, pipeline in candidates.items():
        evaluated[name] = _evaluate_model(pipeline, x_train, y_train, x_test, y_test)

    best_name, best_info = sorted(
        evaluated.items(),
        key=lambda item: (
            item[1]["rmse"],
            item[1]["mae"],
            -item[1]["r2"],
        ),
    )[0]

    timestamp_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = f"expanded_global_{best_name}_{timestamp_label}"
    metrics = {
        "rmse": round(best_info["rmse"], 6),
        "mae": round(best_info["mae"], 6),
        "r2": round(best_info["r2"], 6),
        "train_rows": int(len(x_train)),
        "validation_rows": int(len(x_test)),
        "candidate": best_name,
        "target": "next_step max(global_risk_score, forecast_risk_score)",
    }
    bundle = {
        "model": best_info["pipeline"],
        "task": "regression",
        "feature_names": list(DEFAULT_PREDICTION_FEATURES),
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
    }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp_file:
        joblib.dump(bundle, tmp_file.name)
        temp_model_path = tmp_file.name

    extra_metadata = {
        "feature_names": list(DEFAULT_PREDICTION_FEATURES),
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "task": "regression",
        "feature_source": "global_features",
        "target_definition": "next_step max(global_risk_score, forecast_risk_score)",
        "candidate": best_name,
    }
    register_model(temp_model_path, version=version, metrics=metrics, stage="staging", extra_metadata=extra_metadata)
    if promote:
        promote_model(version)

    try:
        Path(temp_model_path).unlink(missing_ok=True)
    except Exception:
        pass

    return TrainingResult(
        version=version,
        metrics=metrics,
        feature_names=list(DEFAULT_PREDICTION_FEATURES),
        schema_version=PREDICTION_SCHEMA_VERSION,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and register the expanded global prediction model")
    parser.add_argument("--mode", default=DEFAULT_MODE)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--no-promote", action="store_true")
    args = parser.parse_args()

    result = train_and_register_expanded_model(mode=args.mode, limit=args.limit, promote=not args.no_promote)
    print(json.dumps({
        "version": result.version,
        "schema_version": result.schema_version,
        "feature_names": result.feature_names,
        "metrics": result.metrics,
    }, indent=2))


if __name__ == "__main__":
    main()
