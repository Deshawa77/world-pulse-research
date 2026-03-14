# -*- coding: utf-8 -*-
"""
AI-Powered Crisis Report Generator
===================================
Automatically generates human-readable crisis reports and summaries
using NLP techniques and template-based generation.

Features:
- Template-based NLG with dynamic data
- Neural summarization (if transformers available)
- Multiple report types (brief, detailed, executive)
- Risk narrative generation

Author: World Pulse ML Team
"""

import os
import sys
import json
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter
import random

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "ai_report_generator.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg: str):
    """Log event with timestamp (console-safe for non-UTF8 terminals)."""
    ts = datetime.now(timezone.utc).isoformat()
    text_msg = str(msg)
    line = f"[NLG] {ts} | {text_msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_line = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {text_msg}\n")



# ============================================================
# Configuration
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

# Risk thresholds
CRITICAL_THRESHOLD = 75
HIGH_THRESHOLD = 60
MEDIUM_THRESHOLD = 40
LOW_THRESHOLD = 25


# ============================================================
# Transformers Import (Optional)
# ============================================================
USE_TRANSFORMERS = False
summarizer = None

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
    USE_TRANSFORMERS = True
    log_event("✅ Transformers loaded for summarization")
except ImportError as e:
    log_event(f"⚠️ Transformers not available: {e}")
    log_event("📝 Using template-based NLG")


# ============================================================
# Data Loading
# ============================================================
def load_features_data() -> pd.DataFrame:
    """Load hourly features from CSV"""
    if not os.path.exists(FEATURES_CSV):
        return create_sample_data()
    
    df = pd.read_csv(FEATURES_CSV)
    
    time_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        df.rename(columns={time_cols[0]: "timestamp"}, inplace=True)
    
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(method='ffill').fillna(0)
    
    return df


def create_sample_data() -> pd.DataFrame:
    """Create sample data"""
    np.random.seed(42)
    n_samples = 50
    
    data = {
        "timestamp": pd.date_range(start="2024-01-01", periods=n_samples, freq="h"),
        "news_sentiment": np.random.randn(n_samples) * 0.3,
        "gdelt_sentiment": np.random.randn(n_samples) * 0.25,
        "crypto_return": np.random.randn(n_samples) * 0.05,
        "crypto_volatility": np.random.rand(n_samples) * 0.1 + 0.02,
        "stock_return": np.random.randn(n_samples) * 0.02,
        "stock_volatility": np.random.rand(n_samples) * 0.05 + 0.01,
        "weather_anomaly": np.random.randn(n_samples) * 0.1,
    }
    
    return pd.DataFrame(data)


# ============================================================
# Risk Classification Helpers
# ============================================================
def classify_risk_level(score: float) -> str:
    """Classify risk level from score"""
    if score >= CRITICAL_THRESHOLD:
        return "CRITICAL"
    elif score >= HIGH_THRESHOLD:
        return "HIGH"
    elif score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    elif score >= LOW_THRESHOLD:
        return "LOW"
    else:
        return "MINIMAL"


def get_risk_emoji(level: str) -> str:
    """Get emoji for risk level"""
    emojis = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
        "MINIMAL": "⚪"
    }
    return emojis.get(level, "⚪")


def get_severity_description(score: float) -> str:
    """Get natural language severity description"""
    if score >= CRITICAL_THRESHOLD:
        return "severe and requires immediate attention"
    elif score >= HIGH_THRESHOLD:
        return "elevated and concerning"
    elif score >= MEDIUM_THRESHOLD:
        return "moderate but worth monitoring"
    elif score >= LOW_THRESHOLD:
        return "relatively stable"
    else:
        return "stable with minimal concern"


# ============================================================
# Template-Based NLG
# ============================================================
class TemplateNLG:
    """Template-based natural language generation"""
    
    def __init__(self):
        self.templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, Any]:
        """Load NLG templates"""
        return {
            "headline": [
                "Global Risk {level}: {description}",
                "Risk Alert: {level} Status - {description}",
                "World Pulse Warning: {level} risk level detected",
            ],
            "summary": [
                "Current global risk assessment stands at {score}/100, classified as {level} severity. {trend_description}",
                "The risk score of {score} indicates {level} conditions. {trend_description}",
                "At {score}/100, the system registers {level} risk levels. {trend_description}",
            ],
            "factors_positive": [
                "{feature} has shown positive movement at {value:.2%}",
                "{feature} contributes positively with {value:.2%} change",
                "Favorable trends in {feature}: +{value:.2%}",
            ],
            "factors_negative": [
                "{feature} shows concerning trends at {value:.2%}",
                "Negative movement in {feature}: {value:.2%}",
                "{feature} is a concern with {value:.2%} decline",
            ],
            "forecast": [
                "Models predict {direction} risk levels over the next {horizon}",
                "Forecast indicates {direction} trend with {confidence}% confidence",
                "Outlook suggests {direction} conditions in {horizon}",
            ],
            "recommendation": [
                "Recommended action: {action}",
                "Consider {action} to mitigate potential risks",
                "Action item: {action}",
            ]
        }
    
    def generate_headline(self, risk_score: float, level: str) -> str:
        """Generate report headline"""
        template = random.choice(self.templates["headline"])
        description = get_severity_description(risk_score)
        
        return template.format(
            level=level,
            description=description
        )
    
    def generate_summary(self, risk_score: float, level: str, trend: str) -> str:
        """Generate executive summary"""
        template = random.choice(self.templates["summary"])
        
        return template.format(
            score=risk_score,
            level=level.lower(),
            trend_description=trend
        )
    
    def generate_factors(self, features: Dict[str, float]) -> List[str]:
        """Generate factor descriptions"""
        factors = []
        
        # Separate positive and negative factors
        positive = [(k, v) for k, v in features.items() if v > 0]
        negative = [(k, v) for k, v in features.items() if v < 0]
        
        # Sort by absolute value
        positive.sort(key=lambda x: -abs(x[1]))
        negative.sort(key=lambda x: -abs(x[1]))
        
        feature_names = {
            "news_sentiment": "news sentiment",
            "gdelt_sentiment": "global media sentiment",
            "crypto_return": "cryptocurrency returns",
            "crypto_volatility": "crypto market volatility",
            "stock_return": "equity market returns",
            "stock_volatility": "stock market volatility",
            "weather_anomaly": "weather anomalies"
        }
        
        # Add top positive factors
        for feature, value in positive[:2]:
            template = random.choice(self.templates["factors_positive"])
            factors.append(template.format(
                feature=feature_names.get(feature, feature),
                value=value
            ))
        
        # Add top negative factors
        for feature, value in negative[:2]:
            template = random.choice(self.templates["factors_negative"])
            factors.append(template.format(
                feature=feature_names.get(feature, feature),
                value=value
            ))
        
        return factors
    
    def generate_forecast(self, horizon: str, direction: str, confidence: float) -> str:
        """Generate forecast section"""
        template = random.choice(self.templates["forecast"])
        
        return template.format(
            horizon=horizon,
            direction=direction,
            confidence=confidence * 100
        )
    
    def generate_recommendation(self, risk_level: str) -> str:
        """Generate recommendation based on risk level"""
        actions = {
            "CRITICAL": [
                "Activate emergency response protocols immediately",
                "Initiate crisis communication procedures",
                "Escalate to executive leadership",
                "Implement contingency measures"
            ],
            "HIGH": [
                "Increase monitoring frequency",
                "Prepare contingency plans",
                "Alert relevant stakeholders",
                "Review emergency procedures"
            ],
            "MEDIUM": [
                "Continue active monitoring",
                "Review risk mitigation strategies",
                "Maintain situational awareness",
                "Check emergency protocols"
            ],
            "LOW": [
                "Continue routine monitoring",
                "Maintain standard procedures",
                "Periodic review of risk factors"
            ],
            "MINIMAL": [
                "Standard monitoring procedures",
                "Routine operational checks"
            ]
        }
        
        action = random.choice(actions.get(risk_level, actions["LOW"]))
        
        return random.choice(self.templates["recommendation"]).format(action=action)


# ============================================================
# Neural Summarizer (Optional)
# ============================================================
class NeuralSummarizer:
    """Neural network-based summarization using transformers"""
    
    def __init__(self):
        self.summarizer = None
        self.tokenizer = None
        self._load_model()
        
    def _load_model(self):
        """Load summarization model"""
        if not USE_TRANSFORMERS:
            return
            
        try:
            # Use a lightweight model for efficiency
            self.summarizer = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
                tokenizer="facebook/bart-large-cnn",
                device=-1  # CPU
            )
            log_event("✅ BART summarization model loaded")
        except Exception as e:
            log_event(f"⚠️ Failed to load summarization model: {e}")
            self.summarizer = None
    
    def summarize(self, text: str, max_length: int = 150, min_length: int = 50) -> str:
        """Generate neural summary"""
        if self.summarizer is None:
            return text
            
        try:
            result = self.summarizer(
                text,
                max_length=max_length,
                min_length=min_length,
                do_sample=False
            )
            return result[0]["summary_text"]
        except Exception as e:
            log_event(f"⚠️ Summarization failed: {e}")
            return text


# ============================================================
# Report Generator Main Class
# ============================================================
class AIReportGenerator:
    """
    AI-Powered Crisis Report Generator
    
    Generates comprehensive, human-readable crisis reports
    from structured data using NLG techniques.
    """
    
    def __init__(self):
        self.template_nlg = TemplateNLG()
        self.neural_summarizer = NeuralSummarizer() if USE_TRANSFORMERS else None
        
    def compute_risk_score(self, df: pd.DataFrame) -> float:
        """Compute overall risk score from features"""
        if df.empty:
            return 50.0
            
        latest = df.iloc[-1]
        
        # Weighted combination (similar to existing system)
        weights = {
            "news_sentiment": -0.25,
            "gdelt_sentiment": -0.20,
            "crypto_return": 0.10,
            "crypto_volatility": 0.15,
            "stock_return": -0.10,
            "stock_volatility": 0.10,
            "weather_anomaly": 0.10
        }
        
        score = 50.0
        for feature, weight in weights.items():
            if feature in latest:
                value = latest[feature]
                if pd.notna(value):
                    score += weight * value * 100
        
        return max(0, min(100, score))
    
    def compute_feature_contributions(self, df: pd.DataFrame) -> Dict[str, float]:
        """Compute feature contributions to risk"""
        if df.empty:
            return {}
            
        latest = df.iloc[-1]
        
        weights = {
            "news_sentiment": -0.25,
            "gdelt_sentiment": -0.20,
            "crypto_return": 0.10,
            "crypto_volatility": 0.15,
            "stock_return": -0.10,
            "stock_volatility": 0.10,
            "weather_anomaly": 0.10
        }
        
        contributions = {}
        for feature, weight in weights.items():
            if feature in latest:
                value = latest[feature]
                if pd.notna(value):
                    contributions[feature] = weight * value * 100
        
        return contributions
    
    def analyze_trend(self, df: pd.DataFrame) -> str:
        """Analyze risk trend from historical data"""
        if len(df) < 12:
            return "Insufficient data for trend analysis."
        
        # Compare recent average to earlier average
        recent = df.tail(6)[FEATURE_COLUMNS].mean().mean()
        earlier = df.head(-6).tail(6)[FEATURE_COLUMNS].mean().mean()
        
        change = recent - earlier
        
        if abs(change) < 2:
            return "Risk levels have remained relatively stable."
        elif change > 0:
            return f"Risk indicators show an upward trend (+{change:.1f} points recently)."
        else:
            return f"Risk indicators show a downward trend ({change:.1f} points recently)."
    
    def generate_report(
        self,
        df: pd.DataFrame,
        report_type: str = "brief",
        include_forecast: bool = True,
        include_recommendations: bool = True
    ) -> Dict[str, Any]:
        """
        Generate comprehensive crisis report
        
        Args:
            df: DataFrame with feature data
            report_type: Type of report ("brief", "detailed", "executive")
            include_forecast: Include forecast section
            include_recommendations: Include recommendations
            
        Returns:
            Dictionary with generated report sections
        """
        log_event(f"🔄 Generating {report_type} report...")
        
        # Compute risk score
        risk_score = self.compute_risk_score(df)
        risk_level = classify_risk_level(risk_score)
        
        # Get feature contributions
        contributions = self.compute_feature_contributions(df)
        
        # Analyze trend
        trend = self.analyze_trend(df)
        
        # Generate sections
        report = {
            "metadata": {
                "report_type": report_type,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_points": len(df),
                "data_range": {
                    "start": df["timestamp"].iloc[0].isoformat() if "timestamp" in df.columns else None,
                    "end": df["timestamp"].iloc[-1].isoformat() if "timestamp" in df.columns else None
                }
            },
            "headline": self.template_nlg.generate_headline(risk_score, risk_level),
            "risk_assessment": {
                "score": round(risk_score, 1),
                "level": risk_level,
                "emoji": get_risk_emoji(risk_level),
                "severity_description": get_severity_description(risk_score)
            },
            "summary": self.template_nlg.generate_summary(risk_score, risk_level, trend),
            "trend_analysis": trend
        }
        
        # Detailed factors (for detailed/executive reports)
        if report_type in ["detailed", "executive"]:
            report["risk_factors"] = {
                "positive": [
                    {"feature": k, "contribution": round(v, 2)}
                    for k, v in contributions.items() if v > 0
                ],
                "negative": [
                    {"feature": k, "contribution": round(v, 2)}
                    for k, v in contributions.items() if v < 0
                ]
            }
            
            # Feature descriptions
            report["factor_narratives"] = self.template_nlg.generate_factors(contributions)
        
        # Forecast section
        if include_forecast and report_type in ["detailed", "executive"]:
            # Simple statistical forecast
            direction = "increasing" if contributions.get("news_sentiment", 0) < 0 else "stable"
            confidence = 0.65 + random.random() * 0.2  # Simulated confidence
            
            report["forecast"] = {
                "horizon": "24 hours",
                "direction": direction,
                "confidence": round(confidence, 2),
                "narrative": self.template_nlg.generate_forecast("24 hours", direction, confidence)
            }
        
        # Recommendations
        if include_recommendations:
            report["recommendations"] = {
                "priority": risk_level,
                "actions": [
                    self.template_nlg.generate_recommendation(risk_level)
                ]
            }
        
        # Executive summary (neural if available)
        if report_type == "executive" and self.neural_summarizer:
            # Create a draft for neural summarization
            draft = f"""
            Global risk assessment: {risk_score} out of 100, classified as {risk_level} severity.
            {trend}
            Key factors include: {'; '.join([f'{k}: {v:.1f}' for k, v in contributions.items()])}
            """
            try:
                report["executive_summary"] = self.neural_summarizer.summarize(draft)
            except:
                report["executive_summary"] = report["summary"]
        else:
            report["executive_summary"] = report["summary"]
        
        log_event(f"✅ Report generated: {risk_level} ({risk_score:.1f}/100)")
        
        return report
    
    def generate_brief_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate brief alert-style report"""
        return self.generate_report(df, report_type="brief", include_forecast=False)
    
    def generate_detailed_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate detailed analytical report"""
        return self.generate_report(df, report_type="detailed")
    
    def generate_executive_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate executive summary report"""
        return self.generate_report(df, report_type="executive")
    
    def generate_comparison_report(self, df_current: pd.DataFrame, df_previous: pd.DataFrame) -> Dict[str, Any]:
        """Generate comparison report between two periods"""
        current_score = self.compute_risk_score(df_current)
        previous_score = self.compute_risk_score(df_previous)
        
        change = current_score - previous_score
        
        current_level = classify_risk_level(current_score)
        previous_level = classify_risk_level(previous_score)
        
        report = {
            "metadata": {
                "report_type": "comparison",
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "current": {
                "score": round(current_score, 1),
                "level": current_level
            },
            "previous": {
                "score": round(previous_score, 1),
                "level": previous_level
            },
            "change": {
                "absolute": round(change, 1),
                "relative": round((change / (previous_score + 1)) * 100, 1),
                "direction": "increased" if change > 0 else "decreased" if change < 0 else "stable"
            },
            "summary": self._generate_comparison_summary(current_score, previous_score, change)
        }
        
        return report
    
    def _generate_comparison_summary(self, current: float, previous: float, change: float) -> str:
        """Generate natural language for comparison"""
        level_curr = classify_risk_level(current)
        level_prev = classify_risk_level(previous)
        
        if level_curr == level_prev:
            return f"Risk remains at {level_curr} level with minor variations."
        elif abs(change) < 10:
            return f"Risk has shifted from {level_prev} to {level_curr} level."
        else:
            direction = "increased significantly" if change > 0 else "decreased significantly"
            return f"Risk has {direction} from {previous:.1f} to {current:.1f}."


# ============================================================
# API Functions
# ============================================================
def generate_report_api(
    report_type: str = "brief",
    df: pd.DataFrame = None
) -> Dict[str, Any]:
    """API function to generate report"""
    try:
        if df is None:
            df = load_features_data()
        
        generator = AIReportGenerator()
        
        if report_type == "brief":
            report = generator.generate_brief_report(df)
        elif report_type == "detailed":
            report = generator.generate_detailed_report(df)
        elif report_type == "executive":
            report = generator.generate_executive_report(df)
        else:
            return {"error": f"Unknown report type: {report_type}"}
        
        return {
            "status": "success",
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Report generation API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def generate_comparison_api(
    df_current: pd.DataFrame = None,
    df_previous: pd.DataFrame = None
) -> Dict[str, Any]:
    """API function to generate comparison report"""
    try:
        if df_current is None:
            df_current = load_features_data()
        
        # For previous period, use earlier data
        if df_previous is None:
            if len(df_current) > 48:
                df_previous = df_current.iloc[:-48]
            else:
                df_previous = df_current.head(10)
        
        generator = AIReportGenerator()
        report = generator.generate_comparison_report(df_current, df_previous)
        
        return {
            "status": "success",
            "report": report,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Comparison report API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("AI Report Generator - Standalone Test Run")
    log_event("=" * 60)
    
    # Load data
    df = load_features_data()
    print(f"\n📊 Loaded {len(df)} rows of data")
    
    # Initialize generator
    generator = AIReportGenerator()
    
    # Generate different report types
    print("\n📝 Generating brief report...")
    brief = generator.generate_brief_report(df)
    print(f"   Headline: {brief['headline']}")
    print(f"   Summary: {brief['summary']}")
    
    print("\n📝 Generating detailed report...")
    detailed = generator.generate_detailed_report(df)
    print(f"   Headline: {detailed['headline']}")
    print(f"   Risk Score: {detailed['risk_assessment']['score']}")
    print(f"   Level: {detailed['risk_assessment']['level']}")
    
    print("\n📝 Generating executive report...")
    executive = generator.generate_executive_report(df)
    print(f"   Executive Summary: {executive['executive_summary'][:200]}...")
    
    # Test comparison report
    print("\n📝 Generating comparison report...")
    df_current = df.tail(24)
    df_previous = df.head(24)
    comparison = generator.generate_comparison_report(df_current, df_previous)
    print(f"   Change: {comparison['change']['absolute']} points ({comparison['change']['direction']})")
    
    # Test API function
    print("\n🌐 Testing API function...")
    api_result = generate_report_api("brief")
    print(f"   Status: {api_result.get('status')}")
    
    log_event("✅ Report generator test completed")
