# processing/global_crisis_detector.py

from database.mongo import db
from datetime import datetime, timedelta
from collections import defaultdict
from monitoring.email_alert import send_email_alert

# Collections to monitor
COLLECTIONS = ["news", "reddit", "gdelt", "wiki", "who", "trends"]

# Settings
HISTORY_DAYS = 7
WARNING_THRESHOLD = -0.15
ALERT_THRESHOLD = -0.25
SEVERE_THRESHOLD = -0.40


# --------------------------
# Get average sentiment per day
# --------------------------
def get_daily_sentiment(days=HISTORY_DAYS):
    today = datetime.utcnow().date()
    daily_sentiment = {}

    for i in range(days):
        day = today - timedelta(days=i)
        sentiments = []
        source_counts = {}

        for col_name in COLLECTIONS:
            collection = db[col_name]
            count = 0

            for doc in collection.find({}, {"data.sentiment.vader.compound": 1, "data.processed_at": 1}):
                processed_time = doc.get("data", {}).get("processed_at")
                sentiment = doc.get("data", {}).get("sentiment", {}).get("vader", {}).get("compound")

                if sentiment is None:
                    continue

                if processed_time:
                    try:
                        doc_date = datetime.fromisoformat(processed_time).date()
                        if doc_date == day:
                            sentiments.append(sentiment)
                            count += 1
                    except:
                        continue

            if count > 0:
                source_counts[col_name] = count

        avg = sum(sentiments) / len(sentiments) if sentiments else None  # None if no valid data
        daily_sentiment[str(day)] = {
            "avg": avg,
            "sources": source_counts
        }

    return dict(sorted(daily_sentiment.items()))


# --------------------------
# Determine alert level
# --------------------------
def get_alert_level(delta):
    if delta is None:
        return None
    if delta <= SEVERE_THRESHOLD:
        return "SEVERE"
    elif delta <= ALERT_THRESHOLD:
        return "ALERT"
    elif delta <= WARNING_THRESHOLD:
        return "WARNING"
    return None


# --------------------------
# Get dominant topics (from topic modeling)
# --------------------------
def get_top_topics():
    topic_collection = db.get("topics", None)
    if not topic_collection:
        return []

    topic_counts = defaultdict(int)
    for doc in topic_collection.find():
        topic = doc.get("topic")
        if topic:
            topic_counts[topic] += 1

    if not topic_counts:
        return []

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    return [t[0] for t in sorted_topics[:3]]


# --------------------------
# AI-style summary
# --------------------------
def generate_summary(level, delta, topics):
    topic_text = ", ".join(topics) if topics else "multiple global factors"
    return (
        f"{level or 'Low risk'}: Global risk score: {abs(delta or 0) * 100:.0f}/100.\n"
        f"Current drivers: {topic_text}."
    )


# --------------------------
# Crisis Detection
# --------------------------
def detect_crisis(email_alert_func=None, verbose=True):
    history = get_daily_sentiment()
    dates = list(history.keys())

    if len(dates) < 2:
        if verbose:
            print("Not enough data.")
        return None

    today = dates[-1]
    yesterday = dates[-2]

    current_avg = history[today]["avg"]
    previous_avg = history[yesterday]["avg"]

    if current_avg is None or previous_avg is None:
        if verbose:
            print("No valid sentiment data to compute crisis.")
        return None

    delta = current_avg - previous_avg

    if verbose:
        print("\nSource contribution today:")
        for src, cnt in history[today]["sources"].items():
            print(f"  {src}: {cnt} docs")
        print(f"Yesterday Sentiment: {previous_avg:.3f}")
        print(f"Today Sentiment:     {current_avg:.3f}")
        print(f"Change:              {delta:.3f}")

    level = get_alert_level(delta)

    if level:
        topics = get_top_topics()
        alert = {
            "date": today,
            "previous_sentiment": previous_avg,
            "current_sentiment": current_avg,
            "delta": delta,
            "level": level,
            "top_topics": topics,
            "sources": history[today]["sources"],
            "message": generate_summary(level, delta, topics),
            "created_at": datetime.utcnow().isoformat()
        }

        # Save to alerts collection
        db["alerts"].insert_one(alert)

        if verbose:
            print("\n⚠️ GLOBAL ALERT!")
            print(alert["message"])

        # Send email alert
        try:
            if email_alert_func:
                email_alert_func(
                    subject=f"GLOBAL {level} ALERT",
                    message=alert["message"]
                )
        except Exception as e:
            if verbose:
                print(f"⚠️ Failed to send email alert: {e}")

        return alert
    else:
        if verbose:
            print("\nSystem Stable. No crisis detected.")
        return None


# --------------------------
# Main entry
# --------------------------
def main():
    detect_crisis(verbose=True)


if __name__ == "__main__":
    main()
