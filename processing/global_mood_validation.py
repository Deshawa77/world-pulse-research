import math
import os
from datetime import datetime, timezone

import pandas as pd
from pymongo import DESCENDING

from database.mongo import db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUND_TRUTH_CSV = os.path.join(PROJECT_ROOT, "data", "global_mood_ground_truth.csv")


def _parse_day(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        return None


def load_ground_truth(day: datetime | None = None):
    if not os.path.exists(GROUND_TRUTH_CSV):
        return pd.DataFrame(columns=["date", "mood_score", "mood_label", "source", "notes"])
    df = pd.read_csv(GROUND_TRUTH_CSV)
    if day is None or df.empty:
        return df
    target_day = (day or datetime.now(timezone.utc)).date().isoformat()
    return df[df["date"].astype(str) == target_day].copy()


def _latest_global_mood_scores():
    pipeline = [
        {"$match": {"mode": "online", "features.global_mood_score": {"$exists": True}}},
        {"$sort": {"_id": -1}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": {"$ifNull": ["$timestamp", "$features.timestamp"]},
                    }
                },
                "doc": {"$first": "$$ROOT"},
            }
        },
        {
            "$project": {
                "date": "$_id",
                "timestamp": "$doc.timestamp",
                "features": "$doc.features",
            }
        },
    ]
    docs = list(db.global_features.aggregate(pipeline))
    if docs:
        return docs
    docs = list(db.dashboard_features.aggregate(pipeline))
    return docs


def _classification_metrics(labels, probs):
    if not labels:
        return None
    preds_50 = [1 if p >= 0.5 else 0 for p in probs]
    preds_70 = [1 if p >= 0.7 else 0 for p in probs]
    accuracy_50 = sum(int(a == b) for a, b in zip(labels, preds_50)) / len(labels)
    accuracy_70 = sum(int(a == b) for a, b in zip(labels, preds_70)) / len(labels)
    brier = sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels)
    clipped = [min(max(p, 1e-6), 1 - 1e-6) for p in probs]
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(clipped, labels)) / len(labels)
    return {
        "accuracy_at_50": round(accuracy_50, 4),
        "accuracy_at_70": round(accuracy_70, 4),
        "brier_score": round(brier, 4),
        "log_loss": round(log_loss, 4),
        "positive_rate": round(sum(labels) / len(labels), 4),
        "avg_predicted_negative_mood": round(sum(probs) / len(probs), 4),
    }


def _regression_metrics(actuals, preds):
    if not actuals:
        return None
    abs_errors = [abs(p - a) for a, p in zip(actuals, preds)]
    sq_errors = [(p - a) ** 2 for a, p in zip(actuals, preds)]
    mae = sum(abs_errors) / len(abs_errors)
    rmse = math.sqrt(sum(sq_errors) / len(sq_errors))
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "avg_labeled_mood": round(sum(actuals) / len(actuals), 4),
        "avg_predicted_mood": round(sum(preds) / len(preds), 4),
    }


def run_global_mood_validation(day: datetime | None = None, persist: bool = True):
    truth_df = load_ground_truth(day)
    latest = {str(row.get("date") or "").strip(): row for row in _latest_global_mood_scores()}
    rows = []
    for _, item in truth_df.iterrows():
        row_date = str(item.get("date") or "").strip()
        if not row_date:
            continue
        model_row = latest.get(row_date)
        if not model_row:
            continue
        features = model_row.get("features") or {}
        mood_score = float(features.get("global_mood_score", 50.0) or 50.0)
        confidence = float(features.get("global_mood_confidence", 0.0) or 0.0)
        uncertainty = float(features.get("global_mood_uncertainty", 18.0) or 18.0)
        evaluated = {
            "date": row_date,
            "predicted_mood_score": round(mood_score, 2),
            "predicted_negative_mood_prob": round(max(0.0, min((100.0 - mood_score) / 100.0, 1.0)), 4),
            "confidence": round(confidence, 4),
            "uncertainty": round(uncertainty, 2),
            "source": item.get("source"),
            "notes": item.get("notes"),
        }
        if pd.notna(item.get("mood_score")):
            evaluated["labeled_mood_score"] = float(item.get("mood_score"))
        if pd.notna(item.get("mood_label")):
            evaluated["mood_label"] = int(item.get("mood_label"))
        rows.append(evaluated)

    if not rows:
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sample_count": 0,
            "ground_truth_rows": int(len(truth_df.index)),
            "status": "no_ground_truth_matches",
            "metrics": {},
            "evaluated_rows": [],
            "ground_truth_path": GROUND_TRUTH_CSV,
        }
        if persist:
            db.global_mood_validation.insert_one(summary)
        return summary

    score_rows = [row for row in rows if "labeled_mood_score" in row]
    label_rows = [row for row in rows if "mood_label" in row]
    metrics = {
        "confidence_avg": round(sum(float(row["confidence"]) for row in rows) / len(rows), 4),
        "uncertainty_avg": round(sum(float(row["uncertainty"]) for row in rows) / len(rows), 4),
    }
    regression = _regression_metrics(
        [float(row["labeled_mood_score"]) for row in score_rows],
        [float(row["predicted_mood_score"]) for row in score_rows],
    )
    classification = _classification_metrics(
        [int(row["mood_label"]) for row in label_rows],
        [float(row["predicted_negative_mood_prob"]) for row in label_rows],
    )
    if regression:
        metrics["regression"] = regression
    if classification:
        metrics["classification"] = classification

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(rows),
        "ground_truth_rows": int(len(truth_df.index)),
        "status": "ok",
        "metrics": metrics,
        "evaluated_rows": rows,
        "ground_truth_path": GROUND_TRUTH_CSV,
    }
    if persist:
        db.global_mood_validation.insert_one(summary)
    return summary


def latest_global_mood_validation():
    doc = db.global_mood_validation.find_one(sort=[("_id", DESCENDING)])
    if not doc:
        return {"status": "missing"}
    doc["_id"] = str(doc["_id"])
    return doc
