# -*- coding: utf-8 -*-
"""
World Pulse System Test Script
Checks Kafka streaming, Data Lake, Mongo, ML Engine, and Email alerts
"""

import os, json, logging
from datetime import datetime
from kafka import KafkaConsumer
from database.mongo import db
from feature_store.feature_store import FeatureStore
from orchestrator import run_ml_engine, send_email, EMAIL_ALERT

# -------------------------------
# Logging setup
# -------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------
# 1️⃣ Kafka Streaming Test
# -------------------------------
KAFKA_BROKER = "localhost:9092"
TOPICS = [
    "news_topic","gdelt_topic","wiki_topic","trends_topic","earthquakes_topic",
    "weather_topic","crypto_topic","fred_topic","exchange_rates_topic",
    "who_topic","stocks_topic","worldbank_topic"
]

def test_kafka():
    logging.info("Starting Kafka streaming test...")
    for topic in TOPICS:
        logging.info(f"Checking topic '{topic}'...")
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=KAFKA_BROKER,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )
        for i, msg in enumerate(consumer):
            record = msg.value
            logging.info(f"Record {i+1}: {record}")
            # Check datetime fields
            for k, v in record.items():
                if 'time' in k.lower() or 'date' in k.lower():
                    try:
                        datetime.fromisoformat(v)
                    except Exception as e:
                        logging.warning(f"Datetime parse failed for field '{k}': {v}")
            if i >= 4:
                break
        consumer.close()
    logging.info("Kafka test complete.\n")

# -------------------------------
# 2️⃣ Data Lake & Mongo Test
# -------------------------------
def test_datalake_mongo():
    logging.info("Checking Data Lake JSON files...")
    dl_path = "data_lake"
    for file_name in os.listdir(dl_path):
        if file_name.endswith(".json"):
            file_path = os.path.join(dl_path, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                logging.info(f"{file_name}: {len(lines)} records found")
                if lines:
                    sample = json.loads(lines[-1])
                    logging.info(f"Sample record: {sample}")

    logging.info("\nChecking MongoDB collections...")
    collections = [t.replace("_topic","") for t in TOPICS]
    for coll_name in collections:
        coll = db[coll_name]
        count = coll.count_documents({})
        sample = coll.find_one()
        logging.info(f"Mongo collection '{coll_name}': {count} records, sample: {sample}")
        if sample and "_hash" not in sample:
            logging.warning(f"Record in '{coll_name}' missing _hash!")

# -------------------------------
# 3️⃣ ML Engine Validation
# -------------------------------
def test_ml_engine():
    logging.info("Testing FeatureStore and ML Engine...")
    fs = FeatureStore()
    df_global = fs.read_global()
    df_country = fs.read_country()
    logging.info(f"Global features (last 3 rows):\n{df_global.tail(3)}")
    logging.info(f"Country features (last 3 rows):\n{df_country.tail(3)}")
    
    logging.info("Running ML engine...")
    try:
        run_ml_engine()
        logging.info("ML engine ran successfully.")
    except Exception as e:
        logging.error(f"ML engine error: {e}")

# -------------------------------
# 4️⃣ Email Alert Test
# -------------------------------
def test_email():
    logging.info("Testing Email alerts...")
    global EMAIL_ALERT
    EMAIL_ALERT = True
    try:
        send_email("Test Alert", "This is a test from World Pulse!")
        logging.info("Email sent successfully (check inbox).")
    except Exception as e:
        logging.error(f"Email test failed: {e}")

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    test_kafka()
    test_datalake_mongo()
    test_ml_engine()
    test_email()
    logging.info("✅ All tests complete.")
