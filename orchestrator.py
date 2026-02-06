import collectors.news as news
# import collectors.reddit as reddit  # Uncomment if you have Reddit API keys
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

from database.mongo import insert, insert_run_metadata
import time
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import preprocessing
from processing import preprocess_data

# --------------------------
# Logging Setup
# --------------------------
logging.basicConfig(
    filename="orchestrator.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

REQUEST_DELAY_SECONDS = 5

# --------------------------
# Safe fetch + Mongo insert
# --------------------------
def _safe_fetch_and_store(label, fetch_fn, collection_name, unique_keys=None):
    """
    Fetch data safely, log errors, insert into MongoDB with duplicate check.
    """
    try:
        data = fetch_fn()
        count_fetched = len(data) if isinstance(data, list) else len(data.keys())
        logging.info(f"{label}: Fetched {count_fetched} items")

        try:
            inserted_count = insert(collection_name, data, unique_keys=unique_keys)
            logging.info(f"{label}: Inserted {inserted_count} new items into {collection_name}")
        except Exception as e:
            logging.error(f"{label}: Failed to insert into MongoDB - {e}")
            traceback.print_exc()
            inserted_count = 0

        return data, inserted_count, None

    except Exception as e:
        logging.error(f"{label}: Fetch failed - {e}")
        traceback.print_exc()
        return [], 0, str(e)

# --------------------------
# Orchestration
# --------------------------
def orchestrate_parallel(selected_collectors=None):
    tasks = {
        "news": (lambda: news.fetch_news("earthquake", page_size=5), "news", ["data.title", "data.query"]),
        # "reddit": (lambda: reddit.fetch_reddit_posts("earthquake", limit=5), "reddit", ["data.title", "data.query"]),
        "gdelt": (lambda: gdelt.fetch_gdelt_articles("(earthquake OR flood)", max_records=5), "gdelt", ["data.title", "data.url"]),
        "wiki": (lambda: wiki.fetch_pageviews("Earthquake", days=5), "wiki", ["data.date"]),
        "trends": (lambda: trends.fetch_trends("earthquake"), "trends", ["data.date"]),
        "earthquakes": (lambda: usgs.fetch_earthquakes(), "earthquakes", ["data.id"]),
        "weather": (lambda: weather.fetch_weather("Tokyo"), "weather", ["data.timestamp"]),
        "crypto": (lambda: coingecko.fetch_crypto("bitcoin", "usd", 5), "crypto", ["data.timestamp"]),
        "fred": (lambda: fred.fetch_indicator("GDP", "2025-01-01", "2026-01-01"), "fred", ["data.date"]),
        "exchange_rates": (lambda: frankfurter.fetch_exchange_rates("USD"), "economics", ["data.currency"]),
        "who": (lambda: who.fetch_who_indicator("WHOSIS_000001", max_results=5), "who", ["data.date"]),
        "stocks": (lambda: twelvedata.fetch_stock("AAPL", "1day", 5), "stocks", ["data.timestamp"]),
        "worldbank": (lambda: worldbank.fetch_worldbank_data(date="2020:2025", per_page=5), "worldbank", ["data.date"])
    }

    if selected_collectors:
        tasks = {k: v for k, v in tasks.items() if k in selected_collectors}

    unified_data = {}
    run_summary = {"total_fetched": {}, "total_inserted": {}, "errors": {}}

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_label = {
            executor.submit(_safe_fetch_and_store, label, fn, collection, unique_keys): label
            for label, (fn, collection, unique_keys) in tasks.items()
        }

        for future in as_completed(future_to_label):
            label = future_to_label[future]
            try:
                data, inserted_count, error = future.result()
                unified_data[label] = data
                run_summary["total_fetched"][label] = len(data) if isinstance(data, list) else len(data.keys())
                run_summary["total_inserted"][label] = inserted_count
                if error:
                    run_summary["errors"][label] = error
            except Exception as e:
                logging.error(f"{label}: Unhandled exception - {e}")
                traceback.print_exc()
                unified_data[label] = []
                run_summary["errors"][label] = str(e)

    insert_run_metadata("orchestration_run", run_summary)

    return unified_data

# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    logging.info("Starting Orchestrator...")
    start_time = time.time()

    # Step 1: Fetch & store all data
    data = orchestrate_parallel()
    end_time = time.time()

    for key, value in data.items():
        if isinstance(value, list):
            print(f"{key}: {len(value)} items")
        elif isinstance(value, dict):
            print(f"{key}: dict with {len(value)} keys")
        else:
            print(f"{key}: {type(value)}")

    print(f"\nOrchestration complete in {end_time - start_time:.2f} seconds!")
    logging.info(f"Orchestration complete in {end_time - start_time:.2f} seconds!")

    # --------------------------
    # Step 2: Preprocess Data
    # --------------------------
    print("\nStarting data preprocessing...")
    logging.info("Starting data preprocessing...")
    preprocess_data.__name__ = "__main__"  # allows running as script
    preprocess_data.main()  # call main() function from preprocess_data.py
    logging.info("Data preprocessing complete!")
