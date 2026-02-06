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

nltk.download('stopwords')
nltk.download('wordnet')

stop_words = set(stopwords.words('english'))
lemmatizer = WordNetLemmatizer()

# --------------------------
# Utility Functions
# --------------------------

def remove_duplicates(collection_name, unique_keys):
    collection = db[collection_name]
    seen = set()
    duplicates = 0
    for doc in collection.find():
        key_vals = tuple(
            doc.get(k.split('.')[0], None) if '.' not in k else doc.get(k.split('.')[0], {}).get(k.split('.')[1], None)
            for k in unique_keys
        )
        if key_vals in seen:
            collection.delete_one({'_id': doc['_id']})
            duplicates += 1
        else:
            seen.add(key_vals)
    print(f"{collection_name}: Removed {duplicates} duplicates.")

def standardize_timestamps(collection_name, timestamp_keys):
    collection = db[collection_name]
    for doc in collection.find():
        updated = False
        for key in timestamp_keys:
            parts = key.split('.')
            val = doc
            for p in parts:
                val = val.get(p, None)
                if val is None:
                    break
            if val:
                try:
                    iso_val = datetime.fromisoformat(str(val)).astimezone(timezone.utc).isoformat()
                    ref = doc
                    for p in parts[:-1]:
                        ref = ref[p]
                    ref[parts[-1]] = iso_val
                    updated = True
                except Exception:
                    continue
        if updated:
            collection.replace_one({'_id': doc['_id']}, doc)

def fill_missing_timeseries(collection_name, value_key):
    collection = db[collection_name]
    docs = list(collection.find())
    if not docs:
        return
    df = pd.DataFrame([doc['data'] for doc in docs])
    if value_key in df:
        df[value_key] = pd.to_numeric(df[value_key], errors='coerce')
        df[value_key].interpolate(method='linear', inplace=True)
        df[value_key].fillna(0, inplace=True)
    for idx, doc in enumerate(docs):
        doc['data'][value_key] = df.loc[idx, value_key]
        collection.replace_one({'_id': doc['_id']}, doc)

def normalize_timeseries(collection_name, value_key):
    collection = db[collection_name]
    docs = list(collection.find())
    if not docs:
        return
    values = np.array([float(doc['data'][value_key]) for doc in docs]).reshape(-1,1)
    scaler = MinMaxScaler()
    scaled_values = scaler.fit_transform(values)
    for idx, doc in enumerate(docs):
        doc['data'][value_key] = float(scaled_values[idx])
        collection.replace_one({'_id': doc['_id']}, doc)

def clean_text(text):
    text = text.lower()
    text = re.sub(r'http\S+', '', text)  # remove URLs
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)  # remove punctuation
    text = re.sub(r"\s+", " ", text)  # normalize spaces
    words = text.split()
    words = [lemmatizer.lemmatize(w) for w in words if w not in stop_words]
    return " ".join(words)

def preprocess_text(collection_name, text_keys):
    collection = db[collection_name]
    for doc in collection.find():
        updated = False
        for key in text_keys:
            parts = key.split('.')
            val = doc
            for p in parts:
                val = val.get(p, None)
                if val is None:
                    break
            if val:
                cleaned = clean_text(val)
                ref = doc
                for p in parts[:-1]:
                    ref = ref[p]
                ref[parts[-1]] = cleaned
                updated = True
        if updated:
            collection.replace_one({'_id': doc['_id']}, doc)

def export_collection_to_csv(collection_name, filename):
    collection = db[collection_name]
    docs = list(collection.find())
    df = pd.json_normalize(docs)
    df.to_csv(filename, index=False)
    print(f"{collection_name}: Exported {len(docs)} records to {filename}")

# --------------------------
# Main Cleaning & Preprocessing
# --------------------------
if __name__ == "__main__":
    # Remove duplicates
    remove_duplicates("news", ["data.title", "data.query"])
    remove_duplicates("reddit", ["data.title", "data.query"])
    remove_duplicates("crypto", ["data.timestamp"])
    remove_duplicates("stocks", ["data.timestamp"])
    remove_duplicates("weather", ["data.timestamp"])

    # Standardize timestamps
    standardize_timestamps("news", ["data.published_at"])
    standardize_timestamps("reddit", ["data.created_utc"])
    standardize_timestamps("crypto", ["data.timestamp"])
    standardize_timestamps("stocks", ["data.timestamp"])
    standardize_timestamps("weather", ["data.timestamp"])

    # Fill missing and normalize numeric features
    fill_missing_timeseries("crypto", "price")
    normalize_timeseries("crypto", "price")

    fill_missing_timeseries("stocks", "close")
    normalize_timeseries("stocks", "close")

    fill_missing_timeseries("weather", "temperature")
    normalize_timeseries("weather", "temperature")

    # Preprocess text
    preprocess_text("news", ["data.title", "data.description"])
    preprocess_text("reddit", ["data.title", "data.text"])
    preprocess_text("gdelt", ["data.title"])

    # Export for ML/NLP
    export_collection_to_csv("news", "processed_news.csv")
    export_collection_to_csv("reddit", "processed_reddit.csv")
    export_collection_to_csv("crypto", "processed_crypto.csv")
    export_collection_to_csv("stocks", "processed_stocks.csv")
    export_collection_to_csv("weather", "processed_weather.csv")

    print("Data preprocessing complete!")
