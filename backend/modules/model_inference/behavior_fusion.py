"""
Behavior fusion model inference adapter.

Phase-oriented design:
- Safe to import even when model artifacts are missing.
- Returns rich metadata for dual-run logging.
- Never throws into API path; caller decides fallback behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


FEATURES = [
    "posture_score_10",
    "movement_score",
    "eye_contact_avg",
    "speech_wpm",
    "filler_count",
    "duration_sec",
]


@dataclass
class BehaviorInferenceResult:
    confidence_score: Optional[float]
    model_loaded: bool
    model_version: str
    features: Dict[str, float]
    error: Optional[str] = None


_behavior_model = None
_behavior_model_error: Optional[str] = None


def _model_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "models" / "behavior" / "v1" / "behavior_model.joblib"


def _load_model():
    global _behavior_model, _behavior_model_error
    if _behavior_model is not None:
        return _behavior_model
    if _behavior_model_error is not None:
        return None
    try:
        import joblib

        path = _model_path()
        if not path.exists():
            _behavior_model_error = f"Model artifact missing: {path}"
            return None
        _behavior_model = joblib.load(path)
        return _behavior_model
    except Exception as exc:  # pragma: no cover - defensive runtime behavior
        _behavior_model_error = str(exc)
        return None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _extract_features(report: Dict[str, Any], behavior_insights: Dict[str, Any]) -> Dict[str, float]:
    final_summary = report.get("final_summary", {})
    speech = report.get("speech_analysis", {})
    return {
        "posture_score_10": _safe_float(final_summary.get("posture_score"), 0.0),
        "movement_score": _safe_float(final_summary.get("movement_score"), 0.0),
        "eye_contact_avg": _safe_float(behavior_insights.get("eye_contact_score"), 0.0),
        "speech_wpm": _safe_float(final_summary.get("speaking_speed_wpm"), 0.0),
        "filler_count": _safe_float(
            speech.get("filler_words_count") if speech.get("filler_words_count") is not None else speech.get("filler_words"),
            0.0,
        ),
        "duration_sec": _safe_float(
            speech.get("audio_duration_seconds")
            if speech.get("audio_duration_seconds") is not None
            else speech.get("duration_sec"),
            0.0,
        ),
    }


def infer_behavior_confidence(report: Dict[str, Any], behavior_insights: Dict[str, Any]) -> BehaviorInferenceResult:
    model = _load_model()
    features = _extract_features(report, behavior_insights)
    if model is None:
        return BehaviorInferenceResult(
            confidence_score=None,
            model_loaded=False,
            model_version="behavior_fusion_model_v1",
            features=features,
            error=_behavior_model_error or "Behavior model unavailable",
        )

    try:
        # Preserve feature order expected by training artifact.
        x = [[features[name] for name in FEATURES]]
        pred = float(model.predict(x)[0])
        pred = max(0.0, min(10.0, pred))
        return BehaviorInferenceResult(
            confidence_score=pred,
            model_loaded=True,
            model_version="behavior_fusion_model_v1",
            features=features,
        )
    except Exception as exc:
        return BehaviorInferenceResult(
            confidence_score=None,
            model_loaded=False,
            model_version="behavior_fusion_model_v1",
            features=features,
            error=str(exc),
        )

