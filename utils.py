
# utils.py
import os
import sys
from datetime import datetime, timezone

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")

def log_event(msg):
    ts = datetime.now(timezone.utc).isoformat()
    text_msg = str(msg)
    try:
        print(text_msg, flush=True)
    except UnicodeEncodeError:
        safe_msg = text_msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
        print(safe_msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {text_msg}\n")
