"""
Eye-contact estimation from video frames using MediaPipe Face Mesh.

Reuses a single FaceMesh instance across frames. Thread-safe for parallel
workers via a processing lock.
"""

from __future__ import annotations

import glob
import os
import threading
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

# --- Heuristic tuning (forward-facing + optional iris centrality) ---

# How far nose.x may deviate from eye midline (as fraction of inter-eye width) before score drops
YAW_TOLERANCE = 0.35

# Expected nose.y offset below eye midline (normalized); deviation penalized
EXPECTED_NOSE_BELOW_EYES = 0.08
PITCH_TOLERANCE = 0.25

# Weight face-forward vs iris when iris landmarks exist (refine_landmarks=True)
FORWARD_VS_IRIS_WEIGHT = (0.45, 0.55)

# Iris ratio 0.5 = centered; scale how fast score drops when off-center
IRIS_CENTER_SHARPNESS = 2.2

_face_mesh = None
_face_mesh_lock = threading.Lock()
_face_mesh_available: Optional[bool] = None


def _get_face_mesh():
    """Lazy singleton FaceMesh; returns None if MediaPipe Face Mesh is unavailable."""
    global _face_mesh, _face_mesh_available
    if _face_mesh_available is False:
        return None
    if _face_mesh is not None:
        return _face_mesh
    try:
        import mediapipe as mp

        if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "face_mesh"):
            _face_mesh_available = False
            return None
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _face_mesh_available = True
        print("[INFO] Eye contact: MediaPipe Face Mesh initialized.")
        return _face_mesh
    except Exception as e:
        print(f"[WARN] Eye contact: Face Mesh unavailable ({e}).")
        _face_mesh_available = False
        return None


def _face_forward_score(lms: List[Any]) -> float:
    """
    Score 0–1 from head pose proxy: nose vs eye midline (yaw) and vertical alignment (pitch).
    Uses canonical Face Mesh indices.
    """
    nose = lms[1]
    le_o = lms[33]
    re_o = lms[263]
    mid_x = (le_o.x + re_o.x) * 0.5
    eye_width = abs(re_o.x - le_o.x) + 1e-6
    yaw_dev = abs(nose.x - mid_x) / eye_width
    yaw_score = float(max(0.0, min(1.0, 1.0 - yaw_dev / YAW_TOLERANCE)))

    mid_y = (le_o.y + re_o.y) * 0.5
    pitch_dev = abs((nose.y - mid_y) - EXPECTED_NOSE_BELOW_EYES)
    pitch_score = float(max(0.0, min(1.0, 1.0 - pitch_dev / PITCH_TOLERANCE)))

    return 0.55 * yaw_score + 0.45 * pitch_score


def _iris_centrality_score(lms: List[Any]) -> Optional[float]:
    """
    If refined landmarks present (478 points), score horizontal iris position within each eye.
    Returns None if iris indices are missing.
    """
    if len(lms) < 478:
        return None
    try:
        lo, li = lms[33], lms[133]
        iris_l = lms[468]
        span_l = li.x - lo.x
        if abs(span_l) < 1e-6:
            return None
        r_l = (iris_l.x - lo.x) / span_l

        ri, ro = lms[362], lms[263]
        iris_r = lms[473]
        span_r = ro.x - ri.x
        if abs(span_r) < 1e-6:
            return None
        r_r = (iris_r.x - ri.x) / span_r
    except (IndexError, AttributeError):
        return None

    def centrality(ratio: float) -> float:
        return float(max(0.0, min(1.0, 1.0 - abs(ratio - 0.5) * IRIS_CENTER_SHARPNESS)))

    return (centrality(r_l) + centrality(r_r)) * 0.5


def detect_eye_contact(frame: np.ndarray) -> float:
    """
    Estimate eye contact / camera engagement for one BGR image.

    Combines face-forward orientation with optional iris centrality when
    ``refine_landmarks`` is enabled. Returns 0 if no face is detected or
    Face Mesh is unavailable.

    Parameters
    ----------
    frame :
        OpenCV BGR image (any size; very small images may be less reliable).

    Returns
    -------
    float
        Score in ``[0, 1]`` (higher = more likely facing camera / centered gaze).
    """
    if frame is None or frame.size == 0:
        return 0.0

    mesh = _get_face_mesh()
    if mesh is None:
        return 0.0

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    with _face_mesh_lock:
        results = mesh.process(rgb)

    if not results.multi_face_landmarks:
        return 0.0

    lms = results.multi_face_landmarks[0].landmark
    forward = _face_forward_score(lms)
    iris = _iris_centrality_score(lms)
    if iris is None:
        return float(max(0.0, min(1.0, forward)))
    w_fwd, w_iris = FORWARD_VS_IRIS_WEIGHT
    combined = w_fwd * forward + w_iris * iris
    return float(max(0.0, min(1.0, combined)))


def analyze_eye_contact(frames: List[str]) -> List[Dict[str, Any]]:
    """
    Run eye-contact scoring on a list of frame image paths (same order as callers expect).

    Missing or unreadable files yield ``eye_contact: 0.0`` for that path.

    Parameters
    ----------
    frames :
        Absolute or relative paths to frame images (e.g. JPG).

    Returns
    -------
    list of dict
        Each item: ``{"path": <normalized path>, "eye_contact": <float 0–1>}``.
    """
    out: List[Dict[str, Any]] = []
    for raw_path in frames:
        path = os.path.normpath(str(raw_path))
        img = cv2.imread(path)
        if img is None:
            out.append({"path": path, "eye_contact": 0.0})
            continue
        score = detect_eye_contact(img)
        out.append({"path": path, "eye_contact": round(score, 4)})
    return out


def analyze_eye_contact_frames_dir(frames_dir: str, subsample_step: int = 1) -> Dict[str, Any]:
    """
    Convenience: glob ``*.jpg`` in ``frames_dir``, sort, apply subsampling (match emotion/body), analyze.

    Returns a payload suitable for ``build_behavior_insights``:

    * ``eye_contact_per_frame``: list of per-frame dicts
    * ``avg_eye_contact``: mean score (0 if no frames)
    * ``frames_analyzed``: count of paths processed
    """
    frames_dir = str(frames_dir)
    pattern = os.path.join(frames_dir, "*.jpg")
    all_frames = sorted(glob.glob(pattern))
    if subsample_step > 1:
        paths = all_frames[::subsample_step]
    else:
        paths = all_frames

    mesh = _get_face_mesh()
    eye_contact_available = mesh is not None

    if not paths:
        return {
            "eye_contact_per_frame": [],
            "avg_eye_contact": 0.0,
            "frames_analyzed": 0,
            "eye_contact_available": eye_contact_available,
        }

    per_frame = analyze_eye_contact(paths)
    scores = [float(row["eye_contact"]) for row in per_frame]
    avg = sum(scores) / len(scores) if scores else 0.0
    return {
        "eye_contact_per_frame": per_frame,
        "avg_eye_contact": round(avg, 4),
        "frames_analyzed": len(per_frame),
        "eye_contact_available": eye_contact_available,
    }
