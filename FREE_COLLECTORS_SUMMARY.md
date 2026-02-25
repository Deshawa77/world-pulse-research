# World Pulse - FREE Data Collectors Summary

## Overview
This document summarizes the **12 FREE data collectors** implemented for the World Pulse system. All collectors are free to use for academic/research purposes with generous rate limits.

## Total Data Sources: 24 (12 Original + 12 New)

---

## 12 NEW FREE Data Collectors

### 1. Social Media & Community (3 collectors)

#### YouTube Data API
- **File**: `collectors/youtube.py`
- **Free Tier**: 100 requests/day
- **Data**: Trending videos, comments, search results, video statistics
- **API Key**: `YOUTUBE_API_KEY`
- **Features**:
  - Regional trending videos
  - Comment sentiment analysis
  - Search monitoring
  - Video engagement metrics

#### Stack Overflow API
- **File**: `collectors/stackoverflow.py`
- **Free Tier**: 300 requests/day
- **Data**: Questions, answers, tags, view counts
- **Features**:
  - Trending technology tags
  - Developer sentiment
  - Technology adoption tracking
  - Community health metrics

#### Reddit Enhanced
- **File**: `collectors/reddit_enhanced.py`
- **Free Tier**: 60 requests/minute (OAuth app required)
- **Data**: Posts, comments, scores, multi-subreddit monitoring
- **API Keys**: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- **Features**:
  - Multi-subreddit monitoring (finance, news, crisis)
  - Comment thread analysis
  - Cross-subreddit sentiment comparison
  - Search functionality

---

### 2. Financial & Market Data (4 collectors)

#### Alpha Vantage
- **File**: `collectors/alphavantage.py`
- **Free Tier**: 5 calls/minute, 500/day
- **Data**: Stock quotes, intraday prices, sector performance, crypto
- **API Key**: `ALPHAVANTAGE_API_KEY`
- **Features**:
  - Real-time stock quotes
  - Intraday price data
  - Sector performance tracking
  - Cryptocurrency exchange rates
  - Technical indicators

#### Financial Modeling Prep
- **File**: `collectors/financialmodelingprep.py`
- **Free Tier**: 250 requests/day
- **Data**: Income statements, balance sheets, cash flow, SEC filings
- **API Key**: `FMP_API_KEY`
- **Features**:
  - Company financial health metrics
  - SEC EDGAR filings
  - Stock list monitoring
  - Financial ratio analysis

#### EOD Historical Data
- **File**: `collectors/eodhistorical.py`
- **Free Tier**: 1000 requests/day
- **Data**: End-of-day prices, fundamentals, macro indicators
- **API Token**: `EOD_API_TOKEN`
- **Features**:
  - Global exchange coverage (60+ exchanges)
  - Fundamental data
  - Macroeconomic indicators
  - Bulk data download

#### Messari
- **File**: `collectors/messari.py`
- **Free Tier**: 1000 requests/day
- **Data**: Crypto asset metrics, market data, news, on-chain metrics
- **API Key**: `MESSARI_API_KEY`
- **Features**:
  - On-chain activity metrics
  - Market data aggregation
  - Crypto news sentiment
  - Asset profile information

---

### 3. Geopolitical & Crisis Intelligence (2 collectors)

#### ACLED (Armed Conflict Location & Event Data)
- **File**: `collectors/acled.py`
- **Free Tier**: Free for academic/research use
- **Data**: Conflict events, fatalities, actor information, locations
- **API Access**: `ACLED_API_KEY`, `ACLED_EMAIL`
- **Features**:
  - Armed conflict events
  - Protest and riot tracking
  - Fatality counts
  - Actor identification
  - Geographic hotspot detection

#### ReliefWeb
- **File**: `collectors/reliefweb.py`
- **Free Tier**: Completely free, no API key required
- **Data**: Disaster reports, jobs, training, countries
- **Features**:
  - Disaster situation reports
  - Humanitarian job postings
  - Training opportunities
  - Country crisis profiles
  - Headline monitoring

---

### 4. Environmental & Climate Data (2 collectors)

#### NASA Earth Data
- **File**: `collectors/nasa_earth.py`
- **Free Tier**: 1000 requests/hour
- **Data**: Natural disasters, wildfires, severe storms, climate metrics
- **API Key**: `NASA_API_KEY` (optional but recommended)
- **Features**:
  - EONET natural event tracking
  - Wildfire monitoring
  - Severe weather alerts
  - POWER climate data
  - Environmental anomaly detection

#### OpenAQ (Air Quality)
- **File**: `collectors/openairquality.py`
- **Free Tier**: 100 requests/minute
- **Data**: PM2.5, PM10, O3, NO2, SO2, CO measurements
- **Features**:
  - Real-time air quality data
  - Multiple pollutant tracking
  - Location-based monitoring
  - Measurement location mapping
  - Health impact assessment

---

### 5. Advanced NLP & AI (1 collector)

#### HuggingFace Inference API
- **File**: `collectors/huggingface_nlp.py`
- **Free Tier**: 1000 requests/minute
- **Data**: Sentiment, emotion, toxicity, summarization
- **API Token**: `HUGGINGFACE_API_TOKEN`
- **Features**:
  - RoBERTa sentiment analysis
  - Emotion detection (anger, joy, sadness, fear, etc.)
  - Toxicity detection
  - Zero-shot classification
  - Text summarization
  - Named entity recognition

---

## API Keys Required

Add these to your `.env` file:

```bash
# YouTube Data API (100 requests/day free)
YOUTUBE_API_KEY=your_youtube_api_key_here

# Alpha Vantage (5 calls/minute free)
ALPHAVANTAGE_API_KEY=your_alphavantage_key_here

# ACLED (Free for academic use)
ACLED_API_KEY=your_acled_key_here
ACLED_EMAIL=your_email@example.com

# NASA Earth Data (1000 requests/hour free, optional)
NASA_API_KEY=your_nasa_api_key_here

# HuggingFace (1000 requests/minute free)
HUGGINGFACE_API_TOKEN=hf_your_token_here

# ReliefWeb (No key required)

# Messari (1000 requests/day free)
MESSARI_API_KEY=your_messari_key_here

# Financial Modeling Prep (250 requests/day free)
FMP_API_KEY=your_fmp_key_here

# EOD Historical Data (1000 requests/day free)
EOD_API_TOKEN=your_eod_token_here

# Reddit Enhanced (Free, requires app registration)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=WorldPulse:v1.0 (by /u/yourusername)
```

---

## Rate Limits Summary

| Collector | Free Tier | Rate Limit |
|-----------|-----------|------------|
| YouTube | 100 requests/day | ~4/hour |
| Alpha Vantage | 500 requests/day | 5/minute |
| ACLED | Academic free | 100/minute |
| NASA Earth | 1000 requests/hour | 16/minute |
| HuggingFace | 1000 requests/minute | 1000/minute |
| Stack Overflow | 300 requests/day | ~12/hour |
| OpenAQ | 100 requests/minute | 100/minute |
| ReliefWeb | Unlimited | No limit |
| Messari | 1000 requests/day | ~40/hour |
| Financial Modeling Prep | 250 requests/day | ~10/hour |
| EOD Historical | 1000 requests/day | ~40/hour |
| Reddit Enhanced | 60 requests/minute | 60/minute |

---

## Configuration

All collectors are configured in `config.py`:

```python
COLLECTOR_CONFIG = {
    "youtube": {"enabled": True, "interval": 300},
    "alphavantage": {"enabled": True, "interval": 300},
    "acled": {"enabled": True, "interval": 600},
    "nasa_earth": {"enabled": True, "interval": 600},
    "huggingface_nlp": {"enabled": True, "interval": 300},
    "stackoverflow": {"enabled": True, "interval": 300},
    "openaq": {"enabled": True, "interval": 600},
    "reliefweb": {"enabled": True, "interval": 300},
    "messari": {"enabled": True, "interval": 300},
    "financialmodelingprep": {"enabled": True, "interval": 300},
    "eodhistorical": {"enabled": True, "interval": 300},
    "reddit_enhanced": {"enabled": True, "interval": 300},
}
```

---

## New Features Available

The new collectors add these features to the ML pipeline:

```python
EXTENDED_FEATURE_COLUMNS = [
    # Social Media
    "youtube_sentiment",
    "stackoverflow_sentiment", 
    "reddit_enhanced_sentiment",
    # Financial
    "alphavantage_sentiment",
    "fmp_financial_health",
    "eod_market_breadth",
    # Crisis & Conflict
    "acled_conflict_intensity",
    "reliefweb_crisis_score",
    # Environmental
    "nasa_environmental_anomaly",
    "openaq_air_quality_index",
    # NLP/AI
    "huggingface_sentiment",
    # Crypto
    "messari_onchain_activity"
]
```

---

## Testing Individual Collectors

```python
# Test YouTube
from collectors.youtube import fetch_youtube_data
data = fetch_youtube_data()
print(f"YouTube: {len(data)} records")

# Test Alpha Vantage
from collectors.alphavantage import fetch_alphavantage_data
data = fetch_alphavantage_data()
print(f"Alpha Vantage: {len(data)} records")

# Test ACLED
from collectors.acled import fetch_acled_data
data = fetch_acled_data()
print(f"ACLED: {len(data)} records")

# Test all new collectors
from orchestrator_final import main
main()  # Starts all 24 collectors
```

---

## Integration

The new collectors integrate seamlessly with the existing pipeline:

1. **Data Collection** → Kafka topics (e.g., `youtube_topic`, `acled_topic`)
2. **Preprocessing** → Standardization and cleaning
3. **NLP Analysis** → Sentiment and topic extraction
4. **Feature Engineering** → New features extracted
5. **ML Models** → Enhanced predictions
6. **Dashboard** → Real-time visualization

---

## Production-Grade Features

All collectors include:
- ✅ Standardized data schema (id/source/category/collected_at/data)
- ✅ Robust error handling
- ✅ Rate limit management
- ✅ API key validation
- ✅ Logging and observability
- ✅ Kafka integration
- ✅ MongoDB persistence
- ✅ Configurable intervals
- ✅ Graceful degradation

---

## Removed Non-Free APIs

The following paid APIs were removed to keep the system 100% free:
- ❌ LinkedIn API (requires expensive partner program)
- ❌ OpenAI API (pay-per-use, costs real money)

---

## Next Steps

1. **Obtain free API keys** from the services above
2. **Add keys to `.env` file**
3. **Test individual collectors** using `__main__` blocks
4. **Run `orchestrator_final.py`** to start all 24 collectors
5. **Monitor dashboard** for new data streams
6. **Tune ML models** with new features

---

## Support

- **API Documentation**: See individual collector files
- **Rate Limit Issues**: Reduce `interval` in `config.py`
- **API Key Issues**: Verify keys in `.env` file
- **Integration Issues**: Check Kafka and MongoDB connectivity

---

**Note**: This system is designed for university research projects. All APIs listed are free for academic use. Ensure compliance with each API's terms of service.
