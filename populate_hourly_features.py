import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import requests
from pycoingecko import CoinGeckoAPI
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from dotenv import load_dotenv

load_dotenv()

# API keys
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Sentiment analyzer and CoinGecko client
analyzer = SentimentIntensityAnalyzer()
cg = CoinGeckoAPI()

# --- Fetch News ---
def fetch_news_texts(query="bitcoin", page_size=20):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY,
        "sortBy": "publishedAt",
        "language": "en"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            return []
        texts = []
        for item in data.get("articles", []):
            title = item.get("title") or ""
            desc = item.get("description") or ""
            texts.append(title + ". " + desc)
        return texts
    except:
        return []

def compute_sentiment(texts):
    return [analyzer.polarity_scores(t)["compound"] for t in texts if t]

# --- Fetch GDELT (placeholder still, replace if you have collector) ---
def fetch_gdelt_sentiments(query="bitcoin"):
    return [0.05, -0.02]

# --- Crypto Prices ---
def get_crypto_prices(coin="bitcoin", vs_currency="usd", minutes=60):
    try:
        history = cg.get_coin_market_chart_by_id(id=coin, vs_currency=vs_currency, days=1)
        prices = [p[1] for p in history["prices"]][-minutes:]
        return prices if prices else []
    except:
        return []

# --- Stock Prices (TwelveData) ---
def fetch_stock_prices_twelvedata(symbols=["AAPL"], interval="5min", outputsize=12):
    stock_dict = {}
    base_url = "https://api.twelvedata.com/time_series"

    for symbol in symbols:
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_API_KEY
        }
        try:
            resp = requests.get(base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if "values" not in data:
                print(f"Error fetching {symbol}: {data}")
                stock_dict[symbol] = []
                continue

            # Reverse to chronological order
            closes = [float(item["close"]) for item in reversed(data["values"])]
            stock_dict[symbol] = closes

        except Exception as e:
            print(f"Exception fetching {symbol}: {e}")
            stock_dict[symbol] = []

    return stock_dict

# --- Weather ---
def fetch_weather(lat=6.9271, lon=79.8612):
    url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=minutely,daily&appid={OPENWEATHER_KEY}&units=metric"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        temps = [h["temp"] for h in data.get("hourly", [])]
        return temps
    except:
        return []

def compute_weather_anomaly(weather_data):
    return pd.Series(weather_data).diff().mean() if weather_data else np.nan

# --- Global Risk ---
def calculate_global_risk(news_mean, gdelt_mean, crypto_vol, weather_anomaly):
    return 0.3*news_mean + 0.3*gdelt_mean + 0.2*(crypto_vol/100) + 0.2*(weather_anomaly if not np.isnan(weather_anomaly) else 0)

# --- Main ---
def populate_hourly_features():
    # News
    news_texts = fetch_news_texts("bitcoin")
    news_sentiments = compute_sentiment(news_texts)
    news_mean = np.mean(news_sentiments) if news_sentiments else np.nan
    news_std = np.std(news_sentiments) if news_sentiments else np.nan

    # GDELT
    gdelt_sentiments = fetch_gdelt_sentiments("bitcoin")
    gdelt_mean = np.mean(gdelt_sentiments) if gdelt_sentiments else np.nan
    gdelt_std = np.std(gdelt_sentiments) if gdelt_sentiments else np.nan

    # Crypto
    crypto_prices = get_crypto_prices("bitcoin")
    crypto_return = (crypto_prices[-1] - crypto_prices[0]) / crypto_prices[0] if len(crypto_prices) > 1 else np.nan
    crypto_volatility = np.std(np.diff(crypto_prices)) if len(crypto_prices) > 1 else np.nan

    # Stock
    stock_prices_dict = fetch_stock_prices_twelvedata(["AAPL", "MSFT"])
    all_returns = []
    for prices in stock_prices_dict.values():
        if len(prices) > 1:
            all_returns.extend(np.diff(prices)/prices[:-1])
    stock_return = np.mean(all_returns) if all_returns else np.nan
    stock_volatility = np.std(all_returns) if all_returns else np.nan

    # Weather
    weather_data = fetch_weather(6.9271, 79.8612)
    weather_anomaly = compute_weather_anomaly(weather_data)

    # Global Risk
    global_risk_score = calculate_global_risk(news_mean, gdelt_mean, crypto_volatility, weather_anomaly)

    # Compose row
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "news_sentiment": news_mean,
        "news_sentiment_std": news_std,
        "gdelt_sentiment": gdelt_mean,
        "gdelt_sentiment_std": gdelt_std,
        "crypto_return": crypto_return,
        "crypto_volatility": crypto_volatility,
        "stock_return": stock_return,
        "stock_volatility": stock_volatility,
        "weather_anomaly": weather_anomaly,
        "global_risk_score": global_risk_score
    }

    # Save CSV cleanly
    csv_path = "data/hourly_features.csv"
    columns = list(row.keys())

    if os.path.exists(csv_path):
        df_existing = pd.read_csv(csv_path)
        df_new = pd.DataFrame([row], columns=columns)
        df_combined = pd.concat([df_existing[columns], df_new], ignore_index=True)
    else:
        df_combined = pd.DataFrame([row], columns=columns)

    df_combined.to_csv(csv_path, index=False)
    print("✅ hourly_features.csv populated successfully.")

if __name__ == "__main__":
    populate_hourly_features()
