# World Pulse - New Data Collectors Guide

## Overview

This guide documents the 15 new production-grade data collectors added to the World Pulse system. These collectors expand the system's capabilities across social media, financial data, geopolitical intelligence, environmental monitoring, and advanced NLP processing.

## New Collectors Summary

### 1. Social Media & Community Data

#### YouTube Data API (`collectors/youtube.py`)
- **Purpose**: Collect trending videos, comments, and search results for sentiment analysis
- **Data**: Video titles, descriptions, comments, view counts, likes, regional trends
- **API Key**: `YOUTUBE_API_KEY`
- **Rate Limit**: 100 requests/day (free tier)
- **Features**:
  - Trending videos by region
  - Comment sentiment analysis
  - Search result monitoring
  - Video statistics tracking

#### Stack Overflow API (`collectors/stackoverflow.py`)
- **Purpose**: Monitor developer sentiment and technology trends
- **Data**: Questions, answers, tags, view counts, scores
- **Features**:
  - Trending technology tags
  - Question sentiment analysis
  - Developer community health
  - Technology adoption trends

#### Reddit Enhanced (`collectors/reddit_enhanced.py`)
- **Purpose**: Extended Reddit data collection with multi-subreddit support
- **Data**: Posts, comments, scores, subreddit activity
- **API Credentials**: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- **Features**:
  - Multiple subreddit monitoring (finance, news, crisis)
  - Comment thread analysis
  - Search functionality
  - Cross-subreddit sentiment comparison

### 2. Financial & Market Data

#### Alpha Vantage (`collectors/alphavantage.py`)
- **Purpose**: Real-time and historical stock market data
- **Data**: Stock quotes, intraday prices, sector performance, crypto
- **API Key**: `ALPHAVANTAGE_API_KEY`
- **Rate Limit**: 5 calls/minute (free tier), 75 calls/minute (premium)
- **Features**:
  - Real-time stock quotes
  - Intraday price data
  - Sector performance tracking
  - Cryptocurrency exchange rates
  - Technical indicators

#### Financial Modeling Prep (`collectors/financialmodelingprep.py`)
- **Purpose**: Comprehensive financial statements and SEC filings
- **Data**: Income statements, balance sheets, cash flow, SEC filings
- **API Key**: `FMP_API_KEY`
- **Rate Limit**: 250 requests/minute
- **Features**:
  - Company financial health metrics
  - SEC EDGAR filings
  - Stock list monitoring
  - Financial ratio analysis

#### EOD Historical Data (`collectors/eodhistorical.py`)
- **Purpose**: Global market data and fundamentals
- **Data**: End-of-day prices, fundamentals, macro indicators
- **API Token**: `EOD_API_TOKEN`
- **Rate Limit**: 1000 requests/day (free tier)
- **Features**:
  - Global exchange coverage
  - Fundamental data
  - Macroeconomic indicators
  - Bulk data download

#### Messari (`collectors/messari.py`)
- **Purpose**: Cryptocurrency on-chain analytics and market data
- **Data**: Asset metrics, market data, news, on-chain metrics
- **API Key**: `MESSARI_API_KEY`
- **Features**:
  - On-chain activity metrics
  - Market data aggregation
  - Crypto news sentiment
  - Asset profile information

### 3. Geopolitical & Crisis Intelligence

#### ACLED (Armed Conflict Location & Event Data) (`collectors/acled.py`)
- **Purpose**: Real-time conflict and crisis event monitoring
- **Data**: Conflict events, fatalities, actor information, locations
- **API Access**: `ACLED_API_KEY`, `ACLED_EMAIL`
- **Features**:
  - Armed conflict events
  - Protest and riot tracking
  - Fatality counts
  - Actor identification
  - Geographic hotspot detection

#### ReliefWeb (`collectors/reliefweb.py`)
- **Purpose**: Humanitarian crisis and disaster information
- **Data**: Disaster reports, jobs, training, countries
- **Features**:
  - Disaster situation reports
  - Humanitarian job postings
  - Training opportunities
  - Country crisis profiles
  - Headline monitoring

### 4. Environmental & Climate Data

#### NASA Earth Data (`collectors/nasa_earth.py`)
- **Purpose**: Natural events and climate data monitoring
- **Data**: Natural disasters, wildfires, severe storms, climate metrics
- **API Key**: `NASA_API_KEY` (optional, but recommended)
- **Features**:
  - EONET natural event tracking
  - Wildfire monitoring
  - Severe weather alerts
  - POWER climate data
  - Environmental anomaly detection

#### OpenAQ (Air Quality) (`collectors/openairquality.py`)
- **Purpose**: Global air quality monitoring
- **Data**: PM2.5, PM10, O3, NO2, SO2, CO measurements
- **Features**:
  - Real-time air quality data
  - Multiple pollutant tracking
  - Location-based monitoring
  - Measurement location mapping
  - Health impact assessment

### 5. Advanced NLP & AI Services

#### HuggingFace Inference API (`collectors/huggingface_nlp.py`)
- **Purpose**: State-of-the-art NLP model inference
- **Data**: Sentiment, emotion, toxicity, summarization
- **API Token**: `HUGGINGFACE_API_TOKEN`
- **Rate Limit**: 1000 requests/minute (free tier)
- **Features**:
  - RoBERTa sentiment analysis
  - Emotion detection (anger, joy, sadness, etc.)
  - Toxicity detection
  - Zero-shot classification
  - Text summarization
  - Named entity recognition

#### OpenAI API (`collectors/openai_nlp.py`)
- **Purpose**: GPT-powered advanced text analysis
- **Data**: Sentiment, summaries, entities, crisis classification
- **API Key**: `OPENAI_API_KEY`
- **Rate Limit**: 60 requests/minute (varies by tier)
- **Cost**: Pay-per-use (monitor costs carefully)
- **Features**:
  - Advanced sentiment analysis
  - Text summarization
  - Named entity extraction
  - Crisis classification
  - Custom analysis prompts

#### LinkedIn API (`collectors/linkedin.py`)
- **Purpose**: Professional network sentiment and job market trends
- **Data**: Company updates, job postings, industry trends
- **API Access**: `LINKEDIN_ACCESS_TOKEN` (requires partner program)
- **Features**:
  - Company update monitoring
  - Job market sentiment
  - Industry trend analysis
  - Professional network insights

## Configuration

### Environment Variables

Create or update your `.env` file with the following API keys:

```bash
# YouTube Data API
YOUTUBE_API_KEY=your_youtube_api_key_here

# Alpha Vantage
ALPHAVANTAGE_API_KEY=your_alphavantage_key_here

# ACLED (Armed Conflict)
ACLED_API_KEY=your_acled_key_here
ACLED_EMAIL=your_email@example.com

# NASA (optional but recommended)
NASA_API_KEY=your_nasa_api_key_here

# HuggingFace
HUGGINGFACE_API_TOKEN=hf_your_token_here

# LinkedIn (requires partner access)
LINKEDIN_ACCESS_TOKEN=your_linkedin_token_here

# ReliefWeb (no key required for basic access)

# Messari
MESSARI_API_KEY=your_messari_key_here

# Financial Modeling Prep
FMP_API_KEY=your_fmp_key_here

# EOD Historical Data
EOD_API_TOKEN=your_eod_token_here

# Reddit (enhanced)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=WorldPulse:v1.0 (by /u/yourusername)

# OpenAI (optional - has costs)
OPENAI_API_KEY=sk-your_openai_key_here
```

### Collector Configuration

Edit `config.py` to enable/disable collectors:

```python
COLLECTOR_CONFIG = {
    "youtube": {"enabled": True, "interval": 300},
    "alphavantage": {"enabled": True, "interval": 300},
    "acled": {"enabled": True, "interval": 600},
    "nasa_earth": {"enabled": True, "interval": 600},
    "huggingface_nlp": {"enabled": True, "interval": 300},
    "stackoverflow": {"enabled": True, "interval": 300},
    "openaq": {"enabled": True, "interval": 600},
    "linkedin": {"enabled": False, "interval": 600},  # Requires partner access
    "reliefweb": {"enabled": True, "interval": 300},
    "messari": {"enabled": True, "interval": 300},
    "financialmodelingprep": {"enabled": True, "interval": 300},
    "eodhistorical": {"enabled": True, "interval": 300},
    "reddit_enhanced": {"enabled": True, "interval": 300},
    "openai_nlp": {"enabled": False, "interval": 600},  # Cost consideration
}
```

## Data Schema

All collectors follow a standardized schema:

```json
{
  "id": "unique_record_identifier",
  "source": "collector_name",
  "category": "data_category",
  "collected_at": "ISO8601_timestamp",
  "data": {
    // Collector-specific fields
  }
}
```

### Categories
- `social_media`: YouTube, Reddit, Stack Overflow, LinkedIn
- `financial`: Alpha Vantage, FMP, EOD, Messari
- `crisis`: ACLED, ReliefWeb
- `environmental`: NASA Earth, OpenAQ
- `nlp`: HuggingFace, OpenAI

## Usage Examples

### Testing Individual Collectors

```python
# Test YouTube collector
from collectors.youtube import fetch_youtube_data
data = fetch_youtube_data()
print(f"Collected {len(data)} YouTube records")

# Test Alpha Vantage
from collectors.alphavantage import fetch_alphavantage_data
data = fetch_alphavantage_data()
print(f"Collected {len(data)} financial records")

# Test ACLED
from collectors.acled import fetch_acled_data
data = fetch_acled_data()
print(f"Collected {len(data)} conflict events")
```

### Running All New Collectors

```python
from orchestrator_updated import main
main()  # Starts all collectors including new ones
```

### Custom Data Collection

```python
from collectors.youtube import fetch_trending_videos, fetch_video_comments

# Get trending videos in specific region
videos = fetch_trending_videos(region_code="US", max_results=10)

# Get comments for sentiment analysis
for video in videos:
    comments = fetch_video_comments(video["data"]["video_id"], max_results=50)
    # Process comments for sentiment...
```

## Integration with ML Pipeline

The new collectors feed into the existing ML pipeline:

1. **Data Collection** → Kafka topics
2. **Preprocessing** → Standardization and cleaning
3. **NLP Analysis** → Sentiment and topic extraction
4. **Feature Engineering** → New features from collector data
5. **ML Models** → Enhanced predictions with new data sources
6. **Dashboard** → Real-time visualization

### New Features Available

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
    # Crisis
    "acled_conflict_intensity",
    "reliefweb_crisis_score",
    # Environmental
    "nasa_environmental_anomaly",
    "openaq_air_quality_index",
    # NLP
    "huggingface_sentiment",
    "openai_crisis_probability",
    # Crypto
    "messari_onchain_activity"
]
```

## API Rate Limits & Best Practices

### Rate Limit Management

```python
from config import API_RATE_LIMITS
import time

def rate_limited_call(collector_name, fetch_function):
    limit = API_RATE_LIMITS.get(collector_name, 60)
    interval = 60.0 / limit  # seconds between calls
    
    while True:
        result = fetch_function()
        time.sleep(interval)
        yield result
```

### Error Handling

All collectors include robust error handling:

```python
try:
    data = fetch_collector_data()
except requests.RequestException as e:
    # Network error - retry with backoff
    log_event(f"Network error: {e}")
except ValueError as e:
    # Data parsing error
    log_event(f"Data error: {e}")
except Exception as e:
    # Unexpected error
    log_event(f"Unexpected error: {e}")
```

## Cost Considerations

### Free Tier Limits

| Collector | Free Tier | Cost Estimate |
|-----------|-----------|---------------|
| YouTube | 100 requests/day | Free |
| Alpha Vantage | 5 calls/minute | Free |
| HuggingFace | 1000 requests/minute | Free |
| NASA | 1000 requests/hour | Free |
| OpenAQ | 100 requests/minute | Free |
| Stack Overflow | 300 requests/day | Free |
| Reddit | 60 requests/minute | Free |
| OpenAI | $0.002-0.06 per 1K tokens | ~$0.01-0.50 per analysis |
| ACLED | Academic use free | Free for research |
| Messari | 1000 requests/day | Free tier available |

### Cost Optimization Tips

1. **Enable caching** for expensive API calls
2. **Use sampling** for high-volume data sources
3. **Batch requests** where possible
4. **Monitor usage** with built-in observability
5. **Disable expensive collectors** when not needed (OpenAI)

## Monitoring & Observability

### Health Checks

```python
from backend.observability import health_check

# Check all collector health
status = health_check()
for collector, health in status["collectors"].items():
    print(f"{collector}: {health['status']}")
```

### Metrics Collection

Each collector reports:
- API call count
- Success/failure rates
- Data volume
- Latency metrics
- Error rates

## Troubleshooting

### Common Issues

1. **API Key Errors**
   - Verify keys in `.env` file
   - Check key permissions and quotas
   - Ensure keys are not expired

2. **Rate Limit Exceeded**
   - Reduce collection frequency in `config.py`
   - Implement exponential backoff
   - Consider upgrading API tier

3. **Data Quality Issues**
   - Check API response format changes
   - Verify data validation in collectors
   - Review preprocessing pipeline

4. **Memory Issues**
   - Reduce batch sizes in collectors
   - Implement streaming for large datasets
   - Use database pagination

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. **API Key Protection**
   - Never commit keys to version control
   - Use environment variables
   - Rotate keys regularly

2. **Data Privacy**
   - Respect API terms of service
   - Handle PII according to regulations
   - Implement data retention policies

3. **Rate Limiting**
   - Implement client-side rate limiting
   - Use exponential backoff
   - Monitor for abuse

## Next Steps

1. **Obtain API keys** for desired collectors
2. **Update `.env` file** with credentials
3. **Test individual collectors** using `__main__` blocks
4. **Configure collector settings** in `config.py`
5. **Run orchestrator** with new collectors
6. **Monitor dashboard** for new data streams
7. **Tune ML models** with new features

## Support & Resources

- **API Documentation**: See individual collector files for API links
- **Issue Tracking**: Check `TODO.md` for known issues
- **Feature Requests**: Submit via project management system
- **API Status Pages**:
  - YouTube: https://status.cloud.google.com/
  - Alpha Vantage: https://www.alphavantage.co/support/
  - HuggingFace: https://status.huggingface.co/
  - NASA: https://status.earthdata.nasa.gov/

---

**Note**: This system is designed for research and educational purposes. Ensure compliance with all API terms of service and data usage policies.
