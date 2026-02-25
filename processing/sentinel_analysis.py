"""
SENTINEL AI - Intelligent Risk Assistant
Analysis service for generating AI-driven risk insights.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from database.mongo import db
import numpy as np


# Domain definitions for multi-domain signal detection
DOMAINS = {
    "geopolitical": ["news_sentiment", "gdelt_sentiment", "conflict_index"],
    "financial": ["crypto_return", "crypto_volatility", "stock_return", "stock_volatility", "market_volatility"],
    "behavioral": ["search_spike", "trends", "social_sentiment", "wiki_activity"],
    "environmental": ["weather_anomaly", "earthquake_count", "disaster_count", "climate_stress"],
    "health": ["who_alerts", "disease_outbreak", "health_sentiment"]
}

# Feature impact weights for top drivers
FEATURE_WEIGHTS = {
    "news_sentiment": 0.4,
    "gdelt_sentiment": 0.4,
    "crypto_return": 0.35,
    "crypto_volatility": 0.3,
    "stock_return": 0.3,
    "stock_volatility": 0.25,
    "weather_anomaly": 0.2,
    "conflict_index": 0.45,
    "market_volatility": 0.35,
    "search_spike": 0.15,
    "trends": 0.1,
    "social_sentiment": 0.2,
    "earthquake_count": 0.15,
    "disaster_count": 0.2,
    "who_alerts": 0.25,
    "disease_outbreak": 0.3
}

# Feature display names
FEATURE_NAMES = {
    "news_sentiment": "news sentiment shifts",
    "gdelt_sentiment": "global media sentiment",
    "crypto_return": "cryptocurrency market movements",
    "crypto_volatility": "crypto volatility",
    "stock_return": "equity market performance",
    "stock_volatility": "market volatility",
    "weather_anomaly": "weather anomalies",
    "conflict_index": "geopolitical instability",
    "market_volatility": "financial market volatility",
    "search_spike": "search interest spikes",
    "trends": "trending topic shifts",
    "social_sentiment": "social media sentiment",
    "earthquake_count": "seismic activity",
    "disaster_count": "natural disaster signals",
    "who_alerts": "health authority alerts",
    "disease_outbreak": "disease outbreak indicators"
}


def get_threat_level(risk_score: float) -> str:
    """
    Determine threat level based on risk score thresholds.
    
    Args:
        risk_score: Global risk score (0-100)
        
    Returns:
        Threat level string: stable, guarded, elevated, or critical
    """
    if risk_score < 50:
        return "stable"
    elif risk_score < 70:
        return "guarded"
    elif risk_score < 85:
        return "elevated"
    else:
        return "critical"


def detect_multi_domain_signal(features: Dict[str, float]) -> Tuple[bool, List[str]]:
    """
    Detect if 3+ major domains are showing significant signals simultaneously.
    
    Args:
        features: Dictionary of feature values
        
    Returns:
        Tuple of (multi_domain_signal boolean, list of active domains)
    """
    active_domains = []
    
    for domain, domain_features in DOMAINS.items():
        # Count how many features in this domain are showing significant activity
        active_features = 0
        for feature in domain_features:
            if feature in features:
                value = abs(features[feature])
                # Threshold for "significant" activity
                if value > 0.3:  # Normalized threshold
                    active_features += 1
        
        # If domain has at least 2 active features, consider it active
        if active_features >= 2:
            active_domains.append(domain)
    
    return len(active_domains) >= 3, active_domains


def calculate_top_drivers(features: Dict[str, float], limit: int = 3) -> List[Dict[str, Any]]:
    """
    Calculate top contributing factors to risk score.
    
    Args:
        features: Dictionary of feature values
        limit: Number of top drivers to return
        
    Returns:
        List of top drivers with feature name and impact score
    """
    drivers = []
    
    for feature, value in features.items():
        if feature in FEATURE_WEIGHTS:
            # Calculate impact as absolute value * weight
            impact = abs(value) * FEATURE_WEIGHTS[feature]
            drivers.append({
                "feature": feature,
                "impact": round(impact, 2),
                "display_name": FEATURE_NAMES.get(feature, feature.replace("_", " "))
            })
    
    # Sort by impact descending and return top N
    drivers.sort(key=lambda x: x["impact"], reverse=True)
    return drivers[:limit]


def calculate_confidence(features: Dict[str, float], data_freshness_hours: float) -> float:
    """
    Calculate confidence level based on data quality and freshness.
    
    Args:
        features: Dictionary of feature values
        data_freshness_hours: Hours since last data update
        
    Returns:
        Confidence score (0.0 - 1.0)
    """
    # Base confidence
    confidence = 0.7
    
    # Adjust for data completeness
    expected_features = len(FEATURE_WEIGHTS)
    available_features = sum(1 for f in features if f in FEATURE_WEIGHTS and features[f] != 0)
    completeness_factor = available_features / expected_features
    
    # Adjust for data freshness
    freshness_factor = max(0, 1 - (data_freshness_hours / 24))  # Decay over 24 hours
    
    # Calculate final confidence
    confidence = (0.4 * completeness_factor) + (0.4 * freshness_factor) + 0.2
    
    return round(min(1.0, max(0.5, confidence)), 2)


def generate_analysis_text(
    risk_trend: str,
    top_drivers: List[Dict[str, Any]],
    threat_level: str,
    multi_domain: bool
) -> str:
    """
    Generate deterministic analysis text using templates.
    
    Args:
        risk_trend: Risk trend direction (increasing, decreasing, stable)
        top_drivers: List of top contributing factors
        threat_level: Current threat level
        multi_domain: Whether multi-domain signal is detected
        
    Returns:
        Analysis text string
    """
    # Trend descriptions
    trend_desc = {
        "increasing": "rising",
        "decreasing": "declining",
        "stable": "stable with moderate fluctuations"
    }.get(risk_trend, "changing")
    
    # Get driver descriptions
    driver_descriptions = []
    for driver in top_drivers[:3]:
        display_name = driver.get("display_name", driver["feature"].replace("_", " "))
        driver_descriptions.append(display_name)
    
    # Build base sentence
    if len(driver_descriptions) >= 3:
        analysis = f"Systemic risk is {trend_desc}. {driver_descriptions[0]}, {driver_descriptions[1]}, and {driver_descriptions[2]} are contributing to upward pressure on global risk."
    elif len(driver_descriptions) == 2:
        analysis = f"Systemic risk is {trend_desc}. {driver_descriptions[0]} and {driver_descriptions[1]} are contributing to upward pressure on global risk."
    elif len(driver_descriptions) == 1:
        analysis = f"Systemic risk is {trend_desc}. {driver_descriptions[0]} is contributing to upward pressure on global risk."
    else:
        analysis = f"Systemic risk is {trend_desc}. Multiple global factors are contributing to current risk levels."
    
    # Add multi-domain context if applicable
    if multi_domain and threat_level in ["elevated", "critical"]:
        analysis += " Multi-domain signal detected across geopolitical, financial, and behavioral indicators."
    
    return analysis


def compute_sentinel_analysis() -> Dict[str, Any]:
    """
    Compute complete sentinel analysis for the current risk state.
    
    Returns:
        Dictionary containing all sentinel analysis data
    """
    # Get latest global features
    latest_doc = db.global_features.find_one({"mode": "online"}, sort=[("_id", -1)])
    
    if not latest_doc:
        # Return default analysis if no data
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "risk_score": 50.0,
            "risk_delta": 0.0,
            "risk_trend": "stable",
            "threat_level": "stable",
            "top_drivers": [],
            "multi_domain_signal": False,
            "confidence": 0.5,
            "analysis_text": "Insufficient data for analysis. Awaiting incoming signals."
        }
    
    features = latest_doc.get("features", {})
    current_risk = float(features.get("global_risk_score", 50.0))
    
    # Get previous risk score for delta calculation
    prev_doc = db.global_features.find_one(
        {"mode": "online", "_id": {"$lt": latest_doc["_id"]}},
        sort=[("_id", -1)]
    )
    prev_risk = float(prev_doc.get("features", {}).get("global_risk_score", current_risk)) if prev_doc else current_risk
    
    # Calculate risk delta
    risk_delta = round(current_risk - prev_risk, 2)
    
    # Determine trend
    if risk_delta > 1.0:
        risk_trend = "increasing"
    elif risk_delta < -1.0:
        risk_trend = "decreasing"
    else:
        risk_trend = "stable"
    
    # Get threat level
    threat_level = get_threat_level(current_risk)
    
    # Detect multi-domain signal
    multi_domain, active_domains = detect_multi_domain_signal(features)
    
    # Calculate top drivers
    top_drivers = calculate_top_drivers(features)
    
    # Calculate confidence
    timestamp = latest_doc.get("timestamp", datetime.utcnow().isoformat())
    try:
        if isinstance(timestamp, str):
            ts_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts_dt = timestamp
        freshness_hours = (datetime.utcnow() - ts_dt.replace(tzinfo=None)).total_seconds() / 3600
    except:
        freshness_hours = 0
    
    confidence = calculate_confidence(features, freshness_hours)
    
    # Generate analysis text
    analysis_text = generate_analysis_text(risk_trend, top_drivers, threat_level, multi_domain)
    
    return {
        "timestamp": timestamp if isinstance(timestamp, str) else timestamp.isoformat(),
        "risk_score": round(current_risk, 2),
        "risk_delta": risk_delta,
        "risk_trend": risk_trend,
        "threat_level": threat_level,
        "top_drivers": top_drivers,
        "multi_domain_signal": multi_domain,
        "active_domains": active_domains if multi_domain else [],
        "confidence": confidence,
        "analysis_text": analysis_text
    }


def get_sentinel_history(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get historical sentinel analysis data.
    
    Args:
        limit: Number of historical records to return
        
    Returns:
        List of historical sentinel analysis records
    """
    docs = list(db.global_features.find({"mode": "online"}).sort("timestamp", -1).limit(limit))
    
    history = []
    prev_risk = None
    
    for doc in reversed(docs):
        features = doc.get("features", {})
        current_risk = float(features.get("global_risk_score", 50.0))
        
        if prev_risk is not None:
            risk_delta = round(current_risk - prev_risk, 2)
        else:
            risk_delta = 0.0
        
        threat_level = get_threat_level(current_risk)
        multi_domain, _ = detect_multi_domain_signal(features)
        top_drivers = calculate_top_drivers(features)
        
        history.append({
            "timestamp": doc.get("timestamp", datetime.utcnow().isoformat()),
            "risk_score": round(current_risk, 2),
            "risk_delta": risk_delta,
            "threat_level": threat_level,
            "multi_domain_signal": multi_domain,
            "top_drivers": top_drivers
        })
        
        prev_risk = current_risk
    
    return history
