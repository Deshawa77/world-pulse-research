# daily_crisis_predictor.py
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import classification_report
import joblib
import os

# ============================
# Paths
# ============================
DATA_PATH = "../data/daily_features.csv"
MODEL_DIR = "../models"
os.makedirs(MODEL_DIR, exist_ok=True)

# ============================
# Main ML Pipeline
# ============================

def run_crisis_model():
    print("\n🚀 Starting Phase 3 — Global Crisis ML Engine\n")

    # --- Load dataset ---
    df = pd.read_csv(DATA_PATH)

    # --- Create crisis target ---
    df["crisis"] = (df["global_risk_score"] > 70).astype(int)

    # --- Features ---
    features = [
        "news_sentiment", "gdelt_sentiment",
        "crypto_return", "crypto_volatility",
        "stock_return", "stock_volatility",
        "weather_anomaly"
    ]

    X = df[features]
    y = df["crisis"]

    # --- Train/Test split (chronological) ---
    train_size = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]

    # ============================
    # Logistic Regression
    # ============================
    print("=== Logistic Regression ===")
    lr_model = LogisticRegression(max_iter=2000)
    lr_model.fit(X_train, y_train)
    y_pred_lr = lr_model.predict(X_test)
    print(classification_report(y_test, y_pred_lr))
    joblib.dump(lr_model, os.path.join(MODEL_DIR, "logistic_model.pkl"))

    # ============================
    # Random Forest
    # ============================
    print("=== Random Forest ===")
    rf_model = RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        random_state=7
    )
    rf_model.fit(X_train, y_train)
    y_pred_rf = rf_model.predict(X_test)
    print(classification_report(y_test, y_pred_rf))
    joblib.dump(rf_model, os.path.join(MODEL_DIR, "rf_model.pkl"))

    # ============================
    # Gradient Boosting
    # ============================
    print("=== Gradient Boosting ===")
    gb_model = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        random_state=7
    )
    gb_model.fit(X_train, y_train)
    y_pred_gb = gb_model.predict(X_test)
    print(classification_report(y_test, y_pred_gb))
    joblib.dump(gb_model, os.path.join(MODEL_DIR, "gb_model.pkl"))

    # ============================
    # Latest prediction
    # ============================
    latest_features = X.iloc[-1].values.reshape(1, -1)
    latest_prob = gb_model.predict_proba(latest_features)[0, 1]

    print("\n============================")
    print("🌍 LIVE GLOBAL CRISIS FORECAST")
    print("============================")
    print(f"Predicted crisis probability: {latest_prob:.3f}")
    
    if latest_prob > 0.7:
        print("🔴 STATUS: HIGH RISK")
    elif latest_prob > 0.4:
        print("🟠 STATUS: MODERATE RISK")
    else:
        print("🟢 STATUS: LOW RISK")

    print("\n✅ Phase 3 ML pipeline complete.")
    print(f"📦 Models saved in: {MODEL_DIR}")

# ============================
# Entry point
# ============================

if __name__ == "__main__":
    run_crisis_model()
