# AlignMe: Intelligent Habit Health for the Modern Workday

AlignMe is a context-aware AI wellness coach that turns moment-to-moment posture tracking into long-term physical resilience. Using real-time computer vision, AlignMe establishes an individual's healthy baseline geometry, identifies cervical strain, and delivers subtle auditory alerts alongside preventive health guidance.

---

## Key Features

- **Personalized Geometry Learning:** Calibrates against the user's natural posture rather than static height or angle assumptions.
- **Distance-Invariant Tracking:** Calculates scale-invariant ratios to ensure accuracy regardless of webcam distance.
- **Real-Time Health Insights:** Displays active physical impacts (e.g., cervical spine load) and preventive micro-break guidance on screen.
- **Interactive Audio Feedback:** Triggers TTS voice alerts when forward-head posture exceeds risk thresholds.
- **Privacy-First Processing:** Runs entirely on local hardware without streaming video to cloud servers.

---

## Architecture Flow

```text
  [Webcam Stream] 
        │
        ▼
 [MediaPipe Pose] ──> Extracts Landmarks (Nose, Shoulders)
        │
        ▼
 [Geometry Engine] ──> Calculates Ratio = NeckLength / ShoulderWidth
        │
        ├── Calibration State: Sets Baseline Ratio
        └── Evaluation State: Ratio < (Baseline * 0.75)
                │
                ├── [TRUE]  ──> Render Risk Overlay + Fire Audio Alert
                └── [FALSE] ──> Render Optimal Alignment Overlay