"""
HuggingFace Inference API Collector
Advanced transformer-based sentiment analysis and NLP
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
INFERENCE_API = "https://api-inference.huggingface.co/models"

# Pre-trained models for various NLP tasks
MODELS = {
    "sentiment": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "emotion": "j-hartmann/emotion-english-distilroberta-base",
    "ner": "dslim/bert-base-NER",
    "summarization": "facebook/bart-large-cnn",
    "zero_shot": "facebook/bart-large-mnli",
    "toxicity": "unitary/toxic-bert"
}

def query_huggingface(
    model: str,
    inputs: str,
    options: Optional[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    Query HuggingFace Inference API
    
    Args:
        model: Model identifier
        inputs: Text input
        options: Additional options like wait_for_model
    """
    if not API_TOKEN:
        print("HuggingFace API token not configured")
        return None
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"{INFERENCE_API}/{model}"
    
    payload = {
        "inputs": inputs
    }
    
    if options:
        payload["options"] = options
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        print(f"HuggingFace API error for {model}: {e}")
        return None

def analyze_sentiment_advanced(text: str) -> Optional[Dict[str, Any]]:
    """
    Advanced sentiment analysis using RoBERTa
    Returns: positive, negative, neutral scores
    """
    result = query_huggingface(
        MODELS["sentiment"],
        text,
        options={"wait_for_model": True}
    )
    
    if not result or not isinstance(result, list):
        return None
    
    # Parse results
    scores = {}
    for item in result[0]:
        label = item.get("label", "").lower()
        score = item.get("score", 0)
        scores[label] = score
    
    collected_at = datetime.now(timezone.utc).isoformat()
    
    return {
        "id": f"hf_sentiment_{hash(text) % 10000000}_{collected_at}",
        "source": "huggingface",
        "category": "nlp",
        "collected_at": collected_at,
        "data": {
            "text": text[:500],  # Truncate for storage
            "sentiment": scores,
            "model": MODELS["sentiment"],
            "type": "advanced_sentiment"
        }
    }

def analyze_emotion(text: str) -> Optional[Dict[str, Any]]:
    """
    Emotion detection: anger, disgust, fear, joy, neutral, sadness, surprise
    """
    result = query_huggingface(
        MODELS["emotion"],
        text,
        options={"wait_for_model": True}
    )
    
    if not result or not isinstance(result, list):
        return None
    
    emotions = {}
    for item in result[0]:
        label = item.get("label", "").lower()
        score = item.get("score", 0)
        emotions[label] = score
    
    collected_at = datetime.now(timezone.utc).isoformat()
    
    return {
        "id": f"hf_emotion_{hash(text) % 10000000}_{collected_at}",
        "source": "huggingface",
        "category": "nlp",
        "collected_at": collected_at,
        "data": {
            "text": text[:500],
            "emotions": emotions,
            "dominant_emotion": max(emotions, key=emotions.get) if emotions else "unknown",
            "model": MODELS["emotion"],
            "type": "emotion_detection"
        }
    }

def detect_toxicity(text: str) -> Optional[Dict[str, Any]]:
    """
    Detect toxic content: toxic, severe_toxic, obscene, threat, insult, identity_hate
    """
    result = query_huggingface(
        MODELS["toxicity"],
        text,
        options={"wait_for_model": True}
    )
    
    if not result or not isinstance(result, list):
        return None
    
    toxicity_scores = {}
    for item in result[0]:
        label = item.get("label", "").lower()
        score = item.get("score", 0)
        toxicity_scores[label] = score
    
    collected_at = datetime.now(timezone.utc).isoformat()
    
    return {
        "id": f"hf_toxicity_{hash(text) % 10000000}_{collected_at}",
        "source": "huggingface",
        "category": "nlp",
        "collected_at": collected_at,
        "data": {
            "text": text[:500],
            "toxicity_scores": toxicity_scores,
            "is_toxic": toxicity_scores.get("toxic", 0) > 0.5,
            "model": MODELS["toxicity"],
            "type": "toxicity_detection"
        }
    }

def zero_shot_classify(text: str, candidate_labels: List[str]) -> Optional[Dict[str, Any]]:
    """
    Zero-shot classification for custom categories
    """
    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": candidate_labels}
    }
    
    if not API_TOKEN:
        return None
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"{INFERENCE_API}/{MODELS['zero_shot']}"
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if not result or not isinstance(result, dict):
            return None
        
        labels = result.get("labels", [])
        scores = result.get("scores", [])
        
        classification = dict(zip(labels, scores))
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"hf_zeroshot_{hash(text) % 10000000}_{collected_at}",
            "source": "huggingface",
            "category": "nlp",
            "collected_at": collected_at,
            "data": {
                "text": text[:500],
                "classification": classification,
                "top_label": labels[0] if labels else "unknown",
                "confidence": scores[0] if scores else 0,
                "model": MODELS["zero_shot"],
                "type": "zero_shot_classification"
            }
        }
        
    except requests.RequestException as e:
        print(f"HuggingFace Zero-Shot API error: {e}")
        return None

def summarize_text(text: str, max_length: int = 130) -> Optional[Dict[str, Any]]:
    """
    Summarize long text using BART
    """
    payload = {
        "inputs": text,
        "parameters": {
            "max_length": max_length,
            "min_length": 30,
            "do_sample": False
        }
    }
    
    if not API_TOKEN:
        return None
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"{INFERENCE_API}/{MODELS['summarization']}"
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if not result or not isinstance(result, list):
            return None
        
        summary = result[0].get("summary_text", "")
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"hf_summary_{hash(text) % 10000000}_{collected_at}",
            "source": "huggingface",
            "category": "nlp",
            "collected_at": collected_at,
            "data": {
                "original_text": text[:1000],
                "summary": summary,
                "model": MODELS["summarization"],
                "type": "summarization"
            }
        }
        
    except requests.RequestException as e:
        print(f"HuggingFace Summarization API error: {e}")
        return None

def fetch_huggingface_nlp_data(sample_texts: List[str] = None) -> List[Dict[str, Any]]:
    """
    Main collector function - analyze sample texts with advanced NLP
    """
    if sample_texts is None:
        # Default sample texts for testing
        sample_texts = [
            "The global economy is showing signs of recovery after the pandemic.",
            "Climate change poses an existential threat to humanity.",
            "New breakthrough in AI technology announced today.",
            "Stock markets rally as inflation concerns ease.",
            "Natural disaster strikes coastal region causing widespread damage."
        ]
    
    all_records = []
    
    for text in sample_texts[:3]:  # Limit to avoid rate limits
        # Sentiment analysis
        sentiment = analyze_sentiment_advanced(text)
        if sentiment:
            all_records.append(sentiment)
        
        # Emotion detection
        emotion = analyze_emotion(text)
        if emotion:
            all_records.append(emotion)
        
        # Toxicity detection
        toxicity = detect_toxicity(text)
        if toxicity:
            all_records.append(toxicity)
        
        # Zero-shot classification
        labels = ["politics", "economy", "technology", "environment", "health"]
        zeroshot = zero_shot_classify(text, labels)
        if zeroshot:
            all_records.append(zeroshot)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_huggingface_nlp_data()
    print(f"Total records collected: {len(data)}")
    if data:
        for record in data[:2]:
            print(f"Sample record type: {record['data']['type']}")
            print(f"Data: {record['data']}")
            print("---")
