"""
Speech scorer model inference adapter.

Current artifact predicts clarity score (1-10). Confidence can be added later
once the training target is expanded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


FEATURES = [
    "speech_wpm",
    "filler_count",
    "pause_ratio",
    "speech_word_count",
    "duration_sec",
]


@dataclass
class SpeechInferenceResult:
    clarity_score: Optional[float]
    model_loaded: bool
    model_version: str
    features: Dict[str, float]
    error: Optional[str] = None


_speech_model = None
_speech_model_error: Optional[str] = None


def _model_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "models" / "speech" / "v1" / "speech_model.joblib"


def _load_model():
    global _speech_model, _speech_model_error
    if _speech_model is not None:
        return _speech_model
    if _speech_model_error is not None:
        return None
    try:
        import joblib

        path = _model_path()
        if not path.exists():
            _speech_model_error = f"Model artifact missing: {path}"
            return None
        _speech_model = joblib.load(path)
        return _speech_model
    except Exception as exc:
        _speech_model_error = str(exc)
        return None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _extract_features(speech: Dict[str, Any]) -> Dict[str, float]:
    return {
        "speech_wpm": _safe_float(speech.get("speaking_speed_wpm"), 0.0),
        "filler_count": _safe_float(
            speech.get("filler_words_count") if speech.get("filler_words_count") is not None else speech.get("filler_words"),
            0.0,
        ),
        "pause_ratio": _safe_float(
            speech.get("pause_ratio") if speech.get("pause_ratio") is not None else speech.get("silence_ratio"),
            0.0,
        ),
        "speech_word_count": _safe_float(speech.get("word_count"), 0.0),
        "duration_sec": _safe_float(
            speech.get("audio_duration_seconds")
            if speech.get("audio_duration_seconds") is not None
            else speech.get("duration_sec"),
            0.0,
        ),
    }


def infer_speech_clarity(speech: Dict[str, Any]) -> SpeechInferenceResult:
    model = _load_model()
    features = _extract_features(speech)
    if model is None:
        return SpeechInferenceResult(
            clarity_score=None,
            model_loaded=False,
            model_version="speech_scorer_model_v1",
            features=features,
            error=_speech_model_error or "Speech model unavailable",
        )

    try:
        x = [[features[name] for name in FEATURES]]
        pred = float(model.predict(x)[0])
        pred = max(1.0, min(10.0, pred))
        return SpeechInferenceResult(
            clarity_score=pred,
            model_loaded=True,
            model_version="speech_scorer_model_v1",
            features=features,
        )
    except Exception as exc:
        return SpeechInferenceResult(
            clarity_score=None,
            model_loaded=False,
            model_version="speech_scorer_model_v1",
            features=features,
            error=str(exc),
        )

