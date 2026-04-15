"""Body language analysis using MediaPipe Pose (legacy or Tasks API)."""
import cv2
import numpy as np
import os
import glob
from pathlib import Path

from modules.behavior_analysis import posture_score_to_label

# Try legacy mp.solutions.pose first (mediapipe < 0.10.28)
_pose_module = None
try:
    import mediapipe as mp
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
        _pose_module = mp.solutions.pose
except Exception:
    pass

# Try new PoseLandmarker (mp.tasks.vision) for mediapipe 0.10.28+
_pose_landmarker_cls = None
_mp_tasks_vision = None
if _pose_module is None:
    try:
        import mediapipe as mp
        if hasattr(mp, "tasks") and hasattr(mp.tasks, "vision"):
            _pose_landmarker_cls = getattr(mp.tasks.vision, "PoseLandmarker", None)
            _mp_tasks_vision = mp.tasks.vision
    except Exception:
        pass

# Model URL for PoseLandmarker (downloaded on first use)
_POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

_body_analyzer = None


def _download_pose_model():
    """Download pose_landmarker_lite.task to backend/.mediapipe_models/"""
    cache_dir = Path(__file__).resolve().parent.parent / ".mediapipe_models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "pose_landmarker_lite.task"
    if model_path.exists():
        return str(model_path)
    try:
        import urllib.request
        print("[INFO] Downloading pose_landmarker_lite.task (first run)...")
        urllib.request.urlretrieve(_POSE_MODEL_URL, model_path)
        print("[INFO] Pose model downloaded.")
        return str(model_path)
    except Exception as e:
        print(f"[WARN] Could not download pose model: {e}")
        return None


def _get_body_analyzer():
    """Get or create cached BodyLanguageAnalyzer (legacy, Tasks, or stub)."""
    global _body_analyzer
    if _body_analyzer is not None:
        return _body_analyzer

    # 1. Try legacy mp.solutions.pose
    if _pose_module is not None:
        try:
            _body_analyzer = _LegacyBodyAnalyzer()
            print("[INFO] Body analysis using MediaPipe Pose (legacy).")
            return _body_analyzer
        except Exception as e:
            print(f"[WARN] Legacy Pose init failed: {e}. Trying Tasks API...")

    # 2. Try new PoseLandmarker
    if _pose_landmarker_cls is not None and _mp_tasks_vision is not None:
        model_path = _download_pose_model()
        if model_path:
            try:
                _body_analyzer = _TasksBodyAnalyzer(model_path)
                print("[INFO] Body analysis using MediaPipe PoseLandmarker (Tasks API).")
                return _body_analyzer
            except Exception as e:
                print(f"[WARN] PoseLandmarker init failed: {e}. Using stub.")

    # 3. Fallback stub
    print("[WARN] MediaPipe Pose unavailable. Body analysis disabled.")
    _body_analyzer = _BodyStub()
    return _body_analyzer


class _BodyStub:
    """Used when no Pose API is available."""
    def analyze_video(self, frames_dir, max_frames=500, subsample_step=2):
        return {
            "posture_score": 0,
            "movement_score": 0,
            "gesture_label": "Pose unavailable (MediaPipe Pose not available)",
            "missing_frames": 0,
            "frames_processed": 0,
            "posture_per_frame": [],
        }


class _LegacyBodyAnalyzer:
    """Uses mp.solutions.pose (legacy API)."""
    def __init__(self):
        self.pose = _pose_module.Pose(static_image_mode=True, model_complexity=0)

    def analyze_frame(self, image):
        results = self.pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return None
        return results.pose_landmarks.landmark

    def analyze_video(self, frames_dir, max_frames=500, subsample_step=2):
        return _analyze_frames_common(self, frames_dir, max_frames, subsample_step)


class _TasksBodyAnalyzer:
    """Uses mp.tasks.vision.PoseLandmarker (Tasks API)."""
    def __init__(self, model_path):
        import mediapipe as mp
        BaseOptions = mp.tasks.BaseOptions
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.IMAGE,
        )
        self.landmarker = PoseLandmarker.create_from_options(options)

    def analyze_frame(self, image):
        import mediapipe as mp
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)
        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None
        # pose_landmarks[0] = first person's landmarks (list of NormalizedLandmark)
        return result.pose_landmarks[0]

    def analyze_video(self, frames_dir, max_frames=500, subsample_step=2):
        return _analyze_frames_common(self, frames_dir, max_frames, subsample_step)


def _analyze_frames_common(analyzer, frames_dir, max_frames, subsample_step):
    """Shared logic: iterate frames, compute posture/movement, return report."""
    def _fallback(msg="Pose not detected (ensure upper body visible)"):
        return {
            "posture_score": 0,
            "movement_score": 0,
            "gesture_label": msg,
            "missing_frames": 0,
            "frames_processed": 0,
            "posture_per_frame": [],
        }
    try:
        frames_dir = str(frames_dir)
        all_frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    except Exception:
        return _fallback("No frames available")
    if not all_frames:
        return _fallback("No frames to analyze")
    try:
        frames = all_frames[::subsample_step] if subsample_step > 1 else all_frames
        frames = frames[:max_frames]
    except Exception:
        return _fallback()

    try:
        posture_scores = []
        movement_scores = []
        posture_per_frame = []
        missing_frames = 0
        prev_left_hand = None
        prev_right_hand = None

        for frame_path in frames:
            img = cv2.imread(frame_path)
            if img is None:
                missing_frames += 1
                continue
            try:
                landmarks = analyzer.analyze_frame(img)
            except Exception:
                missing_frames += 1
                continue

            if landmarks is None or len(landmarks) < 17:
                missing_frames += 1
                continue

            # MediaPipe indices: 11=left_shoulder, 12=right_shoulder, 15=left_wrist, 16=right_wrist
            left_shoulder = landmarks[11]
            right_shoulder = landmarks[12]
            left_wrist = landmarks[15]
            right_wrist = landmarks[16]

            shoulder_diff = abs(left_shoulder.y - right_shoulder.y)
            posture_unit = 1 - min(shoulder_diff, 1.0)
            posture_scores.append(posture_unit)
            score_10 = round(float(posture_unit * 10), 1)
            posture_per_frame.append(
                {
                    "path": os.path.normpath(frame_path),
                    "posture": posture_score_to_label(score_10),
                }
            )

            if prev_left_hand is not None:
                left_dist = abs(prev_left_hand.x - left_wrist.x) + abs(prev_left_hand.y - left_wrist.y)
                right_dist = abs(prev_right_hand.x - right_wrist.x) + abs(prev_right_hand.y - right_wrist.y)
                movement_scores.append(left_dist + right_dist)

            prev_left_hand = left_wrist
            prev_right_hand = right_wrist

        if not posture_scores:
            return _fallback("Insufficient pose data (ensure upper body visible)")

        posture = round(float(np.mean(posture_scores)), 2) if posture_scores else 0
        movement = round(float(np.mean(movement_scores)), 2) if movement_scores else 0
        posture_score_10 = round(posture * 10, 1)
        if movement < 0.05:
            gesture_label = "Very still (possibly stiff)"
        elif movement < 0.30:
            gesture_label = "Normal controlled movement"
        else:
            gesture_label = "Excessive hand movement"
        return {
            "posture_score": posture_score_10,
            "movement_score": movement,
            "gesture_label": gesture_label,
            "missing_frames": missing_frames,
            "frames_processed": len(posture_scores) + missing_frames,
            "posture_per_frame": posture_per_frame,
        }
    except Exception:
        return _fallback()


def analyze_video(frames_dir, max_frames=500, subsample_step=2):
    """Analyze body language from extracted video frames."""
    return _get_body_analyzer().analyze_video(frames_dir, max_frames, subsample_step)


# Backward compatibility for imports
BodyLanguageAnalyzer = _LegacyBodyAnalyzer if _pose_module else (_TasksBodyAnalyzer if _pose_landmarker_cls else _BodyStub)
