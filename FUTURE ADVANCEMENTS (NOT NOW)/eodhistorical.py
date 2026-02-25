"""
EOD Historical Data API Collector
Fetches global market data, fundamentals, and macro indicators
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("EOD_API_TOKEN")
BASE_URL = "https://eodhistoricaldata.com/api"

def fetch_stock_quote(symbol: str, exchange: str = "US") -> Optional[Dict[str, Any]]:
    """
    Fetch real-time stock quote
    """
    if not API_TOKEN:
        print("EOD API token not configured")
        return None
    
    url = f"{BASE_URL}/real-time/{symbol}.{exchange}"
    
    params = {
        "api_token": API_TOKEN,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"eod_quote_{symbol}_{exchange}_{collected_at}",
            "source": "eodhistorical",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "symbol": symbol,
                "exchange": exchange,
                "open": data.get("open"),
                "high": data.get("high"),
                "low": data.get("low"),
                "close": data.get("close"),
                "volume": data.get("volume"),
                "previous_close": data.get("previousClose"),
                "change": data.get("change"),
                "change_percent": data.get("change_p"),
                "timestamp": data.get("timestamp"),
                "type": "stock_quote"
            }
        }
        
    except requests.RequestException as e:
        print(f"EOD Quote API error: {e}")
        return None

def fetch_historical_data(
    symbol: str,
    exchange: str = "US",
    period: str = "d",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch historical OHLCV data
    """
    if not API_TOKEN:
        return []
    
    url = f"{BASE_URL}/eod/{symbol}.{exchange}"
    
    params = {
        "api_token": API_TOKEN,
        "fmt": "json",
        "period": period
    }
    
    if from_date:
        params["from"] = from_date
    
    if to_date:
        params["to"] = to_date
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data:
            record = {
                "id": f"eod_hist_{symbol}_{exchange}_{item.get('date')}_{collected_at}",
                "source": "eodhistorical",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "exchange": exchange,
                    "date": item.get("date"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "adjusted_close": item.get("adjusted_close"),
                    "volume": item.get("volume"),
                    "type": "historical_price"
                }
            }
            records.append(record)
        
        print(f"EOD: Fetched {len(records)} historical records for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"EOD Historical API error: {e}")
        return []

def fetch_fundamentals(symbol: str, exchange: str = "US") -> Optional[Dict[str, Any]]:
    """
    Fetch company fundamentals
    """
    if not API_TOKEN:
        return None
    
    url = f"{BASE_URL}/fundamentals/{symbol}.{exchange}"
    
    params = {
        "api_token": API_TOKEN,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        general = data.get("General", {})
        highlights = data.get("Highlights", {})
        valuation = data.get("Valuation", {})
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"eod_fund_{symbol}_{exchange}_{collected_at}",
            "source": "eodhistorical",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "symbol": symbol,
                "exchange": exchange,
                "name": general.get("Name"),
                "description": general.get("Description", "")[:500],
                "sector": general.get("Sector"),
                "industry": general.get("Industry"),
                "employees": general.get("FullTimeEmployees"),
                "market_capitalization": highlights.get("MarketCapitalization"),
                "pe_ratio": highlights.get("PERatio"),
                "eps": highlights.get("EarningsShare"),
                "dividend_yield": highlights.get("DividendYield"),
                "book_value": valuation.get("BookValue"),
                "trailing_pe": valuation.get("TrailingPE"),
                "forward_pe": valuation.get("ForwardPE"),
                "type": "fundamentals"
            }
        }
        
    except requests.RequestException as e:
        print(f"EOD Fundamentals API error: {e}")
        return None

def fetch_macro_indicators(country: str = "USA") -> List[Dict[str, Any]]:
    """
    Fetch macroeconomic indicators
    """
    if not API_TOKEN:
        return []
    
    url = f"{BASE_URL}/macro-indicator/{country}"
    
    params = {
        "api_token": API_TOKEN,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for indicator in data:
            record = {
                "id": f"eod_macro_{country}_{indicator.get('Indicator')}_{collected_at}",
                "source": "eodhistorical",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "country": country,
                    "indicator": indicator.get("Indicator"),
                    "value": indicator.get("Value"),
                    "date": indicator.get("Date"),
                    "type": "macro_indicator"
                }
            }
            records.append(record)
        
        print(f"EOD: Fetched {len(records)} macro indicators for {country}")
        return records
        
    except requests.RequestException as e:
        print(f"EOD Macro API error: {e}")
        return []

def fetch_exchange_list() -> List[Dict[str, Any]]:
    """
    Fetch list of available exchanges
    """
    if not API_TOKEN:
        return []
    
    url = f"{BASE_URL}/exchanges-list"
    
    params = {
        "api_token": API_TOKEN,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for exchange in data:
            record = {
                "id": f"eod_exchange_{exchange.get('Code')}_{collected_at}",
                "source": "eodhistorical",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "code": exchange.get("Code"),
                    "name": exchange.get("Name"),
                    "country": exchange.get("Country"),
                    "currency": exchange.get("Currency"),
                    "type": "exchange"
                }
            }
            records.append(record)
        
        print(f"EOD: Fetched {len(records)} exchanges")
        return records
        
    except requests.RequestException as e:
        print(f"EOD Exchange API error: {e}")
        return []

def fetch_eodhistorical_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive market data
    """
    all_records = []
    
    # Major indices and stocks
    symbols = [
        ("AAPL", "US"),
        ("MSFT", "US"),
        ("GOOGL", "US"),
        ("AMZN", "US"),
        ("TSLA", "US"),
        ("SPY", "US"),   # S&P 500 ETF
        ("QQQ", "US"),   # Nasdaq ETF
        ("IWM", "US"),   # Russell 2000
    ]
    
    # Fetch quotes
    for symbol, exchange in symbols:
        quote = fetch_stock_quote(symbol, exchange)
        if quote:
            all_records.append(quote)
    
    # Fetch fundamentals for top companies
    for symbol, exchange in symbols[:4]:
        fundamentals = fetch_fundamentals(symbol, exchange)
        if fundamentals:
            all_records.append(fundamentals)
    
    # Fetch macro indicators for major economies
    countries = ["USA", "GBR", "DEU", "JPN", "CHN"]
    for country in countries:
        macro = fetch_macro_indicators(country)
        all_records.extend(macro)
    
    # Fetch exchange list
    exchanges = fetch_exchange_list()
    all_records.extend(exchanges[:20])  # Limit to top 20
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_eodhistorical_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
