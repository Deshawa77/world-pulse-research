
# utils.py
import os
from datetime import datetime, timezone

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")

def log_event(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")
