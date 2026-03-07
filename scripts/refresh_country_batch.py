import argparse
import os
import sys
from pprint import pprint

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processing.country_daily_risk import country_daily_refresh_if_due


def main():
    parser = argparse.ArgumentParser(description="Refresh the next batch of country map data.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-records", type=int, default=4)
    args = parser.parse_args()

    summary = country_daily_refresh_if_due(max_records=args.max_records, batch_size=args.batch_size)
    pprint(summary)


if __name__ == "__main__":
    main()
