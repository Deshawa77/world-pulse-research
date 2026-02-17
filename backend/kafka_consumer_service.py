import os
import json
from datetime import datetime
from backend.kafka_client import get_consumer

DATA_LAKE_PATH = "data_lake/raw"
consumer = get_consumer()

for message in consumer:
    event = message.value
    source = event["source"]

    folder = os.path.join(DATA_LAKE_PATH, source)
    os.makedirs(folder, exist_ok=True)

    filename = datetime.utcnow().strftime("%Y-%m-%d") + ".json"
    file_path = os.path.join(folder, filename)

    with open(file_path, "a") as f:
        f.write(json.dumps(event) + "\n")

    print(f"Saved {source} to data lake")
