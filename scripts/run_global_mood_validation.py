import argparse
import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.global_mood_validation import run_global_mood_backtest, run_global_mood_validation


def main() -> None:
    parser = argparse.ArgumentParser(description='Run global mood validation and optional historical backtest')
    parser.add_argument('--backtest', action='store_true', help='Run rolling historical backtest instead of point-in-time validation')
    parser.add_argument('--days', type=int, default=60, help='Window size in days for --backtest')
    args = parser.parse_args()

    if args.backtest:
        pprint(run_global_mood_backtest(days=max(1, args.days)))
        return

    pprint(run_global_mood_validation())


if __name__ == '__main__':
    main()
