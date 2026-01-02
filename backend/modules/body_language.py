import cv2
import mediapipe as mp
import numpy as np
import os
import glob


class BodyLanguageAnalyzer:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(static_image_mode=False)

    def analyze_frame(self, image):
        results = self.pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        if not results.pose_landmarks:
            return None

        return results.pose_landmarks.landmark

    def calculate_angle(self, a, b, c):
        """Utility for angle calculation."""
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)

        radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - \
                  np.arctan2(a[1]-b[1], a[0]-b[0])
        angle = np.abs(radians * 180.0 / np.pi)

        if angle > 180.0:
            angle = 360 - angle

        return angle

    def analyze_video(self, frames_dir, max_frames=500):
        frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))

        posture_scores = []
        movement_scores = []
        missing_frames = 0
        prev_left_hand = None
        prev_right_hand = None

        for i, frame_path in enumerate(frames[:max_frames]):
            img = cv2.imread(frame_path)
            landmarks = self.analyze_frame(img)

            if landmarks is None:
                missing_frames += 1
                continue

            # Extract some key points
            nose = landmarks[0]
            left_shoulder = landmarks[11]
            right_shoulder = landmarks[12]
            left_wrist = landmarks[15]
            right_wrist = landmarks[16]

            # Posture stability: shoulder alignment
            shoulder_diff = abs(left_shoulder.y - right_shoulder.y)
            posture_scores.append(1 - shoulder_diff)

            # Movement: hand movement between frames
            if prev_left_hand:
                left_dist = abs(prev_left_hand.x - left_wrist.x) + abs(prev_left_hand.y - left_wrist.y)
                right_dist = abs(prev_right_hand.x - right_wrist.x) + abs(prev_right_hand.y - right_wrist.y)
                movement_scores.append(left_dist + right_dist)

            prev_left_hand = left_wrist
            prev_right_hand = right_wrist

        posture = round(float(np.mean(posture_scores)), 2) if posture_scores else 0
        movement = round(float(np.mean(movement_scores)), 2) if movement_scores else 0

        # Adjust thresholds for 1 FPS (movement between frames is naturally larger)
        if movement < 0.05:
            gesture_label = "Very still (possibly stiff)"
        elif movement < 0.30:
            gesture_label = "Normal controlled movement"
        else:
            gesture_label = "Excessive hand movement"

        return {
            "posture_score": posture,
            "movement_score": movement,
            "gesture_label": gesture_label,
            "missing_frames": missing_frames,
            "frames_processed": len(posture_scores) + missing_frames,
        }
