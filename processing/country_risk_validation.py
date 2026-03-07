import math
import os
from datetime import datetime, timezone

import pandas as pd
from pymongo import DESCENDING

from database.mongo import db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUND_TRUTH_CSV = os.path.join(PROJECT_ROOT, 'data', 'country_risk_ground_truth.csv')


def _parse_day(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if 'T' in raw:
        raw = raw.split('T', 1)[0]
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        return None


def load_ground_truth(day: datetime | None = None):
    if not os.path.exists(GROUND_TRUTH_CSV):
        return pd.DataFrame(columns=['date', 'country', 'risk_label', 'source', 'notes'])
    df = pd.read_csv(GROUND_TRUTH_CSV)
    if day is None or df.empty:
        return df
    target_day = (day or datetime.now(timezone.utc)).date().isoformat()
    return df[df['date'].astype(str) == target_day].copy()


def _latest_country_scores():
    pipeline = [
        {'$match': {'mode': 'online'}},
        {'$sort': {'_id': -1}},
        {'$group': {'_id': '$country', 'doc': {'$first': '$$ROOT'}}},
        {'$project': {'country': '$_id', 'timestamp': '$doc.timestamp', 'features': '$doc.features'}},
    ]
    return list(db.country_features.aggregate(pipeline))


def _calibration_bins(labels, probs, bins=5):
    if not labels:
        return []
    rows = []
    for idx in range(bins):
        lo = idx / bins
        hi = (idx + 1) / bins
        bucket = [i for i, p in enumerate(probs) if (lo <= p < hi) or (idx == bins - 1 and p == 1.0)]
        if not bucket:
            continue
        rows.append({
            'bin': f'{lo:.1f}-{hi:.1f}',
            'count': len(bucket),
            'mean_prediction': round(sum(probs[i] for i in bucket) / len(bucket), 4),
            'observed_rate': round(sum(labels[i] for i in bucket) / len(bucket), 4),
        })
    return rows


def run_country_risk_validation(day: datetime | None = None, persist: bool = True):
    truth_df = load_ground_truth(day)
    latest = {row.get('country'): row for row in _latest_country_scores()}
    rows = []
    for _, item in truth_df.iterrows():
        country = str(item.get('country') or '').strip().upper()
        model_row = latest.get(country)
        if not model_row:
            continue
        features = model_row.get('features') or {}
        risk = float(features.get('global_risk_score', 0.0) or 0.0)
        rows.append({
            'country': country,
            'label': int(item.get('risk_label', 0)),
            'prob': max(0.0, min(risk / 100.0, 1.0)),
            'risk_score': round(risk, 2),
            'war_state_rules': features.get('war_state_rules', []),
            'source_count': int(features.get('source_count', 0) or 0),
        })

    if not rows:
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'sample_count': 0,
            'ground_truth_rows': int(len(truth_df.index)),
            'status': 'no_ground_truth_matches',
            'calibration_bins': [],
        }
        if persist:
            db.country_model_validation.insert_one(summary)
        return summary

    labels = [row['label'] for row in rows]
    probs = [row['prob'] for row in rows]
    preds_50 = [1 if p >= 0.5 else 0 for p in probs]
    preds_70 = [1 if p >= 0.7 else 0 for p in probs]
    accuracy_50 = sum(int(a == b) for a, b in zip(labels, preds_50)) / len(labels)
    accuracy_70 = sum(int(a == b) for a, b in zip(labels, preds_70)) / len(labels)
    brier = sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels)
    clipped = [min(max(p, 1e-6), 1 - 1e-6) for p in probs]
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(clipped, labels)) / len(labels)
    positive_count = sum(labels)
    calibration_bins = _calibration_bins(labels, probs, bins=5)

    summary = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'sample_count': len(rows),
        'ground_truth_rows': int(len(truth_df.index)),
        'status': 'ok',
        'metrics': {
            'accuracy_at_50': round(accuracy_50, 4),
            'accuracy_at_70': round(accuracy_70, 4),
            'brier_score': round(brier, 4),
            'log_loss': round(log_loss, 4),
            'positive_rate': round(positive_count / len(labels), 4),
            'avg_predicted_risk': round(sum(probs) / len(probs), 4),
        },
        'calibration_bins': calibration_bins,
        'evaluated_rows': rows,
    }
    if persist:
        db.country_model_validation.insert_one(summary)
    return summary


def latest_country_risk_validation():
    doc = db.country_model_validation.find_one(sort=[('_id', DESCENDING)])
    if not doc:
        return {'status': 'missing'}
    doc['_id'] = str(doc['_id'])
    return doc
