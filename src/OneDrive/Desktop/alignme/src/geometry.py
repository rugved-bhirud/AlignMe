import math

class PostureAnalyzer:
    def __init__(self, baseline_threshold=0.75):
        self.baseline_ratio = None
        self.threshold = baseline_threshold

    def compute_ratio(self, nose, left_shoulder, right_shoulder):
        """
        Computes a scale-invariant ratio:
        Ratio = (Nose-to-Shoulder-Midpoint Vertical Distance) / (Shoulder-to-Shoulder Width)
        """
        mid_shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
        neck_length = abs(mid_shoulder_y - nose.y)
        shoulder_width = abs(left_shoulder.x - right_shoulder.x)

        if shoulder_width == 0:
            return None

        return neck_length / shoulder_width

    def calibrate(self, ratio):
        self.baseline_ratio = ratio

    def is_misaligned(self, current_ratio):
        if self.baseline_ratio is None or current_ratio is None:
            return False
        return current_ratio < (self.baseline_ratio * self.threshold)