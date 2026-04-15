"""
CLI sanity check for backend training-row JSONL logs.

Usage:
    python ml/pipelines/check_training_rows.py
    python ml/pipelines/check_training_rows.py --jsonl backend/training_rows/interview_segments.jsonl --sample-size 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Import from backend module (repo-root execution expected).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.modules.training_data_logger import get_training_row_log_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--jsonl",
        default="backend/training_rows/interview_segments.jsonl",
        help="Path to training row JSONL log",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="How many rows to inspect for required-field sanity",
    )
    args = parser.parse_args()

    status = get_training_row_log_status(Path(args.jsonl), sample_size=max(1, args.sample_size))
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()

