from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

collectors = [
    "news",
    "gdelt",
    "wiki",
    "trends",
    "usgs",
    "weather",
    "coingecko",
    "fred",
    "frankfurter",
    "who",
    "twelvedata",
    "worldbank"
]

def run_collector(c):
    print(f"Starting {c}...")
    result = subprocess.run(["python", f"collectors/{c}.py"], capture_output=True, text=True)
    return c, result.stdout, result.stderr

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(run_collector, c) for c in collectors]
    for future in as_completed(futures):
        c, out, err = future.result()
        print(f"\nFinished {c}:\n{out}")
        if err:
            print(f"Errors in {c}:\n{err}")
