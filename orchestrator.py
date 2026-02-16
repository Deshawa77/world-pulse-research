# -*- coding: utf-8 -*-
"""
World Pulse Orchestrator - Optimized Production Streaming
Collectors → Kafka → Consumer → Data Lake → Preprocessing → Mongo → NLP → Feature Store → ML → Alerts
"""

import sys, io, os, json, logging, traceback, time, hashlib
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from kafka import KafkaProducer, KafkaConsumer
import pandas as pd
import numpy as np
import joblib
from email.mime.text import MIMEText
import smtplib

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
# -------------------------------
# JSON serializer for datetime
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
from database.mongo import db
from processing.preprocess_data import main as preprocess_main, process_record as preprocess_record
from processing.nlp_analysis import clean_text, analyze_text
from processing.daily_feature_builder import build_hourly_features
from processing.topic_modeling_with_nlp import process_record as topic_modeling_process_record
from processing.global_crisis_detector import detect_crisis
from feature_store.feature_store import FeatureStore
from feature_store.model_registry import get_production_model

fs = FeatureStore()

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
# ML Engine
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

def run_ml_engine():
    try:
        model = load_model()
        df_features = fs.read_global()
        if df_features.empty:
            df_features = pd.read_csv("./data/hourly_features.csv")
        latest = df_features.iloc[-1]
        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0,1]
        level,message = classify_risk(prob)

        forecast_df = compute_forecast(latest)
        forecast_probs = [model.predict_proba(forecast_df.iloc[[i]][FEATURE_COLUMNS])[0,1] for i in range(len(forecast_df))]

        country_df = fs.read_country()
        if country_df.empty:
            country_df = pd.read_csv("./data/country_features.csv")
        country_risks = {row["country"]: round(float(model.predict_proba(row[FEATURE_COLUMNS].values.reshape(1,-1))[0,1]),3)
                         for _,row in country_df.iterrows()}

        df_history = pd.read_csv("./data/hourly_features.csv")
        anomalies = detect_anomalies(df_history)

        log_event(f"Time: {datetime.now(timezone.utc).isoformat()}")
        log_event(f"Crisis Probability: {prob:.4f} | Risk Level: {level}")
        log_event(f"7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
        log_event(f"Country Risks: {country_risks}")
        log_event(f"Anomalies: {anomalies}")
        log_event(f"System Status: {message}")

        fs.write_global(df_history)
        if level=="🔴 CRITICAL":
            send_email("🚨 GLOBAL CRISIS ALERT", f"Crisis probability: {prob:.2f}\n{country_risks}")

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
    if unique_key not in record:
        record["_hash"] = compute_record_hash(record)
        query = {"_hash": record["_hash"]}
    else:
        query = {unique_key: record[unique_key]}
        existing = coll.find_one(query)
        new_hash = compute_record_hash(record)
        if existing and existing.get("_hash") == new_hash:
            return False
        record["_hash"] = new_hash
    coll.update_one(query, {"$set": record}, upsert=True)
    return True

# -------------------------------
# Kafka Consumer → Full Stream Processing
# -------------------------------
def process_message(record, topic):
    collection = topic.replace("_topic","")
    try:
        # 1️⃣ Data Lake
        os.makedirs("data_lake", exist_ok=True)
        with open(f"data_lake/{collection}.json","a",encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False)+"\n")

        # 2️⃣ Preprocessing → NLP → Features
        processed_record = preprocess_record(record)

        # NLP processing
        if 'text' in processed_record:
            processed_record['cleaned_text'] = clean_text(processed_record['text'])
            processed_record['analysis'] = analyze_text(processed_record['cleaned_text'])

        # Feature building: now correctly call build_hourly_features
        processed_record.update(build_hourly_features())

        # Topic modeling
        processed_record = topic_modeling_process_record(processed_record)

        # 3️⃣ Mongo (delta)
        if upsert_delta(collection, processed_record, unique_key="id"):
            log_event(f"Mongo updated with new/changed record for {collection}")

        # 4️⃣ Crisis detection + ML
        detect_crisis(email_alert_func=send_email)
        run_ml_engine()

    except Exception as e:
        log_event(f"Error processing message from {topic}: {e}")
        traceback.print_exc()

def start_kafka_stream(parallel_workers=4):
    consumer = KafkaConsumer(
        *[topic for _,topic in COLLECTOR_TASKS.values()],
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

    # 0️⃣ Run full preprocessing pipeline at startup
    try:
        log_event("🚀 Running full preprocessing (preprocess_data.main)...")
        preprocess_main()
        log_event("✅ Preprocessing completed successfully")
    except Exception as e:
        log_event(f"❌ Preprocessing pipeline failed: {e}")
        traceback.print_exc()

    # 1️⃣ Start collectors
    start_all_collectors()

    # 2️⃣ Start Kafka stream
    start_kafka_stream(parallel_workers=8)
