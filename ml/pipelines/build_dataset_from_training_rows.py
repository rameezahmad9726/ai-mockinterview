"""
Build training parquet directly from backend JSONL training-row logs.

Usage:
    python ml/pipelines/build_dataset_from_training_rows.py
    python ml/pipelines/build_dataset_from_training_rows.py --jsonl backend/training_rows/interview_segments.jsonl --out data/processed/interview_segments_v1.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def build_dataset(jsonl_path: Path, out_path: Path) -> int:
    if not jsonl_path.exists():
        print(f"[WARN] Training row log not found: {jsonl_path}")
        return 0

    rows: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                print(f"[WARN] Skipping malformed JSONL row #{idx}: {exc}")
                continue
            rows.append(row)

    if not rows:
        print(f"[WARN] No rows found in {jsonl_path}")
        return 0

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"[DONE] Wrote {len(df)} rows to {out_path}")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--jsonl",
        default="backend/training_rows/interview_segments.jsonl",
        help="Input JSONL training rows path",
    )
    parser.add_argument(
        "--out",
        default="data/processed/interview_segments_v1.parquet",
        help="Output parquet path",
    )
    args = parser.parse_args()
    build_dataset(Path(args.jsonl), Path(args.out))


if __name__ == "__main__":
    main()

