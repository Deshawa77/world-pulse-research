from pprint import pprint

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.global_mood_validation import run_global_mood_validation


if __name__ == "__main__":
    pprint(run_global_mood_validation())
