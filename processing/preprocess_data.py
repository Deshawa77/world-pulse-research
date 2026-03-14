from database.mongo import db
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import re
import string
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sklearn.preprocessing import MinMaxScaler
from pymongo import UpdateOne

# --------------------------
# NLP Setup
# --------------------------
try:
    nltk.data.find('corpora/stopwords')
except:
    nltk.download('stopwords')

try:
    nltk.data.find('corpora/wordnet')
except:
    nltk.download('wordnet')

stop_words = set(stopwords.words('english'))
lemmatizer = WordNetLemmatizer()

# --------------------------
# Utility Functions
# --------------------------
def remove_duplicates(collection_name, unique_keys):
    collection = db[collection_name]
    seen = set()
    bulk_ops = []
    duplicates = 0

    for doc in collection.find({}, {"_id": 1, **{k.split('.')[0]: 1 for k in unique_keys}}):
        key_vals = []
        for k in unique_keys:
            parts = k.split(".")
            val = doc
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
            key_vals.append(val)
        key_vals = tuple(key_vals)
        # Skip dedupe when none of the configured keys exist on a record.
        if all(v is None for v in key_vals):
            continue
        if key_vals in seen:
            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"_duplicate": True}}))
            duplicates += 1
        else:
            seen.add(key_vals)
    if bulk_ops:
        collection.bulk_write(bulk_ops)
        collection.delete_many({"_duplicate": True})
    print(f"{collection_name}: Removed {duplicates} duplicates.")

def standardize_timestamps(collection_name, timestamp_keys):
    collection = db[collection_name]
    bulk_ops = []
    for doc in collection.find():
        updated = False
        for key in timestamp_keys:
            parts = key.split(".")
            val = doc
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
            if val:
                try:
                    dt = pd.to_datetime(val, errors="coerce", utc=True)
                    if pd.notna(dt):
                        ref = doc
                        for p in parts[:-1]:
                            ref = ref[p]
                        ref[parts[-1]] = dt.isoformat()
                        updated = True
                except:
                    pass
        if updated:
            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}))
    if bulk_ops:
        collection.bulk_write(bulk_ops)
    print(f"{collection_name}: timestamps standardized.")

def fill_missing_timeseries(collection_name, value_key):
    collection = db[collection_name]
    docs = list(collection.find())
    values = []
    valid_docs = []
    for doc in docs:
        if "data" in doc and value_key in doc["data"]:
            try:
                values.append(float(doc["data"][value_key]))
                valid_docs.append(doc)
            except:
                values.append(np.nan)
                valid_docs.append(doc)
    if not values:
        return
    series = pd.Series(values).astype(float)
    series = series.interpolate(method="linear").fillna(0)
    bulk_ops = []
    for idx, doc in enumerate(valid_docs):
        bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {f"data.{value_key}": float(series.iloc[idx])}}))
    if bulk_ops:
        collection.bulk_write(bulk_ops)
    print(f"{collection_name}: missing values filled for {value_key}.")

def normalize_timeseries(collection_name, value_key):
    collection = db[collection_name]
    docs = list(collection.find())
    values = []
    valid_docs = []
    for doc in docs:
        if "data" in doc and value_key in doc["data"]:
            try:
                values.append(float(doc["data"][value_key]))
                valid_docs.append(doc)
            except:
                pass
    if not values:
        return
    values = np.array(values).reshape(-1, 1)
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(values)
    bulk_ops = []
    for idx, doc in enumerate(valid_docs):
        bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {f"data.{value_key}_normalized": float(scaled[idx][0])}}))
    if bulk_ops:
        collection.bulk_write(bulk_ops)
    print(f"{collection_name}: normalized {value_key} → {value_key}_normalized.")

def clean_text(text):
    if not isinstance(text, str):
        return text
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)
    text = re.sub(r"\s+", " ", text)
    words = text.split()
    words = [lemmatizer.lemmatize(w) for w in words if w not in stop_words]
    return " ".join(words)

def preprocess_text(collection_name, text_keys):
    collection = db[collection_name]
    bulk_ops = []
    for doc in collection.find():
        updated_fields = {}
        for key in text_keys:
            parts = key.split(".")
            val = doc
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
            if isinstance(val, str) and val.strip():
                cleaned = clean_text(val)
                updated_fields[key] = cleaned
        if updated_fields:
            update_doc = {"$set": {}}
            for k, v in updated_fields.items():
                update_doc["$set"][k] = v
            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, update_doc))
    if bulk_ops:
        collection.bulk_write(bulk_ops)
    print(f"{collection_name}: text preprocessing complete.")

def export_collection_to_csv(collection_name, filename):
    collection = db[collection_name]
    docs = list(collection.find())
    if not docs:
        print(f"{collection_name}: No data to export.")
        return
    df = pd.json_normalize(docs, sep="_")
    df.to_csv(filename, index=False)
    print(f"{collection_name}: Exported {len(docs)} records → {filename}")

# --------------------------
# New: Per-record preprocessing for streaming
# --------------------------
def process_record(record):
    """
    Minimal preprocessing for a single record (streaming mode).
    Mirrors batch preprocessing steps for one record.
    """
    if not isinstance(record, dict):
        return record
    # Lowercase and clean text fields
    for key in ["title", "description", "text"]:
        if key in record and isinstance(record[key], str):
            record[key] = clean_text(record[key])
    # Standardize timestamps if present
    for key in ["published_at", "created_utc", "timestamp"]:
        if key in record:
            try:
                dt = pd.to_datetime(record[key], errors="coerce", utc=True)
                if pd.notna(dt):
                    record[key] = dt.isoformat()
            except:
                pass
    return record

# --------------------------
# Main Pipeline (batch)
# --------------------------
def main():
    print("\n🚀 Starting World Pulse preprocessing pipeline...\n")

    # Deduplication
    remove_duplicates("news", ["data.title", "data.query"])
    remove_duplicates("reddit", ["data.title", "data.query"])
    remove_duplicates("crypto", ["data.timestamp"])
    remove_duplicates("stocks", ["data.timestamp"])
    remove_duplicates("weather", ["data.timestamp", "data.date", "data.city", "data_city", "data_timestamp"])

    # Timestamp normalization
    standardize_timestamps("news", ["data.published_at"])
    standardize_timestamps("reddit", ["data.created_utc"])
    standardize_timestamps("crypto", ["data.timestamp"])
    standardize_timestamps("stocks", ["data.timestamp"])
    standardize_timestamps("weather", ["data.timestamp", "data.date", "data_timestamp", "collected_at"])

    # Time-series processing
    fill_missing_timeseries("crypto", "price")
    normalize_timeseries("crypto", "price")
    fill_missing_timeseries("stocks", "close")
    normalize_timeseries("stocks", "close")
    fill_missing_timeseries("weather", "temperature")
    normalize_timeseries("weather", "temperature")

    # NLP processing
    preprocess_text("news", ["data.title", "data.description"])
    preprocess_text("reddit", ["data.title", "data.text"])
    preprocess_text("gdelt", ["data.title"])

    # Export ML-ready datasets
    export_collection_to_csv("news", "processed_news.csv")
    export_collection_to_csv("reddit", "processed_reddit.csv")
    export_collection_to_csv("crypto", "processed_crypto.csv")
    export_collection_to_csv("stocks", "processed_stocks.csv")
    export_collection_to_csv("weather", "processed_weather.csv")

    print("\n✅ World Pulse preprocessing pipeline complete.\n")

# --------------------------
# Entry Point
# --------------------------
if __name__ == "__main__":
    main()


