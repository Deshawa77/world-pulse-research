# processing/nlp_sentiment_advanced.py

from database.mongo import db
import pandas as pd
import re
import string

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
except ImportError:  # pragma: no cover - optional runtime dependency
    nltk = None
    stopwords = None
    WordNetLemmatizer = None

try:
    from textblob import TextBlob
except ImportError:  # pragma: no cover - optional runtime dependency
    TextBlob = None

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:  # pragma: no cover - optional runtime dependency
    SentimentIntensityAnalyzer = None

# ----------------------------
# Lightweight fallbacks for optional NLP dependencies
# ----------------------------
stop_words = set()
if nltk is not None and stopwords is not None:
    try:
        stop_words = set(stopwords.words('english'))
    except LookupError:
        stop_words = set()

lemmatizer = None
if WordNetLemmatizer is not None:
    try:
        lemmatizer = WordNetLemmatizer()
        if nltk is not None:
            nltk.data.find('corpora/wordnet')
    except LookupError:
        lemmatizer = WordNetLemmatizer()
    except Exception:
        lemmatizer = None

vader_analyzer = SentimentIntensityAnalyzer() if SentimentIntensityAnalyzer is not None else None

# ----------------------------
# Text cleaning
# ----------------------------
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if stop_words:
        words = [w for w in words if w not in stop_words]
    if lemmatizer is not None:
        words = [lemmatizer.lemmatize(w) for w in words]
    return " ".join(words)

# ----------------------------
# Sentiment analysis
# ----------------------------
def analyze_text(text):
    cleaned = clean_text(text)

    if TextBlob is not None:
        tb = TextBlob(cleaned)
        tb_sentiment = tb.sentiment
        textblob_sentiment = {
            "polarity": float(tb_sentiment.polarity),
            "subjectivity": float(tb_sentiment.subjectivity),
        }
    else:
        textblob_sentiment = {
            "polarity": 0.0,
            "subjectivity": 0.0,
        }

    if vader_analyzer is not None:
        vader_scores = vader_analyzer.polarity_scores(cleaned)
    else:
        vader_scores = {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}

    return {
        "textblob": textblob_sentiment,
        "vader": vader_scores
    }

# ----------------------------
# Collections and their text fields
# ----------------------------
COLLECTIONS = {
    "news": ["data.title", "data.description"],
    "reddit": ["data.title", "data.text"],
    "gdelt": ["data.title"],
    "wiki": ["data.summary"],
    "who": ["data.description"]
}

# ----------------------------
# Process a single collection
# ----------------------------
def process_collection(collection_name, text_keys):
    collection = db[collection_name]
    updated_count = 0

    for doc in collection.find():
        full_text = []

        for key in text_keys:
            parts = key.split(".")
            val = doc
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                if val is None:
                    break
            if val is not None:
                full_text.append(str(val))

        if full_text:
            combined_text = " ".join(full_text)
            sentiment = analyze_text(combined_text)

            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"data.sentiment": sentiment}}
            )
            updated_count += 1

    print(f"{collection_name}: Processed {updated_count} documents for advanced sentiment analysis.")

# ----------------------------
# Export results
# ----------------------------
def export_collection_to_csv(collection_name, filename):
    collection = db[collection_name]
    docs = list(collection.find())
    if not docs:
        print(f"{collection_name}: No documents found.")
        return
    df = pd.json_normalize(docs)
    df.to_csv(filename, index=False)
    print(f"{collection_name}: Exported {len(docs)} records to {filename}")

# ----------------------------
# Main
# ----------------------------
def main():
    print("Starting advanced NLP sentiment analysis...")
    for collection_name, text_keys in COLLECTIONS.items():
        process_collection(collection_name, text_keys)
        export_collection_to_csv(collection_name, f"advanced_sentiment_{collection_name}.csv")
    print("Advanced NLP sentiment analysis complete!")

if __name__ == "__main__":
    main()
