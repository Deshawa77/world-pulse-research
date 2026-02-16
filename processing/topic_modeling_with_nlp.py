# processing/topic_modeling_with_nlp.py

from database.mongo import db
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
import pandas as pd
import yake
from datetime import datetime

# -------------------------------
# Collections and text keys
# -------------------------------
COLLECTIONS = {
    "news": ["data.title", "data.description"],
    "reddit": ["data.title", "data.text"],
    "gdelt": ["data.title"],
    "wiki": ["data.summary"],
    "who": ["data.description"]
}

# -------------------------------
# Helper: Fetch texts from Mongo
# -------------------------------
def fetch_texts(collection_name, text_keys):
    collection = db[collection_name]
    docs = []
    doc_ids = []
    for doc in collection.find():
        combined_text = []
        for key in text_keys:
            parts = key.split(".")
            val = doc
            for p in parts:
                val = val.get(p, None)
                if val is None:
                    break
            if val:
                combined_text.append(str(val))
        if combined_text:
            docs.append(" ".join(combined_text))
            doc_ids.append(doc["_id"])
    return docs, doc_ids

# -------------------------------
# Topic modeling batch function
# -------------------------------
def topic_modeling(texts):
    vectorizer = CountVectorizer(stop_words="english")
    model = BERTopic(vectorizer_model=vectorizer, language="english")
    topics, probs = model.fit_transform(texts)
    return model, topics

# -------------------------------
# Keyword extraction
# -------------------------------
def extract_keywords(texts, top=5):
    kw_extractor = yake.KeywordExtractor(top=top, stopwords=None)
    return [kw_extractor.extract_keywords(t) for t in texts]

# -------------------------------
# Update Mongo documents
# -------------------------------
def update_documents(collection_name, doc_ids, topics, topic_model, keywords):
    collection = db[collection_name]
    for i, doc_id in enumerate(doc_ids):
        topic_num = topics[i]
        if topic_num == -1:
            topic_name = "Other"
            topic_words = []
        else:
            topic_words = [w for w, _ in topic_model.get_topic(topic_num)]
            topic_name = ", ".join(topic_words[:3])
        keyword_list = [kw for kw, _ in keywords[i]]
        collection.update_one(
            {"_id": doc_id},
            {"$set": {
                "data.topic": topic_name,
                "data.topic_words": topic_words,
                "data.keywords": keyword_list
            }}
        )

# -------------------------------
# Export to CSV
# -------------------------------
def export_collection_to_csv(collection_name, doc_ids, topics, topic_model, keywords):
    rows = []
    for i, doc_id in enumerate(doc_ids):
        topic_num = topics[i]
        if topic_num == -1:
            topic_name = "Other"
            topic_words = []
        else:
            topic_words = [w for w, _ in topic_model.get_topic(topic_num)]
            topic_name = ", ".join(topic_words[:3])
        keyword_list = [kw for kw, _ in keywords[i]]
        rows.append({
            "doc_id": str(doc_id),
            "topic": topic_name,
            "topic_words": ", ".join(topic_words),
            "keywords": ", ".join(keyword_list)
        })
    df = pd.DataFrame(rows)
    filename = f"topics_keywords_{collection_name}.csv"
    df.to_csv(filename, index=False)
    print(f"{collection_name}: Exported {len(rows)} records to {filename}")

# -------------------------------
# Daily summary
# -------------------------------
def generate_daily_summary():
    sentiment_totals = 0
    sentiment_count = 0
    topics_counter = {}

    for collection_name in COLLECTIONS:
        collection = db[collection_name]
        for doc in collection.find():
            sentiment = doc.get("data", {}).get("sentiment", {}).get("polarity", 0)
            sentiment_totals += sentiment
            sentiment_count += 1
            topic = doc.get("data", {}).get("topic", None)
            if topic:
                topics_counter[topic] = topics_counter.get(topic, 0) + 1

    avg_sentiment = sentiment_totals / sentiment_count if sentiment_count else 0
    top_topics = sorted(topics_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    summary = f"Daily World Summary ({datetime.now().date()}):\n"
    summary += f"Global sentiment is {'positive' if avg_sentiment > 0 else 'negative' if avg_sentiment < 0 else 'neutral'} (avg polarity={avg_sentiment:.2f}).\n"
    summary += "Top topics today: " + ", ".join([t[0] for t in top_topics])
    print(summary)
    return summary

# -------------------------------
# Per-record stub for orchestrator
# -------------------------------
def process_record(record):
    """
    Stub for per-record topic modeling in streaming.
    Since BERTopic is batch, we just mark the record as pending for topic assignment.
    """
    record["topic_modeling_status"] = "pending"
    return record

# -------------------------------
# Main batch routine
# -------------------------------
def main():
    print("Starting Topic Modeling with NLP...")

    for collection_name, text_keys in COLLECTIONS.items():
        print(f"\nProcessing collection: {collection_name}")
        texts, doc_ids = fetch_texts(collection_name, text_keys)
        if not texts:
            print(f"{collection_name}: No text to process.")
            continue

        topic_model, topics = topic_modeling(texts)
        keywords = extract_keywords(texts)
        update_documents(collection_name, doc_ids, topics, topic_model, keywords)
        export_collection_to_csv(collection_name, doc_ids, topics, topic_model, keywords)

    generate_daily_summary()
    print("\nTopic Modeling with NLP complete!")

# -------------------------------
# Run if called directly
# -------------------------------
if __name__ == "__main__":
    main()
