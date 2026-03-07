# Risk Score Fix Plan - COMPLETED ✓

## Problem
Sentinel AI keeps giving risk alert above 75 all the time due to biased risk calculation formula.

## Root Cause
The formula in `processing/global_risk.py`:
- `risk_score = 50 - (avg_sentiment * 40)` - negative sentiment (common) increases risk
- Adding volatility (`* 20`) and volume scores easily pushes above 75

## Solution Applied - BOTH FIXES

### 1. Balanced the Formula ✓
- Changed `avg_sentiment * 40` → `avg_sentiment * 15`
- This reduces the extreme impact of negative sentiment

### 2. Added Damping Factors ✓
- Sentiment: 40 → 15 (reduced by 62.5%)
- Volatility: 20 → 8 (reduced by 60%)
- Volume: max 10 → 5, divisor 5 → 10 (reduced by 50%)

## Files Edited
- [x] processing/global_risk.py - Fixed compute_global_risk() function

## Changes Made (lines ~83-96):
```
python
# OLD (biased):
risk_score = 50 - (avg_sentiment * 40)
risk_score += sentiment_std * 20
volume_score = min(10, new_articles_count / 5)

# NEW (balanced & damped):
risk_score = 50 - (avg_sentiment * 15)  # balanced sentiment
risk_score += sentiment_std * 8            # damped volatility
volume_score = min(5, new_articles_count / 10)  # capped volume
```

## Expected Result
