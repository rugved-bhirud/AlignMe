import pyttsx3
import threading
import time
import random

class VoiceEngine:
    def __init__(self):
        self.is_speaking = False
        self.prompts = [
            "Alert! Keyboard goblin posture detected. Unfold your spine!",
            "Hey human, you look like a sad shrimp right now. Sit up!",
            "Warning! Neck turning into a candy cane. Engage core!",
            "Gravity is winning! Straighten your neck before it gets stuck like that.",
            "Excuse me, flesh entity. Your cervical spine is crying. Sit straight!"
        ]

    def trigger_alert(self):
        if self.is_speaking:
            return

        self.is_speaking = True

        def _speak():
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.setProperty('pitch', 120)
            msg = random.choice(self.prompts)
            engine.say(msg)
            engine.runAndWait()
            time.sleep(3)  # Cooldown time
            self.is_speaking = False

        threading.Thread(target=_speak, daemon=True).start()