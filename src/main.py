import cv2
import time
import os
import sys
import csv
import platform
import threading
import json
import webbrowser
from datetime import datetime, date
import customtkinter as ctk
from PIL import Image, ImageDraw
import numpy as np
import mediapipe as mp
import pystray
import pyttsx3

if platform.system() == "Windows":
    import winsound

mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils


class VoiceEngine:
    def __init__(self):
        pass

    def trigger_alert(self, message):
        def run_speech():
            try:
                engine = pyttsx3.init()
                engine.setProperty('rate', 165)
                engine.setProperty('volume', 1.0)
                engine.say(message)
                engine.runAndWait()
                engine.stop()
            except Exception as e:
                print("TTS Engine Error:", e)

        threading.Thread(target=run_speech, daemon=True).start()


class PostureAnalyzer:
    def __init__(self):
        self.baseline_ratio = None
        self.calibrated = False

    def compute_ratio(self, nose, left_ear, right_ear, left_shoulder, right_shoulder):
        shoulder_width = ((left_shoulder.x - right_shoulder.x) ** 2 + (left_shoulder.y - right_shoulder.y) ** 2) ** 0.5
        if shoulder_width < 1e-5:
            return 0.0
        
        shoulder_x = (left_shoulder.x + right_shoulder.x) / 2.0
        ear_x = (left_ear.x + right_ear.x) / 2.0
        
        forward_lean = abs(ear_x - shoulder_x) / shoulder_width
        return forward_lean

    def calibrate(self, current_ratio):
        self.baseline_ratio = current_ratio
        self.calibrated = True
        return True

    def is_misaligned(self, current_ratio):
        if not self.calibrated:
            return False
        return current_ratio > (self.baseline_ratio + 0.08)


class PostureApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.withdraw()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#030712")

        self.title("AlignMe - Enterprise Posture & Ergonomic Intelligence")
        
        self.is_fullscreen = False
        self.attributes("-fullscreen", False)
        self.geometry("1280x720")
        self.resizable(True, True)
        
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.analyzer = PostureAnalyzer()
        self.voice = VoiceEngine()
        
        self.pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.is_tracking = False      
        self.start_time = None
        self.total_work_elapsed = 0
        self.last_active_timestamp = None

        self.calibrating = False
        self.calibration_start = 0
        self.optimal_time_counter = 0
        self.last_frame_time = time.time()
        self.is_running = True
        self.exit_popup_active = False

        self.second_timer = 0.0
        self.second_optimal_time = 0.0
        self.second_scores_current_minute = []
        self.minute_averages = []

        self.water_reminder_interval = 45 * 60 
        self.stretch_reminder_interval = 30 * 60 
        self.water_elapsed_time = 0.0
        self.stretch_elapsed_time = 0.0

        self.show_water_alert = False
        self.show_stretch_alert = False
        self.alert_start_time = 0
        self.water_popup_active = False
        
        self.last_gesture_toggle_time = 0
        self.user_is_waving = False
        self.wave_timer = 0.0

        self.load_gamification_data()

        self.main_layout = ctk.CTkFrame(self, fg_color="#030712")
        self.main_layout.pack(fill="both", expand=True)

        self.main_layout.grid_columnconfigure(0, weight=5)
        self.main_layout.grid_columnconfigure(1, weight=1)
        self.main_layout.grid_rowconfigure(0, weight=1)

        # Left panel now takes full height for the camera feed
        self.left_panel = ctk.CTkFrame(self.main_layout, fg_color="transparent")
        self.left_panel.grid(row=0, column=0, padx=(14, 8), pady=14, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(0, weight=1)

        self.video_frame = ctk.CTkFrame(
            self.left_panel, 
            corner_radius=16, 
            fg_color="#090D16",
            border_width=1,
            border_color="#1E293B"
        )
        self.video_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        self.video_label = ctk.CTkLabel(self.video_frame, text="")
        self.video_label.place(relx=0.5, rely=0.5, anchor="center")

        # Sidebar (Right Column)
        self.sidebar = ctk.CTkFrame(
            self.main_layout, 
            width=380, 
            corner_radius=16, 
            fg_color="#0F172A",
            border_width=1,
            border_color="#1E293B"
        )
        self.sidebar.grid(row=0, column=1, padx=(6, 14), pady=14, sticky="nsew")
        self.sidebar.pack_propagate(False)

        self.title_lbl = ctk.CTkLabel(
            self.sidebar, 
            text="✨ AlignMe Dashboard", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F8FAFC"
        )
        self.title_lbl.pack(pady=(12, 2))

        self.gamify_header_btn = ctk.CTkButton(
            self.sidebar,
            text=f"🔥 Streak: {self.game_data['streak']} Days | ⚡ Level {self.game_data['level']} ({self.game_data['xp']} XP)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            text_color="#FBBF24",
            height=28,
            corner_radius=8,
            command=self.open_gamification_modal
        )
        self.gamify_header_btn.pack(fill="x", padx=12, pady=(0, 6))

        # Avatar / 3D Model Frame placed compactly inside the right column
        self.avatar_frame = ctk.CTkFrame(
            self.sidebar, 
            corner_radius=12, 
            fg_color="#090D16",
            border_width=1,
            border_color="#1E293B",
            height=130
        )
        self.avatar_frame.pack(fill="x", padx=12, pady=4)
        self.avatar_frame.pack_propagate(False)

        self.avatar_label = ctk.CTkLabel(self.avatar_frame, text="")
        self.avatar_label.place(relx=0.5, rely=0.5, anchor="center")

        self.date_lbl = ctk.CTkLabel(
            self.sidebar, 
            text=datetime.now().strftime("%A, %B %d, %Y"), 
            font=ctk.CTkFont(size=11, weight="normal"),
            text_color="#64748B"
        )
        self.date_lbl.pack(pady=(0, 6))

        self.status_container = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=38)
        self.status_container.pack(fill="x", padx=12, pady=2)
        self.status_container.pack_propagate(False)

        self.status_box = ctk.CTkLabel(
            self.status_container, 
            text="⚡ Press C or give 👍 to Calibrate", 
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1E293B", 
            text_color="#38BDF8",
            corner_radius=8
        )
        self.status_box.pack(fill="both", expand=True)

        self.features_frame = ctk.CTkFrame(
            self.sidebar, 
            fg_color="#182238", 
            corner_radius=12,
            border_width=1,
            border_color="#1E293B"
        )
        self.features_frame.pack(fill="x", padx=12, pady=4)

        self.privacy_lbl = ctk.CTkLabel(
            self.features_frame,
            text="🔒 On-Device Local Processing",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#34D399"
        )
        self.privacy_lbl.pack(anchor="w", padx=10, pady=(6, 2))

        self.meeting_mode_var = ctk.BooleanVar(value=False)
        self.meeting_toggle = ctk.CTkCheckBox(
            self.features_frame,
            text="Meeting Mode (Mute Audio)",
            variable=self.meeting_mode_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#E2E8F0",
            checkbox_width=18,
            checkbox_height=18
        )
        self.meeting_toggle.pack(anchor="w", padx=10, pady=2)

        self.location_container = ctk.CTkFrame(self.features_frame, fg_color="transparent")
        self.location_container.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkLabel(
            self.location_container, 
            text="📍 Location:", 
            font=ctk.CTkFont(size=11, weight="bold"), 
            text_color="#38BDF8"
        ).pack(side="left", padx=(0, 6))

        self.location_menu = ctk.CTkOptionMenu(
            self.location_container,
            values=["Home", "College", "Office", "Library", "Other"],
            width=150,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0EA5E9",
            button_color="#0284C7",
            height=26
        )
        self.location_menu.set("Home")
        self.location_menu.pack(side="left", fill="x", expand=True)

        self.btn_grid = ctk.CTkFrame(self.features_frame, fg_color="transparent")
        self.btn_grid.pack(fill="x", padx=8, pady=(4, 8))

        self.recal_btn = ctk.CTkButton(
            self.btn_grid,
            text="Recalibrate",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0EA5E9",
            hover_color="#0284C7",
            height=28,
            command=lambda: self.start_or_resume_tracking()
        )
        self.recal_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.stretch_btn = ctk.CTkButton(
            self.btn_grid,
            text="Stretch",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            height=28,
            command=lambda: self.play_voice_alert_async("Time for a quick stretch break!")
        )
        self.stretch_btn.pack(side="left", expand=True, fill="x", padx=(2, 2))

        self.map_btn = ctk.CTkButton(
            self.btn_grid,
            text="🗺 Map",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706",
            height=28,
            command=self.open_posture_map_window
        )
        self.map_btn.pack(side="left", expand=True, fill="x", padx=(2, 0))

        self.live_guidance_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#182238",
            corner_radius=12,
            border_width=1,
            border_color="#1E293B"
        )
        self.live_guidance_card.pack(fill="x", padx=12, pady=4)

        self.guidance_title = ctk.CTkLabel(
            self.live_guidance_card,
            text="🧭 Live Posture Guidance",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.guidance_title.pack(anchor="w", padx=10, pady=(6, 2))

        self.live_health_lbl = ctk.CTkLabel(
            self.live_guidance_card,
            text="• Status: System paused or awaiting calibration.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#E2E8F0",
            wraplength=330,
            justify="left"
        )
        self.live_health_lbl.pack(anchor="w", padx=10, pady=2)

        self.live_action_lbl = ctk.CTkLabel(
            self.live_guidance_card,
            text="• Action: Show 👍 to start tracking.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38BDF8",
            wraplength=330,
            justify="left"
        )
        self.live_action_lbl.pack(anchor="w", padx=10, pady=(2, 8))

        self.water_settings_frame = ctk.CTkFrame(
            self.sidebar, 
            fg_color="#182238", 
            corner_radius=12,
            border_width=1,
            border_color="#1E293B"
        )
        self.water_settings_frame.pack(fill="x", padx=12, pady=4)

        self.water_title = ctk.CTkLabel(
            self.water_settings_frame,
            text="💧 Water Alert Interval",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38BDF8"
        )
        self.water_title.pack(anchor="w", padx=10, pady=(6, 2))

        self.water_controls = ctk.CTkFrame(self.water_settings_frame, fg_color="transparent")
        self.water_controls.pack(fill="x", padx=10, pady=(0, 6))

        self.water_mode_menu = ctk.CTkOptionMenu(
            self.water_controls,
            values=["HH:MM Mode", "Custom Mins"],
            width=95,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0EA5E9",
            button_color="#0284C7",
            height=26,
            command=self.on_water_mode_change
        )
        self.water_mode_menu.pack(side="left", padx=(0, 4))

        self.hhmm_frame = ctk.CTkFrame(self.water_controls, fg_color="transparent")
        self.hhmm_frame.pack(side="left", expand=True, fill="x")

        hours_list = [f"{i:02d}" for i in range(13)]
        self.hh_option = ctk.CTkOptionMenu(
            self.hhmm_frame,
            values=hours_list,
            width=45,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F172A",
            button_color="#334155",
            height=26
        )
        self.hh_option.set("00")
        self.hh_option.pack(side="left", padx=(0, 2))

        ctk.CTkLabel(self.hhmm_frame, text=":", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F8FAFC").pack(side="left")

        minutes_list = [f"{i:02d}" for i in range(0, 60, 1)]
        self.mm_option = ctk.CTkOptionMenu(
            self.hhmm_frame,
            values=minutes_list,
            width=45,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0F172A",
            button_color="#334155",
            height=26
        )
        self.mm_option.set("45")
        self.mm_option.pack(side="left", padx=(2, 4))

        self.set_time_btn = ctk.CTkButton(
            self.hhmm_frame,
            text="Set",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            height=26,
            width=32,
            command=self.update_water_interval
        )
        self.set_time_btn.pack(side="left", expand=True, fill="x")

        self.custom_frame = ctk.CTkFrame(self.water_controls, fg_color="transparent")

        self.custom_water_entry = ctk.CTkEntry(
            self.custom_frame,
            placeholder_text="Mins",
            font=ctk.CTkFont(size=10),
            height=26,
            width=50
        )
        self.custom_water_entry.pack(side="left", padx=(0, 4))
        self.custom_water_entry.bind("<Return>", lambda e: self.apply_custom_water_interval())

        self.custom_water_btn = ctk.CTkButton(
            self.custom_frame,
            text="Set Custom",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            height=26,
            command=self.apply_custom_water_interval
        )
        self.custom_water_btn.pack(side="left", expand=True, fill="x")

        self.metrics_frame = ctk.CTkFrame(
            self.sidebar, 
            fg_color="#182238", 
            corner_radius=12,
            border_width=1,
            border_color="#1E293B"
        )
        self.metrics_frame.pack(fill="x", padx=12, pady=4)

        self.worktime_lbl = ctk.CTkLabel(
            self.metrics_frame, 
            text="⏱ Work Duration: 00:00:00", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#E2E8F0"
        )
        self.worktime_lbl.pack(anchor="w", padx=10, pady=(8, 2))

        self.good_time_lbl = ctk.CTkLabel(
            self.metrics_frame, 
            text="🎯 Optimal Alignment: 00:00:00", 
            font=ctk.CTkFont(size=11, weight="bold"), 
            text_color="#34D399"
        )
        self.good_time_lbl.pack(anchor="w", padx=10, pady=2)

        self.score_lbl = ctk.CTkLabel(
            self.metrics_frame,
            text="📊 Posture Compliance: 0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.score_lbl.pack(anchor="w", padx=10, pady=(4, 2))

        self.score_bar = ctk.CTkProgressBar(self.metrics_frame, height=6, corner_radius=3, progress_color="#38BDF8")
        self.score_bar.set(0.0)
        self.score_bar.pack(fill="x", padx=10, pady=(2, 8))

        self.risks_card = ctk.CTkFrame(
            self.sidebar, 
            fg_color="#0D1527", 
            corner_radius=12,
            border_width=1,
            border_color="#334155"
        )
        self.risks_card.pack(fill="both", expand=True, padx=12, pady=4)

        self.risk_header = ctk.CTkLabel(
            self.risks_card,
            text="🛡 Ergonomic Strain & Risk Analysis",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FBBF24"
        )
        self.risk_header.pack(anchor="w", padx=10, pady=(8, 4))

        self.stressed_box = ctk.CTkFrame(
            self.risks_card,
            fg_color="#1E293B",
            corner_radius=8,
            border_width=1,
            border_color="#38BDF8"
        )
        self.stressed_box.pack(fill="x", padx=8, pady=3)

        self.stressed_area_lbl = ctk.CTkLabel(
            self.stressed_box,
            text="📍 Main Stressed Area:\n• Neck, upper back & shoulder muscles",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#E0F2FE",
            wraplength=310,
            justify="left"
        )
        self.stressed_area_lbl.pack(anchor="w", padx=8, pady=6)

        self.problem_box = ctk.CTkFrame(
            self.risks_card,
            fg_color="#27141A",
            corner_radius=8,
            border_width=1,
            border_color="#EF4444"
        )
        self.problem_box.pack(fill="x", padx=8, pady=3)

        self.possible_problem_lbl = ctk.CTkLabel(
            self.problem_box,
            text="⚠️ Possible Strain Symptoms:\n• Neck strain, stiffness, upper-back discomfort",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#FCA5A5",
            wraplength=310,
            justify="left"
        )
        self.possible_problem_lbl.pack(anchor="w", padx=8, pady=6)

        self.disclaimer_lbl = ctk.CTkLabel(
            self.risks_card,
            text="* Medical disclaimer: Software reports ergonomic strain risk indicators, not medical diagnoses.",
            font=ctk.CTkFont(size=8, slant="italic"),
            text_color="#64748B",
            wraplength=310,
            justify="left"
        )
        self.disclaimer_lbl.pack(anchor="w", padx=8, pady=(4, 6))

        self.info_lbl = ctk.CTkLabel(
            self.sidebar, 
            text="⌨ Controls: 👍 Start | 👎 Pause | Wave hand to greet pet!", 
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#475569"
        )
        self.info_lbl.pack(pady=(2, 6))

        self.cap = cv2.VideoCapture(0)

        self.bind("<Key>", self.handle_keypress)
        self.bind("<Escape>", lambda event: self.on_close())
        self.bind("<F11>", lambda event: self.toggle_fullscreen())
        
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.setup_tray_icon()

        self.update_idletasks()
        self.after(100, self._reveal_window)
        self.update_feed()

    def create_tray_image(self):
        image = Image.new("RGB", (64, 64), color="#0F172A")
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 12, 52, 52), fill="#0EA5E9")
        draw.text((22, 22), "A", fill="#FFFFFF")
        return image

    def setup_tray_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem("Restore App", self.show_from_tray, default=True),
            pystray.MenuItem("Quit AlignMe", self.quit_from_tray)
        )
        self.tray_icon = pystray.Icon("AlignMe", self.create_tray_image(), "AlignMe Posture Intelligence", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.withdraw()

    def show_from_tray(self, icon=None, item=None):
        self.deiconify()
        try:
            self.state("zoomed")
        except Exception:
            pass

    def quit_from_tray(self, icon=None, item=None):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        self.on_close()

    def load_gamification_data(self):
        self.gamify_filename = "align_gamification.json"
        self.game_data = {"streak": 0, "xp": 0, "level": 1, "last_active_date": ""}
        if os.path.exists(self.gamify_filename):
            try:
                with open(self.gamify_filename, "r", encoding="utf-8") as f:
                    self.game_data = json.load(f)
            except Exception:
                pass

    def save_gamification_data(self):
        try:
            with open(self.gamify_filename, "w", encoding="utf-8") as f:
                json.dump(self.game_data, f, indent=2)
        except Exception as e:
            print("Error saving gamification state:", e)

    def update_streak_and_xp(self, session_score):
        today_str = str(date.today())
        last_date = self.game_data.get("last_active_date", "")

        earned_xp = int(session_score * 2)
        self.game_data["xp"] += earned_xp

        new_level = (self.game_data["xp"] // 500) + 1
        self.game_data["level"] = new_level

        if session_score >= 75:
            if last_date != today_str:
                if last_date == "":
                    self.game_data["streak"] = 1
                else:
                    d_last = datetime.strptime(last_date, "%Y-%m-%d").date()
                    d_today = date.today()
                    diff = (d_today - d_last).days
                    if diff == 1:
                        self.game_data["streak"] += 1
                    elif diff > 1:
                        self.game_data["streak"] = 1 
                self.game_data["last_active_date"] = today_str

        self.save_gamification_data()
        self.gamify_header_btn.configure(
            text=f"🔥 Streak: {self.game_data['streak']} Days | ⚡ Level {self.game_data['level']} ({self.game_data['xp']} XP)"
        )

    def open_gamification_modal(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Ergonomic Streak & Achievements")
        popup.geometry("420x350")
        popup.grab_set()
        popup.attributes("-topmost", True)

        ctk.CTkLabel(
            popup, 
            text="🏆 Ergo Achievement Board", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#FBBF24"
        ).pack(pady=(20, 10))

        card = ctk.CTkFrame(popup, fg_color="#1E293B", corner_radius=12)
        card.pack(fill="x", padx=25, pady=10)

        streak_val = self.game_data.get("streak", 0)
        xp_val = self.game_data.get("xp", 0)
        lvl_val = self.game_data.get("level", 1)

        ctk.CTkLabel(card, text=f"🔥 Current Streak: {streak_val} Day(s)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#38BDF8").pack(anchor="w", padx=15, pady=(12, 4))
        ctk.CTkLabel(card, text=f"⚡ Current Level: Level {lvl_val}", font=ctk.CTkFont(size=14, weight="bold"), text_color="#34D399").pack(anchor="w", padx=15, pady=4)
        ctk.CTkLabel(card, text=f"✨ Accumulated XP: {xp_val} XP", font=ctk.CTkFont(size=14, weight="bold"), text_color="#F472B6").pack(anchor="w", padx=15, pady=(4, 12))

        ctk.CTkLabel(
            popup, 
            text="Maintain an average compliance score > 75% daily\nto keep your streak burning and level up!", 
            font=ctk.CTkFont(size=11), 
            text_color="#94A3B8",
            justify="center"
        ).pack(pady=10)

        ctk.CTkButton(
            popup, 
            text="Got It!", 
            fg_color="#0EA5E9", 
            hover_color="#0284C7",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=popup.destroy,
            height=36
        ).pack(pady=15, fill="x", padx=40)

    def open_posture_map_window(self):
        filename = "daily_posture_log.csv"
        location_data = {} 

        if os.path.exists(filename):
            try:
                with open(filename, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        loc = row.get("Location Tag", "Home")
                        score_str = row.get("Average Posture Compliance Score", "0%").replace("%", "")
                        try:
                            score = float(score_str)
                        except ValueError:
                            score = 0.0

                        if loc not in location_data:
                            location_data[loc] = {"total_score": 0.0, "count": 0}
                        location_data[loc]["total_score"] += score
                        location_data[loc]["count"] += 1
            except Exception as e:
                print("Error reading posture logs for map:", e)

        default_coords = {
            "Home": {"lat": 28.7041, "lng": 77.1025, "name": "Home"},
            "College": {"lat": 28.6139, "lng": 77.2090, "name": "College"},
            "Office": {"lat": 28.5355, "lng": 77.3910, "name": "Office"},
            "Library": {"lat": 28.5800, "lng": 77.2100, "name": "Library"},
            "Other": {"lat": 28.6500, "lng": 77.1500, "name": "Other"}
        }

        markers_js = []
        for loc, info in location_data.items():
            avg_score = info["total_score"] / max(1, info["count"])
            coord = default_coords.get(loc, {"lat": 28.6000, "lng": 77.2000, "name": loc})
            
            markers_js.append({
                "lat": coord["lat"],
                "lng": coord["lng"],
                "title": f"Location: {loc}",
                "popup": f"<b>{loc}</b><br>Average Compliance: <b>{round(avg_score, 1)}%</b><br>Total Sessions: {info['count']}"
            })

        if not markers_js:
            markers_js.append({
                "lat": 28.7041, 
                "lng": 77.1025, 
                "title": "Home (No saved logs yet)", 
                "popup": "<b>Home</b><br>No sessions recorded yet. Complete a session and save it!"
            })

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AlignMe - Posture History Heatmap</title>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <style>
                body {{ margin: 0; padding: 0; background: #0f172a; font-family: sans-serif; color: #f8fafc; }}
                #header {{ padding: 15px 20px; background: #1e293b; border-bottom: 1px solid #334155; }}
                #map {{ height: calc(100vh - 70px); width: 100%; }}
                .marker-card {{ font-size: 13px; color: #0f172a; }}
            </style>
        </head>
        <body>
            <div id="header">
                <h2 style="margin: 0; font-size: 18px; color: #38BDF8;">🌍 AlignMe - Saved Posture Geographic History</h2>
                <p style="margin: 4px 0 0 0; font-size: 12px; color: #94A3B8;">Aggregated compliance ratings from your saved session logs across locations.</p>
            </div>
            <div id="map"></div>

            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script>
                var map = L.map('map').setView([28.6139, 77.2090], 12);

                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    maxZoom: 19,
                    attribution: '© OpenStreetMap contributors'
                }}).addTo(map);

                var markersData = {json.dumps(markers_js)};

                markersData.forEach(function(item) {{
                    var marker = L.marker([item.lat, item.lng]).addTo(map);
                    marker.bindPopup("<div class='marker-card'>" + item.popup + "</div>");
                }});
            </script>
        </body>
        </html>
        """

        html_filename = "posture_heatmap.html"
        try:
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            webbrowser.open('file://' + os.path.realpath(html_filename))
        except Exception as e:
            print("Error launching browser map:", e)

    def play_voice_alert_async(self, message):
        if getattr(self, "meeting_mode_var", None) and self.meeting_mode_var.get():
            return
        try:
            self.voice.trigger_alert(message)
        except Exception as e:
            print("Audio alert error:", e)

    def _reveal_window(self):
        self.deiconify()

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)

    def on_water_mode_change(self, mode):
        if mode == "Custom Mins":
            self.hhmm_frame.pack_forget()
            self.custom_frame.pack(side="left", expand=True, fill="x")
        else:
            self.custom_frame.pack_forget()
            self.hhmm_frame.pack(side="left", expand=True, fill="x")

    def apply_custom_water_interval(self):
        try:
            val = float(self.custom_water_entry.get().strip())
            if val > 0:
                self.water_reminder_interval = val * 60
                self.water_elapsed_time = 0.0
                self.water_title.configure(text=f"💧 Water Alert ({val}m active)")
            else:
                self.water_title.configure(text="💧 Enter value > 0")
        except ValueError:
            self.water_title.configure(text="💧 Enter valid number!")

    def update_water_interval(self):
        hrs = int(self.hh_option.get())
        mins = int(self.mm_option.get())
        total_seconds = (hrs * 3600) + (mins * 60)

        if total_seconds > 0:
            self.water_reminder_interval = total_seconds
            self.water_elapsed_time = 0.0
            self.water_title.configure(text=f"💧 Water Alert ({hrs:02d}h {mins:02d}m set)")
        else:
            self.water_title.configure(text="💧 Choose interval > 0m")

    def play_100db_beep(self):
        if getattr(self, "meeting_mode_var", None) and self.meeting_mode_var.get():
            return
        try:
            if platform.system() == "Windows":
                winsound.Beep(2500, 1000)
            else:
                print('\a', end='', flush=True)
        except Exception as e:
            print("Audio Alert Triggered:", e)

    def trigger_water_alert_popup(self):
        if self.water_popup_active:
            return

        self.water_popup_active = True
        self.stop_tracking()
        self.play_100db_beep()

        popup = ctk.CTkToplevel(self)
        popup.title("Hydration Break")
        popup.geometry("450x260")
        popup.grab_set()
        popup.attributes("-topmost", True)

        ctk.CTkLabel(
            popup, 
            text="💧 Hydration Break Required!", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38BDF8"
        ).pack(pady=(22, 10))

        ctk.CTkLabel(
            popup, 
            text="Time to drink water! Posture tracking is paused.\nDrink water, sit upright, then press the button below.", 
            font=ctk.CTkFont(size=13), 
            justify="center"
        ).pack(pady=10)

        def on_user_drank_water():
            popup.destroy()
            self.water_popup_active = False
            self.water_elapsed_time = 0.0
            self.show_water_alert = False
            self.start_or_resume_tracking()

        popup.protocol("WM_DELETE_WINDOW", on_user_drank_water)

        ctk.CTkButton(
            popup, 
            text="I Drank Water 🥤", 
            fg_color="#10B981", 
            hover_color="#059669",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=45,
            command=on_user_drank_water
        ).pack(pady=20, fill="x", padx=40)

    def handle_keypress(self, event):
        key = event.char.lower()
        if key == 'c':
            self.start_or_resume_tracking()
        elif key == 's':
            self.stop_tracking()
        elif key == 'q':
            self.on_close()

    def start_or_resume_tracking(self):
        self.calibrating = True
        self.calibration_start = time.time()
        self.is_tracking = True
        self.last_active_timestamp = time.time()

        if self.start_time is None:
            self.start_time = time.time()

        self.status_box.configure(text="⏳ CALIBRATING GEOMETRY...", fg_color="#D97706", text_color="#FFFFFF")

    def stop_tracking(self):
        if self.is_tracking:
            self.is_tracking = False
            self.calibrating = False
            self.status_box.configure(text="⏸ PAUSED - Press C or 👍 to Resume", fg_color="#DC2626", text_color="#FFFFFF")

    def detect_hand_gesture(self, hand_landmarks):
        thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
        thumb_mcp = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_MCP]
        
        index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
        middle_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
        ring_tip = hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP]
        pinky_tip = hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP]
        
        index_pip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_PIP]
        middle_pip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_PIP]
        ring_pip = hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_PIP]
        pinky_pip = hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_PIP]

        fingers_folded = (
            index_tip.y > index_pip.y and
            middle_tip.y > middle_pip.y and
            ring_tip.y > ring_pip.y and
            pinky_tip.y > pinky_pip.y
        )

        if fingers_folded:
            if thumb_tip.y < thumb_mcp.y - 0.05:
                return "THUMBS_UP"
            elif thumb_tip.y > thumb_mcp.y + 0.05:
                return "THUMBS_DOWN"

        fingers_extended = (
            index_tip.y < index_pip.y and
            middle_tip.y < middle_pip.y and
            ring_tip.y < ring_pip.y and
            pinky_tip.y < pinky_pip.y
        )
        if fingers_extended:
            return "WAVE"

        return None

    def get_live_posture_score(self):
        if self.total_work_elapsed <= 0:
            return 0
        score = int((self.optimal_time_counter / self.total_work_elapsed) * 100)
        return min(100, max(0, score))

    def get_final_averaged_posture_score(self):
        all_averages = list(self.minute_averages)
        
        if self.second_scores_current_minute:
            current_min_avg = sum(self.second_scores_current_minute) / len(self.second_scores_current_minute)
            all_averages.append(current_min_avg)

        if not all_averages:
            return self.get_live_posture_score()
            
        return round(sum(all_averages) / len(all_averages))

    def generate_slime_pet_frame(self, posture_compliance, width, height):
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        canvas[:] = (15, 23, 42) 

        is_good = posture_compliance >= 80
        time_sec = time.time()

        if self.user_is_waving:
            body_color = (236, 72, 153) 
            status_str = "👋 Slime is waving back at you!"
        elif is_good:
            body_color = (120, 217, 56) 
            status_str = "🟢 Happy Slime (Good Posture)"
        else:
            body_color = (56, 56, 217)   
            status_str = "🔴 Panicked Slime (Slouching!)"

        cv2.putText(canvas, f"🟢 Slime-Mold Pet: {posture_compliance}%", (12, 22), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (56, 189, 248), 1, cv2.LINE_AA)
        cv2.putText(canvas, status_str, (12, height - 12), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

        center_x = width // 2
        center_y = int(height * 0.55)

        base_radius = int(min(width, height) * 0.28)
        wobble = int(np.sin(time_sec * (12 if self.user_is_waving else (4 if is_good else 12))) * 6)
        
        rx = base_radius + wobble if is_good else int(base_radius * 0.9 + wobble)
        ry = base_radius - wobble if is_good else int(base_radius * 0.75 - wobble)

        for offset_r in range(3, 0, -1):
            alpha_color = tuple(int(c * (0.4 + offset_r * 0.2)) for c in body_color)
            cv2.ellipse(canvas, (center_x, center_y + offset_r * 2), (rx + offset_r * 4, ry + offset_r * 4), 
                        0, 0, 360, alpha_color, 1, cv2.LINE_AA)

        cv2.ellipse(canvas, (center_x, center_y), (rx, ry), 0, 0, 360, body_color, -1, cv2.LINE_AA)
        cv2.ellipse(canvas, (center_x, center_y), (rx, ry), 0, 0, 360, (255, 255, 255), 1, cv2.LINE_AA)

        if self.user_is_waving:
            wave_offset_x = center_x + rx + int(np.sin(time_sec * 25) * 15)
            wave_offset_y = center_y - int(ry * 0.3) + int(np.cos(time_sec * 20) * 10)
            cv2.circle(canvas, (wave_offset_x, wave_offset_y), int(base_radius * 0.18), body_color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (wave_offset_x, wave_offset_y), int(base_radius * 0.18), (255, 255, 255), 1, cv2.LINE_AA)

        eye_y = center_y - int(ry * 0.2)
        left_eye_x = center_x - int(rx * 0.35)
        right_eye_x = center_x + int(rx * 0.35)
        eye_radius = max(8, int(base_radius * 0.12))

        jitter_x = int(np.sin(time_sec * 20) * 4) if not is_good else 0
        jitter_y = int(np.cos(time_sec * 25) * 3) if not is_good else 0

        for ex in [left_eye_x, right_eye_x]:
            cv2.circle(canvas, (ex, eye_y), eye_radius, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (ex, eye_y), eye_radius, (0, 0, 0), 1, cv2.LINE_AA)
            pupil_x = ex + jitter_x
            pupil_y = eye_y + jitter_y
            cv2.circle(canvas, (pupil_x, pupil_y), max(3, int(eye_radius // 2.5)), (0, 0, 0), -1, cv2.LINE_AA)

        return canvas

    def update_feed(self):
        if not self.is_running:
            return

        ret, frame = self.cap.read()
        if ret:
            now = time.time()
            dt = now - self.last_frame_time
            self.last_frame_time = now

            self.date_lbl.configure(text=datetime.now().strftime("%A, %B %d, %Y"))

            if self.user_is_waving and (now - self.wave_timer > 2.0):
                self.user_is_waving = False

            is_optimal_this_frame = False
            is_slouching = False

            if self.is_tracking and self.last_active_timestamp is not None:
                self.total_work_elapsed += dt
                self.water_elapsed_time += dt
                self.stretch_elapsed_time += dt

                if self.water_elapsed_time >= self.water_reminder_interval:
                    self.show_water_alert = True
                    self.alert_start_time = now
                    self.trigger_water_alert_popup()

                if self.stretch_elapsed_time >= self.stretch_reminder_interval:
                    self.show_stretch_alert = True
                    self.alert_start_time = now
                    self.stretch_elapsed_time = 0.0
                    self.play_voice_alert_async("Time to stand up and stretch!")

            if self.show_stretch_alert and (now - self.alert_start_time > 8):
                self.show_stretch_alert = False

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            pose_results = self.pose.process(rgb_frame)
            hands_results = self.hands.process(rgb_frame)
            _ = self.face_mesh.process(rgb_frame)

            if not self.is_tracking:
                health_text = "System paused. Give a 👍 Thumbs Up or press 'C' to start."
                preventive_text = "Action: Show 👍 to start tracking."
            else:
                health_text = "Monitoring posture geometry."
                preventive_text = "Action: Maintain neutral head position and open chest. 👎 to pause."

            if hands_results.multi_hand_landmarks:
                for hand_landmarks in hands_results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing.DrawingSpec(color=(250, 204, 21), thickness=2, circle_radius=2),
                        mp_drawing.DrawingSpec(color=(56, 189, 248), thickness=2, circle_radius=2)
                    )
                    
                    gesture = self.detect_hand_gesture(hand_landmarks)
                    if gesture == "WAVE":
                        self.user_is_waving = True
                        self.wave_timer = now
                    elif now - self.last_gesture_toggle_time > 2.0:
                        if gesture == "THUMBS_UP" and not self.is_tracking:
                            self.last_gesture_toggle_time = now
                            self.start_or_resume_tracking()
                        elif gesture == "THUMBS_DOWN" and self.is_tracking:
                            self.last_gesture_toggle_time = now
                            self.stop_tracking()

            if pose_results.pose_landmarks and self.is_tracking:
                landmarks = pose_results.pose_landmarks.landmark

                mp_drawing.draw_landmarks(
                    frame,
                    pose_results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(56, 189, 248), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(241, 245, 249), thickness=2, circle_radius=2)
                )

                nose = landmarks[mp_pose.PoseLandmark.NOSE]
                left_ear = landmarks[mp_pose.PoseLandmark.LEFT_EAR]
                right_ear = landmarks[mp_pose.PoseLandmark.RIGHT_EAR]
                left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
                right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]

                if left_shoulder.visibility > 0.2 and right_shoulder.visibility > 0.2:
                    current_ratio = self.analyzer.compute_ratio(
                        nose, left_ear, right_ear, left_shoulder, right_shoulder
                    )

                    if self.calibrating:
                        if time.time() - self.calibration_start > 1.0:
                            success = self.analyzer.calibrate(current_ratio)
                            if success:
                                self.calibrating = False
                                self.status_box.configure(
                                    text="🔴 Tracking Active - Give 👎 to Pause", 
                                    fg_color="#059669", 
                                    text_color="#FFFFFF"
                                )

                    elif self.analyzer.calibrated:
                        if self.analyzer.is_misaligned(current_ratio):
                            is_slouching = True
                            self.stressed_box.configure(border_color="#EF4444")
                            self.stressed_area_lbl.configure(
                                text="📍 Main Stressed Area:\n• Cervical spine & upper shoulders"
                            )
                            self.possible_problem_lbl.configure(
                                text="⚠️ Possible Strain Symptoms:\n• Forward neck strain, spinal stiffness & muscle fatigue"
                            )
                            
                            health_text = "Forward head posture/slouching detected!"
                            preventive_text = "Action: Pull shoulders back and raise chin."
                            self.play_voice_alert_async("Please align your spine and posture")
                        else:
                            self.stressed_box.configure(border_color="#10B981")
                            self.stressed_area_lbl.configure(
                                text="📍 Main Stressed Area:\n• Balanced posture — minimal strain"
                            )
                            self.possible_problem_lbl.configure(
                                text="⚠️ Possible Strain Symptoms:\n• Neutral alignment maintained"
                            )
                            
                            health_text = "Spine in neutral geometry."
                            preventive_text = "Action: Keep chest open and maintain alignment."
                            self.optimal_time_counter += dt
                            is_optimal_this_frame = True

            if self.is_tracking and not self.calibrating:
                self.second_timer += dt
                if is_optimal_this_frame:
                    self.second_optimal_time += dt

                if self.second_timer >= 1.0:
                    sec_score = (self.second_optimal_time / self.second_timer) * 100
                    self.second_scores_current_minute.append(sec_score)

                    self.second_timer = 0.0
                    self.second_optimal_time = 0.0

                    if len(self.second_scores_current_minute) >= 60:
                        minute_avg = sum(self.second_scores_current_minute) / len(self.second_scores_current_minute)
                        self.minute_averages.append(minute_avg)
                        self.second_scores_current_minute = []

            if self.user_is_waving:
                self.live_health_lbl.configure(text="• Status: Hand wave detected! Slime is waving back.", text_color="#F472B6")
                self.live_action_lbl.configure(text="• Action: Enjoy interacting with your posture pet!", text_color="#EC4899")
            elif is_slouching:
                self.live_health_lbl.configure(text=f"• Status: {health_text}", text_color="#FCA5A5")
                self.live_action_lbl.configure(text=f"• Action: {preventive_text}", text_color="#EF4444")
            elif self.show_water_alert:
                self.live_health_lbl.configure(text="• Status: Hydration reminder active.", text_color="#FCD34D")
                self.live_action_lbl.configure(text="• Action: Drink water and take a sip break.", text_color="#F59E0B")
            elif self.show_stretch_alert:
                self.live_health_lbl.configure(text="• Status: Stretch break recommended.", text_color="#C084FC")
                self.live_action_lbl.configure(text="• Action: Stand up and roll your shoulders.", text_color="#A855F7")
            else:
                self.live_health_lbl.configure(text=f"• Status: {health_text}", text_color="#E2E8F0")
                self.live_action_lbl.configure(text=f"• Action: {preventive_text}", text_color="#38BDF8")

            hrs, rem = divmod(int(self.total_work_elapsed), 3600)
            mins, secs = divmod(rem, 60)
            self.worktime_lbl.configure(text=f"⏱ Work Duration: {hrs:02d}:{mins:02d}:{secs:02d}")

            g_hrs, g_rem = divmod(int(self.optimal_time_counter), 3600)
            g_mins, g_secs = divmod(g_rem, 60)
            self.good_time_lbl.configure(text=f"🎯 Optimal Alignment: {g_hrs:02d}:{g_mins:02d}:{g_secs:02d}")

            live_score = self.get_live_posture_score()
            self.score_lbl.configure(text=f"📊 Posture Compliance: {live_score}%")
            self.score_bar.set(live_score / 100.0)

            max_w_vid = max(100, self.video_frame.winfo_width() - 10)
            max_h_vid = max(100, self.video_frame.winfo_height() - 10)
            scale_vid = min(max_w_vid / float(w), max_h_vid / float(h))
            t_w_vid, t_h_vid = max(1, int(w * scale_vid)), max(1, int(h * scale_vid))

            resized_frame = cv2.resize(frame, (t_w_vid, t_h_vid), interpolation=cv2.INTER_AREA)
            img_vid = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            img_vid_pil = Image.fromarray(img_vid)
            img_tk_vid = ctk.CTkImage(light_image=img_vid_pil, dark_image=img_vid_pil, size=(t_w_vid, t_h_vid))
            self.video_label.configure(image=img_tk_vid)

            max_w_av = max(100, self.avatar_frame.winfo_width() - 10)
            max_h_av = max(100, self.avatar_frame.winfo_height() - 10)
            scale_av = min(max_w_av / float(w), max_h_av / float(h))
            t_w_av, t_h_av = max(1, int(w * scale_av)), max(1, int(h * scale_av))

            avatar_canvas = self.generate_slime_pet_frame(live_score, w, h)
            resized_avatar = cv2.resize(avatar_canvas, (t_w_av, t_h_av), interpolation=cv2.INTER_AREA)
            img_av = cv2.cvtColor(resized_avatar, cv2.COLOR_BGR2RGB)
            img_av_pil = Image.fromarray(img_av)
            img_tk_av = ctk.CTkImage(light_image=img_av_pil, dark_image=img_av_pil, size=(t_w_av, t_h_av))
            self.avatar_label.configure(image=img_tk_av)

        self.after(15, self.update_feed)

    def save_csv_log(self):
        filename = "daily_posture_log.csv"

        today_date = datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")
        location_tag = self.location_menu.get()

        total_work_sec = int(self.total_work_elapsed)
        hrs, rem = divmod(total_work_sec, 3600)
        mins, secs = divmod(rem, 60)
        formatted_work_time = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        good_sec = int(self.optimal_time_counter)
        g_hrs, g_rem = divmod(good_sec, 3600)
        g_mins, g_secs = divmod(g_rem, 60)
        formatted_good_time = f"{g_hrs:02d}:{g_mins:02d}:{g_secs:02d}"

        final_score = self.get_final_averaged_posture_score()
        score_val = f"{final_score}%"

        self.update_streak_and_xp(final_score)

        headers = [
            "Log Date",
            "Session Timestamp",
            "Location Tag",
            "Total Work Duration (HH:MM:SS)",
            "Good Posture Duration (HH:MM:SS)",
            "Average Posture Compliance Score"
        ]

        row_data = [
            today_date,
            current_time,
            location_tag,
            formatted_work_time,
            formatted_good_time,
            score_val
        ]

        file_exists = os.path.exists(filename)

        try:
            with open(filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerow(row_data)
            print("Session log successfully saved to", filename)
        except Exception as e:
            print("Error saving CSV log:", e)

    def on_close(self):
        if self.exit_popup_active:
            return
        
        self.exit_popup_active = True
        self.stop_tracking()
        self.is_running = False

        popup = ctk.CTkToplevel(self)
        popup.title("Save Session & Exit")
        popup.geometry("400x220")
        popup.grab_set()
        popup.attributes("-topmost", True)

        ctk.CTkLabel(
            popup, 
            text="Exit AlignMe Application?", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#F8FAFC"
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            popup, 
            text="Would you like to save this session's metrics\nto your daily posture logs before exiting?", 
            font=ctk.CTkFont(size=12), 
            justify="center",
            text_color="#94A3B8"
        ).pack(pady=5)

        def save_and_quit():
            self.save_csv_log()
            popup.destroy()
            self._fully_destroy()

        def discard_and_quit():
            popup.destroy()
            self._fully_destroy()

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=20, fill="x", padx=30)

        ctk.CTkButton(
            btn_frame, 
            text="Save & Exit", 
            fg_color="#10B981", 
            hover_color="#059669",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=save_and_quit,
            height=36
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, 
            text="Exit Without Saving", 
            fg_color="#334155", 
            hover_color="#475569",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=discard_and_quit,
            height=36
        ).pack(side="right", expand=True, fill="x", padx=(5, 0))

        popup.protocol("WM_DELETE_WINDOW", discard_and_quit)

    def _fully_destroy(self):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            if self.cap.isOpened():
                self.cap.release()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    app = PostureApp()
    app.mainloop()