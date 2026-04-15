"""
Starter training script for speech_scorer_model_v1.

Usage:
    python ml/pipelines/train_speech.py --data data/processed/interview_segments_v1.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split


FEATURES = [
    "speech_wpm",
    "filler_count",
    "pause_ratio",
    "speech_word_count",
    "duration_sec",
]
TARGET = "label_clarity_1_10"


def train(data_path: Path, out_dir: Path) -> dict:
    df = pd.read_parquet(data_path)
    df = df.dropna(subset=FEATURES + [TARGET])

    x = df[FEATURES]
    y = df[TARGET]

    x_train, x_val, y_train, y_val = train_test_split(
        x, y, test_size=0.2, random_state=42
    )

    model = GradientBoostingRegressor(random_state=42)
    model.fit(x_train, y_train)
    pred = model.predict(x_val)
    mae = float(mean_absolute_error(y_val, pred))

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "speech_model.joblib")

    metrics = {
        "model_name": "speech_scorer_model_v1",
        "target": TARGET,
        "features": FEATURES,
        "mae": mae,
        "rows_train": int(len(x_train)),
        "rows_val": int(len(x_val)),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to parquet dataset")
    parser.add_argument(
        "--out",
        default="models/speech/v1",
        help="Output directory for artifacts",
    )
    args = parser.parse_args()

    metrics = train(Path(args.data), Path(args.out))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

