import collectors.news as news
# import collectors.reddit as reddit
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

from database.mongo import insert, insert_run_metadata, db
import time, traceback, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from processing import preprocess_data, nlp_analysis, topic_modeling_with_nlp
from processing.global_crisis_detector import detect_crisis
from processing.daily_feature_builder import build_daily_features
from monitoring.email_alert import send_email_alert
from processing.crisis_by_country import crisis_heatmap
from processing.crisis_forecast import forecast_sentiment
from processing.ai_summary import generate_summary
from processing.global_risk import compute_global_risk

logging.basicConfig(
    filename="orchestrator.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def _clean_topic(topic):
    if not topic:
        return None
    topic = str(topic).strip()
    if topic in ["Other", ", ,", ", , ", "921, ,", "1494, ,"]:
        return None
    if topic.replace(",", "").strip().isdigit():
        return None
    if len(topic) < 3:
        return None
    return topic

def get_top_daily_topics(limit=5):
    topic_counts = {}
    for col in ["news", "gdelt"]:
        for doc in db[col].find({}, {"data.topic": 1}):
            raw_topic = doc.get("data", {}).get("topic", "")
            if not raw_topic:
                continue
            for t in [t.strip() for t in raw_topic.split(",") if t.strip()]:
                t_clean = _clean_topic(t)
                if t_clean:
                    topic_counts[t_clean] = topic_counts.get(t_clean, 0) + 1
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    if not sorted_topics:
        return ["multiple global factors"]
    return [t[0] for t in sorted_topics[:limit]]

def _safe_fetch_and_store(label, fetch_fn, collection_name, unique_keys=None):
    try:
        data = fetch_fn()
        count_fetched = len(data) if isinstance(data, list) else len(data.keys())
        logging.info(f"{label}: Fetched {count_fetched} items")
        try:
            inserted_count = insert(collection_name, data, unique_keys=unique_keys)
            logging.info(f"{label}: Inserted {inserted_count} new items into {collection_name}")
        except Exception as e:
            logging.error(f"{label}: Mongo insert failed - {e}")
            traceback.print_exc()
            inserted_count = 0
        return data, inserted_count, None
    except Exception as e:
        logging.error(f"{label}: Fetch failed - {e}")
        traceback.print_exc()
        return [], 0, str(e)

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

def run_pipeline():
    logging.info("Starting World Pulse Pipeline...")
    start_time = time.time()

    data = orchestrate_parallel()
    print(f"\nOrchestration complete in {time.time() - start_time:.2f} seconds!")

    try:
        print("\nStarting preprocessing...")
        preprocess_data.main()
        logging.info("Preprocessing complete")
    except Exception as e:
        logging.error(f"Preprocessing error: {e}")
        traceback.print_exc()

    try:
        print("\nRunning NLP sentiment analysis...")
        nlp_analysis.main()
    except Exception as e:
        logging.error(f"NLP error: {e}")
        traceback.print_exc()

    try:
        print("\nBuilding daily features...")
        build_daily_features()
    except Exception as e:
        logging.error(f"build_daily_features error: {e}")
        traceback.print_exc()

    try:
        print("\nRunning topic modeling...")
        topic_modeling_with_nlp.main()
    except Exception as e:
        logging.error(f"Topic modeling error: {e}")
        traceback.print_exc()

    try:
        print("\nRunning Global Crisis Detector...")
        detect_crisis(email_alert_func=send_email_alert)
    except Exception as e:
        logging.error(f"Crisis detector error: {e}")
        traceback.print_exc()

    try:
        print("\nGenerating crisis heatmap by country...")
        crisis_heatmap()
    except Exception as e:
        logging.error(f"Crisis heatmap error: {e}")
        traceback.print_exc()

    try:
        print("\nForecasting tomorrow's sentiment...")
        forecast_sentiment()
    except Exception as e:
        logging.error(f"Forecast error: {e}")
        traceback.print_exc()

    # ---------------------
    # AI Summary + Risk Score + Save to Mongo History
    # ---------------------
    try:
        print("\nGenerating executive AI summary...")
        summary_text = generate_summary()
        risk_score, top_topics = 0, []

        try:
            risk_score, top_topics = compute_global_risk()
        except Exception:
            pass

        print(summary_text)
        top_topics_today = get_top_daily_topics()
        print("Top topics today:", ", ".join(top_topics_today))

        # Save risk to Mongo history
        try:
            db.global_risk_history.insert_one({
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "risk_score": risk_score,
                "top_topics": top_topics,
                "updated_at": datetime.utcnow()
            })
            logging.info("Saved global risk history for today")
        except Exception as e:
            logging.error(f"Failed to save global risk history: {e}")
            traceback.print_exc()

        # Optional email alert
        if risk_score > 50:
            topics_text = ", ".join(top_topics) if top_topics else "multiple global factors"
            send_email_alert(
                subject=f"World Pulse Risk Update: {risk_score}",
                message=summary_text + f"\n\nTop Topics: {topics_text}"
            )

    except Exception as e:
        logging.error(f"AI summary error: {e}")
        traceback.print_exc()

    logging.info("World Pulse Pipeline Completed")

if __name__ == "__main__":
    CHECK_INTERVAL = 60 * 60
    print("Starting hourly World Pulse monitoring...")
    logging.info("Starting hourly World Pulse monitoring...")

    # Print today's global risk immediately on script start
    try:
        risk, topics = compute_global_risk()
        print(f"[GLOBAL RISK] {datetime.utcnow().date()}: {risk} → Top Topics: {topics}")
    except Exception as e:
        print(f"Could not compute global risk: {e}")

    while True:
        try:
            print("\nRunning full pipeline...")
            logging.info("Running full pipeline...")
            run_pipeline()
        except Exception as e:
            print("Monitoring error:", e)
            logging.error(f"Monitoring error: {e}")
        print(f"Sleeping for {CHECK_INTERVAL/60:.0f} minutes...")
        logging.info(f"Sleeping for {CHECK_INTERVAL/60:.0f} minutes...")
        time.sleep(CHECK_INTERVAL)

