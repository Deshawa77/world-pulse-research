from database.mongo import db
from collections import defaultdict

def crisis_heatmap():
    collection = db["gdelt"]
    country_sentiment = defaultdict(list)

    for doc in collection.find(
        {},
        {
            "data.sentiment.polarity": 1,
            "data.country": 1
        }
    ):
        sentiment = doc.get("data", {}).get("sentiment", {}).get("polarity")
        country = doc.get("data", {}).get("country")

        if sentiment is not None and country:
            country_sentiment[country].append(sentiment)

    result = {}
    for country, values in country_sentiment.items():
        result[country] = sum(values) / len(values)

    return result
