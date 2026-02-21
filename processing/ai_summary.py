# ai_summary.py (orchestrator-friendly version)
import re
from collections import Counter
from datetime import datetime
import math

# -----------------------------
# Language filter (fast ASCII check)
# -----------------------------
def is_english(text):
    try:
        text.encode("ascii")
        return True
    except:
        return False

# -----------------------------
# Stopwords for topic extraction
# -----------------------------
STOPWORDS = {
    "the","is","in","and","to","of","for","on","with","at","by",
    "an","be","this","that","from","as","it","are","was","were",
    "has","have","had","but","not","or","will","can","about",
    "after","before","over","under","more","less","into","out",
    "up","down","new","latest","says","said","report",
    "year","years","day","days","week","weeks",
    "world","global","update","breaking"
}

# -----------------------------
# NLP Helper: Extract top topics
# -----------------------------
def extract_top_topics(texts, top_n=5):
    words = []
    for text in texts:
        if not text:
            continue
        tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        tokens = [t for t in tokens if t not in STOPWORDS]
        words.extend(tokens)
    if not words:
        return ["no data"]
    counter = Counter(words)
    return [word for word, _ in counter.most_common(top_n)]

# -----------------------------
# Helper: safely get nested dict values
# -----------------------------
def get_nested(d, path, default=None):
    keys = path.split(".")
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d

# -----------------------------
# Compute returns + volatility from stored data
# -----------------------------
def compute_returns_and_volatility(prices):
    if not prices or len(prices) < 2:
        return 0.0, 0.0
    returns = [(prices[i]/prices[i-1]-1) for i in range(1,len(prices))]
    avg_return = sum(returns)/len(returns)
    variance = sum((r-avg_return)**2 for r in returns)/len(returns)
    volatility = math.sqrt(variance)
    return avg_return, volatility

# -----------------------------
# Compute global risk from stored MongoDB data
# -----------------------------
def compute_global_risk_score(db, top_n_topics=5):
    """
    Reads live prices, news, GDELT from MongoDB (already populated by orchestrator),
    computes returns, volatility, sentiment, topics, and global risk.
    """
    # Fetch latest stored features
    news_docs = list(db.news.find().sort("collected_at",-1).limit(100))
    gdelt_docs = list(db.gdelt.find().sort("collected_at",-1).limit(100))
    crypto_docs = list(db.crypto.find().sort("timestamp",-1).limit(100))
    stock_docs = list(db.stocks.find().sort("timestamp",-1).limit(100))

    # Sentiment averages
    news_avg = sum(d.get("nlp",{}).get("sentiment",0) for d in news_docs)/len(news_docs) if news_docs else 0
    gdelt_avg = sum(d.get("nlp",{}).get("sentiment",0) for d in gdelt_docs)/len(gdelt_docs) if gdelt_docs else 0

    # Market averages + volatility
    crypto_prices = [get_nested(d,"data.price_normalized",0) for d in crypto_docs if get_nested(d,"data.price_normalized",0)>0]
    crypto_avg, crypto_vol = compute_returns_and_volatility(crypto_prices)

    stock_prices = [get_nested(d,"data.close_normalized",0) for d in stock_docs if get_nested(d,"data.close_normalized",0)>0]
    stock_avg, stock_vol = compute_returns_and_volatility(stock_prices)

    # Risk score formula
    sentiment_component = 1 - ((news_avg + gdelt_avg)/2)
    market_component = crypto_avg + stock_avg
    raw_score = (sentiment_component * 60) + (market_component * 40)
    global_risk_score = max(0,min(raw_score,100))

    # Topics
    news_texts = [get_nested(d,"data.title") for d in news_docs if get_nested(d,"data.title") and is_english(get_nested(d,"data.title"))]
    gdelt_texts = [get_nested(d,"data.title") for d in gdelt_docs if get_nested(d,"data.title") and is_english(get_nested(d,"data.title"))]
    top_topics = extract_top_topics(news_texts + gdelt_texts, top_n=top_n_topics) or ["no data"]

    # Feature dict
    features = {
        "news_sentiment": round(news_avg,4),
        "gdelt_sentiment": round(gdelt_avg,4),
        "crypto_return": round(crypto_avg,4),
        "stock_return": round(stock_avg,4),
        "crypto_volatility": round(crypto_vol,4),
        "stock_volatility": round(stock_vol,4),
        "global_risk_score": round(global_risk_score,2),
        "top_topics": top_topics,
        "timestamp": datetime.utcnow()
    }

    return features

# -----------------------------
# Read-Only Summary
# -----------------------------
def update_global_features(db):
    """
    Build a summary from the latest online global_features document.
    This function is intentionally read-only.
    """
    doc = db.global_features.find_one({"mode": "online"}, sort=[("timestamp", -1)])
    if not doc:
        return "No global features available"

    features = doc.get("features", {})
    risk_score = features.get("global_risk_score", 50)
    top_topics = features.get("top_topics", ["no data"])

    return (
        f"Moderate risk: Global Risk Score: {risk_score}/100.\n"
        f"Top topics influencing sentiment today: {top_topics}"
    )
