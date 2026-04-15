"""
Interview-focused behavior synthesis from per-frame emotion, posture, and eye-contact signals.

Designed for extension without rewriting core logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

# --- Tunable weights (single place to adjust scoring / thresholds) ---

BASE_CONFIDENCE = 0.5

EMOTION_STATE_SCORE: Dict[str, float] = {
    "confident": 0.4,
    "calm": 0.4,
    "low_confidence": -0.2,
    "nervous": -0.3,
    "stressed": -0.3,
}

POSTURE_SCORE: Dict[str, float] = {
    "straight": 0.3,
    "bad": -0.2,
}

# Eye contact: contribution = weight * per-frame score (0–1), then clamped in aggregate
EYE_CONTACT_WEIGHT = 0.3

# Feedback thresholds (on mean eye-contact score)
EYE_CONTACT_LOW_THRESHOLD = 0.4
EYE_CONTACT_HIGH_THRESHOLD = 0.7

# Minimum 0–10 posture score (from body_language) to count as "straight"
POSTURE_STRAIGHT_MIN_SCORE = 6.0

# Trend: difference between late vs early segment (on internal 0–1 quality scale)
TREND_IMPROVE_THRESHOLD = 0.08
TREND_DECLINE_THRESHOLD = 0.08

# Map raw model labels (case-insensitive) to interview-relevant states
RAW_EMOTION_TO_STATE: Dict[str, str] = {
    "happy": "confident",
    "neutral": "calm",
    "sad": "low_confidence",
    "fear": "nervous",
    "angry": "stressed",
    "surprise": "calm",
    "disgust": "stressed",
}

TrendLabel = Literal["improved", "declined", "stable"]


class TrendResult(TypedDict, total=False):
    """Structured trend output from ``analyze_trend``."""

    trend: TrendLabel
    score_early: float
    score_late: float


def map_emotion(emotion: str) -> str:
    """
    Map a raw vision-model emotion label to an interview-relevant state.

    Unknown labels default to ``calm`` so the pipeline stays resilient.
    """
    if not emotion:
        return "calm"
    key = emotion.strip().lower()
    return RAW_EMOTION_TO_STATE.get(key, "calm")


def posture_score_to_label(score_10: float) -> str:
    """Convert a 0–10 posture score to ``straight`` or ``bad``."""
    return "straight" if score_10 >= POSTURE_STRAIGHT_MIN_SCORE else "bad"


def compute_confidence(
    emotion: str,
    posture: str,
    eye_contact_score: Optional[float] = None,
) -> float:
    """
    Combine mapped emotion, posture, and optional eye-contact into a 0–1 confidence score.

    ``emotion`` should already be mapped (e.g. ``confident``, ``nervous``).
    ``posture`` is ``straight`` or ``bad``.
    If ``eye_contact_score`` is ``None``, the eye-contact term is omitted (backward compatible).
    Otherwise adds ``EYE_CONTACT_WEIGHT * eye_contact_score`` (clamped per term).
    """
    emo_delta = EMOTION_STATE_SCORE.get(emotion, 0.0)
    pos_delta = POSTURE_SCORE.get(posture, POSTURE_SCORE["bad"])
    total = BASE_CONFIDENCE + emo_delta + pos_delta
    if eye_contact_score is not None:
        ec = float(max(0.0, min(1.0, eye_contact_score)))
        total += EYE_CONTACT_WEIGHT * ec
    return float(max(0.0, min(1.0, total)))


def _frame_quality_score(
    mapped_emotion: str,
    posture: str,
    eye_contact: Optional[float] = None,
) -> float:
    """Internal 0–1 scalar for trend comparison (not the same as compute_confidence)."""
    emo_rank = {
        "confident": 1.0,
        "calm": 0.85,
        "low_confidence": 0.45,
        "nervous": 0.35,
        "stressed": 0.3,
    }.get(mapped_emotion, 0.7)
    pos_rank = 1.0 if posture == "straight" else 0.4
    # Blend; eye contact nudges trend when present
    if eye_contact is None:
        return 0.6 * emo_rank + 0.4 * pos_rank
    ec = float(max(0.0, min(1.0, eye_contact)))
    return 0.5 * emo_rank + 0.35 * pos_rank + 0.15 * ec


def analyze_trend(frames_data: List[Dict[str, Any]]) -> TrendResult:
    """
    Detect improvement, decline, or stability over the interview segment.

    ``frames_data`` items should include ``emotion`` (mapped) and ``posture``;
    optional ``eye_contact`` (float 0–1) refines the quality curve.
    """
    if not frames_data:
        return {"trend": "stable", "score_early": 0.0, "score_late": 0.0}

    qualities = [
        _frame_quality_score(
            str(f.get("emotion", "calm")),
            str(f.get("posture", "bad")),
            f.get("eye_contact") if f.get("eye_contact") is not None else None,
        )
        for f in frames_data
    ]
    n = len(qualities)
    third = max(1, n // 3)
    early = sum(qualities[:third]) / third
    late = sum(qualities[-third:]) / third

    diff = late - early
    if diff > TREND_IMPROVE_THRESHOLD:
        trend: TrendLabel = "improved"
    elif diff < -TREND_DECLINE_THRESHOLD:
        trend = "declined"
    else:
        trend = "stable"

    return {"trend": trend, "score_early": early, "score_late": late}


def generate_feedback(
    confidence_score: float,
    trend: TrendResult,
    avg_eye_contact: Optional[float] = None,
    eye_contact_available: bool = True,
) -> str:
    """
    Produce human-readable feedback from aggregate confidence, trend, and optional eye contact.

    Eye-contact sentences are skipped when ``eye_contact_available`` is False (e.g. model not loaded).
    """
    trend_label = trend.get("trend", "stable")
    parts: List[str] = []

    if confidence_score >= 0.72:
        parts.append("You appeared confident throughout the interview.")
    elif confidence_score >= 0.45:
        parts.append(
            "You showed moderate confidence; you can still improve posture and facial expressiveness."
        )
    else:
        parts.append(
            "You seemed nervous or low-energy. Try to relax, breathe steadily, and maintain upright posture."
        )

    if trend_label == "improved":
        parts.append("You improved as the interview progressed.")
    elif trend_label == "declined":
        parts.append("Energy and composure dipped toward the end; finish with the same focus you started with.")
    else:
        parts.append("Your presence stayed fairly consistent across the recording.")

    if eye_contact_available and avg_eye_contact is not None:
        if avg_eye_contact < EYE_CONTACT_LOW_THRESHOLD:
            parts.append("Try to maintain better eye contact with the camera.")
        elif avg_eye_contact > EYE_CONTACT_HIGH_THRESHOLD:
            parts.append("Good job maintaining eye contact.")

    return " ".join(parts)


def merge_per_frame_signals(
    emotion_per_frame: Optional[List[Dict[str, Any]]],
    posture_per_frame: Optional[List[Dict[str, Any]]],
    eye_contact_per_frame: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Align emotion, posture, and eye contact by frame file path.

    Missing pose defaults to ``bad`` (conservative). Missing eye row leaves
    ``eye_contact`` unset (omits eye term in ``compute_confidence`` for that frame).
    """
    if not emotion_per_frame:
        return []

    posture_by_path: Dict[str, str] = {}
    if posture_per_frame:
        for row in posture_per_frame:
            p = row.get("path")
            if p:
                posture_by_path[str(p)] = str(row.get("posture", "bad"))

    eye_by_path: Dict[str, float] = {}
    if eye_contact_per_frame:
        for row in eye_contact_per_frame:
            p = row.get("path")
            if p is None:
                continue
            try:
                eye_by_path[str(p)] = float(row.get("eye_contact", 0.0))
            except (TypeError, ValueError):
                eye_by_path[str(p)] = 0.0

    frames_data: List[Dict[str, Any]] = []
    for i, row in enumerate(emotion_per_frame, start=1):
        path = str(row.get("path", ""))
        raw = str(row.get("label", "neutral"))
        mapped = map_emotion(raw)
        posture = posture_by_path.get(path, "bad")
        eye_val: Optional[float] = None
        if path in eye_by_path:
            eye_val = eye_by_path[path]
        entry: Dict[str, Any] = {
            "frame": i,
            "path": path,
            "emotion_raw": raw,
            "emotion": mapped,
            "posture": posture,
        }
        if eye_val is not None:
            entry["eye_contact"] = eye_val
        frames_data.append(entry)
    return frames_data


def summarize_behavior(
    frames_data: List[Dict[str, Any]],
    *,
    avg_eye_contact: Optional[float] = None,
    eye_contact_available: bool = True,
) -> Dict[str, Any]:
    """
    Aggregate per-frame rows into confidence score, trend label, feedback, and eye-contact summary.

    Returns the structure expected by the API / report layer.
    """
    if not frames_data:
        trend: TrendResult = {"trend": "stable", "score_early": 0.0, "score_late": 0.0}
        return {
            "confidence_score": round(BASE_CONFIDENCE, 3),
            "trend": trend["trend"],
            "feedback": generate_feedback(
                BASE_CONFIDENCE,
                trend,
                avg_eye_contact=0.0,
                eye_contact_available=eye_contact_available,
            ),
            "eye_contact_score": round(0.0, 3),
            "frames_analyzed": 0,
            "per_frame": [],
        }

    confidences = [
        compute_confidence(
            str(f["emotion"]),
            str(f["posture"]),
            f.get("eye_contact") if f.get("eye_contact") is not None else None,
        )
        for f in frames_data
    ]
    avg_confidence = sum(confidences) / len(confidences)
    trend = analyze_trend(frames_data)

    eye_scores = [float(f["eye_contact"]) for f in frames_data if f.get("eye_contact") is not None]
    if eye_scores:
        computed_avg_eye = sum(eye_scores) / len(eye_scores)
    else:
        computed_avg_eye = avg_eye_contact if avg_eye_contact is not None else 0.0

    feedback = generate_feedback(
        avg_confidence,
        trend,
        avg_eye_contact=computed_avg_eye,
        eye_contact_available=eye_contact_available,
    )

    return {
        "confidence_score": round(float(max(0.0, min(1.0, avg_confidence))), 3),
        "trend": trend["trend"],
        "feedback": feedback,
        "eye_contact_score": round(float(computed_avg_eye), 3),
        "frames_analyzed": len(frames_data),
        "per_frame": [
            {
                "frame": f["frame"],
                "emotion": f["emotion"],
                "posture": f["posture"],
                **({"eye_contact": round(float(f["eye_contact"]), 3)} if f.get("eye_contact") is not None else {}),
            }
            for f in frames_data
        ],
    }


def build_behavior_insights(
    emotion_data: Dict[str, Any],
    body_data: Dict[str, Any],
    eye_contact_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build behavior summary from emotion, body language, and optional eye-contact payloads.

    ``eye_contact_data`` may include ``eye_contact_per_frame``, ``avg_eye_contact``,
    and ``eye_contact_available`` (from ``eye_contact.analyze_eye_contact_frames_dir``).
    """
    emotion_pf = emotion_data.get("emotion_per_frame")
    posture_pf = body_data.get("posture_per_frame")
    eye_pf = None
    avg_eye: Optional[float] = None
    eye_available = False
    if eye_contact_data and isinstance(eye_contact_data, dict):
        eye_available = bool(eye_contact_data.get("eye_contact_available", True))
        raw = eye_contact_data.get("eye_contact_per_frame")
        if isinstance(raw, list):
            eye_pf = raw
        if eye_contact_data.get("avg_eye_contact") is not None:
            try:
                avg_eye = float(eye_contact_data["avg_eye_contact"])
            except (TypeError, ValueError):
                avg_eye = None

    frames_data = merge_per_frame_signals(
        emotion_pf if isinstance(emotion_pf, list) else None,
        posture_pf if isinstance(posture_pf, list) else None,
        eye_pf,
    )
    return summarize_behavior(
        frames_data,
        avg_eye_contact=avg_eye,
        eye_contact_available=eye_available,
    )
