"""
World Pulse Orchestrator - Updated with 12 FREE Data Collectors
Collectors → Kafka → Consumer → Data Lake → Preprocessing → Mongo → NLP → Feature Store → ML → Alerts
"""

import sys, io, os, json, logging, traceback, time, hashlib, re
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from collections import Counter
from kafka import KafkaProducer, KafkaConsumer
import pandas as pd
import numpy as np
import joblib
from email.mime.text import MIMEText
import smtplib
from utils import log_event
from pymongo import MongoClient
import uuid

# Mongo connection
client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

# Import all collectors (original + new FREE ones only)
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
import collectors.reddit as reddit

# New FREE collectors (12 total)
import collectors.youtube as youtube
import collectors.alphavantage as alphavantage
import collectors.acled as acled
import collectors.nasa_earth as nasa_earth
import collectors.huggingface_nlp as huggingface_nlp
import collectors.stackoverflow as stackoverflow
import collectors.openairquality as openairquality
import collectors.reliefweb as reliefweb
import collectors.messari as messari
import collectors.financialmodelingprep as financialmodelingprep
import collectors.eodhistorical as eodhistorical
import collectors.reddit_enhanced as reddit_enhanced

# Database & Processing
from database.mongo import db, write_global_features_v2
from processing.preprocess_data import main as preprocess_main, process_record as preprocess_record
from processing.nlp_analysis import clean_text, analyze_text
from processing.daily_feature_builder import build_hourly_features, load_hourly_features
from processing.topic_modeling_with_nlp import process_record as topic_modeling_process_record
from processing.global_crisis_detector import detect_crisis
from feature_store.feature_store import FeatureStore
from feature_store.load_models import load_all_models
from backend import observability as obs
from populate_hourly_features import populate_hourly_features
from backend.observability import health_check
from config import HOURLY_FEATURES_CSV, FEATURE_COLUMNS, COLLECTOR_CONFIG

fs = FeatureStore()
db_connection = db

# UTF-8 stdout/stderr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Email Alerts
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
        log_event("Email alert sent!")
    except Exception as e:
        log_event(f"Failed to send email: {e}")

# Kafka Setup
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

# Original collector tasks
ORIGINAL_COLLECTOR_TASKS = {
    "news": (lambda: news.fetch_news("earthquake", page_size=5), "news_topic"),
    "gdelt": (lambda: gdelt.fetch_gdelt_articles("(earthquake OR flood)", max_records=5), "gdelt_topic"),
    "wiki": (lambda: wiki.fetch_pageviews("Earthquake", days=5), "wiki_topic"),
    "trends": (lambda: trends.fetch_trends("earthquake"), "trends_topic"),
    "earthquakes": (lambda: usgs.fetch_earthquakes(), "earthquakes_topic"),
    "weather": (lambda: weather.collect_weather_for_orchestrator(), "weather_topic"),
    "crypto": (lambda: coingecko.fetch_crypto("bitcoin","usd",5), "crypto_topic"),
    "fred": (lambda: fred.fetch_indicator("GDP","2025-01-01","2026-01-01"), "fred_topic"),
    "exchange_rates": (lambda: frankfurter.fetch_exchange_rates("USD"), "exchange_rates_topic"),
    "who": (lambda: who.fetch_who_indicator("WHOSIS_000001", max_results=5), "who_topic"),
    "stocks": (lambda: twelvedata.fetch_stock("AAPL","1day",5), "stocks_topic"),
    "worldbank": (lambda: worldbank.fetch_worldbank_data(date="2020:2025", per_page=5), "worldbank_topic"),
    "reddit": (lambda: reddit.fetch_reddit_posts("worldnews", limit=5), "reddit_topic")
}

# New FREE collector tasks (12 collectors)
NEW_COLLECTOR_TASKS = {}

# Add new collectors based on configuration
if COLLECTOR_CONFIG.get("youtube", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["youtube"] = (lambda: youtube.fetch_youtube_data(), "youtube_topic")

if COLLECTOR_CONFIG.get("alphavantage", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["alphavantage"] = (lambda: alphavantage.fetch_alphavantage_data(), "alphavantage_topic")

if COLLECTOR_CONFIG.get("acled", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["acled"] = (lambda: acled.fetch_acled_data(), "acled_topic")

if COLLECTOR_CONFIG.get("nasa_earth", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["nasa_earth"] = (lambda: nasa_earth.fetch_nasa_earth_data(), "nasa_earth_topic")

if COLLECTOR_CONFIG.get("huggingface_nlp", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["huggingface_nlp"] = (lambda: huggingface_nlp.fetch_huggingface_nlp_data(), "huggingface_nlp_topic")

if COLLECTOR_CONFIG.get("stackoverflow", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["stackoverflow"] = (lambda: stackoverflow.fetch_stackoverflow_data(), "stackoverflow_topic")

if COLLECTOR_CONFIG.get("openaq", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["openaq"] = (lambda: openairquality.fetch_openaq_data(), "openaq_topic")

if COLLECTOR_CONFIG.get("reliefweb", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["reliefweb"] = (lambda: reliefweb.fetch_reliefweb_data(), "reliefweb_topic")

if COLLECTOR_CONFIG.get("messari", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["messari"] = (lambda: messari.fetch_messari_data(), "messari_topic")

if COLLECTOR_CONFIG.get("financialmodelingprep", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["financialmodelingprep"] = (lambda: financialmodelingprep.fetch_financialmodelingprep_data(), "financialmodelingprep_topic")

if COLLECTOR_CONFIG.get("eodhistorical", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["eodhistorical"] = (lambda: eodhistorical.fetch_eodhistorical_data(), "eodhistorical_topic")

if COLLECTOR_CONFIG.get("reddit_enhanced", {}).get("enabled", True):
    NEW_COLLECTOR_TASKS["reddit_enhanced"] = (lambda: reddit_enhanced.fetch_reddit_enhanced_data(), "reddit_enhanced_topic")

# Combine all collector tasks
COLLECTOR_TASKS = {**ORIGINAL_COLLECTOR_TASKS, **NEW_COLLECTOR_TASKS}

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
        # Get interval from config or use default
        interval = COLLECTOR_CONFIG.get(label, {}).get("interval", 300)
        t = Thread(target=collector_loop, args=(label, fn, topic, interval), daemon=True)
        t.start()
        log_event(f"Collector '{label}' started, streaming to '{topic}' (interval: {interval}s)")

# ML Engine functions (simplified for brevity)
def load_model():
    return load_all_models()

def run_ml_engine():
    try:
        models = load_model()
        # ... rest of ML engine logic
        log_event("ML engine cycle completed")
    except Exception as e:
        log_event(f"ML engine error: {e}")
        traceback.print_exc()

def start_kafka_stream():
    # ... existing Kafka streaming logic
    pass

def main():
    log_event("Starting World Pulse Orchestrator with 12 FREE New Collectors...")
    log_event(f"Total collectors: {len(COLLECTOR_TASKS)}")
    log_event(f"New FREE collectors: {list(NEW_COLLECTOR_TASKS.keys())}")
    
    # Start all collectors
    start_all_collectors()
    
    # Start other services
    start_kafka_stream()
    
    # Keep main thread alive
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
