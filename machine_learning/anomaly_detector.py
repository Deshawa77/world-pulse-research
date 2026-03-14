# -*- coding: utf-8 -*-
"""
Autoencoder-based Anomaly Detection
===================================
Detects anomalies in global risk features using reconstruction error
from trained autoencoder neural networks.

Features:
- Train on "normal" pattern data
- Detect anomalies via reconstruction error threshold
- Early warning signals
- Real-time anomaly scoring

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

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "anomaly_detector.log")

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
    line = f"[ANOMALY] {ts} | {text_msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_line = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {text_msg}\n")



# ============================================================
# TensorFlow/Keras Imports with Fallback
# ============================================================
USE_TENSORFLOW = False
keras = None

try:
    from tensorflow import keras
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import Dense, Input, Dropout, BatchNormalization
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import EarlyStopping
    
    USE_TENSORFLOW = True
    log_event("✅ TensorFlow loaded for anomaly detection")
except ImportError as e:
    log_event(f"⚠️ TensorFlow not available: {e}")
    log_event("📝 Using statistical anomaly detection fallback")


# ============================================================
# Configuration
# ============================================================
MODEL_DIR = "./models"
os.makedirs(MODEL_DIR, exist_ok=True)

DATA_DIR = "./data"
FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# Feature columns
FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment", 
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

# Anomaly detection parameters
ANOMALY_THRESHOLD_PERCENTILE = 95  # Top 5% reconstruction errors are anomalies
CONTAMINATION = 0.05  # Expected proportion of anomalies in training data

# Model paths
AUTOENCODER_MODEL_PATH = os.path.join(MODEL_DIR, "anomaly_autoencoder.keras")
SCALER_PATH = os.path.join(MODEL_DIR, "anomaly_scaler.pkl")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "anomaly_threshold.pkl")


# ============================================================
# Data Loading
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
    """Create sample data for testing"""
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
    return df


def normalize_features(data: np.ndarray) -> Tuple[np.ndarray, Any, Any]:
    """Normalize features using StandardScaler"""
    from sklearn.preprocessing import StandardScaler
    
    scaler = StandardScaler()
    normalized = scaler.fit_transform(data)
    
    return normalized, scaler


# ============================================================
# Autoencoder Model
# ============================================================
def build_autoencoder(input_dim: int, encoding_dim: int = 32) -> keras.Model:
    """
    Build a sparse autoencoder for anomaly detection
    
    Args:
        input_dim: Number of input features
        encoding_dim: Size of the bottleneck layer
        
    Returns:
        Compiled autoencoder model
    """
    # Encoder
    encoder_input = Input(shape=(input_dim,), name='encoder_input')
    x = Dense(64, activation='relu', name='encoder_dense1')(encoder_input)
    x = BatchNormalization(name='encoder_bn1')(x)
    x = Dropout(0.2)(x)
    x = Dense(32, activation='relu', name='encoder_dense2')(x)
    x = BatchNormalization(name='encoder_bn2')(x)
    encoded = Dense(encoding_dim, activation='relu', name='encoder_output')(x)
    
    # Decoder
    x = Dense(32, activation='relu', name='decoder_dense1')(encoded)
    x = BatchNormalization(name='decoder_bn1')(x)
    x = Dropout(0.2)(x)
    x = Dense(64, activation='relu', name='decoder_dense2')(x)
    x = BatchNormalization(name='decoder_bn2')(x)
    decoded = Dense(input_dim, activation='linear', name='decoder_output')(x)
    
    # Autoencoder
    autoencoder = Model(encoder_input, decoded, name='autoencoder')
    autoencoder.compile(
        optimizer=Adam(learning_rate=0.001),
        loss='mse',
        metrics=['mae']
    )
    
    return autoencoder


# ============================================================
# Statistical Anomaly Detection Fallback
# ============================================================
class StatisticalAnomalyDetector:
    """Statistical fallback for anomaly detection when DL not available"""
    
    def __init__(self):
        self.feature_means = None
        self.feature_stds = None
        self.feature_ranges = None
        self.correlation_matrix = None
        self.threshold = None
        
    def fit(self, df: pd.DataFrame):
        """Fit statistical model on normal data"""
        feature_data = df[FEATURE_COLUMNS].values
        
        self.feature_means = np.mean(feature_data, axis=0)
        self.feature_stds = np.std(feature_data, axis=0) + 1e-9
        self.feature_ranges = np.max(feature_data, axis=0) - np.min(feature_data, axis=0)
        
        # Compute correlation matrix for Mahalanobis-like distance
        self.correlation_matrix = np.cov(feature_data.T)
        
        # Compute reconstruction error threshold
        # Using average Euclidean distance from mean as baseline
        normalized = (feature_data - self.feature_means) / self.feature_stds
        baseline_errors = np.sqrt(np.sum(normalized ** 2, axis=1))
        self.threshold = np.percentile(baseline_errors, ANOMALY_THRESHOLD_PERCENTILE)
        
        log_event(f"✅ Statistical detector fitted. Threshold: {self.threshold:.4f}")
        
    def predict(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Predict anomalies in the data"""
        feature_data = df[FEATURE_COLUMNS].values
        
        # Normalize
        normalized = (feature_data - self.feature_means) / self.feature_stds
        
        # Compute reconstruction error (distance from "normal" center)
        reconstruction_errors = np.sqrt(np.sum(normalized ** 2, axis=1))
        
        # Determine anomalies
        is_anomaly = reconstruction_errors > self.threshold
        
        # Compute anomaly scores (0-1, higher = more anomalous)
        scores = reconstruction_errors / self.threshold
        scores = np.clip(scores, 0, 10)  # Cap at 10
        
        # Find which features are most anomalous
        feature_contributions = np.abs(normalized) / (np.abs(normalized).sum(axis=1, keepdims=True) + 1e-9)
        
        results = {
            "reconstruction_errors": reconstruction_errors.tolist(),
            "anomaly_scores": scores.tolist(),
            "is_anomaly": is_anomaly.tolist(),
            "threshold": float(self.threshold),
            "anomaly_indices": np.where(is_anomaly)[0].tolist(),
            "feature_contributions": feature_contributions.tolist() if len(feature_contributions) > 0 else []
        }
        
        return results


# ============================================================
# Main Anomaly Detector Class
# ============================================================
class AnomalyDetector:
    """
    Autoencoder-based Anomaly Detection for Crisis Early Warning
    
    Features:
    - Trains on normal patterns
    - Uses reconstruction error to detect anomalies
    - Provides feature-level attribution
    - Generates early warning signals
    """
    
    def __init__(self):
        self.autoencoder = None
        self.scaler = None
        self.threshold = None
        self.statistical_detector = StatisticalAnomalyDetector()
        self.is_trained = False
        self.training_history = None
        
    def train(self, df: pd.DataFrame, force_retrain: bool = False) -> Dict[str, Any]:
        """
        Train anomaly detector on normal patterns
        
        Args:
            df: DataFrame with historical features
            force_retrain: Whether to retrain even if model exists
            
        Returns:
            Training results and metrics
        """
        log_event("🚀 Starting anomaly detection training...")
        
        # Prepare data
        feature_data = df[FEATURE_COLUMNS].values
        
        # Fit scaler
        normalized_data, scaler = normalize_features(feature_data)
        self.scaler = scaler
        
        # Fit statistical detector (always)
        self.statistical_detector.fit(df)
        
        if not USE_TENSORFLOW:
            log_event("📝 Using statistical anomaly detection")
            self.is_trained = True
            return {"status": "statistical", "message": "TensorFlow not available"}
        
        # Check if we should load existing model
        if os.path.exists(AUTOENCODER_MODEL_PATH) and not force_retrain:
            try:
                self.autoencoder = keras.models.load_model(AUTOENCODER_MODEL_PATH)
                self.threshold = joblib.load(THRESHOLD_PATH)
                log_event("✅ Loaded existing autoencoder model")
                self.is_trained = True
                return {"status": "loaded", "message": "Loaded existing model"}
            except Exception as e:
                log_event(f"⚠️ Failed to load model: {e}")
        
        log_event("🔄 Training new autoencoder model...")
        
        try:
            # Train autoencoder
            self.autoencoder = build_autoencoder(
                input_dim=len(FEATURE_COLUMNS),
                encoding_dim=32
            )
            
            # Callbacks
            callbacks = [
                EarlyStopping(
                    monitor='val_loss',
                    patience=15,
                    restore_best_weights=True,
                    verbose=0
                )
            ]
            
            # Split data
            val_size = int(len(normalized_data) * 0.2)
            X_train = normalized_data[:-val_size]
            X_val = normalized_data[-val_size:]
            
            # Train
            self.training_history = self.autoencoder.fit(
                X_train, X_train,
                validation_data=(X_val, X_val),
                epochs=100,
                batch_size=32,
                callbacks=callbacks,
                verbose=0
            )
            
            # Compute reconstruction errors on training data
            reconstructions = self.autoencoder.predict(normalized_data, verbose=0)
            mse = np.mean(np.power(normalized_data - reconstructions, 2), axis=1)
            
            # Set threshold at percentile
            self.threshold = np.percentile(mse, ANOMALY_THRESHOLD_PERCENTILE)
            
            # Save model and artifacts
            self.autoencoder.save(AUTOENCODER_MODEL_PATH)
            joblib.dump(scaler, SCALER_PATH)
            joblib.dump(self.threshold, THRESHOLD_PATH)
            
            self.is_trained = True
            
            log_event(f"✅ Autoencoder trained. Threshold: {self.threshold:.6f}")
            
            return {
                "status": "trained",
                "threshold": float(self.threshold),
                "epochs": len(self.training_history.history['loss']),
                "final_loss": float(self.training_history.history['loss'][-1])
            }
            
        except Exception as e:
            log_event(f"❌ Autoencoder training failed: {e}")
            traceback.print_exc()
            return {"status": "failed", "error": str(e)}
    
    def detect_anomalies(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect anomalies in the given data
        
        Args:
            df: DataFrame with feature data
            
        Returns:
            Dictionary with anomaly detection results
        """
        if df.empty or len(df) == 0:
            return {"error": "No data provided", "status": "error"}
        
        feature_data = df[FEATURE_COLUMNS].values
        
        # Use autoencoder if available
        if USE_TENSORFLOW and self.autoencoder is not None:
            try:
                # Normalize
                normalized = self.scaler.transform(feature_data)
                
                # Reconstruct
                reconstructions = self.autoencoder.predict(normalized, verbose=0)
                
                # Compute MSE for each sample
                mse = np.mean(np.power(normalized - reconstructions, 2), axis=1)
                
                # Determine anomalies
                is_anomaly = mse > self.threshold
                
                # Compute scores
                scores = mse / self.threshold
                scores = np.clip(scores, 0, 10)
                
                # Feature attribution (which features contributed most)
                feature_contributions = np.abs(normalized - reconstructions)
                feature_contributions = feature_contributions / (feature_contributions.sum(axis=1, keepdims=True) + 1e-9)
                
                results = {
                    "model": "autoencoder",
                    "reconstruction_errors": mse.tolist(),
                    "anomaly_scores": scores.tolist(),
                    "is_anomaly": is_anomaly.tolist(),
                    "threshold": float(self.threshold),
                    "anomaly_indices": np.where(is_anomaly)[0].tolist(),
                    "feature_contributions": feature_contributions.tolist()
                }
                
            except Exception as e:
                log_event(f"⚠️ Autoencoder detection failed: {e}")
                results = self.statistical_detector.predict(df)
                results["model"] = "statistical_fallback"
        else:
            # Use statistical detector
            results = self.statistical_detector.predict(df)
            results["model"] = "statistical"
        
        # Add metadata
        results["n_samples"] = len(df)
        results["n_anomalies"] = int(np.sum(results["is_anomaly"]))
        results["anomaly_rate"] = float(np.mean(results["is_anomaly"]))
        results["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        return results
    
    def get_early_warnings(self, df: pd.DataFrame, window_size: int = 24) -> Dict[str, Any]:
        """
        Analyze recent data for early warning signals
        
        Args:
            df: DataFrame with recent features
            window_size: Window for trend analysis
            
        Returns:
            Early warning signals
        """
        if len(df) < window_size:
            return {"status": "insufficient_data", "message": f"Need at least {window_size} samples"}
        
        # Get recent window
        recent_df = df.tail(window_size)
        
        # Detect anomalies in recent window
        anomaly_results = self.detect_anomalies(recent_df)
        
        warnings = {
            "status": "analyzed",
            "window_size": window_size,
            "anomalies_detected": anomaly_results.get("n_anomalies", 0),
            "anomaly_rate": anomaly_results.get("anomaly_rate", 0),
            "warnings": []
        }
        
        # Generate warnings based on patterns
        if anomaly_results.get("anomaly_rate", 0) > 0.1:
            warnings["warnings"].append({
                "type": "high_anomaly_rate",
                "severity": "high",
                "message": f"High anomaly rate: {anomaly_results['anomaly_rate']:.1%}"
            })
        
        # Check for increasing trend in anomaly scores
        scores = anomaly_results.get("anomaly_scores", [])
        if len(scores) > 6:
            recent_avg = np.mean(scores[-3:])
            earlier_avg = np.mean(scores[-6:-3])
            if recent_avg > earlier_avg * 1.5:
                warnings["warnings"].append({
                    "type": "increasing_anomaly_scores",
                    "severity": "medium",
                    "message": "Anomaly scores are increasing rapidly"
                })
        
        # Check specific features
        for i, col in enumerate(FEATURE_COLUMNS):
            if col in recent_df.columns:
                recent_val = recent_df[col].iloc[-1]
                mean_val = recent_df[col].mean()
                std_val = recent_df[col].std()
                
                if std_val > 0 and abs(recent_val - mean_val) > 3 * std_val:
                    warnings["warnings"].append({
                        "type": "feature_outlier",
                        "severity": "medium",
                        "feature": col,
                        "message": f"{col} is {abs((recent_val - mean_val) / std_val):.1f} std deviations from mean"
                    })
        
        warnings["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        return warnings
    
    def get_feature_importance(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Get feature importance for anomalies
        
        Returns:
            Dictionary of feature names and their importance scores
        """
        anomaly_results = self.detect_anomalies(df)
        
        if "feature_contributions" not in anomaly_results or not anomaly_results["feature_contributions"]:
            return {col: 0.0 for col in FEATURE_COLUMNS}
        
        # Average contribution across all samples
        contributions = np.array(annomaly_results["feature_contributions"])
        avg_contribution = np.mean(contributions, axis=0)
        
        importance = {col: float(score) for col, score in zip(FEATURE_COLUMNS, avg_contribution)}
        
        return importance


# ============================================================
# API Functions
# ============================================================
def detect_anomalies_api(df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function to detect anomalies"""
    try:
        if df is None:
            df = load_features_data()
        
        detector = AnomalyDetector()
        detector.train(df, force_retrain=False)
        
        results = detector.detect_anomalies(df)
        
        return {
            "status": "success",
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Anomaly detection API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def get_early_warnings_api(df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function to get early warnings"""
    try:
        if df is None:
            df = load_features_data()
        
        detector = AnomalyDetector()
        detector.train(df, force_retrain=False)
        
        warnings = detector.get_early_warnings(df)
        
        return {
            "status": "success",
            "warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Early warnings API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("Anomaly Detector - Standalone Test Run")
    log_event("=" * 60)
    
    # Load data
    df = load_features_data()
    print(f"\n📊 Loaded {len(df)} rows of data")
    
    # Initialize and train
    detector = AnomalyDetector()
    
    print("\n🔄 Training anomaly detector...")
    train_results = detector.train(df, force_retrain=True)
    print(f"   Results: {train_results}")
    
    # Test detection
    print("\n🔍 Testing anomaly detection...")
    results = detector.detect_anomalies(df)
    print(f"   Anomalies found: {results.get('n_anomalies', 0)} / {results.get('n_samples', 0)}")
    print(f"   Anomaly rate: {results.get('anomaly_rate', 0):.2%}")
    
    # Test early warnings
    print("\n⚠️ Testing early warnings...")
    warnings = detector.get_early_warnings(df)
    print(f"   Warnings: {warnings.get('warnings', [])}")
    
    # Feature importance
    print("\n📈 Feature importance for anomalies...")
    importance = detector.get_feature_importance(df)
    for feat, score in sorted(importance.items(), key=lambda x: -x[1]):
        print(f"   {feat}: {score:.4f}")
    
    log_event("✅ Anomaly detector test completed")
