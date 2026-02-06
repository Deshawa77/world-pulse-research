# orchestrator.py

import collectors.news as news
# import collectors.reddit as reddit  # Uncomment when you have a Reddit API key
import collectors.gdelt as gdelt
import collectors.wiki as wiki
import collectors.trends as trends
import collectors.usgs as usgs
import collectors.weather as weather
import collectors.coingecko as coingecko
import collectors.fred as fred
import collectors.frankfurter as frankfurter
import collectors.who as who
import collectors.twelvedata as twelvedata
import collectors.worldbank as worldbank
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

REQUEST_DELAY_SECONDS = 5

def _safe_fetch(label, fetch_fn, default):
    try:
        return fetch_fn()
    except Exception as e:
        print(f"Error fetching {label}: {e}")
        traceback.print_exc()
        return default

def orchestrate_parallel():
    tasks = {
        "news": lambda: news.fetch_news("earthquake", page_size=5),
        # "reddit": lambda: reddit.fetch_reddit_posts("earthquake", limit=5),
        "gdelt": lambda: gdelt.fetch_gdelt_articles("(earthquake OR flood)", max_records=5),
        "wiki": lambda: wiki.fetch_pageviews("Earthquake", days=5),
        "trends": lambda: trends.fetch_trends("earthquake"),
        "earthquakes": lambda: usgs.fetch_earthquakes(),
        "weather": lambda: weather.fetch_weather("Tokyo"),
        "crypto": lambda: coingecko.fetch_crypto("bitcoin", "usd", 5),
        "fred": lambda: fred.fetch_indicator("GDP", "2025-01-01", "2026-01-01"),
        "exchange_rates": lambda: frankfurter.fetch_exchange_rates("USD"),
        "who": lambda: who.fetch_who_indicator("WHOSIS_000001", max_results=5),
        "stocks": lambda: twelvedata.fetch_stock("AAPL", "1day", 5),
        "worldbank": lambda: worldbank.fetch_worldbank_data(date="2020:2025", per_page=5)
    }

    unified_data = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_label = {executor.submit(_safe_fetch, label, fn, []): label for label, fn in tasks.items()}

        for future in as_completed(future_to_label):
            label = future_to_label[future]
            try:
                unified_data[label] = future.result()
            except Exception as e:
                print(f"Unhandled error fetching {label}: {e}")
                traceback.print_exc()
                unified_data[label] = [] if label != "weather" and label != "exchange_rates" else {}

    return unified_data


if __name__ == "__main__":
    print("Starting parallel orchestrator...\n")
    start_time = time.time()
    data = orchestrate_parallel()
    end_time = time.time()

    # Print summaries
    for key, value in data.items():
        if isinstance(value, list):
            print(f"{key}: {len(value)} items")
        elif isinstance(value, dict):
            print(f"{key}: dict with {len(value)} keys")
        else:
            print(f"{key}: {type(value)}")

    print(f"\nOrchestration complete in {end_time - start_time:.2f} seconds!")
