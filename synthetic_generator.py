import pandas as pd
import numpy as np
from datetime import datetime, timedelta, UTC

path = "data/daily_features.csv"
days = 365
start_date = datetime.now(UTC) - timedelta(days=days)

np.random.seed(7)
data = []

market_crash = False
crash_days_left = 0

disaster_cluster = False
disaster_days_left = 0

trend_spike = False
trend_days_left = 0

for i in range(days):
    date = start_date + timedelta(days=i)

    # Trigger regimes
    if not market_crash and np.random.rand() < 0.03:
        market_crash = True
        crash_days_left = np.random.randint(5, 12)

    if not disaster_cluster and np.random.rand() < 0.04:
        disaster_cluster = True
        disaster_days_left = np.random.randint(3, 8)

    if not trend_spike and np.random.rand() < 0.05:
        trend_spike = True
        trend_days_left = np.random.randint(2, 6)

    # Base signals
    news_sentiment = np.random.normal(0, 0.2)
    gdelt_sentiment = np.random.normal(0, 0.2)

    crypto_return = np.random.normal(0, 0.02)
    crypto_volatility = abs(np.random.normal(0.04, 0.015))

    stock_return = np.random.normal(0, 0.015)
    stock_volatility = abs(np.random.normal(0.02, 0.01))

    weather_anomaly = np.clip(np.random.normal(0.3, 0.15), 0, 1)

    # Apply regimes
    if market_crash:
        crypto_return -= np.random.uniform(0.03, 0.08)
        stock_return -= np.random.uniform(0.02, 0.05)
        crypto_volatility += np.random.uniform(0.05, 0.15)
        stock_volatility += np.random.uniform(0.02, 0.05)
        news_sentiment -= np.random.uniform(0.3, 0.7)
        gdelt_sentiment -= np.random.uniform(0.3, 0.7)
        crash_days_left -= 1
        if crash_days_left <= 0:
            market_crash = False

    if disaster_cluster:
        weather_anomaly += np.random.uniform(0.3, 0.6)
        gdelt_sentiment -= np.random.uniform(0.2, 0.5)
        disaster_days_left -= 1
        if disaster_days_left <= 0:
            disaster_cluster = False

    if trend_spike:
        news_sentiment -= np.random.uniform(0.2, 0.5)
        gdelt_sentiment -= np.random.uniform(0.2, 0.5)
        trend_days_left -= 1
        if trend_days_left <= 0:
            trend_spike = False

    # Global risk model
    risk = (
        45
        - 25 * news_sentiment
        - 20 * gdelt_sentiment
        + 250 * crypto_volatility
        + 150 * stock_volatility
        + 30 * weather_anomaly
        + np.random.normal(0, 4)
    )

    risk = np.clip(risk, 0, 100)

    data.append({
        "timestamp": date.isoformat(),
        "news_sentiment": news_sentiment,
        "gdelt_sentiment": gdelt_sentiment,
        "crypto_return": crypto_return,
        "crypto_volatility": crypto_volatility,
        "stock_return": stock_return,
        "stock_volatility": stock_volatility,
        "weather_anomaly": weather_anomaly,
        "global_risk_score": risk
    })

df = pd.DataFrame(data)
df.to_csv(path, index=False)

print("Phase-2 synthetic dataset created")
print("Rows:", len(df))
print("Crisis days (>70):", (df["global_risk_score"] > 70).sum())
