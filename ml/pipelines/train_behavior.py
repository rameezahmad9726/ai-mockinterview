"""
Starter training script for behavior_fusion_model_v1.

Usage:
    python ml/pipelines/train_behavior.py --data data/processed/interview_segments_v1.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split


FEATURES = [
    "posture_score_10",
    "movement_score",
    "eye_contact_avg",
    "speech_wpm",
    "filler_count",
    "duration_sec",
]
TARGET = "label_confidence_1_10"


def train(data_path: Path, out_dir: Path) -> dict:
    df = pd.read_parquet(data_path)
    df = df.dropna(subset=FEATURES + [TARGET])

    x = df[FEATURES]
    y = df[TARGET]

    x_train, x_val, y_train, y_val = train_test_split(
        x, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    pred = model.predict(x_val)
    mae = float(mean_absolute_error(y_val, pred))

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "behavior_model.joblib")

    metrics = {
        "model_name": "behavior_fusion_model_v1",
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
        default="models/behavior/v1",
        help="Output directory for artifacts",
    )
    args = parser.parse_args()

    metrics = train(Path(args.data), Path(args.out))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

