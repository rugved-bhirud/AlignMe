import math
import time
import numpy as np


class PostureAnalyzer:
    def __init__(self, baseline_threshold=0.75, persistent_seconds=2.0, recovery_seconds=1.0):
        self.baseline_threshold = baseline_threshold
        self.persistent_seconds = persistent_seconds
        self.recovery_seconds = recovery_seconds
        
        # Calibration baseline values
        self.calibrated = False
        self.baseline_ratio = None
        
        # State tracking & timing variables
        self.is_currently_slouching = False
        self.slouch_start_time = None
        self.recovery_start_time = None

    def _get_distance(self, p1, p2):
        """Calculate Euclidean distance between two 2D points."""
        return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)

    def _calculate_angle(self, p1, p2):
        """Calculate shoulder tilt angle in degrees."""
        delta_x = p2.x - p1.x
        delta_y = p2.y - p1.y
        angle_rad = math.atan2(delta_y, delta_x)
        return abs(math.degrees(angle_rad))

    def compute_ratio(self, nose, left_ear, right_ear, left_shoulder, right_shoulder):
        """Calculates distance-normalized vertical alignment ratio with fallbacks."""
        # Calculate shoulder width for scale normalization
        shoulder_width = self._get_distance(left_shoulder, right_shoulder)
        if shoulder_width <= 0.001:
            return 0.0

        shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2.0

        # Primary: Use ears if visible; Fallback: Use nose position
        ear_vis_ok = (getattr(left_ear, 'visibility', 1.0) > 0.3 and getattr(right_ear, 'visibility', 1.0) > 0.3)
        if ear_vis_ok:
            head_mid_y = (left_ear.y + right_ear.y) / 2.0
        else:
            head_mid_y = nose.y

        vert_dist = abs(shoulder_mid_y - head_mid_y)
        return vert_dist / shoulder_width

    def calibrate(self, ratio_val_or_landmarks):
        """Establishes baseline geometry ratios during neutral upright posture."""
        if isinstance(ratio_val_or_landmarks, (float, int)):
            if ratio_val_or_landmarks > 0:
                self.baseline_ratio = float(ratio_val_or_landmarks)
                self.calibrated = True
                return True
            return False

        landmarks = ratio_val_or_landmarks
        if not landmarks or not hasattr(landmarks, 'landmark'):
            return False

        pts = landmarks.landmark
        left_ear, right_ear = pts[7], pts[8]
        left_shoulder, right_shoulder = pts[11], pts[12]
        nose = pts[0]

        computed = self.compute_ratio(nose, left_ear, right_ear, left_shoulder, right_shoulder)
        if computed > 0:
            self.baseline_ratio = computed
            self.calibrated = True
            return True

        return False

    def is_misaligned(self, current_ratio):
        """Evaluates active frame metric against calibrated baseline."""
        if not self.calibrated or self.baseline_ratio is None or self.baseline_ratio == 0:
            return False

        ratio_drop = current_ratio / self.baseline_ratio
        return ratio_drop < self.baseline_threshold

    def analyze(self, landmarks):
        """Analyzes active frame landmarks against calibrated baseline with temporal persistence & recovery."""
        default_response = {
            "is_good": True,
            "current_ratio": 0.0,
            "baseline": self.baseline_ratio if self.baseline_ratio else 0.0,
            "shoulder_tilt": 0.0
        }

        if not landmarks or not hasattr(landmarks, 'landmark') or not self.calibrated:
            return default_response

        pts = landmarks.landmark
        nose = pts[0]
        left_ear, right_ear = pts[7], pts[8]
        left_shoulder, right_shoulder = pts[11], pts[12]

        current_ratio = self.compute_ratio(nose, left_ear, right_ear, left_shoulder, right_shoulder)
        shoulder_tilt = self._calculate_angle(left_shoulder, right_shoulder)

        # Raw frame check using your exact geometry logic
        frame_is_bad = self.is_misaligned(current_ratio) or shoulder_tilt > 15.0
        current_time = time.time()

        if frame_is_bad:
            self.recovery_start_time = None
            if not self.is_currently_slouching:
                if self.slouch_start_time is None:
                    self.slouch_start_time = current_time
                elif current_time - self.slouch_start_time >= self.persistent_seconds:
                    self.is_currently_slouching = True
        else:
            self.slouch_start_time = None
            if self.is_currently_slouching:
                if self.recovery_start_time is None:
                    self.recovery_start_time = current_time
                elif current_time - self.recovery_start_time >= self.recovery_seconds:
                    self.is_currently_slouching = False

        return {
            "is_good": not self.is_currently_slouching,
            "current_ratio": round(current_ratio, 4),
            "baseline": round(self.baseline_ratio, 4) if self.baseline_ratio else 0.0,
            "shoulder_tilt": round(shoulder_tilt, 2)
        }