"""
Financial Modeling Prep API Collector
Fetches SEC filings, financial statements, and stock fundamentals
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/api/v3"

def fetch_income_statement(symbol: str, period: str = "quarter", limit: int = 4) -> List[Dict[str, Any]]:
    """
    Fetch income statements for a company
    """
    if not API_KEY:
        print("FMP API key not configured")
        return []
    
    url = f"{BASE_URL}/income-statement/{symbol}"
    
    params = {
        "period": period,
        "limit": limit,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for statement in data:
            record = {
                "id": f"fmp_income_{symbol}_{statement.get('date')}_{collected_at}",
                "source": "financialmodelingprep",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "date": statement.get("date"),
                    "period": statement.get("period"),
                    "revenue": statement.get("revenue"),
                    "net_income": statement.get("netIncome"),
                    "gross_profit": statement.get("grossProfit"),
                    "operating_income": statement.get("operatingIncome"),
                    "ebitda": statement.get("ebitda"),
                    "eps": statement.get("eps"),
                    "eps_diluted": statement.get("epsdiluted"),
                    "type": "income_statement"
                }
            }
            records.append(record)
        
        print(f"FMP: Fetched {len(records)} income statements for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"FMP Income Statement API error: {e}")
        return []

def fetch_balance_sheet(symbol: str, period: str = "quarter", limit: int = 4) -> List[Dict[str, Any]]:
    """
    Fetch balance sheets for a company
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/balance-sheet-statement/{symbol}"
    
    params = {
        "period": period,
        "limit": limit,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for statement in data:
            record = {
                "id": f"fmp_balance_{symbol}_{statement.get('date')}_{collected_at}",
                "source": "financialmodelingprep",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "date": statement.get("date"),
                    "period": statement.get("period"),
                    "total_assets": statement.get("totalAssets"),
                    "total_liabilities": statement.get("totalLiabilities"),
                    "total_stockholders_equity": statement.get("totalStockholdersEquity"),
                    "cash_and_cash_equivalents": statement.get("cashAndCashEquivalents"),
                    "total_debt": statement.get("totalDebt"),
                    "net_debt": statement.get("netDebt"),
                    "type": "balance_sheet"
                }
            }
            records.append(record)
        
        print(f"FMP: Fetched {len(records)} balance sheets for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"FMP Balance Sheet API error: {e}")
        return []

def fetch_cash_flow(symbol: str, period: str = "quarter", limit: int = 4) -> List[Dict[str, Any]]:
    """
    Fetch cash flow statements for a company
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/cash-flow-statement/{symbol}"
    
    params = {
        "period": period,
        "limit": limit,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for statement in data:
            record = {
                "id": f"fmp_cashflow_{symbol}_{statement.get('date')}_{collected_at}",
                "source": "financialmodelingprep",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "date": statement.get("date"),
                    "period": statement.get("period"),
                    "operating_cash_flow": statement.get("operatingCashFlow"),
                    "free_cash_flow": statement.get("freeCashFlow"),
                    "capital_expenditure": statement.get("capitalExpenditure"),
                    "dividends_paid": statement.get("dividendsPaid"),
                    "net_change_in_cash": statement.get("netChangeInCash"),
                    "type": "cash_flow_statement"
                }
            }
            records.append(record)
        
        print(f"FMP: Fetched {len(records)} cash flow statements for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"FMP Cash Flow API error: {e}")
        return []

def fetch_sec_filings(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch SEC filings (10-K, 10-Q, 8-K, etc.)
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/sec_filings/{symbol}"
    
    params = {
        "limit": limit,
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for filing in data:
            record = {
                "id": f"fmp_sec_{symbol}_{filing.get('fillingDate')}_{collected_at}",
                "source": "financialmodelingprep",
                "category": "financial",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "filing_date": filing.get("fillingDate"),
                    "accepted_date": filing.get("acceptedDate"),
                    "cik": filing.get("cik"),
                    "type": filing.get("type"),
                    "link": filing.get("link"),
                    "final_link": filing.get("finalLink"),
                    "description": self._get_filing_description(filing.get("type")),
                    "filing_type": "sec_filing"
                }
            }
            records.append(record)
        
        print(f"FMP: Fetched {len(records)} SEC filings for {symbol}")
        return records
        
    except requests.RequestException as e:
        print(f"FMP SEC Filings API error: {e}")
        return []

def _get_filing_description(filing_type: str) -> str:
    """Get description for SEC filing type"""
    descriptions = {
        "10-K": "Annual report",
        "10-Q": "Quarterly report",
        "8-K": "Current report (material events)",
        "4": "Insider trading report",
        "13F": "Institutional investment report",
        "DEF 14A": "Proxy statement",
        "S-1": "Registration statement (IPO)"
    }
    return descriptions.get(filing_type, "Other SEC filing")

def fetch_stock_quote_fmp(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch real-time stock quote
    """
    if not API_KEY:
        return None
    
    url = f"{BASE_URL}/quote/{symbol}"
    
    params = {
        "apikey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        quote = data[0]
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"fmp_quote_{symbol}_{collected_at}",
            "source": "financialmodelingprep",
            "category": "financial",
            "collected_at": collected_at,
            "data": {
                "symbol": symbol,
                "name": quote.get("name"),
                "price": quote.get("price"),
                "change": quote.get("change"),
                "changes_percentage": quote.get("changesPercentage"),
                "volume": quote.get("volume"),
                "market_cap": quote.get("marketCap"),
                "pe_ratio": quote.get("pe"),
                "eps": quote.get("eps"),
                "52_week_high": quote.get("yearHigh"),
                "52_week_low": quote.get("yearLow"),
                "exchange": quote.get("exchange"),
                "type": "stock_quote"
            }
        }
        
    except requests.RequestException as e:
        print(f"FMP Quote API error: {e}")
        return None

def fetch_financialmodelingprep_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive financial data
    """
    all_records = []
    
    # Major companies to track
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM"]
    
    # Fetch quotes for all symbols
    for symbol in symbols:
        quote = fetch_stock_quote_fmp(symbol)
        if quote:
            all_records.append(quote)
    
    # Fetch financial statements for top companies (limit to avoid rate limits)
    for symbol in symbols[:3]:
        income = fetch_income_statement(symbol, period="quarter", limit=2)
        all_records.extend(income)
        
        balance = fetch_balance_sheet(symbol, period="quarter", limit=2)
        all_records.extend(balance)
        
        cashflow = fetch_cash_flow(symbol, period="quarter", limit=2)
        all_records.extend(cashflow)
        
        sec = fetch_sec_filings(symbol, limit=5)
        all_records.extend(sec)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_financialmodelingprep_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
