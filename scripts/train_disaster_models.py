from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from sklearn.calibration import CalibratedClassifierCV
except Exception:
    CalibratedClassifierCV = None

from machine_learning.disaster_models import DISASTER_MODEL_DIR, HAZARD_FEATURES

DATA_PATH = ROOT / "data" / "disaster_training_data.csv"
MODEL_METADATA_PATH = DISASTER_MODEL_DIR / "metadata.json"
CALIBRATED_HAZARDS = {"flood", "wildfire"}
CONSERVATIVE_HAZARDS = {
    "cyclone": {"post_scale": 0.9, "severity_cap": 0.8, "confidence_cap": 0.74, "threshold_floor": 0.58},
    "earthquake": {"post_scale": 0.84, "severity_cap": 0.72, "confidence_cap": 0.68, "threshold_floor": 0.6},
}


def _safe_auc(y_true: pd.Series, y_prob: list[float]) -> float | None:
    try:
        if y_true.nunique() < 2:
            return None
        return float(roc_auc_score(y_true, y_prob))
    except Exception:
        return None


def _build_base_pipeline() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=500, class_weight="balanced")),
    ])


def _fit_model(hazard: str, x_train: pd.DataFrame, y_train: pd.Series):
    base = _build_base_pipeline()
    if hazard in CALIBRATED_HAZARDS and CalibratedClassifierCV is not None and y_train.nunique() > 1 and len(x_train) >= 80:
        try:
            calibrated = CalibratedClassifierCV(estimator=base, method="sigmoid", cv=3)
        except TypeError:
            calibrated = CalibratedClassifierCV(base_estimator=base, method="sigmoid", cv=3)
        return calibrated.fit(x_train, y_train), "sigmoid"
    return base.fit(x_train, y_train), None


def _pick_threshold(hazard: str, y_true: pd.Series, y_prob: np.ndarray) -> tuple[float, dict[str, float]]:
    thresholds = np.linspace(0.35, 0.8, 19) if hazard in CALIBRATED_HAZARDS else np.linspace(0.5, 0.85, 15)
    best_threshold = 0.5
    best_score = -1.0
    best_metrics = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    for threshold in thresholds:
        preds = (y_prob >= threshold).astype(int)
        precision = float(precision_score(y_true, preds, zero_division=0))
        recall = float(recall_score(y_true, preds, zero_division=0))
        f1 = float(f1_score(y_true, preds, zero_division=0))
        score = (0.55 * precision) + (0.3 * recall) + (0.15 * f1) if hazard in CALIBRATED_HAZARDS else (0.68 * precision) + (0.18 * recall) + (0.14 * f1)
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
            best_metrics = {"precision": precision, "recall": recall, "f1": f1}

    conservative = CONSERVATIVE_HAZARDS.get(hazard)
    if conservative:
        best_threshold = max(best_threshold, float(conservative["threshold_floor"]))
    return round(best_threshold, 6), {key: round(value, 6) for key, value in best_metrics.items()}


def train_disaster_models(data_path: Path = DATA_PATH) -> dict[str, Any]:
    if not data_path.exists():
        raise FileNotFoundError(f"Training data not found: {data_path}")

    frame = pd.read_csv(data_path)
    if frame.empty:
        raise RuntimeError("Disaster training dataset is empty")

    DISASTER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(data_path),
        "models": {},
    }

    for hazard, feature_names in HAZARD_FEATURES.items():
        hazard_frame = frame.loc[frame["hazard"] == hazard].copy()
        if len(hazard_frame) < 40:
            raise RuntimeError(f"Need at least 40 rows for {hazard}; found {len(hazard_frame)}")

        x = hazard_frame[feature_names].copy()
        y = hazard_frame["target_alert"].astype(int)

        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y if y.nunique() > 1 else None,
        )

        fitted, calibration_method = _fit_model(hazard, x_train, y_train)
        proba = fitted.predict_proba(x_test)[:, 1]
        threshold, threshold_metrics = _pick_threshold(hazard, y_test, proba)
        preds = (proba >= threshold).astype(int)

        conservative = CONSERVATIVE_HAZARDS.get(hazard, {})
        metrics = {
            "train_rows": int(len(x_train)),
            "validation_rows": int(len(x_test)),
            "positive_rate": round(float(y.mean()), 6),
            "accuracy": round(float(accuracy_score(y_test, preds)), 6),
            "brier_score": round(float(brier_score_loss(y_test, proba)), 6),
            "roc_auc": round(_safe_auc(y_test, proba) or 0.0, 6),
            "precision": threshold_metrics["precision"],
            "recall": threshold_metrics["recall"],
            "f1": threshold_metrics["f1"],
        }
        bundle = {
            "model": fitted,
            "hazard": hazard,
            "feature_names": feature_names,
            "trained_at": metadata["trained_at"],
            "metrics": metrics,
            "model_type": "calibrated_logistic_regression" if calibration_method else "logistic_regression",
            "data_path": str(data_path),
            "threshold": threshold,
            "calibration_method": calibration_method,
            "post_scale": float(conservative.get("post_scale") or 1.0),
            "severity_cap": float(conservative.get("severity_cap") or 0.96),
            "confidence_cap": float(conservative.get("confidence_cap") or 0.92),
        }

        model_path = DISASTER_MODEL_DIR / f"{hazard}_model.joblib"
        joblib.dump(bundle, model_path)
        metadata["models"][hazard] = {
            "path": str(model_path),
            "feature_names": feature_names,
            "metrics": metrics,
            "threshold": threshold,
            "calibration_method": calibration_method,
            "post_scale": bundle["post_scale"],
            "severity_cap": bundle["severity_cap"],
            "confidence_cap": bundle["confidence_cap"],
        }

    MODEL_METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train persisted hazard-specific disaster models")
    parser.add_argument("--data", default=str(DATA_PATH))
    args = parser.parse_args()

    result = train_disaster_models(Path(args.data))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
