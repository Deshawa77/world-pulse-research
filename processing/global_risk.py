from database.mongo import db
from datetime import datetime, timedelta

# -------------------------
# Collections & weights
# -------------------------
# Weight per source: news and gdelt are more influential than wiki, who, trends
COLLECTIONS = {
    "news": 0.4,
    "gdelt": 0.4,
    "wiki": 0.05,
    "who": 0.1,
    "trends": 0.05
}

# -------------------------
# Helper: Safe sentiment average with weights
# -------------------------
def _get_daily_average(day):
    weighted_sentiments = []
    total_weight = 0

    for col, weight in COLLECTIONS.items():
        for doc in db[col].find(
            {}, {"data.sentiment.vader.compound": 1, "data.processed_at": 1}
        ):
            sentiment = doc.get("data", {}).get("sentiment", {}).get("vader", {}).get("compound")
            processed_time = doc.get("data", {}).get("processed_at")

            if sentiment is None or not processed_time:
                continue

            try:
                doc_date = datetime.fromisoformat(processed_time).date()
            except:
                continue

            if doc_date == day:
                weighted_sentiments.append(sentiment * weight)
                total_weight += weight

    if weighted_sentiments and total_weight > 0:
        return sum(weighted_sentiments) / total_weight
    return 0.0

# -------------------------
# Helper: Clean topics
# -------------------------
def _clean_topic(topic):
    if not topic:
        return None

    topic = str(topic).strip()

    # Remove garbage topics
    if topic in ["Other", ", ,", ", , ", "921, ,", "1494, ,"]:
        return None

    # Remove numeric-only or comma-only topics
    if topic.replace(",", "").strip().isdigit():
        return None

    if len(topic) < 3:
        return None

    return topic

# -------------------------
# Helper: Get top topics
# -------------------------
def _get_top_topics(limit=5):
    topic_counts = {}

    for col in ["news", "gdelt"]:
        cursor = db[col].aggregate([
            {"$group": {"_id": "$data.topic", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20}
        ])

        for doc in cursor:
            topic = _clean_topic(doc["_id"])
            if topic:
                topic_counts[topic] = topic_counts.get(topic, 0) + doc["count"]

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    return [t[0] for t in sorted_topics[:limit]] if sorted_topics else ["multiple global factors"]

# -------------------------
# Main Risk Function
# -------------------------
def compute_global_risk(days=2):
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # -------------------------
    # Sentiment averages (weighted)
    # -------------------------
    today_avg = _get_daily_average(today)
    yesterday_avg = _get_daily_average(yesterday)

    # -------------------------
    # Change in sentiment → risk score
    # -------------------------
    delta = today_avg - yesterday_avg
    # Normalize delta (-1 to +1) → 0..100
    risk_score = (1 - delta) / 2 * 100
    risk_score = max(0, min(100, risk_score))

    # -------------------------
    # Get top topics
    # -------------------------
    top_topics = _get_top_topics()

    return round(risk_score, 2), top_topics
