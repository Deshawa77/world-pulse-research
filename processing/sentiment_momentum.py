# -*- coding: utf-8 -*-
"""
Sentiment Momentum & Trend Analysis
===================================
Tracks sentiment velocity, acceleration, and predicts sentiment shifts
using technical analysis-inspired indicators.

Features:
- Sentiment momentum indicators (like RSI, MACD for sentiment)
- Velocity and acceleration tracking
- Trend reversal prediction
- Divergence detection

Author: World Pulse ML Team
"""

import os
import sys
import json
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any
from collections import deque

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "sentiment_momentum.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg: str):
    """Log event with timestamp"""
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[MOMENTUM] {ts} | {msg}", flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")


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

# Sentiment features
SENTIMENT_FEATURES = ["news_sentiment", "gdelt_sentiment"]

# Indicator parameters
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2

# Thresholds
OVERSOLD_THRESHOLD = 30
OVERBOUGHT_THRESHOLD = 70
EXTREME_NEGATIVE = -0.5
EXTREME_POSITIVE = 0.5


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
    n_samples = 100
    
    # Create realistic sentiment with trends and oscillations
    t = np.linspace(0, 4 * np.pi, n_samples)
    
    data = {
        "timestamp": pd.date_range(start="2024-01-01", periods=n_samples, freq="h"),
        "news_sentiment": np.sin(t) * 0.3 + np.random.randn(n_samples) * 0.1,
        "gdelt_sentiment": np.sin(t + 0.5) * 0.25 + np.random.randn(n_samples) * 0.08,
        "crypto_return": np.random.randn(n_samples) * 0.05,
        "crypto_volatility": np.random.rand(n_samples) * 0.1 + 0.02,
        "stock_return": np.random.randn(n_samples) * 0.02,
        "stock_volatility": np.random.rand(n_samples) * 0.05 + 0.01,
        "weather_anomaly": np.random.randn(n_samples) * 0.1,
    }
    
    return pd.DataFrame(data)


# ============================================================
# Technical Indicators for Sentiment
# ============================================================
def compute_rsi(values: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
    """
    Compute Relative Strength Index (RSI)
    
    RSI > 70 = Overbought (potential reversal down)
    RSI < 30 = Oversold (potential reversal up)
    """
    deltas = np.diff(values)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    # Use rolling mean
    avg_gain = np.convolve(gains, np.ones(period)/period, mode='same')
    avg_loss = np.convolve(losses, np.ones(period)/period, mode='same')
    
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    # Pad with NaN
    rsi = np.concatenate([np.full(period, np.nan), rsi])
    
    return rsi


def compute_macd(values: np.ndarray, fast: int = MACD_FAST, slow: int = MACD_SLOW, 
                 signal: int = MACD_SIGNAL) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute MACD (Moving Average Convergence Divergence)
    
    MACD Line = Fast EMA - Slow EMA
    Signal Line = EMA of MACD Line
    Histogram = MACD Line - Signal Line
    """
    # Compute EMAs
    ema_fast = pd.Series(values).ewm(span=fast, adjust=False).mean().values
    ema_slow = pd.Series(values).ewm(span=slow, adjust=False).mean().values
    
    macd_line = ema_fast - ema_slow
    signal_line = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().values
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def compute_bollinger_bands(values: np.ndarray, period: int = BOLLINGER_PERIOD, 
                            num_std: float = BOLLINGER_STD) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Bollinger Bands"""
    rolling_mean = pd.Series(values).rolling(window=period).mean().values
    rolling_std = pd.Series(values).rolling(window=period).std().values
    
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    
    return upper_band, rolling_mean, lower_band


def compute_momentum(values: np.ndarray, period: int = 10) -> np.ndarray:
    """Compute momentum (rate of change)"""
    momentum = np.zeros_like(values)
    momentum[period:] = (values[period:] - values[:-period]) / (np.abs(values[:-period]) + 1e-10)
    
    return momentum


def compute_acceleration(values: np.ndarray, period: int = 10) -> np.ndarray:
    """Compute acceleration (change in momentum)"""
    momentum = compute_momentum(values, period)
    acceleration = np.zeros_like(momentum)
    acceleration[period:] = momentum[period:] - momentum[:-period]
    
    return acceleration


def compute_velocity(values: np.ndarray, period: int = 5) -> np.ndarray:
    """Compute velocity (short-term rate of change)"""
    velocity = np.zeros_like(values)
    velocity[period:] = values[period:] - values[:-period]
    
    return velocity


def detect_divergence(values: np.ndarray, prices: np.ndarray, lookback: int = 20) -> List[Dict[str, Any]]:
    """
    Detect bullish/bearish divergence
    
    Bullish: Price makes lower low, but indicator makes higher low
    Bearish: Price makes higher high, but indicator makes lower high
    """
    divergences = []
    
    if len(values) < lookback * 2:
        return divergences
    
    # Get recent values
    recent_prices = prices[-lookback:]
    recent_indicator = values[-lookback:]
    
    # Find local extrema
    from scipy.signal import argrelextrema
    
    price_max_idx = argrelextrema(recent_prices, np.greater, order=3)[0]
    price_min_idx = argrelextrema(recent_prices, np.less, order=3)[0]
    
    indicator_max_idx = argrelextrema(recent_indicator, np.greater, order=3)[0]
    indicator_min_idx = argrelextrema(recent_indicator, np.less, order=3)[0]
    
    # Check for bullish divergence (price lower low, indicator higher low)
    if len(price_min_idx) > 0 and len(indicator_min_idx) > 0:
        last_price_min = price_min_idx[-1]
        last_indicator_min = indicator_min_idx[-1]
        
        if last_price_min > last_indicator_min:
            price_low = recent_prices[last_price_min]
            indicator_low = recent_indicator[last_indicator_min]
            
            if indicator_low > np.nanmean(recent_indicator):
                divergences.append({
                    "type": "bullish",
                    "strength": abs(indicator_low - np.nanmean(recent_indicator)),
                    "description": "Potential upward reversal (bullish divergence)"
                })
    
    # Check for bearish divergence (price higher high, indicator lower high)
    if len(price_max_idx) > 0 and len(indicator_max_idx) > 0:
        last_price_max = price_max_idx[-1]
        last_indicator_max = indicator_max_idx[-1]
        
        if last_price_max > last_indicator_max:
            price_high = recent_prices[last_price_max]
            indicator_high = recent_indicator[last_indicator_max]
            
            if indicator_high < np.nanmean(recent_indicator):
                divergences.append({
                    "type": "bearish",
                    "strength": abs(np.nanmean(recent_indicator) - indicator_high),
                    "description": "Potential downward reversal (bearish divergence)"
                })
    
    return divergences


# ============================================================
# Sentiment Momentum Analyzer
# ============================================================
class SentimentMomentumAnalyzer:
    """
    Sentiment Momentum & Trend Analyzer
    
    Applies technical analysis indicators to sentiment data
    to predict trend reversals and shifts.
    """
    
    def __init__(self):
        self.sentiment_data = None
        self.indicators = {}
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform comprehensive sentiment momentum analysis
        
        Args:
            df: DataFrame with sentiment features
            
        Returns:
            Dictionary with analysis results
        """
        log_event("🔄 Analyzing sentiment momentum...")
        
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": {}
        }
        
        for feature in SENTIMENT_FEATURES:
            if feature not in df.columns:
                continue
                
            values = df[feature].values
            
            if len(values) < RSI_PERIOD:
                log_event(f"⚠️ Insufficient data for {feature}")
                continue
            
            # Compute indicators
            rsi = compute_rsi(values)
            macd_line, signal_line, histogram = compute_macd(values)
            upper, middle, lower = compute_bollinger_bands(values)
            velocity = compute_velocity(values)
            acceleration = compute_acceleration(values)
            momentum = compute_momentum(values)
            
            # Latest values
            latest_rsi = rsi[-1] if not np.isnan(rsi[-1]) else 50
            latest_macd = macd_line[-1] if not np.isnan(macd_line[-1]) else 0
            latest_hist = histogram[-1] if not np.isnan(histogram[-1]) else 0
            latest_velocity = velocity[-1] if not np.isnan(velocity[-1]) else 0
            latest_accel = acceleration[-1] if not np.isnan(acceleration[-1]) else 0
            
            # Determine sentiment state
            state = self._determine_state(
                latest_rsi, latest_macd, latest_hist,
                latest_velocity, values[-1]
            )
            
            # Detect divergence
            divergences = detect_divergence(values, values)
            
            # Trend prediction
            prediction = self._predict_trend(
                latest_rsi, latest_macd, latest_hist,
                latest_velocity, latest_accel, state
            )
            
            results["features"][feature] = {
                "current_value": float(values[-1]),
                "state": state,
                "indicators": {
                    "rsi": {
                        "value": float(latest_rsi),
                        "status": "oversold" if latest_rsi < OVERSOLD_THRESHOLD else 
                                  "overbought" if latest_rsi > OVERBOUGHT_THRESHOLD else "neutral"
                    },
                    "macd": {
                        "line": float(latest_macd),
                        "histogram": float(latest_hist),
                        "status": "bullish" if latest_macd > 0 else "bearish"
                    },
                    "velocity": float(latest_velocity),
                    "acceleration": float(latest_accel),
                    "momentum": float(momentum[-1]) if not np.isnan(momentum[-1]) else 0
                },
                "divergences": divergences,
                "prediction": prediction,
                "support_resistance": {
                    "upper_band": float(upper[-1]) if not np.isnan(upper[-1]) else None,
                    "middle_band": float(middle[-1]) if not np.isnan(middle[-1]) else None,
                    "lower_band": float(lower[-1]) if not np.isnan(lower[-1]) else None
                }
            }
        
        # Overall sentiment analysis
        results["overall"] = self._compute_overall_analysis(results["features"])
        
        log_event(f"✅ Sentiment momentum analysis complete")
        
        return results
    
    def _determine_state(self, rsi: float, macd: float, histogram: float, 
                         velocity: float, value: float) -> str:
        """Determine current sentiment state"""
        states = []
        
        # RSI-based
        if rsi < OVERSOLD_THRESHOLD:
            states.append("oversold")
        elif rsi > OVERBOUGHT_THRESHOLD:
            states.append("overbought")
        
        # MACD-based
        if histogram > 0:
            states.append("bullish_momentum")
        else:
            states.append("bearish_momentum")
        
        # Velocity-based
        if velocity > 0.05:
            states.append("rising")
        elif velocity < -0.05:
            states.append("falling")
        
        # Value-based
        if value < EXTREME_NEGATIVE:
            states.append("extremely_negative")
        elif value > EXTREME_POSITIVE:
            states.append("extremely_positive")
        
        # Determine dominant state
        if "oversold" in states or "extremely_negative" in states:
            return "oversold"
        elif "overbought" in states or "extremely_positive" in states:
            return "overbought"
        elif "bullish_momentum" in states and "rising" in states:
            return "strong_uptrend"
        elif "bearish_momentum" in states and "falling" in states:
            return "strong_downtrend"
        elif "bullish_momentum" in states:
            return "weak_uptrend"
        elif "bearish_momentum" in states:
            return "weak_downtrend"
        else:
            return "neutral"
    
    def _predict_trend(self, rsi: float, macd: float, histogram: float,
                       velocity: float, acceleration: float, state: str) -> Dict[str, Any]:
        """Predict future trend direction"""
        
        # Score-based prediction
        score = 0
        
        # RSI signals
        if rsi < 35:
            score += 2  # Oversold - potential bounce
        elif rsi > 65:
            score -= 2  # Overbought - potential pullback
        elif 40 < rsi < 60:
            score += 0.5  # Neutral zone
        
        # MACD signals
        if histogram > 0:
            score += 1 if histogram > 0.02 else 0.5
        else:
            score -= 1 if histogram < -0.02 else 0.5
        
        # Momentum signals
        if velocity > 0.1:
            score += 1
        elif velocity < -0.1:
            score -= 1
        
        if acceleration > 0:
            score += 0.5  # Accelerating upward
        elif acceleration < 0:
            score -= 0.5  # Accelerating downward
        
        # Determine prediction
        if score >= 2.5:
            direction = "strongly_upward"
            confidence = min(0.9, 0.5 + abs(score) * 0.1)
        elif score >= 1:
            direction = "upward"
            confidence = min(0.8, 0.5 + abs(score) * 0.1)
        elif score <= -2.5:
            direction = "strongly_downward"
            confidence = min(0.9, 0.5 + abs(score) * 0.1)
        elif score <= -1:
            direction = "downward"
            confidence = min(0.8, 0.5 + abs(score) * 0.1)
        else:
            direction = "stable"
            confidence = 0.5
        
        # Generate explanation
        explanations = []
        
        if rsi < 35:
            explanations.append("RSI indicates oversold conditions")
        elif rsi > 65:
            explanations.append("RSI indicates overbought conditions")
        
        if histogram > 0.02:
            explanations.append("MACD shows strong bullish momentum")
        elif histogram < -0.02:
            explanations.append("MACD shows strong bearish momentum")
        
        if acceleration > 0 and velocity > 0:
            explanations.append("Positive acceleration suggests continued rise")
        elif acceleration < 0 and velocity < 0:
            explanations.append("Negative acceleration suggests continued decline")
        
        return {
            "direction": direction,
            "confidence": round(confidence, 2),
            "score": score,
            "explanations": explanations if explanations else ["No strong signals detected"]
        }
    
    def _compute_overall_analysis(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Compute overall sentiment analysis across features"""
        
        if not features:
            return {"status": "no_data"}
        
        # Average values
        values = [f["current_value"] for f in features.values()]
        avg_value = np.mean(values)
        
        # Combined state
        states = [f["state"] for f in features.values()]
        
        # Count states
        from collections import Counter
        state_counts = Counter(states)
        
        dominant_state = state_counts.most_common(1)[0][0] if state_counts else "neutral"
        
        # Combined prediction
        predictions = [f["prediction"] for f in features.values() if "prediction" in f]
        
        if predictions:
            directions = [p["direction"] for p in predictions]
            confidences = [p["confidence"] for p in predictions]
            
            # Weighted average
            avg_confidence = np.mean(confidences)
            
            # Determine dominant direction
            up_count = sum(1 for d in directions if "up" in d)
            down_count = sum(1 for d in directions if "down" in d)
            
            if up_count > down_count:
                overall_direction = "upward" if up_count > len(directions) / 2 else "potentially_upward"
            elif down_count > up_count:
                overall_direction = "downward" if down_count > len(directions) / 2 else "potentially_downward"
            else:
                overall_direction = "stable"
        else:
            overall_direction = "unknown"
            avg_confidence = 0
        
        return {
            "average_sentiment": float(avg_value),
            "dominant_state": dominant_state,
            "direction": overall_direction,
            "confidence": round(avg_confidence, 2),
            "states_distribution": dict(state_counts)
        }
    
    def get_sentiment_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get actionable sentiment signals"""
        
        analysis = self.analyze(df)
        
        signals = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signals": [],
            "alerts": []
        }
        
        overall = analysis.get("overall", {})
        
        # Generate signals based on analysis
        for feature, data in analysis.get("features", {}).items():
            state = data.get("state", "neutral")
            prediction = data.get("prediction", {})
            
            if state == "oversold":
                signals["signals"].append({
                    "type": "buy",
                    "feature": feature,
                    "reason": "Sentiment oversold - potential reversal up",
                    "confidence": 0.7
                })
            
            elif state == "overbought":
                signals["signals"].append({
                    "type": "sell",
                    "feature": feature,
                    "reason": "Sentiment overbought - potential reversal down",
                    "confidence": 0.7
                })
            
            # Divergence signals
            for div in data.get("divergences", []):
                if div["type"] == "bullish":
                    signals["signals"].append({
                        "type": "buy",
                        "feature": feature,
                        "reason": div["description"],
                        "confidence": min(0.8, 0.5 + div["strength"])
                    })
                elif div["type"] == "bearish":
                    signals["signals"].append({
                        "type": "sell",
                        "feature": feature,
                        "reason": div["description"],
                        "confidence": min(0.8, 0.5 + div["strength"])
                    })
        
        # Generate alerts for extreme conditions
        if overall.get("direction") in ["strongly_upward", "strongly_downward"]:
            signals["alerts"].append({
                "type": "extreme_sentiment",
                "severity": "high",
                "message": f"Strong sentiment momentum detected: {overall['direction']}"
            })
        
        # Alert for potential reversal
        if overall.get("dominant_state") in ["oversold", "overbought"]:
            signals["alerts"].append({
                "type": "potential_reversal",
                "severity": "medium",
                "message": f"Sentiment in {overall['dominant_state']} territory - watch for reversal"
            })
        
        return signals


# ============================================================
# API Functions
# ============================================================
def analyze_sentiment_momentum(df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function for sentiment momentum analysis"""
    try:
        if df is None:
            df = load_features_data()
        
        analyzer = SentimentMomentumAnalyzer()
        results = analyzer.analyze(df)
        
        return {
            "status": "success",
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Sentiment momentum analysis API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def get_sentiment_signals(df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function to get sentiment signals"""
    try:
        if df is None:
            df = load_features_data()
        
        analyzer = SentimentMomentumAnalyzer()
        signals = analyzer.get_sentiment_signals(df)
        
        return {
            "status": "success",
            "signals": signals,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Sentiment signals API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("Sentiment Momentum Analyzer - Standalone Test Run")
    log_event("=" * 60)
    
    # Load data
    df = load_features_data()
    print(f"\n📊 Loaded {len(df)} rows of data")
    
    # Initialize analyzer
    analyzer = SentimentMomentumAnalyzer()
    
    # Run analysis
    print("\n🔄 Running sentiment momentum analysis...")
    results = analyzer.analyze(df)
    
    # Display results
    print("\n📈 Feature Analysis:")
    for feature, data in results.get("features", {}).items():
        print(f"\n   {feature}:")
        print(f"      Value: {data.get('current_value', 0):.4f}")
        print(f"      State: {data.get('state', 'unknown')}")
        
        ind = data.get("indicators", {})
        print(f"      RSI: {ind.get('rsi', {}).get('value', 50):.1f} ({ind.get('rsi', {}).get('status', 'N/A')})")
        print(f"      MACD: {ind.get('macd', {}).get('line', 0):.4f}")
        
        pred = data.get("prediction", {})
        print(f"      Prediction: {pred.get('direction', 'unknown')} (confidence: {pred.get('confidence', 0):.2f})")
    
    # Overall analysis
    overall = results.get("overall", {})
    print(f"\n🎯 Overall Analysis:")
    print(f"   Average Sentiment: {overall.get('average_sentiment', 0):.4f}")
    print(f"   Dominant State: {overall.get('dominant_state', 'unknown')}")
    print(f"   Direction: {overall.get('direction', 'unknown')}")
    print(f"   Confidence: {overall.get('confidence', 0):.2f}")
    
    # Test signals
    print("\n📡 Testing signals...")
    signals = analyzer.get_sentiment_signals(df)
    print(f"   Signals: {len(signals.get('signals', []))}")
    print(f"   Alerts: {len(signals.get('alerts', []))}")
    
    # Test API
    print("\n🌐 Testing API function...")
    api_result = analyze_sentiment_momentum()
    print(f"   Status: {api_result.get('status')}")
    
    log_event("✅ Sentiment momentum analyzer test completed")
