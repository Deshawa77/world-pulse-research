"""
Alpha Vantage API Collector
Fetches stock market data, technical indicators, and market sentiment
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"

def fetch_stock_quote(symbol: str = "AAPL") -> Optional[Dict[str, Any]]:
    """
    Fetch real-time stock quote data
    """
    if not API_KEY:
        print("Alpha Vantage API key not configured")
        return None
    
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        quote = data.get("Global Quote", {})
        if not quote:
            return None
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"av_quote_{symbol}_{collected_at}",
            "source": "alphavantage",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "symbol": quote.get("01. symbol"),
                "open": float(quote.get("02. open", 0)),
                "high": float(quote.get("03. high", 0)),
                "low": float(quote.get("04. low", 0)),
                "price": float(quote.get("05. price", 0)),
                "volume": int(quote.get("06. volume", 0)),
                "latest_trading_day": quote.get("07. latest trading day"),
                "previous_close": float(quote.get("08. previous close", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": quote.get("10. change percent", "0%"),
                "type": "stock_quote"
            }
        }
        
    except requests.RequestException as e:
        print(f"Alpha Vantage Quote API error: {e}")
        return None

def fetch_intraday_data(symbol: str = "AAPL", interval: str = "5min") -> List[Dict[str, Any]]:
    """
    Fetch intraday time series data for volatility calculation
    """
    if not API_KEY:
        return []
    
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        time_series_key = f"Time Series ({interval})"
        time_series = data.get(time_series_key, {})
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for timestamp, values in list(time_series.items())[:20]:  # Last 20 intervals
            record = {
                "id": f"av_intraday_{symbol}_{timestamp}",
                "source": "alphavantage",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(values.get("5. volume", 0)),
                    "interval": interval,
                    "type": "intraday"
                }
            }
            records.append(record)
        
        print(f"Alpha Vantage: Fetched {len(records)} intraday records for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"Alpha Vantage Intraday API error: {e}")
        return []

def fetch_market_sentiment(symbol: str = "AAPL") -> Optional[Dict[str, Any]]:
    """
    Fetch market sentiment data (requires premium API)
    """
    if not API_KEY:
        return None
    
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "Information" in data:  # Premium endpoint message
            return None
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        sentiment = data.get("sentiment_score", 0)
        relevance = data.get("relevance_score", 0)
        
        return {
            "id": f"av_sentiment_{symbol}_{collected_at}",
            "source": "alphavantage",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "symbol": symbol,
                "sentiment_score": float(sentiment),
                "relevance_score": float(relevance),
                "type": "market_sentiment"
            }
        }
        
    except requests.RequestException as e:
        print(f"Alpha Vantage Sentiment API error: {e}")
        return None

def fetch_sector_performance() -> List[Dict[str, Any]]:
    """
    Fetch sector performance data
    """
    if not API_KEY:
        return []
    
    params = {
        "function": "SECTOR",
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        # Real-time performance
        rt_performance = data.get("Rank A: Real-Time Performance", {})
        for sector, change in rt_performance.items():
            record = {
                "id": f"av_sector_{sector.replace(' ', '_')}_{collected_at}",
                "source": "alphavantage",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "sector": sector,
                    "change_percent": change,
                    "timeframe": "realtime",
                    "type": "sector_performance"
                }
            }
            records.append(record)
        
        print(f"Alpha Vantage: Fetched {len(records)} sector performance records")
        return records
        
    except requests.RequestException as e:
        print(f"Alpha Vantage Sector API error: {e}")
        return []

def fetch_crypto_data(symbol: str = "BTC", market: str = "USD") -> Optional[Dict[str, Any]]:
    """
    Fetch cryptocurrency data
    """
    if not API_KEY:
        return None
    
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": symbol,
        "to_currency": market,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        exchange_rate = data.get("Realtime Currency Exchange Rate", {})
        if not exchange_rate:
            return None
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"av_crypto_{symbol}_{market}_{collected_at}",
            "source": "alphavantage",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "from_currency": exchange_rate.get("1. From_Currency Code"),
                "to_currency": exchange_rate.get("3. To_Currency Code"),
                "exchange_rate": float(exchange_rate.get("5. Exchange Rate", 0)),
                "bid_price": float(exchange_rate.get("8. Bid Price", 0)),
                "ask_price": float(exchange_rate.get("9. Ask Price", 0)),
                "type": "crypto_exchange"
            }
        }
        
    except requests.RequestException as e:
        print(f"Alpha Vantage Crypto API error: {e}")
        return None

def fetch_alphavantage_data() -> List[Dict[str, Any]]:
    """
    Main collector function - fetches comprehensive market data
    """
    all_records = []
    
    # Major stock indices and symbols
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "IWM"]
    
    # Fetch stock quotes
    for symbol in symbols:
        quote = fetch_stock_quote(symbol)
        if quote:
            all_records.append(quote)
    
    # Fetch intraday data for volatility (limit to 3 symbols to avoid rate limits)
    for symbol in symbols[:3]:
        intraday = fetch_intraday_data(symbol)
        all_records.extend(intraday)
    
    # Fetch sector performance
    sectors = fetch_sector_performance()
    all_records.extend(sectors)
    
    # Fetch crypto data
    crypto = fetch_crypto_data("BTC", "USD")
    if crypto:
        all_records.append(crypto)
    
    crypto_eth = fetch_crypto_data("ETH", "USD")
    if crypto_eth:
        all_records.append(crypto_eth)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_alphavantage_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
