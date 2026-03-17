from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore[assignment]


_ANALYZER = SentimentIntensityAnalyzer() if SentimentIntensityAnalyzer else None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        return f
    except Exception:
        return None


def parse_doc_timestamp(doc: dict[str, Any]) -> datetime | None:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    candidates = [
        data.get("processed_at"),
        doc.get("processed_at"),
        doc.get("collected_at"),
        data.get("published_at"),
        doc.get("timestamp"),
        data.get("timestamp"),
    ]
    for raw in candidates:
        if not raw:
            continue
        parsed = parse_any_datetime(raw)
        if parsed is not None:
            return parsed
    return None


def parse_any_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(raw), fmt)
        except Exception:
            continue
    return None


def _extract_embedded_sentiment(doc: dict[str, Any]) -> float | None:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}

    candidates = [
        (((data.get("sentiment") or {}).get("vader") or {}).get("compound")),
        ((data.get("sentiment") or {}).get("compound")),
        ((data.get("sentiment") or {}).get("polarity")),
        (((doc.get("analysis") or {}).get("sentiment") or {}).get("vader") or {}).get("compound"),
        ((doc.get("nlp") or {}).get("sentiment")),
    ]
    for candidate in candidates:
        value = _safe_float(candidate)
        if value is not None:
            return max(-1.0, min(1.0, value))
    return None


def _build_text_for_sentiment(doc: dict[str, Any]) -> str:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    parts = [
        doc.get("text_en"),
        doc.get("text_original"),
        data.get("nlp_text"),
        data.get("title"),
        data.get("description"),
    ]
    text = " ".join(str(p).strip() for p in parts if p)
    return " ".join(text.split())


def extract_sentiment_signal(doc: dict[str, Any]) -> float | None:
    embedded = _extract_embedded_sentiment(doc)
    if embedded is not None:
        return embedded

    if _ANALYZER is None:
        return None

    text = _build_text_for_sentiment(doc)
    if not text:
        return None

    try:
        score = _ANALYZER.polarity_scores(text).get("compound")
        value = _safe_float(score)
        if value is None:
            return None
        return max(-1.0, min(1.0, value))
    except Exception:
        return None
