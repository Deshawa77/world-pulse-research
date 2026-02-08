# processing/nlp_sentiment_advanced.py

from database.mongo import db
import pandas as pd
import re
import string
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import nltk

# ----------------------------
# NLTK Downloads (only if needed)
# ----------------------------
try:
    stop_words = set(stopwords.words('english'))
except LookupError:
    nltk.download('stopwords')
    stop_words = set(stopwords.words('english'))

try:
    lemmatizer = WordNetLemmatizer()
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')
    lemmatizer = WordNetLemmatizer()

# Setup VADER
vader_analyzer = SentimentIntensityAnalyzer()

# ----------------------------
# Text cleaning
# ----------------------------
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+", "", text)  # remove URLs
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)  # remove punctuation
    text = re.sub(r"\s+", " ", text)  # normalize spaces
    words = text.split()
    words = [lemmatizer.lemmatize(w) for w in words if w not in stop_words]
    return " ".join(words)

# ----------------------------
# Sentiment analysis
# ----------------------------
def analyze_text(text):
    cleaned = clean_text(text)

    # TextBlob analysis
    tb = TextBlob(cleaned)
    tb_sentiment = tb.sentiment
    textblob_sentiment = {
        "polarity": tb_sentiment.polarity,       # -1 to 1
        "subjectivity": tb_sentiment.subjectivity # 0 to 1
    }

    # VADER analysis
    vader_scores = vader_analyzer.polarity_scores(cleaned)

    # Combine
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

            # Update only the sentiment field to avoid overwriting
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
