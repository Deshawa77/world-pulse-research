# -*- coding: utf-8 -*-
"""
Advanced Analytics Integration Module
====================================
Unified API for all 5 advanced ML features:
1. LSTM Predictor - Multi-step ahead forecasting
2. Anomaly Detector - Autoencoder-based anomaly detection
3. Causal Discovery - Root cause analysis
4. AI Report Generator - Natural language reports
5. Sentiment Momentum - Trend analysis & prediction

Author: World Pulse ML Team
"""

import os
import sys
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "advanced_analytics.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg: str):
    """Log event with timestamp"""
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[ADVANCED_ANALYTICS] {ts} | {msg}", flush=True)


# ============================================================
# Data Loading
# ============================================================
DATA_DIR = "./data"
FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment", 
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]


def load_features_from_mongodb(limit=500, mode="online") -> pd.DataFrame:
    """Load features from MongoDB global_features collection."""
    try:
        from database.mongo import get_historical_global_features
        docs = get_historical_global_features(limit=limit, mode=mode)
        if not docs or len(docs) == 0:
            log_event("⚠️ No documents in MongoDB global_features")
            return None
        rows = []
        for doc in docs:
            features = doc.get("features", {})
            if not features:
                features = {k: doc.get(k) for k in FEATURE_COLUMNS}
            row = {
                "timestamp": doc.get("timestamp"),
                "news_sentiment": features.get("news_sentiment"),
                "news_sentiment_std": features.get("news_sentiment_std"),
                "gdelt_sentiment": features.get("gdelt_sentiment"),
                "gdelt_sentiment_std": features.get("gdelt_sentiment_std"),
                "crypto_return": features.get("crypto_return"),
                "crypto_volatility": features.get("crypto_volatility"),
                "stock_return": features.get("stock_return"),
                "stock_volatility": features.get("stock_volatility"),
                "weather_anomaly": features.get("weather_anomaly"),
                "global_risk_score": features.get("global_risk_score"),
            }
            rows.append(row)
        df = pd.DataFrame(rows)
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
        log_event(f"✅ Loaded {len(df)} rows from MongoDB")
        return df
    except ImportError as e:
        log_event(f"⚠️ MongoDB not available: {e}")
        return None
    except Exception as e:
        log_event(f"⚠️ MongoDB error: {e}")
        return None

def load_features_data() -> pd.DataFrame:
    """Load hourly features - prefers MongoDB, falls back to CSV"""
    df = load_features_from_mongodb(limit=500, mode="online")
    if df is not None and len(df) > 10:
        return df
    df = load_features_from_mongodb(limit=500, mode="offline")
    if df is not None and len(df) > 10:
        return df
    log_event("⚠️ Falling back to CSV")
    if not os.path.exists(FEATURES_CSV):
        log_event(f"⚠️ Features file not found: {FEATURES_CSV}")
        np.random.seed(42)
        n = 50
        return pd.DataFrame({
            "timestamp": pd.date_range(start="2024-01-01", periods=n, freq="h"),
            "news_sentiment": np.random.randn(n) * 0.3,
            "gdelt_sentiment": np.random.randn(n) * 0.25,
            "crypto_return": np.random.randn(n) * 0.05,
            "crypto_volatility": np.random.rand(n) * 0.1 + 0.02,
            "stock_return": np.random.randn(n) * 0.02,
            "stock_volatility": np.random.rand(n) * 0.05 + 0.01,
            "weather_anomaly": np.random.randn(n) * 0.1,
        })
    df = pd.read_csv(FEATURES_CSV)
    time_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        df.rename(columns={time_cols[0]: "timestamp"}, inplace=True)
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(method='ffill').fillna(0)
    log_event(f"✅ Loaded {len(df)} rows from CSV")
    return df


# ============================================================
# Import Advanced Modules
# ============================================================
def get_lstm_predictions():
    """Get LSTM multi-step ahead predictions"""
    try:
        from machine_learning.lstm_predictor import get_lstm_predictions
        return get_lstm_predictions()
    except Exception as e:
        log_event(f"❌ LSTM predictions failed: {e}")
        return {"error": str(e), "status": "error"}


def get_anomaly_detection():
    """Get anomaly detection results"""
    try:
        from machine_learning.anomaly_detector import detect_anomalies_api
        return detect_anomalies_api()
    except Exception as e:
        log_event(f"❌ Anomaly detection failed: {e}")
        return {"error": str(e), "status": "error"}


def get_causal_analysis():
    """Get causal discovery and root cause analysis"""
    try:
        from machine_learning.causal_discovery import discover_causal_structure
        return discover_causal_structure()
    except Exception as e:
        log_event(f"❌ Causal analysis failed: {e}")
        return {"error": str(e), "status": "error"}


def get_ai_report(report_type: str = "brief"):
    """Get AI-generated crisis report"""
    try:
        from processing.ai_report_generator import generate_report_api
        return generate_report_api(report_type)
    except Exception as e:
        log_event(f"❌ AI report generation failed: {e}")
        return {"error": str(e), "status": "error"}


def get_sentiment_momentum():
    """Get sentiment momentum analysis"""
    try:
        from processing.sentiment_momentum import analyze_sentiment_momentum
        return analyze_sentiment_momentum()
    except Exception as e:
        log_event(f"❌ Sentiment momentum analysis failed: {e}")
        return {"error": str(e), "status": "error"}


# ============================================================
# Unified Advanced Analytics API
# ============================================================
class AdvancedAnalyticsEngine:
    """
    Unified Advanced Analytics Engine
    
    Provides a single interface for all 5 advanced ML features
    """
    
    def __init__(self):
        self.data = None
        self.results = {}
        
    def load_data(self, df: pd.DataFrame = None):
        """Load data for analysis"""
        if df is None:
            df = load_features_data()
        self.data = df
        log_event(f"✅ Loaded {len(df)} data points")
        
    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Run all advanced analytics and return comprehensive results
        
        Returns:
            Dictionary with all analysis results
        """
        log_event("🚀 Starting full advanced analytics analysis...")
        
        if self.data is None:
            self.load_data()
        
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_points": len(self.data),
            "analyses": {}
        }
        
        # 1. LSTM Predictions
        log_event("📈 Running LSTM predictions...")
        try:
            results["analyses"]["lstm_predictions"] = get_lstm_predictions()
        except Exception as e:
            results["analyses"]["lstm_predictions"] = {"error": str(e)}
        
        # 2. Anomaly Detection
        log_event("🔍 Running anomaly detection...")
        try:
            results["analyses"]["anomaly_detection"] = get_anomaly_detection()
        except Exception as e:
            results["analyses"]["anomaly_detection"] = {"error": str(e)}
        
        # 3. Causal Discovery
        log_event("🔗 Running causal discovery...")
        try:
            results["analyses"]["causal_discovery"] = get_causal_analysis()
        except Exception as e:
            results["analyses"]["causal_discovery"] = {"error": str(e)}
        
        # 4. AI Report Generation
        log_event("📝 Generating AI report...")
        try:
            results["analyses"]["ai_report"] = get_ai_report("executive")
        except Exception as e:
            results["analyses"]["ai_report"] = {"error": str(e)}
        
        # 5. Sentiment Momentum
        log_event("📊 Running sentiment momentum analysis...")
        try:
            results["analyses"]["sentiment_momentum"] = get_sentiment_momentum()
        except Exception as e:
            results["analyses"]["sentiment_momentum"] = {"error": str(e)}
        
        # Compile summary
        results["summary"] = self._compile_summary(results["analyses"])
        
        log_event("✅ Full advanced analytics analysis complete")
        
        return results
    
    def _compile_summary(self, analyses: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a summary from all analyses"""
        
        summary = {
            "risk_level": "unknown",
            "key_findings": [],
            "recommendations": [],
            "alerts": []
        }
        
        # Extract risk level from AI report
        ai_report = analyses.get("ai_report", {})
        if "report" in ai_report:
            report = ai_report["report"]
            risk = report.get("risk_assessment", {})
            summary["risk_level"] = risk.get("level", "UNKNOWN")
            summary["risk_score"] = risk.get("score", 0)
        
        # Extract anomalies
        anomaly = analyses.get("anomaly_detection", {})
        if "results" in anomaly:
            results = anomaly["results"]
            n_anomalies = results.get("n_anomalies", 0)
            if n_anomalies > 0:
                summary["alerts"].append({
                    "type": "anomalies_detected",
                    "severity": "high" if n_anomalies > 5 else "medium",
                    "message": f"{n_anomalies} anomalies detected in recent data"
                })
        
        # Extract sentiment signals
        sentiment = analyses.get("sentiment_momentum", {})
        if "results" in sentiment:
            overall = sentiment["results"].get("overall", {})
            direction = overall.get("direction", "unknown")
            if direction in ["strongly_upward", "strongly_downward"]:
                summary["alerts"].append({
                    "type": "sentiment_extreme",
                    "severity": "medium",
                    "message": f"Strong sentiment momentum: {direction}"
                })
        
        # Extract predictions
        lstm = analyses.get("lstm_predictions", {})
        if "risk_scores" in lstm:
            scores = lstm["risk_scores"]
            if scores:
                # Check for increasing risk
                if any(scores.get(h, 0) > 60 for h in ["1h", "6h"]):
                    summary["recommendations"].append("Near-term risk elevation predicted - monitor closely")
        
        # Extract causal insights
        causal = analyses.get("causal_discovery", {})
        if "graph" in causal:
            graph = causal["graph"]
            drivers = graph.get("key_drivers", [])
            if drivers:
                summary["key_findings"].append(f"Key risk drivers: {', '.join([d['name'] for d in drivers[:3]])}")
        
        return summary
    
    def get_insights(self) -> Dict[str, Any]:
        """Get quick insights from all analyses"""
        
        if not self.results:
            self.run_full_analysis()
        
        return self.results.get("summary", {})


# ============================================================
# API Functions
# ============================================================
def run_advanced_analytics(df: pd.DataFrame = None) -> Dict[str, Any]:
    """
    Main API function for advanced analytics
    
    Returns comprehensive analysis from all 5 advanced ML features
    """
    try:
        engine = AdvancedAnalyticsEngine()
        engine.load_data(df)
        results = engine.run_full_analysis()
        
        return {
            "status": "success",
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Advanced analytics failed: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def get_quick_insights() -> Dict[str, Any]:
    """Get quick insights without full analysis"""
    try:
        engine = AdvancedAnalyticsEngine()
        engine.load_data()
        
        # Run only lightweight analyses
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "insights": {}
        }
        
        # Quick AI report
        results["insights"]["risk_summary"] = get_ai_report("brief")
        
        # Quick anomaly check
        results["insights"]["anomalies"] = get_anomaly_detection()
        
        # Quick sentiment
        results["insights"]["sentiment"] = get_sentiment_momentum()
        
        return {
            "status": "success",
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Quick insights failed: {e}")
        return {"error": str(e), "status": "error"}


def get_predictions_only() -> Dict[str, Any]:
    """Get only LSTM predictions"""
    return get_lstm_predictions()


def get_anomalies_only() -> Dict[str, Any]:
    """Get only anomaly detection"""
    return get_anomaly_detection()


def get_causes_only() -> Dict[str, Any]:
    """Get only causal analysis"""
    return get_causal_analysis()


def get_report_only(report_type: str = "brief") -> Dict[str, Any]:
    """Get only AI report"""
    return get_ai_report(report_type)


def get_sentiment_only() -> Dict[str, Any]:
    """Get only sentiment momentum"""
    return get_sentiment_momentum()


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("Advanced Analytics - Standalone Test Run")
    log_event("=" * 60)
    
    # Initialize engine
    engine = AdvancedAnalyticsEngine()
    
    # Load data
    engine.load_data()
    print(f"\n📊 Loaded {len(engine.data)} data points")
    
    # Test full analysis
    print("\n🚀 Running full advanced analytics...")
    results = engine.run_full_analysis()
    
    print(f"\n✅ Analysis complete!")
    print(f"   Status: {results.get('timestamp')}")
    
    # Show summary
    summary = results.get("summary", {})
    print(f"\n📋 Summary:")
    print(f"   Risk Level: {summary.get('risk_level', 'unknown')}")
    print(f"   Alerts: {len(summary.get('alerts', []))}")
    print(f"   Recommendations: {len(summary.get('recommendations', []))}")
    
    # Test individual APIs
    print("\n🌐 Testing individual APIs...")
    print(f"   LSTM: {get_predictions_only().get('status', 'error')}")
    print(f"   Anomalies: {get_anomalies_only().get('status', 'error')}")
    print(f"   Causal: {get_causes_only().get('status', 'error')}")
    print(f"   Report: {get_report_only('brief').get('status', 'error')}")
    print(f"   Sentiment: {get_sentiment_only().get('status', 'error')}")
    
    log_event("✅ Advanced analytics test completed")
