from database.mongo import db
from datetime import datetime, timedelta
import pandas as pd

# -------------------------
# Collections & weights
# -------------------------
COLLECTIONS = {
    "news": 0.4,
    "gdelt": 0.4,
    "wiki": 0.05,
    "who": 0.1,
    "trends": 0.05
}

# -------------------------
# Helper: Load recent hourly sentiment
# -------------------------
def _get_hourly_sentiments(hours=24):
    """
    Load recent sentiment data from Mongo and return a DataFrame
    with timestamp and weighted polarity for the last `hours` hours.
    """
    rows = []

    for col, weight in COLLECTIONS.items():
        cursor = db[col].find({}, {"data.sentiment.vader.compound": 1, "data.processed_at": 1})
        for doc in cursor:
            sentiment = doc.get("data", {}).get("sentiment", {}).get("vader", {}).get("compound")
            processed_time = doc.get("data", {}).get("processed_at")
            if sentiment is None or not processed_time:
                continue
            try:
                ts = datetime.fromisoformat(processed_time)
            except:
                continue
            if ts >= datetime.utcnow() - timedelta(hours=hours):
                rows.append({"timestamp": ts, "polarity": sentiment * weight})

    if rows:
        df = pd.DataFrame(rows)
        df = df.sort_values("timestamp")
        return df
    else:
        return pd.DataFrame(columns=["timestamp", "polarity"])

# -------------------------
# Helper: Clean topics
# -------------------------
def _clean_topic(topic):
    if not topic:
        return None
    topic = str(topic).strip()
    if topic in ["Other", ", ,", ", , ", "921, ,", "1494, ,"]:
        return None
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
def compute_global_risk():
    """
    Compute global risk dynamically using:
    1) Hourly sentiment averages
    2) Sentiment volatility
    3) Article volume spikes
    4) External events (optional placeholder)
    """

    # Step 1 & 2: Load last 24h sentiment
    df = _get_hourly_sentiments(hours=24)

    if df.empty:
        # No data → neutral risk
        return 50.0, ["no data"]

    # Hourly averages
    hourly_avg = df.groupby(df['timestamp'].dt.hour)['polarity'].mean()
    avg_sentiment = hourly_avg.mean()  # mean of hourly averages

    # Step 3: Sentiment volatility
    sentiment_std = df['polarity'].std() if len(df) > 1 else 0.0

    # Step 4: Article volume spikes (last 1 hour)
    last_hour = datetime.utcnow() - timedelta(hours=1)
    new_articles_count = len(df[df['timestamp'] >= last_hour])
    volume_score = min(10, new_articles_count / 5)  # scale 0–10

    # Step 5: Compute final risk
    risk_score = 50 - (avg_sentiment * 40)    # base risk from sentiment
    risk_score += sentiment_std * 20          # volatility boost
    risk_score += volume_score                 # volume spike
    risk_score = max(0, min(100, risk_score)) # clamp 0–100

    # Step 6: Optional external API signals
    try:
        external_events = []  # placeholder for future API integration
        risk_score += len(external_events) * 2
        risk_score = max(0, min(100, risk_score))
    except:
        pass

    # Step 7: Top topics
    top_topics = _get_top_topics()

    return round(risk_score, 2), top_topics
