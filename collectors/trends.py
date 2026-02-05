from pytrends.request import TrendReq
import pandas as pd
import time

print("Script started...")

try:
    pytrends = TrendReq(hl='en-US', tz=360, timeout=(10,25))
    print("Connected to Google Trends")

    time.sleep(5)  # delay to avoid 429

    def get_trends(keyword="football"):
        print(f"Fetching trends for: {keyword}")

        pytrends.build_payload(
            kw_list=[keyword],
            timeframe='now 7-d',
            geo='',
            gprop=''
        )

        time.sleep(5)  # delay again

        data = pytrends.interest_over_time()
        return data

    keyword = "football"
    trends_data = get_trends(keyword)

    print("\n--- Google Trends Data ---")
    print(trends_data.head())

    if trends_data.empty:
        print("\n❌ No data returned from Google Trends")
    else:
        trends_data.to_csv("google_trends_data.csv")
        print("\n✅ Data saved to google_trends_data.csv")

except Exception as e:
    print("\n🔥 ERROR OCCURRED:")
    print(e)
