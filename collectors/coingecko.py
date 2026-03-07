import requests
from datetime import datetime, timezone
import pandas as pd
import os
import uuid
from backend.kafka_client import send_to_kafka
from database.mongo import insert
from bson import ObjectId

BASE_URL = "https://api.coingecko.com/api/v3"
PROCESSED_CSV = "processed_crypto.csv"
ROLLING_WINDOW = 5  # number of periods for rolling return/volatility


# ----------------------------
# Utilities
# ----------------------------
def generate_uuid():
    return str(uuid.uuid4())


def convert_for_json(obj):
    """Convert datetimes and Mongo ObjectIds to JSON-safe values."""
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj


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

        # Load existing CSV if available
        if os.path.exists(PROCESSED_CSV):
            df = pd.read_csv(PROCESSED_CSV)
        else:
            df = pd.DataFrame()

        new_records = []

        # ----------------------------
        # Process each price point
        # ----------------------------
        for ts_ms, price in data["prices"]:
            # CoinGecko timestamps are in milliseconds
            data_timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

            record = {
                "_id": generate_uuid(),
                "source": "coingecko",
                "category": "crypto",
                "collected_at": collected_at,
                "data_coin_id": coin_id,
                "data_vs_currency": vs_currency,
                "data_timestamp": data_timestamp.isoformat(),
                "data_price": float(price)  # ✅ REAL price (no normalization)
            }

            new_records.append(record)

            # Send to Kafka
            send_to_kafka("crypto_topic", record)
            print(f"[Kafka] {coin_id.upper()} @ {price:.2f} USD")

        # ----------------------------
        # Save to CSV
        # ----------------------------
        if new_records:
            df = pd.concat([df, pd.DataFrame(new_records)], ignore_index=True)
            df.drop_duplicates(subset=["data_coin_id", "data_timestamp"], inplace=True)
            df.to_csv(PROCESSED_CSV, index=False)
            print(f"[CSV] Saved {len(new_records)} records")

        # ----------------------------
        # Insert into MongoDB
        # ----------------------------
        if new_records:
            insert("crypto", new_records)
            print(f"[Mongo] Inserted {len(new_records)} records")

        # ----------------------------
        # Compute rolling metrics
        # ----------------------------
        if df.empty:
            return new_records

        df["data_timestamp"] = pd.to_datetime(df["data_timestamp"], errors="coerce")
        df = df.sort_values("data_timestamp")

        df["return"] = df["data_price"].pct_change(periods=ROLLING_WINDOW)
        df["volatility"] = df["return"].rolling(window=ROLLING_WINDOW).std()

        latest = df.iloc[-1]
        print(
            f"[Stats] Return: {latest.get('return', 0.0):.6f}, "
            f"Volatility: {latest.get('volatility', 0.0):.6f}"
        )

        return new_records

        # ----------------------------
        # After computing rolling metrics
        # ----------------------------
        if not df.empty:
            df["data_timestamp"] = pd.to_datetime(df["data_timestamp"], errors="coerce")
            df = df.sort_values("data_timestamp")
            df["return"] = df["data_price"].pct_change(periods=ROLLING_WINDOW)
            df["volatility"] = df["return"].rolling(window=ROLLING_WINDOW).std()

            latest = df.iloc[-1]
            print(
                f"[Stats] Return: {latest.get('return', 0.0):.6f}, "
                f"Volatility: {latest.get('volatility', 0.0):.6f}"
            )

            # ----------------------------
            # Build top-level snapshot for orchestrator
            # ----------------------------
            snapshot = {
                "_id": generate_uuid(),
                "source": "coingecko",
                "category": "crypto_snapshot",
                "data_price": float(latest["data_price"]),
                "data_volatility": float(latest.get("volatility", 0.0)),
                "return": float(latest.get("return", 0.0)),
                "timestamp": latest["data_timestamp"].isoformat()
            }

            # Send snapshot to Kafka topic for top-level features
            send_to_kafka("crypto_snapshot_topic", snapshot)
            print(f"[Kafka] Top-level crypto snapshot sent: price={snapshot['data_price']:.2f}")

            # Upsert snapshot into Mongo for orchestrator consumption
            from database.mongo import insert_or_update  # create a small helper
            insert_or_update("crypto_snapshot", snapshot, unique_key="category")  # always keep 1 latest doc

    except requests.RequestException as e:
        print("[ERROR] Failed to fetch crypto data:", e)
        return []


# ----------------------------
# Standalone Test
# ----------------------------
if __name__ == "__main__":
    data = fetch_crypto("bitcoin", "usd", days=1)
    if data:
        import json
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data[:3], indent=2))  # print first 3 records