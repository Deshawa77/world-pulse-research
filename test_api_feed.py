import requests
import json

# Test the API endpoint
url = "http://127.0.0.1:8000/dashboard/global-intelligence-feed"
headers = {"x-api-key": "super_secure_api_key"}
params = {"limit": 3}

try:
    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 200:
        data = response.json()
        print("Sample feed items from API:")
        for item in data[:3]:
            print(f"  {item['country']}: {item['timestamp']} - {item['headline'][:50]}...")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Connection error: {e}")
    print("Make sure the backend is running!")

