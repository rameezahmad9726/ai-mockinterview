"""
Phase gate checker for objective go/no-go decisions.

Usage:
    python ml/evaluation/check_phase_gates.py
    python ml/evaluation/check_phase_gates.py --phase phase0_to_phase1
    python ml/evaluation/check_phase_gates.py --metrics artifacts/model_eval_latest.json --baseline artifacts/baseline_v1_metrics.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.modules.training_data_logger import get_training_row_log_status


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _check_phase0_to_phase1(
    training_jsonl: Path,
    dataset_parquet: Path,
    baseline_metrics: Path,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    status = get_training_row_log_status(training_jsonl, sample_size=200)

    checks.append(
        {
            "name": "training_rows_exist",
            "pass": bool(status.get("exists")),
            "details": status.get("path"),
        }
    )
    checks.append(
        {
            "name": "training_rows_schema_ok",
            "pass": bool(status.get("schema_ok")),
            "details": {
                "invalid_rows": status.get("invalid_rows"),
                "missing_required_fields": status.get("missing_required_fields"),
            },
        }
    )
    checks.append(
        {
            "name": "dataset_parquet_exists",
            "pass": dataset_parquet.exists(),
            "details": str(dataset_parquet),
        }
    )
    checks.append(
        {
            "name": "minimum_rows_200",
            "pass": int(status.get("row_count", 0)) >= 200,
            "details": {"row_count": int(status.get("row_count", 0))},
        }
    )
    checks.append(
        {
            "name": "baseline_metrics_exists",
            "pass": baseline_metrics.exists(),
            "details": str(baseline_metrics),
        }
    )

    return {"phase": "phase0_to_phase1", "checks": checks}


def _check_phase1_to_phase2(metrics_path: Path, baseline_path: Path) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    metrics = _read_json(metrics_path)
    baseline = _read_json(baseline_path)

    checks.append(
        {
            "name": "metrics_artifact_exists",
            "pass": metrics is not None,
            "details": str(metrics_path),
        }
    )
    if metrics is None:
        return {"phase": "phase1_to_phase2", "checks": checks}

    behavior = metrics.get("behavior_model", {})
    rows_val = int(behavior.get("rows_val", 0) or 0)
    checks.append(
        {
            "name": "behavior_rows_val_min_50",
            "pass": rows_val >= 50,
            "details": {"rows_val": rows_val},
        }
    )

    # Improvement check is only meaningful if baseline has behavior_mae.
    improved = False
    details: Dict[str, Any] = {"reason": "baseline_missing"}
    if baseline:
        baseline_behavior_mae = baseline.get("behavior_mae")
        current_mae = behavior.get("mae")
        if baseline_behavior_mae is not None and current_mae is not None and baseline_behavior_mae > 0:
            delta = (baseline_behavior_mae - float(current_mae)) / float(baseline_behavior_mae)
            improved = delta >= 0.15
            details = {
                "baseline_behavior_mae": baseline_behavior_mae,
                "current_behavior_mae": current_mae,
                "improvement_ratio": delta,
            }
    checks.append(
        {
            "name": "behavior_mae_improvement_15pct",
            "pass": improved,
            "details": details,
        }
    )

    return {"phase": "phase1_to_phase2", "checks": checks}


def _check_phase2_to_phase3(metrics_path: Path, baseline_path: Path) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    metrics = _read_json(metrics_path)
    baseline = _read_json(baseline_path)

    checks.append(
        {
            "name": "metrics_artifact_exists",
            "pass": metrics is not None,
            "details": str(metrics_path),
        }
    )
    if metrics is None:
        return {"phase": "phase2_to_phase3", "checks": checks}

    speech = metrics.get("speech_model", {})
    rows_val = int(speech.get("rows_val", 0) or 0)
    checks.append(
        {
            "name": "speech_rows_val_min_50",
            "pass": rows_val >= 50,
            "details": {"rows_val": rows_val},
        }
    )

    improved = False
    details: Dict[str, Any] = {"reason": "baseline_missing"}
    if baseline:
        baseline_speech_mae = baseline.get("speech_mae")
        current_mae = speech.get("mae")
        if baseline_speech_mae is not None and current_mae is not None and baseline_speech_mae > 0:
            delta = (baseline_speech_mae - float(current_mae)) / float(baseline_speech_mae)
            improved = delta >= 0.10
            details = {
                "baseline_speech_mae": baseline_speech_mae,
                "current_speech_mae": current_mae,
                "improvement_ratio": delta,
            }
    checks.append(
        {
            "name": "speech_mae_improvement_10pct",
            "pass": improved,
            "details": details,
        }
    )

    return {"phase": "phase2_to_phase3", "checks": checks}


def _finalize(result: Dict[str, Any]) -> Dict[str, Any]:
    checks = result.get("checks", [])
    result["pass"] = all(bool(c.get("pass")) for c in checks)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=["phase0_to_phase1", "phase1_to_phase2", "phase2_to_phase3", "all"],
        default="all",
    )
    parser.add_argument(
        "--training-jsonl",
        default="backend/training_rows/interview_segments.jsonl",
    )
    parser.add_argument(
        "--dataset",
        default="data/processed/interview_segments_v1.parquet",
    )
    parser.add_argument(
        "--metrics",
        default="artifacts/model_eval_latest.json",
    )
    parser.add_argument(
        "--baseline",
        default="artifacts/baseline_v1_metrics.json",
    )
    args = parser.parse_args()

    training_jsonl = Path(args.training_jsonl)
    dataset = Path(args.dataset)
    metrics = Path(args.metrics)
    baseline = Path(args.baseline)

    outputs: List[Dict[str, Any]] = []
    if args.phase in ("phase0_to_phase1", "all"):
        outputs.append(_finalize(_check_phase0_to_phase1(training_jsonl, dataset, baseline)))
    if args.phase in ("phase1_to_phase2", "all"):
        outputs.append(_finalize(_check_phase1_to_phase2(metrics, baseline)))
    if args.phase in ("phase2_to_phase3", "all"):
        outputs.append(_finalize(_check_phase2_to_phase3(metrics, baseline)))

    overall_pass = all(o.get("pass", False) for o in outputs) if outputs else False
    result = {
        "overall_pass": overall_pass,
        "results": outputs,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

