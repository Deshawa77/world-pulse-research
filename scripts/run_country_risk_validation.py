import argparse
import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.country_risk_validation import run_country_risk_backtest, run_country_risk_validation


def main() -> None:
    parser = argparse.ArgumentParser(description='Run country risk validation and optional historical backtest')
    parser.add_argument('--backtest', action='store_true', help='Run rolling historical backtest instead of point-in-time validation')
    parser.add_argument('--days', type=int, default=60, help='Window size in days for --backtest')
    args = parser.parse_args()

    if args.backtest:
        pprint(run_country_risk_backtest(days=max(1, args.days)))
        return

    pprint(run_country_risk_validation())


if __name__ == '__main__':
    main()
