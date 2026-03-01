#!/usr/bin/env python3
"""Test script for advanced analytics module"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from machine_learning.advanced_analytics import run_advanced_analytics

def main():
    print("=" * 60)
    print("Testing Advanced Analytics Module")
    print("=" * 60)
    
    print("\n🚀 Running advanced analytics...")
    result = run_advanced_analytics()
    
    print(f"\n✅ Status: {result.get('timestamp')}")
    
    # Check predictions
    predictions = result.get("predictions", {})
    pred_list = predictions.get("predictions", [])
    print(f"\n📊 Predictions ({len(pred_list)} items):")
    for p in pred_list:
        print(f"   {p.get('horizon')}: {p.get('risk_score')} (confidence: {p.get('confidence')})")
    print(f"   Model: {predictions.get('model_type')}")
    
    # Check anomalies
    anomalies = result.get("anomalies", [])
    print(f"\n🔍 Anomalies ({len(anomalies)} items):")
    for a in anomalies[:3]:
        print(f"   Score: {a.get('anomaly_score'):.2f}, Severity: {a.get('severity')}")
    
    # Check causal graph
    causal = result.get("causal_graph", [])
    print(f"\n🔗 Causal Links ({len(causal)} items):")
    for c in causal[:3]:
        print(f"   {c.get('source')} → {c.get('target')}: {c.get('strength'):.2f}")
    
    # Check sentiment momentum
    momentum = result.get("sentiment_momentum", {})
    print(f"\n📈 Sentiment Momentum:")
    print(f"   Trend: {momentum.get('trend')}")
    print(f"   Velocity: {momentum.get('velocity')}")
    print(f"   RSI: {momentum.get('rsi')}")
    print(f"   MACD: {momentum.get('macd_signal')}")
    
    # Check AI Report
    report = result.get("ai_report", {})
    print(f"\n📝 AI Report:")
    print(f"   Title: {report.get('title')}")
    print(f"   Risk Level: {report.get('risk_level')}")
    print(f"   Summary: {report.get('summary')[:100]}...")
    print(f"   Findings: {len(report.get('key_findings', []))}")
    print(f"   Recommendations: {len(report.get('recommendations', []))}")
    
    print("\n" + "=" * 60)
    print("✅ Advanced Analytics Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
