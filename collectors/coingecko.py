import os
import uuid
from datetime import datetime, timezone

import pandas as pd
import requests
from bson import ObjectId

from backend.kafka_client import send_to_kafka
from database.mongo import insert

BASE_URL = "https://api.coingecko.com/api/v3"
PROCESSED_CSV = "processed_crypto.csv"
ROLLING_WINDOW = 5  # number of periods for rolling return/volatility
DEFAULT_COIN_METADATA = {
    "bitcoin": {"name": "Bitcoin", "symbol": "BTC"},
    "ethereum": {"name": "Ethereum", "symbol": "ETH"},
    "solana": {"name": "Solana", "symbol": "SOL"},
    "binancecoin": {"name": "BNB", "symbol": "BNB"},
    "ripple": {"name": "XRP", "symbol": "XRP"},
    "cardano": {"name": "Cardano", "symbol": "ADA"},
    "dogecoin": {"name": "Dogecoin", "symbol": "DOGE"},
    "tron": {"name": "TRON", "symbol": "TRX"},
    "avalanche-2": {"name": "Avalanche", "symbol": "AVAX"},
    "chainlink": {"name": "Chainlink", "symbol": "LINK"},
}
DEFAULT_COIN_IDS = ("bitcoin", "ethereum", "solana", "binancecoin", "ripple", "cardano")


# ----------------------------
# Utilities
# ----------------------------
def generate_uuid():
    return str(uuid.uuid4())


def convert_for_json(obj):
    """Convert datetimes and Mongo ObjectIds to JSON-safe values."""
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


def get_configured_coin_ids():
    raw_coin_ids = (os.environ.get("CRYPTO_COIN_IDS") or "").strip()
    if not raw_coin_ids:
        return list(DEFAULT_COIN_IDS)

    seen = set()
    coin_ids = []
    for value in raw_coin_ids.split(","):
        coin_id = value.strip().lower()
        if coin_id and coin_id not in seen:
            seen.add(coin_id)
            coin_ids.append(coin_id)

    return coin_ids or list(DEFAULT_COIN_IDS)


def get_coin_metadata(coin_id):
    metadata = DEFAULT_COIN_METADATA.get(coin_id, {})
    fallback_symbol = "".join(part[:1] for part in coin_id.split("-")).upper() or coin_id[:4].upper()
    return {
        "name": metadata.get("name", coin_id.replace("-", " ").title()),
        "symbol": metadata.get("symbol", fallback_symbol),
    }


def _load_crypto_frame():
    if os.path.exists(PROCESSED_CSV):
        return pd.read_csv(PROCESSED_CSV)
    return pd.DataFrame()


def _fetch_single_crypto(coin_id="bitcoin", vs_currency="usd", days=1):
    metadata = get_coin_metadata(coin_id)
    collected_at = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "prices" not in data:
            print("[ERROR] CoinGecko response invalid:", data)
            return []

        df = _load_crypto_frame()
        market_caps = {ts_ms: cap for ts_ms, cap in data.get("market_caps", [])}
        total_volumes = {ts_ms: volume for ts_ms, volume in data.get("total_volumes", [])}
        new_records = []

        for ts_ms, price in data["prices"]:
            data_timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            record = {
                "_id": generate_uuid(),
                "source": "coingecko",
                "category": "crypto",
                "collected_at": collected_at,
                "data_coin_id": coin_id,
                "data_name": metadata["name"],
                "data_symbol": metadata["symbol"],
                "data_vs_currency": vs_currency,
                "data_timestamp": data_timestamp.isoformat(),
                "data_price": float(price),
                "data_market_cap": float(market_caps.get(ts_ms, 0.0) or 0.0),
                "data_volume": float(total_volumes.get(ts_ms, 0.0) or 0.0),
            }

            new_records.append(record)
            send_to_kafka("crypto_topic", record)
            print(f"[Kafka] {metadata['symbol']} @ {price:.2f} USD")

        if new_records:
            df = pd.concat([df, pd.DataFrame(new_records)], ignore_index=True)
            df.drop_duplicates(subset=["data_coin_id", "data_timestamp"], inplace=True)
            df.to_csv(PROCESSED_CSV, index=False)
            print(f"[CSV] Saved {len(new_records)} records for {coin_id}")

            inserted_count = insert("crypto", new_records, unique_keys=["data_coin_id", "data_timestamp"])
            print(f"[Mongo] Inserted {inserted_count} new records for {coin_id}")

        if df.empty:
            return new_records

        df["data_timestamp"] = pd.to_datetime(df["data_timestamp"], errors="coerce")
        coin_df = df[df.get("data_coin_id") == coin_id].copy()
        if coin_df.empty:
            return new_records

        coin_df = coin_df.sort_values("data_timestamp")
        coin_df["return"] = coin_df["data_price"].pct_change(periods=ROLLING_WINDOW)
        coin_df["volatility"] = coin_df["return"].rolling(window=ROLLING_WINDOW).std()

        latest = coin_df.iloc[-1]
        print(
            f"[Stats] {metadata['symbol']} Return: {latest.get('return', 0.0):.6f}, "
            f"Volatility: {latest.get('volatility', 0.0):.6f}"
        )

        return new_records
    except requests.RequestException as e:
        print("[ERROR] Failed to fetch crypto data:", e)
        return []


# ----------------------------
# Main Fetch Function
# ----------------------------
def fetch_crypto(coin_id="bitcoin", vs_currency="usd", days=1):
    """
    Fetch crypto price history from CoinGecko.
    - Sends each record to Kafka
    - Stores in MongoDB
    - Saves locally to CSV
    - Computes rolling return & volatility
    """

    if isinstance(coin_id, (list, tuple, set)):
        all_records = []
        for single_coin_id in coin_id:
            normalized_coin_id = str(single_coin_id).strip().lower()
            if not normalized_coin_id:
                continue
            all_records.extend(_fetch_single_crypto(normalized_coin_id, vs_currency=vs_currency, days=days))
        return all_records

    normalized_coin_id = str(coin_id).strip().lower() if coin_id else "bitcoin"
    return _fetch_single_crypto(normalized_coin_id, vs_currency=vs_currency, days=days)


# ----------------------------
# Standalone Test
# ----------------------------
if __name__ == "__main__":
    data = fetch_crypto(get_configured_coin_ids(), "usd", days=5)
    if data:
        import json

        safe_data = convert_for_json(data)
        print(json.dumps(safe_data[:3], indent=2))  # print first 3 records
