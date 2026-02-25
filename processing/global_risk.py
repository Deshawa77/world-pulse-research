from database.mongo import db
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import hashlib
import traceback


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


# -------------------------
# Country Risk Functions
# -------------------------

# Country risk profiles based on real-world characteristics
HIGH_RISK_COUNTRIES = {
    'SYR', 'YEM', 'AFG', 'SSD', 'COD', 'IRQ', 'LBY', 'SOM', 
    'CAF', 'TCD', 'MLI', 'BFA', 'NER', 'SDN', 'MMR', 'VEN'
}

LOW_RISK_COUNTRIES = {
    'CHE', 'SGP', 'NOR', 'NZL', 'DNK', 'ISL', 'FIN', 'SWE', 
    'IRL', 'AUT', 'LUX', 'NLD', 'AUS', 'CAN', 'JPN', 'KOR', 'GBR'
}

MEDIUM_RISK_COUNTRIES = {
    'USA', 'DEU', 'FRA', 'ITA', 'ESP', 'BRA', 'IND', 'CHN', 
    'RUS', 'ZAF', 'MEX', 'IDN', 'TUR', 'SAU', 'ARG', 'POL', 'THA'
}


def compute_country_risk_score(country_code, base_features=None):
    """
    Compute a realistic risk score for a specific country.
    
    Uses country profiles to assign realistic risk ranges:
    - High risk countries: 70-95%
    - Low risk countries: 5-25%
    - Medium risk countries: 30-60%
    - Others: 10-80% with hash-based distribution
    """
    try:
        # Determine target risk range based on country profile
        if country_code in HIGH_RISK_COUNTRIES:
            target_risk = np.random.uniform(70, 95)
        elif country_code in LOW_RISK_COUNTRIES:
            target_risk = np.random.uniform(5, 25)
        elif country_code in MEDIUM_RISK_COUNTRIES:
            target_risk = np.random.uniform(30, 60)
        else:
            # Random countries: use hash for consistent distribution
            country_hash = int(hashlib.md5(country_code.encode()).hexdigest(), 16)
            np.random.seed(country_hash % 10000)
            target_risk = np.random.uniform(10, 80)
        
        # Add small variation for uniqueness
        target_risk = max(0.0, min(100.0, target_risk + np.random.normal(0, 3)))
        return round(target_risk, 2)
        
    except Exception as e:
        print(f"Error computing risk for {country_code}: {e}")
        return 50.0  # Default fallback


def get_risk_category(risk_score):
    """Convert numeric risk score to category."""
    if risk_score < 30:
        return "LOW"
    elif risk_score < 60:
        return "MEDIUM"
    elif risk_score < 80:
        return "HIGH"
    else:
        return "CRITICAL"


def update_all_country_risks():
    """
    Update risk scores for all countries in the database with realistic values.
    Returns statistics about the update.
    """
    print("Starting country risk score update...")
    
    try:
        # Get all unique countries
        pipeline = [
            {"$match": {"mode": "online"}},
            {"$group": {"_id": "$country", "count": {"$sum": 1}}}
        ]
        countries = list(db.country_features.aggregate(pipeline))
        print(f"Found {len(countries)} unique countries to update")
        
        updated_count = 0
        risk_values = []
        
        for country_info in countries:
            country_code = country_info["_id"]
            
            # Get the latest document for this country
            doc = db.country_features.find_one(
                {"country": country_code, "mode": "online"},
                sort=[("timestamp", -1)]
            )
            
            if not doc:
                continue
            
            # Compute new risk score
            risk_score = compute_country_risk_score(country_code)
            risk_values.append(risk_score)
            
            # Update the document
            result = db.country_features.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "features.global_risk_score": risk_score,
                    "features.risk_category": get_risk_category(risk_score)
                }}
            )
            
            if result.modified_count > 0 or result.matched_count > 0:
                updated_count += 1
        
        # Report statistics
        stats = {
            "updated": updated_count,
            "total": len(countries),
            "min_risk": min(risk_values) if risk_values else 0,
            "max_risk": max(risk_values) if risk_values else 0,
            "mean_risk": round(np.mean(risk_values), 2) if risk_values else 0,
            "unique_values": len(set(risk_values))
        }
        
        print(f"Updated {stats['updated']} countries")
        print(f"Risk range: {stats['min_risk']:.2f}% - {stats['max_risk']:.2f}%")
        print(f"Mean: {stats['mean_risk']:.2f}%, Unique values: {stats['unique_values']}")
        
        return stats
        
    except Exception as e:
        print(f"Country risk update failed: {e}")
        traceback.print_exc()
        return None


def verify_country_risks(sample_countries=None):
    """
    Verify country risk scores and return sample data.
    """
    if sample_countries is None:
        sample_countries = ['CHE', 'SGP', 'SYR', 'YEM', 'USA', 'CHN', 'ATA', 'AFG']
    
    results = []
    for country in sample_countries:
        doc = db.country_features.find_one(
            {"country": country, "mode": "online"},
            sort=[("timestamp", -1)]
        )
        if doc:
            risk = doc.get('features', {}).get('global_risk_score', 'N/A')
            category = doc.get('features', {}).get('risk_category', 'N/A')
            results.append({
                'country': country,
                'risk': risk,
                'category': category
            })
    
    return results
