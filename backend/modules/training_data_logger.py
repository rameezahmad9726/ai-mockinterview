"""
Phase 0 training-data logging utilities.

Writes one JSONL row per analyzed interview so model training datasets can be
built continuously without manual extraction from reports.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REQUIRED_FIELDS = [
    "session_id",
    "segment_id",
    "duration_sec",
    "emotion_dominant",
    "posture_score_10",
    "movement_score",
    "eye_contact_avg",
    "speech_word_count",
    "speech_wpm",
    "filler_count",
    "transcript_text",
    "label_confidence_1_10",
    "label_clarity_1_10",
    "label_trend",
    "label_recommendation",
    "created_at",
]


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
    for key in ("duration_sec", "audio_duration_seconds", "audio_duration_sec", "duration_seconds"):
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


def build_training_row(report: Dict[str, Any], session_id: str, segment_id: str = "full_interview") -> Dict[str, Any]:
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
        "session_id": session_id,
        "segment_id": segment_id,
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


def append_training_row_jsonl(row: Dict[str, Any], out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_training_row_log_status(jsonl_path: Path, sample_size: int = 100) -> Dict[str, Any]:
    """
    Return row count, file metadata, and lightweight schema sanity checks.
    """
    if not jsonl_path.exists():
        return {
            "exists": False,
            "path": str(jsonl_path),
            "row_count": 0,
            "last_updated": None,
            "checked_rows": 0,
            "invalid_rows": 0,
            "missing_required_fields": {},
        }

    stat = jsonl_path.stat()
    row_count = 0
    checked_rows = 0
    invalid_rows = 0
    missing_required_fields: Dict[str, int] = {}

    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row_count += 1
            if checked_rows >= sample_size:
                continue
            checked_rows += 1
            try:
                row = json.loads(line)
            except Exception:
                invalid_rows += 1
                continue

            for key in REQUIRED_FIELDS:
                if key not in row or row.get(key) is None or row.get(key) == "":
                    missing_required_fields[key] = missing_required_fields.get(key, 0) + 1

    return {
        "exists": True,
        "path": str(jsonl_path),
        "row_count": row_count,
        "last_updated": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "file_size_bytes": stat.st_size,
        "checked_rows": checked_rows,
        "invalid_rows": invalid_rows,
        "missing_required_fields": missing_required_fields,
        "schema_ok": invalid_rows == 0 and not missing_required_fields,
    }

