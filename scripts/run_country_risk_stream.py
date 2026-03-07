import threading

from backend.country_risk_stream import run_normalizer_loop, run_risk_loop


if __name__ == '__main__':
    threading.Thread(target=run_normalizer_loop, daemon=True).start()
    run_risk_loop()
