import requests

BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

def fetch_earthquakes():
    response = requests.get(BASE_URL)
    data = response.json()
    
    earthquakes = []
    for feature in data.get("features", []):
        prop = feature["properties"]
        earthquakes.append({
            "place": prop["place"],
            "magnitude": prop["mag"],
            "time": prop["time"],  # timestamp in ms
            "url": prop["url"]
        })
    return earthquakes

if __name__ == "__main__":
    quakes = fetch_earthquakes()
    if quakes:
        for q in quakes[:5]:  # show first 5
            print(q)
    else:
        print("No earthquakes found.")
