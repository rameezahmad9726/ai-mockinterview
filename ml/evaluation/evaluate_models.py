"""
Simple evaluator for exported model metrics.

Usage:
    python ml/evaluation/evaluate_models.py
"""

from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    behavior = _load(Path("models/behavior/v1/metrics.json"))
    speech = _load(Path("models/speech/v1/metrics.json"))

    report = {
        "behavior_model": behavior,
        "speech_model": speech,
    }
    out = Path("artifacts/model_eval_latest.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote evaluation report to {out}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

