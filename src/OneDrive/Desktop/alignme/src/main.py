import cv2
import time
import mediapipe as mp
from geometry import PostureAnalyzer
from audio import VoiceEngine

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils


def main():
    analyzer = PostureAnalyzer(baseline_threshold=0.75)
    voice = VoiceEngine()

    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

    cap = cv2.VideoCapture(0)
    calibrating = False
    calibration_start = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)

        current_status = "PRESS 'C' TO CALIBRATE"
        status_color = (0, 255, 255)
        health_text = "AlignMe: Calibrate your posture to establish baseline geometry."
        preventive_text = "Action: Sit tall, pull shoulders back, and press 'C'."

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark

            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(255, 209, 0), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2)
            )

            nose = landmarks[mp_pose.PoseLandmark.NOSE]
            left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]

            if nose.visibility > 0.5 and left_shoulder.visibility > 0.5 and right_shoulder.visibility > 0.5:
                ratio = analyzer.compute_ratio(nose, left_shoulder, right_shoulder)

                if calibrating:
                    if time.time() - calibration_start > 1.5:
                        analyzer.calibrate(ratio)
                        calibrating = False
                    else:
                        current_status = "LEARNING POSTURE GEOMETRY..."
                        status_color = (0, 255, 255)

                elif analyzer.baseline_ratio is not None:
                    if analyzer.is_misaligned(ratio):
                        current_status = "MISALIGNMENT DETECTED! (SLOUCHING)"
                        status_color = (0, 0, 255)
                        health_text = "Strain: Forward head angle adds ~30lbs pressure to cervical spine."
                        preventive_text = "Fix: Pull screen to eye-level. Tuck chin back and roll shoulders."
                        voice.trigger_alert()
                    else:
                        current_status = "OPTIMAL ALIGNMENT"
                        status_color = (0, 255, 0)
                        health_text = "Health: Spine in neutral geometry. Unobstructed respiratory intake."
                        preventive_text = "Habit: Keep chest open and maintain current ergonomic state."

        # UI Overlays
        cv2.rectangle(frame, (0, 0), (w, 60), (20, 20, 20), -1)
        cv2.putText(frame, current_status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

        cv2.rectangle(frame, (0, h - 90), (w, h), (15, 15, 15), -1)
        cv2.putText(frame, health_text, (20, h - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
        cv2.putText(frame, preventive_text, (20, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 210, 255), 1)

        cv2.imshow("AlignMe MVP - Hackathon Demo", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('c') or key == ord('C'):
            calibrating = True
            calibration_start = time.time()
        elif key == ord('q') or key == ord('Q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()