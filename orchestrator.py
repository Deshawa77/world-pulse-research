# -*- coding: utf-8 -*-
"""
World Pulse Orchestrator - Optimized Production Streaming
Collectors → Kafka → Consumer → Data Lake → Preprocessing → Mongo → NLP → Feature Store → ML → Alerts
"""

import sys, io, os, json, logging, traceback, time, hashlib
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from kafka import KafkaProducer, KafkaConsumer
import pandas as pd
import numpy as np
import joblib
from email.mime.text import MIMEText
import smtplib


def safe_keys(d):
    """Recursively replace numeric keys with safe string keys"""
    if isinstance(d, dict):
        new_d = {}
        for k, v in d.items():
            if isinstance(k, int) or (isinstance(k, str) and k.isdigit()):
                k = f"key_{k}"  # prefix numeric keys
            new_d[k] = safe_keys(v)
        return new_d
    elif isinstance(d, list):
        return [safe_keys(x) for x in d]
    else:
        return d

def stringify_keys(d):
    if isinstance(d, dict):
        return {str(k): stringify_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [stringify_keys(x) for x in d]
    else:
        return d

def safe_update(collection, record):
    # 1. Make a safe copy
    record_safe = record.copy()

    # 2. Convert numeric keys to safe strings
    record_safe = safe_keys(record_safe)

    # 3. Ensure no _id and all keys are strings
    record_safe = sanitize_for_mongo(record_safe)

    # 4. Upsert to Mongo
    collection.update_one({"_hash": record_safe["_hash"]}, {"$set": record_safe}, upsert=True)

def mongo_safe_upsert(collection, record):
    """
    Safely insert/update a record into MongoDB.
    - Converts all keys to strings
    - Handles nested numeric keys safely
    - Removes _id
    - Performs upsert using a unique _hash
    """
    try:
        record_safe = sanitize_for_mongo(record)
        if "_hash" not in record_safe:
            # generate hash if not present
            record_safe["_hash"] = hashlib.md5(
                json.dumps(record_safe, sort_keys=True).encode("utf-8")
            ).hexdigest()

        collection.update_one(
            {"_hash": record_safe["_hash"]},
            {"$set": record_safe},
            upsert=True
        )
        return True
    except Exception as e:
        log_event(f"❌ Mongo upsert failed: {e}")
        traceback.print_exc()
        return False


# -------------------------------
# UTF-8 stdout/stderr
# -------------------------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# -------------------------------
# Logging
# -------------------------------
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")

# -------------------------------
# Email Alerts
# -------------------------------
EMAIL_ALERT = False
EMAIL_TO = "you@example.com"
EMAIL_FROM = "worldpulse.ai@example.com"
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "smtp_user"
SMTP_PASS = "smtp_password"

def send_email(subject, body):
    if not EMAIL_ALERT:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log_event("📧 Email alert sent!")
    except Exception as e:
        log_event(f"❌ Failed to send email: {e}")

# -------------------------------
# Kafka Setup
# -------------------------------
def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

KAFKA_BROKER = "localhost:9092"
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v, default=json_serializer).encode("utf-8")
)

def send_to_kafka(topic, data):
    try:
        if isinstance(data, list):
            for record in data:
                producer.send(topic, record)
        else:
            producer.send(topic, data)
        producer.flush()
        log_event(f"Sent {len(data) if isinstance(data,list) else 1} items to Kafka topic '{topic}'")
    except Exception as e:
        log_event(f"Kafka send failed: {e}")

# -------------------------------
# Import collectors
# -------------------------------
import collectors.news as news
import collectors.gdelt as gdelt
import collectors.wiki as wiki
import collectors.trends as trends
import collectors.usgs as usgs
import collectors.weather as weather
import collectors.coingecko as coingecko
import collectors.fred as fred
import collectors.frankfurter as frankfurter
import collectors.who as who
import collectors.twelvedata as twelvedata
import collectors.worldbank as worldbank

# -------------------------------
# Database & Processing
# -------------------------------
from database.mongo import db, write_global_features_v2
from processing.preprocess_data import main as preprocess_main, process_record as preprocess_record
from processing.nlp_analysis import clean_text, analyze_text
from processing.daily_feature_builder import build_hourly_features, load_hourly_features
from processing.topic_modeling_with_nlp import process_record as topic_modeling_process_record
from processing.global_crisis_detector import detect_crisis
from feature_store.feature_store import FeatureStore
from feature_store.model_registry import get_production_model
from populate_hourly_features import populate_hourly_features



fs = FeatureStore()
db_connection = db

# -------------------------------
# Paths
# -------------------------------
DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# -------------------------------
# Collector Tasks
# -------------------------------
COLLECTOR_TASKS = {
    "news": (lambda: news.fetch_news("earthquake", page_size=5), "news_topic"),
    "gdelt": (lambda: gdelt.fetch_gdelt_articles("(earthquake OR flood)", max_records=5), "gdelt_topic"),
    "wiki": (lambda: wiki.fetch_pageviews("Earthquake", days=5), "wiki_topic"),
    "trends": (lambda: trends.fetch_trends("earthquake"), "trends_topic"),
    "earthquakes": (lambda: usgs.fetch_earthquakes(), "earthquakes_topic"),
    "weather": (lambda: weather.fetch_weather("Tokyo"), "weather_topic"),
    "crypto": (lambda: coingecko.fetch_crypto("bitcoin","usd",5), "crypto_topic"),
    "fred": (lambda: fred.fetch_indicator("GDP","2025-01-01","2026-01-01"), "fred_topic"),
    "exchange_rates": (lambda: frankfurter.fetch_exchange_rates("USD"), "exchange_rates_topic"),
    "who": (lambda: who.fetch_who_indicator("WHOSIS_000001", max_results=5), "who_topic"),
    "stocks": (lambda: twelvedata.fetch_stock("AAPL","1day",5), "stocks_topic"),
    "worldbank": (lambda: worldbank.fetch_worldbank_data(date="2020:2025", per_page=5), "worldbank_topic")
}

topic_feature_map = {topic: build_hourly_features for _, topic in COLLECTOR_TASKS.values()}

# -------------------------------
# Collector Loop
# -------------------------------
def collector_loop(label, fetch_fn, topic, interval_sec=60):
    while True:
        try:
            data = fetch_fn()
            if data:
                send_to_kafka(topic, data)
        except Exception as e:
            log_event(f"Collector '{label}' failed: {e}")
        time.sleep(interval_sec)

def start_all_collectors():
    for label, (fn, topic) in COLLECTOR_TASKS.items():
        t = Thread(target=collector_loop, args=(label, fn, topic), daemon=True)
        t.start()
        log_event(f"Collector '{label}' started, streaming to '{topic}'")

# -------------------------------
# ML Engine & Utility Functions
# -------------------------------
ALERT_THRESHOLD_HIGH = 0.75
ALERT_THRESHOLD_MED = 0.40
FEATURE_COLUMNS = [
    "news_sentiment","gdelt_sentiment","crypto_return","crypto_volatility",
    "stock_return","stock_volatility","weather_anomaly"
]

def load_model():
    path = get_production_model()
    fallback = "./models/gb_model.pkl"
    return joblib.load(path) if path and os.path.exists(path) else joblib.load(fallback)

def classify_risk(prob):
    if prob >= ALERT_THRESHOLD_HIGH: return "🔴 CRITICAL", "GLOBAL CRISIS IMMINENT"
    if prob >= ALERT_THRESHOLD_MED: return "🟠 ELEVATED", "INSTABILITY DETECTED"
    return "🟢 LOW", "STABLE SYSTEM"

def compute_forecast(latest, days=7):
    forecasts = []
    for _ in range(days):
        row = latest.copy()
        for col in FEATURE_COLUMNS:
            if col in row:
                row[col] += np.random.normal(0,0.02)
        forecasts.append(row)
    return pd.DataFrame(forecasts)

def detect_anomalies(df):
    anomalies = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            z = (df[col]-df[col].mean())/(df[col].std()+1e-9)
            anomalies[col] = df[col][abs(z)>2].tolist()
    return anomalies

def sanitize_for_mongo(record):
    """
    Recursively convert all keys to strings and remove None/_id.
    Converts nested numeric keys safely for MongoDB to avoid conflicts like '0.0.1'.
    """
    def sanitize(value):
        if isinstance(value, dict):
            new_dict = {}
            for k, v in value.items():
                # Prefix numeric keys to avoid path conflicts
                if isinstance(k, int) or (isinstance(k, str) and k.isdigit()):
                    k = f"key_{k}"
                new_dict[str(k)] = sanitize(v)
            return new_dict
        elif isinstance(value, list):
            return [sanitize(v) if isinstance(v, (dict, list)) else v for v in value]
        else:
            return value

    sanitized = sanitize(record)
    sanitized.pop("_id", None)
    return sanitized

def run_ml_engine():
    try:
        model = load_model()
        df_features = fs.read_global()
        if df_features.empty:
            log_event("⚠️ No features available to run ML engine. Skipping this cycle.")
            return

        latest = df_features.iloc[-1]
        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0, 1]
        level, message = classify_risk(prob)

        forecast_df = compute_forecast(latest)
        forecast_probs = [
            model.predict_proba(forecast_df.iloc[[i]][FEATURE_COLUMNS])[0, 1]
            for i in range(len(forecast_df))
        ]

        country_df = fs.read_country()
        if country_df.empty:
            country_df = pd.read_csv(os.path.join(DATA_DIR, "country_features.csv"))

        country_risks = {}
        for _, row in country_df.iterrows():
            X_country = pd.DataFrame([row[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
            country_risks[row["country"]] = round(float(model.predict_proba(X_country)[0, 1]), 3)

        df_history = load_hourly_features()
        df_history.dropna(subset=["news_sentiment", "gdelt_sentiment"], how="all", inplace=True)
        anomalies = detect_anomalies(df_history)

        global_coll = db.global_features

        # 1️⃣ Latest record
        latest_record = latest.to_dict()
        latest_record["timestamp"] = datetime.utcnow().isoformat()
        latest_record = sanitize_for_mongo(latest_record)
        latest_record["_hash"] = hashlib.md5(
            json.dumps(latest_record, sort_keys=True).encode("utf-8")
        ).hexdigest()
        mongo_safe_upsert(global_coll, latest_record)

        # 2️⃣ Forecast records
        for i in range(len(forecast_df)):
            rec = forecast_df.iloc[i].to_dict()
            rec["timestamp"] = datetime.utcnow().isoformat()
            rec = sanitize_for_mongo(rec)
            rec["_hash"] = hashlib.md5(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
            mongo_safe_upsert(global_coll, rec)

        # 3️⃣ Country-level records
        for country, risk in country_risks.items():
            rec = {
                "country": str(country),
                "risk": risk,
                "timestamp": datetime.utcnow().isoformat()
            }
            rec = sanitize_for_mongo(rec)
            rec["_hash"] = hashlib.md5(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
            mongo_safe_upsert(global_coll, rec)

        log_event(f"Time: {datetime.now(timezone.utc).isoformat()}")
        log_event(f"Crisis Probability: {prob:.4f} | Risk Level: {level}")
        log_event(f"7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
        log_event(f"Country Risks: {country_risks}")
        log_event(f"Anomalies: {anomalies}")
        log_event(f"System Status: {message}")

        fs.write_global(df_history)

        if level == "🔴 CRITICAL":
            send_email(
                "🚨 GLOBAL CRISIS ALERT",
                f"Crisis probability: {prob:.2f}\n{country_risks}"
            )

    except Exception as e:
        log_event(f"❌ ML Engine error: {e}")
        traceback.print_exc()


# -------------------------------
# Mongo Delta Insert/Update
# -------------------------------
def compute_record_hash(record):
    record_json = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(record_json.encode("utf-8")).hexdigest()

def upsert_delta(collection_name, record, unique_key="id"):
    coll = db[collection_name]

    # 1. Convert numeric keys and sanitize
    record_safe = safe_keys(record)
    record_safe = sanitize_for_mongo(record_safe)

    if unique_key not in record_safe:
        record_safe["_hash"] = compute_record_hash(record_safe)
        query = {"_hash": record_safe["_hash"]}
    else:
        query = {unique_key: record_safe[unique_key]}
        existing = coll.find_one(query)
        new_hash = compute_record_hash(record_safe)
        if existing and existing.get("_hash") == new_hash:
            return False
        record_safe["_hash"] = new_hash

    coll.update_one(query, {"$set": record_safe}, upsert=True)
    return True


# -------------------------------
# Kafka Consumer → Full End-to-End Processing (Batching & CSV Safe)
# -------------------------------
from threading import Thread, Lock
import threading 

BATCH_SIZE = 50
batch_lock = Lock()
message_batch = []

def flush_batch_to_csv(batch, csv_path=HOURLY_FEATURES_CSV):
    if not batch:
        return
    df_batch = pd.DataFrame(batch)

    if os.path.exists(csv_path):
        df_existing = pd.read_csv(csv_path)
        for col in df_existing.columns:
            if col not in df_batch.columns:
                df_batch[col] = 0.0
        for col in df_batch.columns:
            if col not in df_existing.columns:
                df_existing[col] = 0.0
        df_combined = pd.concat([df_existing, df_batch], ignore_index=True)
    else:
        df_combined = df_batch

    df_combined.to_csv(csv_path, index=False)
    log_event(f"Flushed {len(batch)} messages to {csv_path}")

def process_message(record, topic):
    collection = topic.replace("_topic","")
    global message_batch
    try:
        os.makedirs("data_lake", exist_ok=True)
        with open(f"data_lake/{collection}.json", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if not isinstance(record, dict):
            record = json.loads(record)

        processed_record = preprocess_record(record)

        if 'text' in processed_record:
            processed_record['cleaned_text'] = clean_text(processed_record['text'])
            processed_record['analysis'] = analyze_text(processed_record['cleaned_text'])

        feature_builder = topic_feature_map.get(topic)
        if feature_builder:
            features = feature_builder(db_connection)
            processed_record.update(features)

        processed_record = topic_modeling_process_record(processed_record)

        if upsert_delta(collection, processed_record, unique_key="id"):
            log_event(f"Mongo updated with new/changed record for {collection}")

        detect_crisis(email_alert_func=send_email)
        run_ml_engine()

        with batch_lock:
            message_batch.append(processed_record)
            if len(message_batch) >= BATCH_SIZE:
                flush_batch_to_csv(message_batch)
                message_batch = []

    except Exception as e:
        log_event(f"Error processing message from {topic}: {e}")
        traceback.print_exc()

def batch_flusher_thread(interval_sec=30):
    global message_batch
    while True:
        time.sleep(interval_sec)
        with batch_lock:
            if message_batch:
                flush_batch_to_csv(message_batch)
                message_batch = []

def start_kafka_stream(parallel_workers=4):
    threading.Thread(target=batch_flusher_thread, daemon=True).start()

    consumer = KafkaConsumer(
        *topic_feature_map.keys(),
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id="worldpulse_consumer_group"
    )
    log_event("Kafka consumer started (streaming all topics)...")

    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        for message in consumer:
            executor.submit(process_message, message.value, message.topic)

# -------------------------------
# Main
# -------------------------------
if __name__=="__main__":
    log_event("Starting World Pulse Optimized Production Streaming Orchestrator...")

    try:
        log_event("🚀 Running full preprocessing (preprocess_data.main)...")
        preprocess_main()
        log_event("✅ Preprocessing completed successfully")
    except Exception as e:
        log_event(f"❌ Preprocessing pipeline failed: {e}")
        traceback.print_exc()

    # --- Populate hourly features automatically ---
    try:
        populate_hourly_features()
    except Exception as e:
        log_event(f"❌ Failed to populate hourly features: {e}")

    start_all_collectors()
    start_kafka_stream(parallel_workers=8)
