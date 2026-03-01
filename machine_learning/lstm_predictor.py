# -*- coding: utf-8 -*-
"""
LSTM-based Multi-Step Ahead Crisis Forecasting
================================================
Predictive Analytics Engine using Long Short-Term Memory networks
for multi-step ahead crisis prediction (1h, 6h, 24h, 7d)

Features:
- Sequence-to-sequence modeling
- Multi-horizon forecasting
- Ensemble with existing models
- Early warning signals

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
import joblib
import hashlib

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "lstm_predictor.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg: str):
    """Log event with timestamp"""
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[LSTM] {ts} | {msg}", flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")


# ============================================================
# TensorFlow/Keras Imports with Fallback
# ============================================================
USE_TENSORFLOW = False
tf = None
keras = None
Sequential = None
LSTM = None
Dense = None
Dropout = None
Input = None
Model = None
EarlyStopping = None
ReduceLROnPlateau = None

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, Bidirectional, Attention, MultiHeadAttention
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    from tensorflow.keras.optimizers import Adam
    
    USE_TENSORFLOW = True
    log_event("✅ TensorFlow loaded successfully")
except ImportError as e:
    log_event(f"⚠️ TensorFlow not available: {e}")
    log_event("📝 Using statistical fallback for LSTM predictions")


# ============================================================
# Configuration
# ============================================================
MODEL_DIR = "./models"
os.makedirs(MODEL_DIR, exist_ok=True)

DATA_DIR = "./data"
FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# Feature columns (same as existing system)
FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment", 
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

# Prediction horizons
PREDICTION_HORIZONS = {
    "1h": 1,
    "6h": 6,
    "24h": 24,
    "7d": 168  # 7 days * 24 hours
}

# Model hyperparameters
SEQUENCE_LENGTH = 24  # Use 24 hours of history
BATCH_SIZE = 32
EPOCHS = 100
LEARNING_RATE = 0.001

# Threshold for early warning
CRISIS_THRESHOLD_HIGH = 0.75
CRISIS_THRESHOLD_MED = 0.40


# ============================================================
# Data Loading & Preprocessing
# ============================================================
def load_features_from_mongodb(limit=500, mode="online") -> pd.DataFrame:
    """Load features from MongoDB global_features collection."""
    try:
        from database.mongo import get_historical_global_features
        docs = get_historical_global_features(limit=limit, mode=mode)
        if not docs or len(docs) == 0:
            return None
        rows = []
        for doc in docs:
            features = doc.get("features", {})
            if not features:
                features = {k: doc.get(k) for k in FEATURE_COLUMNS}
            row = {
                "timestamp": doc.get("timestamp"),
                "news_sentiment": features.get("news_sentiment"),
                "gdelt_sentiment": features.get("gdelt_sentiment"),
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
    except Exception as e:
        log_event(f"⚠️ MongoDB error: {e}")
        return None

def load_features_data() -> pd.DataFrame:
    """Load hourly features - prefers MongoDB, falls back to CSV"""
    # Try MongoDB first
    df = load_features_from_mongodb(limit=500, mode="online")
    if df is not None and len(df) > 10:
        return df
    # Try offline mode
    df = load_features_from_mongodb(limit=500, mode="offline")
    if df is not None and len(df) > 10:
        return df
    # Fallback to CSV
    log_event("⚠️ Falling back to CSV")
    if not os.path.exists(FEATURES_CSV):
        log_event(f"❌ Features file not found: {FEATURES_CSV}")
        return create_sample_data()
    
    df = pd.read_csv(FEATURES_CSV)
    
    # Find timestamp column
    time_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        df.rename(columns={time_cols[0]: "timestamp"}, inplace=True)
    
    # Fill missing values
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(method='ffill').fillna(0)
    
    log_event(f"✅ Loaded {len(df)} rows from CSV")
    return df


def create_sample_data() -> pd.DataFrame:
    """Create sample data for testing when no data available"""
    np.random.seed(42)
    n_samples = 200
    
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
    
    df = pd.DataFrame(data)
    
    # Add some realistic correlations
    df["global_risk_score"] = (
        -df["news_sentiment"] * 20 +
        -df["gdelt_sentiment"] * 15 +
        df["crypto_volatility"] * 50 +
        df["stock_volatility"] * 30 +
        df["weather_anomaly"] * 20 +
        50 + np.random.randn(n_samples) * 5
    )
    df["global_risk_score"] = df["global_risk_score"].clip(0, 100)
    
    return df


def normalize_data(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """Normalize feature data using min-max scaling"""
    feature_data = df[FEATURE_COLUMNS].values
    
    # Handle NaN/Inf
    feature_data = np.nan_to_num(feature_data, nan=0.0, posinf=1.0, neginf=-1.0)
    
    # Min-max normalization
    min_val = feature_data.min(axis=0)
    max_val = feature_data.max(axis=0)
    max_val = np.where(max_val == min_val, 1.0, max_val)  # Avoid division by zero
    
    normalized = (feature_data - min_val) / (max_val - min_val)
    
    return normalized, min_val, max_val


def create_sequences(data: np.ndarray, seq_length: int, pred_length: int) -> Tuple[np.ndarray, np.ndarray]:
    """Create input sequences and target sequences for training"""
    X, y = [], []
    
    for i in range(len(data) - seq_length - pred_length + 1):
        X.append(data[i:i + seq_length])
        # Target is the first feature (news_sentiment) at pred_length steps ahead
        # Or we can predict the global_risk_score if available
        y.append(data[i + seq_length:i + seq_length + pred_length, 0])  # Predicting first feature
    
    return np.array(X), np.array(y)


# ============================================================
# LSTM Model Architecture
# ============================================================
def build_lstm_model(seq_length: int, pred_length: int, n_features: int = 7) -> keras.Model:
    """Build LSTM model for multi-step prediction"""
    
    if not USE_TENSORFLOW:
        raise RuntimeError("TensorFlow is not available")
    
    model = Sequential([
        # Input layer
        Input(shape=(seq_length, n_features)),
        
        # First LSTM layer with dropout
        LSTM(128, return_sequences=True),
        Dropout(0.2),
        
        # Second LSTM layer
        LSTM(64, return_sequences=False),
        Dropout(0.2),
        
        # Dense layers
        Dense(64, activation='relu'),
        Dropout(0.1),
        Dense(32, activation='relu'),
        
        # Output layer for multi-step prediction
        Dense(pred_length, activation='linear')
    ])
    
    model.compile(
        optimizer=Adam(learning_rate=LEARNING_RATE),
        loss='mse',
        metrics=['mae']
    )
    
    return model


def build_bilstm_model(seq_length: int, pred_length: int, n_features: int = 7) -> keras.Model:
    """Build Bidirectional LSTM model for better sequence understanding"""
    
    if not USE_TENSORFLOW:
        raise RuntimeError("TensorFlow is not available")
    
    model = Sequential([
        Input(shape=(seq_length, n_features)),
        
        # Bidirectional LSTM
        Bidirectional(LSTM(64, return_sequences=True)),
        Dropout(0.2),
        
        Bidirectional(LSTM(32, return_sequences=False)),
        Dropout(0.2),
        
        Dense(32, activation='relu'),
        Dropout(0.1),
        Dense(16, activation='relu'),
        
        Dense(pred_length, activation='linear')
    ])
    
    model.compile(
        optimizer=Adam(learning_rate=LEARNING_RATE),
        loss='mse',
        metrics=['mae']
    )
    
    return model


# ============================================================
# Statistical Fallback (when TensorFlow not available)
# ============================================================
class StatisticalForecaster:
    """Statistical fallback for multi-step forecasting when DL not available"""
    
    def __init__(self):
        self.history = None
        self.feature_means = None
        self.feature_stds = None
        self.trends = {}
        
    def fit(self, df: pd.DataFrame):
        """Fit statistical models on historical data"""
        self.history = df[FEATURE_COLUMNS].values
        self.feature_means = np.mean(self.history, axis=0)
        self.feature_stds = np.std(self.history, axis=0) + 1e-9
        
        # Calculate simple linear trends for each feature
        for i, col in enumerate(FEATURE_COLUMNS):
            y = self.history[:, i]
            x = np.arange(len(y))
            slope, intercept = np.polyfit(x, y, 1)
            self.trends[col] = {"slope": slope, "intercept": intercept}
        
        log_event("✅ Statistical forecaster fitted")
        
    def predict(self, horizon: int) -> Dict[str, np.ndarray]:
        """Predict features for next N hours"""
        predictions = {}
        
        last_values = self.history[-1] if self.history is not None else self.feature_means
        
        for i, col in enumerate(FEATURE_COLUMNS):
            # Use trend extrapolation with dampening
            future_x = len(self.history) + np.arange(horizon)
            trend = self.trends.get(col, {"slope": 0, "intercept": self.feature_means[i]})
            
            # Dampened trend
            dampen = np.array([0.9 ** (i+1) for i in range(horizon)])
            trend_component = trend["slope"] * future_x * dampen
            
            # Mean reversion component
            mean_reversion = (self.feature_means[i] - last_values[i]) * 0.1 * np.arange(1, horizon + 1)
            
            # Combine
            pred = last_values[i] + trend_component + mean_reversion
            predictions[col] = pred
            
        return predictions


# ============================================================
# Main LSTM Predictor Class
# ============================================================
class LSTMPredictor:
    """
    LSTM-based Multi-Step Ahead Crisis Forecaster
    
    Supports:
    - 1-hour ahead prediction
    - 6-hour ahead prediction  
    - 24-hour ahead prediction
    - 7-day ahead prediction
    
    Integrates with existing ML ensemble
    """
    
    def __init__(self, use_bilstm: bool = True):
        self.use_bilstm = use_bilstm
        self.models = {}
        self.scalers = {"min": None, "max": None}
        self.statistical_fallback = StatisticalForecaster()
        self.is_trained = False
        
        # Model paths
        self.model_paths = {
            horizon: os.path.join(MODEL_DIR, f"lstm_model_{horizon}.keras")
            for horizon in PREDICTION_HORIZONS.keys()
        }
        
    def train(self, df: pd.DataFrame, force_retrain: bool = False) -> Dict[str, Any]:
        """
        Train LSTM models for all prediction horizons
        
        Args:
            df: DataFrame with historical features
            force_retrain: Whether to retrain even if models exist
            
        Returns:
            Training history and metrics
        """
        log_event("🚀 Starting LSTM model training...")
        
        # Prepare data
        normalized_data, min_vals, max_vals = normalize_data(df)
        self.scalers = {"min": min_vals, "max": max_vals}
        
        # Fit statistical fallback
        self.statistical_fallback.fit(df)
        
        if not USE_TENSORFLOW:
            log_event("📝 Using statistical fallback - LSTM training skipped")
            return {"status": "statistical_fallback", "message": "TensorFlow not available"}
        
        training_results = {}
        
        for horizon_name, horizon_steps in PREDICTION_HORIZONS.items():
            model_path = self.model_paths[horizon_name]
            
            # Check if model exists and we shouldn't force retrain
            if os.path.exists(model_path) and not force_retrain:
                try:
                    self.models[horizon_name] = keras.models.load_model(model_path)
                    log_event(f"✅ Loaded existing model for {horizon_name}")
                    continue
                except Exception as e:
                    log_event(f"⚠️ Failed to load model {horizon_name}: {e}")
            
            log_event(f"🔄 Training model for {horizon_name} ({horizon_steps} steps ahead)...")
            
            try:
                # Create sequences
                X, y = create_sequences(normalized_data, SEQUENCE_LENGTH, horizon_steps)
                
                if len(X) < 10:
                    log_event(f"⚠️ Not enough data for {horizon_name} training")
                    continue
                
                # Train/validation split
                val_size = int(len(X) * 0.2)
                X_train, X_val = X[:-val_size], X[-val_size:]
                y_train, y_val = y[:-val_size], y[-val_size:]
                
                # Build model
                if self.use_bilstm:
                    model = build_bilstm_model(SEQUENCE_LENGTH, horizon_steps)
                else:
                    model = build_lstm_model(SEQUENCE_LENGTH, horizon_steps)
                
                # Callbacks
                callbacks = [
                    EarlyStopping(
                        monitor='val_loss',
                        patience=10,
                        restore_best_weights=True,
                        verbose=0
                    ),
                    ReduceLROnPlateau(
                        monitor='val_loss',
                        factor=0.5,
                        patience=5,
                        min_lr=1e-6,
                        verbose=0
                    )
                ]
                
                # Train
                history = model.fit(
                    X_train, y_train,
                    validation_data=(X_val, y_val),
                    epochs=EPOCHS,
                    batch_size=BATCH_SIZE,
                    callbacks=callbacks,
                    verbose=0
                )
                
                # Save model
                model.save(model_path)
                self.models[horizon_name] = model
                
                training_results[horizon_name] = {
                    "epochs": len(history.history['loss']),
                    "final_loss": float(history.history['loss'][-1]),
                    "final_val_loss": float(history.history['val_loss'][-1]),
                    "status": "trained"
                }
                
                log_event(f"✅ Model trained for {horizon_name}: "
                         f"loss={history.history['loss'][-1]:.4f}, "
                         f"val_loss={history.history['val_loss'][-1]:.4f}")
                
            except Exception as e:
                log_event(f"❌ Training failed for {horizon_name}: {e}")
                training_results[horizon_name] = {"status": "failed", "error": str(e)}
        
        self.is_trained = len(self.models) > 0
        return training_results
    
    def predict(self, df: pd.DataFrame, horizon: str = "24h") -> Dict[str, Any]:
        """
        Make multi-step ahead predictions
        
        Args:
            df: DataFrame with recent features (at least SEQUENCE_LENGTH rows)
            horizon: Prediction horizon ("1h", "6h", "24h", "7d")
            
        Returns:
            Predictions for each feature at the specified horizon
        """
        if horizon not in PREDICTION_HORIZONS:
            raise ValueError(f"Invalid horizon: {horizon}. Choose from {list(PREDICTION_HORIZONS.keys())}")
        
        horizon_steps = PREDICTION_HORIZONS[horizon]
        
        # Use LSTM model if available
        if USE_TENSORFLOW and horizon in self.models:
            try:
                # Prepare latest sequence
                normalized_data, _, _ = normalize_data(df)
                last_sequence = normalized_data[-SEQUENCE_LENGTH:].reshape(1, SEQUENCE_LENGTH, -1)
                
                # Predict
                predictions = self.models[horizon].predict(last_sequence, verbose=0)
                
                # Denormalize
                # Note: We're predicting the first feature (news_sentiment)
                # For full feature prediction, we'd need separate models
                
                return {
                    "horizon": horizon,
                    "steps": horizon_steps,
                    "predictions": predictions[0].tolist(),
                    "model": "lstm",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            except Exception as e:
                log_event(f"⚠️ LSTM prediction failed: {e}")
        
        # Fallback to statistical
        log_event("📝 Using statistical fallback for prediction")
        stat_predictions = self.statistical_fallback.predict(horizon_steps)
        
        return {
            "horizon": horizon,
            "steps": horizon_steps,
            "predictions": stat_predictions,
            "model": "statistical",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def predict_all_horizons(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Predict for all available horizons"""
        results = {}
        
        for horizon in PREDICTION_HORIZONS.keys():
            try:
                results[horizon] = self.predict(df, horizon)
            except Exception as e:
                log_event(f"❌ Prediction failed for {horizon}: {e}")
                results[horizon] = {"error": str(e)}
        
        return results
    
    def compute_risk_score(self, predictions: Dict[str, np.ndarray]) -> float:
        """
        Compute crisis risk score from predicted features
        
        Uses weighted combination of feature predictions
        Similar to existing ensemble logic
        """
        weights = {
            "news_sentiment": -0.25,
            "gdelt_sentiment": -0.20,
            "crypto_return": 0.10,
            "crypto_volatility": 0.15,
            "stock_return": -0.10,
            "stock_volatility": 0.10,
            "weather_anomaly": 0.10
        }
        
        risk_score = 50.0  # Base score
        
        for feature, weight in weights.items():
            if feature in predictions:
                # Use the last predicted value
                pred_value = predictions[feature][-1] if isinstance(predictions[feature], np.ndarray) else predictions[feature]
                risk_score += weight * pred_value * 100
        
        return max(0, min(100, risk_score))
    
    def get_early_warning_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze historical data for early warning signals
        
        Returns:
            Dictionary with warning indicators
        """
        if len(df) < 10:
            return {"status": "insufficient_data"}
        
        signals = {
            "trend_direction": {},
            "momentum": {},
            "volatility": {},
            "warnings": []
        }
        
        for col in FEATURE_COLUMNS:
            if col not in df.columns:
                continue
                
            values = df[col].values
            
            # Trend (simple linear regression)
            x = np.arange(len(values))
            slope, _ = np.polyfit(x, values, 1)
            signals["trend_direction"][col] = "increasing" if slope > 0 else "decreasing"
            
            # Momentum (rate of change)
            if len(values) > 1:
                roc = (values[-1] - values[-min(6, len(values))]) / (min(6, len(values)) - 1)
                signals["momentum"][col] = float(roc)
            
            # Volatility
            signals["volatility"][col] = float(np.std(values))
        
        # Generate warnings based on signals
        if "news_sentiment" in df.columns:
            latest_sentiment = df["news_sentiment"].iloc[-1]
            if latest_sentiment < -0.5:
                signals["warnings"].append({
                    "type": "sentiment",
                    "severity": "high",
                    "message": "Significant negative sentiment detected"
                })
        
        if "crypto_volatility" in df.columns:
            latest_vol = df["crypto_volatility"].iloc[-1]
            if latest_vol > df["crypto_volatility"].mean() + 2 * df["crypto_volatility"].std():
                signals["warnings"].append({
                    "type": "volatility",
                    "severity": "medium",
                    "message": "Abnormal volatility detected in crypto markets"
                })
        
        return signals


# ============================================================
# API Endpoints Integration
# ============================================================
def get_lstm_predictions() -> Dict[str, Any]:
    """Get LSTM predictions for frontend API"""
    try:
        # Load latest data
        df = load_features_data()
        
        if df.empty:
            return {"error": "No data available", "status": "error"}
        
        # Initialize predictor
        predictor = LSTMPredictor()
        
        # Try to load existing models
        predictor.train(df, force_retrain=False)
        
        # Get predictions for all horizons
        predictions = predictor.predict_all_horizons(df)
        
        # Get early warning signals
        warnings = predictor.get_early_warning_signals(df)
        
        # Compute risk scores for each horizon
        risk_scores = {}
        for horizon, pred in predictions.items():
            if "predictions" in pred and isinstance(pred["predictions"], dict):
                risk_scores[horizon] = predictor.compute_risk_score(pred["predictions"])
        
        return {
            "status": "success",
            "predictions": predictions,
            "risk_scores": risk_scores,
            "early_warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Failed to get LSTM predictions: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def train_lstm_models(force: bool = False) -> Dict[str, Any]:
    """Train LSTM models (can be called periodically)"""
    try:
        df = load_features_data()
        
        if df.empty:
            return {"error": "No data for training", "status": "error"}
        
        predictor = LSTMPredictor()
        results = predictor.train(df, force_retrain=force)
        
        return {
            "status": "success",
            "training_results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ LSTM training failed: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("LSTM Predictor - Standalone Test Run")
    log_event("=" * 60)
    
    # Test data loading
    df = load_features_data()
    print(f"\n📊 Loaded {len(df)} rows of data")
    print(f"   Columns: {df.columns.tolist()}")
    
    # Initialize and train
    predictor = LSTMPredictor(use_bilstm=True)
    
    print("\n🔄 Training LSTM models...")
    train_results = predictor.train(df, force_retrain=True)
    print(f"   Training results: {train_results}")
    
    # Test predictions
    print("\n🔮 Testing predictions...")
    for horizon in ["1h", "6h", "24h", "7d"]:
        pred = predictor.predict(df, horizon)
        print(f"   {horizon}: {pred.get('model', 'unknown')} - {len(pred.get('predictions', []))} predictions")
    
    # Test early warnings
    print("\n⚠️ Testing early warning signals...")
    warnings = predictor.get_early_warning_signals(df)
    print(f"   Warnings: {warnings.get('warnings', [])}")
    
    # Test API function
    print("\n🌐 Testing API function...")
    api_result = get_lstm_predictions()
    print(f"   API Status: {api_result.get('status', 'unknown')}")
    
    log_event("✅ LSTM Predictor test completed")
