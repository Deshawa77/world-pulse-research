# Risk Score Fix Plan

## Problem
Sentinel AI keeps giving risk alert above 75 all the time due to biased risk calculation formula.

## Root Cause
The formula in `processing/global_risk.py`:
- `risk_score = 50 - (avg_sentiment * 40)` - negative sentiment (common) increases risk
- Adding volatility (`* 20`) and volume scores easily pushes above 75

## Solution
Apply BOTH fixes:

### 1. Balance the Formula
- Change from biased to symmetric around 50
- Use `(50 - sentiment * 20)` to center properly

### 2. Add Damping Factors  
- Reduce multipliers to dampen normal fluctuations
- sentiment: 40 → 15
- volatility: 20 → 8
- volume: cap at max 5 instead of 10

## Files to Edit
- [x] processing/global_risk.py - Fix compute_global_risk() function

## Expected Result
Risk scores should now hover around 40-60 normally, only spiking above 75 for genuine critical events.
