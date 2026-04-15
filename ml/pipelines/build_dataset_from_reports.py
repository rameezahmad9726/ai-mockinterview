"""
Build a training parquet dataset from backend report JSON files.

This script creates pseudo-labels from current pipeline outputs so training can
start before human-labeled data is available.

Usage:
    python ml/pipelines/build_dataset_from_reports.py
    python ml/pipelines/build_dataset_from_reports.py --reports-dir backend/reports --out data/processed/interview_segments_v1.parquet
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalized_emotion_histogram(emotion_counts: dict[str, Any]) -> dict[str, float]:
    if not isinstance(emotion_counts, dict) or not emotion_counts:
        return {}
    numeric = {str(k).lower(): _safe_float(v, 0.0) for k, v in emotion_counts.items()}
    total = sum(numeric.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 6) for k, v in numeric.items()}


def _emotion_switch_count(history: list[Any]) -> int:
    labels = [str(x).strip().lower() for x in history if str(x).strip()]
    if len(labels) <= 1:
        return 0
    switches = 0
    prev = labels[0]
    for cur in labels[1:]:
        if cur != prev:
            switches += 1
        prev = cur
    return switches


def _infer_duration_sec(speech: dict[str, Any]) -> float:
    # Prefer explicit duration if present, otherwise derive from words and wpm.
    for key in ("duration_sec", "audio_duration_sec", "duration_seconds"):
        if key in speech and speech.get(key) is not None:
            return max(0.0, _safe_float(speech.get(key), 0.0))
    wc = _safe_int(speech.get("word_count"), 0)
    wpm = _safe_float(speech.get("speaking_speed_wpm"), 0.0)
    if wc > 0 and wpm > 0:
        return round((wc / wpm) * 60.0, 3)
    return 0.0


def _infer_pause_ratio(speech: dict[str, Any]) -> float:
    for key in ("pause_ratio", "silence_ratio"):
        if key in speech and speech.get(key) is not None:
            return max(0.0, min(1.0, _safe_float(speech.get(key), 0.0)))
    return 0.0


def _extract_row(payload: dict[str, Any], source_path: Path) -> dict[str, Any]:
    report = payload.get("report", payload)

    emotion = report.get("emotion_analysis", {}) if isinstance(report, dict) else {}
    body = report.get("body_language", {}) if isinstance(report, dict) else {}
    speech = report.get("speech_analysis", {}) if isinstance(report, dict) else {}
    final_summary = report.get("final_summary", {}) if isinstance(report, dict) else {}
    behavior = report.get("behavior_insights", {}) if isinstance(report, dict) else {}

    recommendation = final_summary.get("recommendation", {})
    if isinstance(recommendation, dict):
        label_recommendation = 1 if bool(recommendation.get("recommended")) else 0
    else:
        label_recommendation = 0

    label_conf = _safe_float(final_summary.get("confidence_score"), 5.0)
    label_clarity = _safe_float(final_summary.get("clarity_score"), 5.0)
    label_trend = str(behavior.get("trend") or "stable").lower()
    if label_trend not in {"improved", "stable", "declined"}:
        label_trend = "stable"

    emotion_counts = emotion.get("emotion_counts") if isinstance(emotion, dict) else {}
    emotion_history = emotion.get("emotion_history") if isinstance(emotion, dict) else []

    transcript = str(speech.get("transcript") or "").strip()
    duration_sec = _infer_duration_sec(speech)

    return {
        "session_id": source_path.stem,
        "segment_id": "full_interview",
        "question_index": 0,
        "segment_start_ms": 0,
        "segment_end_ms": int(duration_sec * 1000) if duration_sec > 0 else 0,
        "duration_sec": duration_sec,
        "emotion_dominant": str(emotion.get("dominant_emotion") or "unknown").lower(),
        "emotion_histogram": _normalized_emotion_histogram(emotion_counts if isinstance(emotion_counts, dict) else {}),
        "emotion_switch_count": _emotion_switch_count(emotion_history if isinstance(emotion_history, list) else []),
        "posture_score_10": _safe_float(body.get("posture_score"), 0.0),
        "movement_score": _safe_float(body.get("movement_score"), 0.0),
        "gesture_label": str(body.get("gesture_label") or ""),
        "eye_contact_avg": _safe_float(behavior.get("eye_contact_score"), 0.0),
        "eye_contact_std": 0.0,
        "speech_word_count": _safe_int(speech.get("word_count"), 0),
        "speech_wpm": _safe_float(speech.get("speaking_speed_wpm"), 0.0),
        "filler_count": _safe_int(
            speech.get("filler_words_count") if speech.get("filler_words_count") is not None else speech.get("filler_words"),
            0,
        ),
        "pause_ratio": _infer_pause_ratio(speech),
        "transcript_text": transcript,
        "tone_summary": str(speech.get("tone_analysis") or ""),
        "recording_quality": "fair",
        "lighting_condition": "unknown",
        "accent_region": "unknown",
        "label_confidence_1_10": max(1.0, min(10.0, label_conf)),
        "label_clarity_1_10": max(1.0, min(10.0, label_clarity)),
        "label_trend": label_trend,
        "label_recommendation": label_recommendation,
        "rater_count": 1,
        "label_disagreement_std": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_dataset(reports_dir: Path, out_path: Path) -> int:
    json_files = sorted(reports_dir.glob("*.json"))
    rows: list[dict[str, Any]] = []
    for file_path in json_files:
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Skipping unreadable JSON {file_path.name}: {exc}")
            continue
        rows.append(_extract_row(payload, file_path))

    if not rows:
        print(f"[WARN] No report JSON rows found in {reports_dir}")
        return 0

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"[DONE] Wrote {len(df)} rows to {out_path}")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reports-dir",
        default="backend/reports",
        help="Directory containing report JSON files",
    )
    parser.add_argument(
        "--out",
        default="data/processed/interview_segments_v1.parquet",
        help="Output parquet path",
    )
    args = parser.parse_args()

    build_dataset(Path(args.reports_dir), Path(args.out))


if __name__ == "__main__":
    main()

