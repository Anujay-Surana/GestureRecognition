from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import cv2
import mediapipe as mp
import math
import platform
import subprocess
import ctypes
import time
from fastapi.responses import StreamingResponse
import uvicorn
from collections import deque
import threading

# For macOS cursor control via pyautogui
import pyautogui

# Import the speech recognition module
from audio import start_speech_recognition, get_recognized_speech
from speechtokey import speech_to_keyboard
from updatedspeech import update_speech_recognition

app = FastAPI()

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MediaPipe Hands and Drawing Utilities
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)
mp_drawing = mp.solutions.drawing_utils

# Global variables for gesture control and smoothing
last_volume_gesture_time = 0
# Set a longer cooldown on Windows (1.0 sec) to slow down volume changes;
# on macOS use a shorter delay (0.3 sec)
volume_gesture_cooldown = 1.0 if platform.system() == "Windows" else 0.3

last_music_gesture_time = 0
music_gesture_cooldown = 2.0  # seconds

last_click_time = 0
click_cooldown = 1.0  # seconds for click action

# For dynamic gesture velocity calculation (now removed)
# Smoothing histories (last 5 frames)
static_gesture_history = deque(maxlen=5)

# Global for cursor control ("Point")
prev_point_position = None

# Global flag to prevent repeated toggling for Rock On
prev_rock_on = False

# Speech recognition globals
speech_recognition_active = False
last_speech_text = None
last_speech_time = 0
speech_display_duration = 5.0  # Display recognized speech for 5 seconds

# -----------------------
# Media & OS Control Functions
# -----------------------
if platform.system() == "Windows":
    def volume_up_windows():
        VK_VOLUME_UP = 0xAF
        KEYEVENTF_EXTENDEDKEY = 0x1
        KEYEVENTF_KEYUP = 0x2
        # Simulate one key press
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

    def volume_down_windows():
        VK_VOLUME_DOWN = 0xAE
        KEYEVENTF_EXTENDEDKEY = 0x1
        KEYEVENTF_KEYUP = 0x2
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        
    def play_pause_music_windows():
        HWND_BROADCAST = 0xFFFF
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_MEDIA_PLAY_PAUSE = 0x0E
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_MEDIA_PLAY_PAUSE << 16)

    def minimize_current_window():
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.user32.ShowWindow(hwnd, 6)

    def maximize_current_window():
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.user32.ShowWindow(hwnd, 3)

    def click_action_windows():
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def volume_up():
        # Increase volume by simulating 3 key presses (~6 units if each press is 2)
        for _ in range(3):
            volume_up_windows()
            time.sleep(0.05)

    def volume_down():
        for _ in range(3):
            volume_down_windows()
            time.sleep(0.05)
        
    def play_pause_music():
        play_pause_music_windows()

    import ctypes.wintypes
    def move_cursor_absolute_windows(x, y):
        ctypes.windll.user32.SetCursorPos(int(x), int(y))

    def move_cursor_absolute(x, y):
        move_cursor_absolute_windows(x, y)

elif platform.system() == "Darwin":
    def volume_up_mac():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = min(current_volume + 6, 100)  # Increase by 6
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)

    def volume_down_mac():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = max(current_volume - 6, 0)  # Decrease by 6
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)
        
    def play_pause_music_mac():
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke space'", shell=True)

    def minimize_current_window():
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"m\" using {command down}'", shell=True)

    def maximize_current_window():
        print("Maximize window not implemented on macOS in this example.")

    def click_action_mac():
        pyautogui.click()

    def volume_up():
        volume_up_mac()

    def volume_down():
        volume_down_mac()
        
    def play_pause_music():
        play_pause_music_mac()

    def move_cursor_absolute_mac(x, y):
        pyautogui.moveTo(x, y, duration=0.1)

    def move_cursor_absolute(x, y):
        move_cursor_absolute_mac(x, y)

else:
    def volume_up():
        print("Volume up not supported on this platform")
    def volume_down():
        print("Volume down not supported on this platform")
    def play_pause_music():
        print("Play/pause music not supported on this platform")
    def minimize_current_window():
        print("Window minimize not supported on this platform")
    def maximize_current_window():
        print("Window maximize not supported on this platform")
    def click_action():
        print("Click action not supported on this platform")
    def move_cursor_absolute(x, y):
        print("Cursor control not supported on this platform")

def click_action_generic():
    if platform.system() == "Windows":
        click_action_windows()
    elif platform.system() == "Darwin":
        click_action_mac()

def get_screen_size():
    if platform.system() == "Windows":
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    elif platform.system() == "Darwin":
        size = pyautogui.size()
        return size.width, size.height
    else:
        return 800, 600

# -----------------------
# Gesture Detection Functions
# -----------------------
def detect_static_gesture(hand_landmarks, frame):
    """
    Detects static gestures using refined finger and thumb positions.
    Recognizes:
      - "Rock On": Index and pinky clearly extended; middle and ring clearly folded.
      - "Open Palm": All four non-thumb fingers clearly extended. (Used for click action.)
      - "Thumbs Up": All non-thumb fingers clearly folded and thumb clearly up.
      - "Thumbs Down": All non-thumb fingers clearly folded and thumb clearly down.
      - "Point": Index extended while middle, ring, pinky, and thumb are folded.
      - "Unrecognized": When no clear gesture is detected.
    """
    landmarks = hand_landmarks.landmark
    h, w, _ = frame.shape

    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    x_min = min(xs) * w
    x_max = max(xs) * w
    y_min = min(ys) * h
    y_max = max(ys) * h
    hand_center_x = (x_min + x_max) / 2
    hand_center_y = (y_min + y_max) / 2
    hand_width = x_max - x_min

    def finger_extended(tip_idx, pip_idx, delta=0.05):
        hand_size = (x_max - x_min) * (y_max - y_min)
        screen_size = w * h
        hand_ratio = hand_size / screen_size
        adjusted_delta = delta * 0.6 if hand_ratio < 0.05 else delta
        return landmarks[tip_idx].y < (landmarks[pip_idx].y - adjusted_delta)

    def finger_folded(tip_idx, pip_idx, margin=0.02):
        return landmarks[tip_idx].y > (landmarks[pip_idx].y + margin)

    index_ext = finger_extended(8, 6)
    middle_ext = finger_extended(12, 10)
    ring_ext = finger_extended(16, 14)
    pinky_ext = finger_extended(20, 18)

    middle_folded = finger_folded(12, 10)
    ring_folded = finger_folded(16, 14)
    pinky_folded = finger_folded(20, 18)

    thumb_mcp = landmarks[2]
    thumb_ip = landmarks[3]
    thumb_tip = landmarks[4]
    delta_thumb = 0.025

    # For Thumbs Up/Down, require that all non-thumb fingers are folded.
    thumb_up = (thumb_tip.y < thumb_mcp.y - delta_thumb) and (abs((thumb_tip.x * w) - hand_center_x) < hand_width * 0.3)
    thumb_down = (thumb_tip.y > thumb_mcp.y + delta_thumb) and (abs((thumb_tip.x * w) - hand_center_x) < hand_width * 0.3)
    thumb_folded = not (thumb_up or thumb_down)

    # Gesture priorities:
    if index_ext and pinky_ext and middle_folded and ring_folded:
        return "Rock On"
    elif index_ext and middle_ext and ring_ext and pinky_ext:
        return "Open Palm"
    elif (not index_ext and not middle_ext and not ring_ext and not pinky_ext) and thumb_up:
        return "Thumbs Up"
    elif (not index_ext and not middle_ext and not ring_ext and not pinky_ext) and thumb_down:
        return "Thumbs Down"
    elif index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext) and thumb_folded:
        return "Point"
    else:
        return "Unrecognized"

# -----------------------
# Frame Processing Function
# -----------------------
def process_frame(frame):
    global last_volume_gesture_time, last_click_time, last_music_gesture_time
    global last_speech_text, last_speech_time, prev_point_position, prev_rock_on

    current_time = time.time()
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)
    h, w, _ = frame.shape

    # Check for any new speech recognition results (do not modify)
    new_speech = get_recognized_speech()
    if new_speech:
        last_speech_text = new_speech
        last_speech_time = current_time
        print(f"New speech recognized: {new_speech}")

    font = cv2.FONT_HERSHEY_SIMPLEX
    
    # Display speech instructions and recognized text (do not modify)
    cv2.putText(frame, "Say 'Hey Adam' to activate speech recognition", 
                (10, h - 60), font, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if last_speech_text and (current_time - last_speech_time < speech_display_duration):
        text = f"Speech: {last_speech_text}"
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, h - 40), (10 + text_size[0] + 20, h - 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.putText(frame, text, (20, h - 20), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    # Gesture instruction overlay
    cv2.putText(frame, "Thumbs Up: Vol + | Thumbs Down: Vol - | Rock On: Music | Point: Cursor | Open Palm: Click", 
                (10, 30), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    first_hand_confirmed_gesture = None
    index_finger_tip = None  # for cursor control ("Point")

    if results.multi_hand_landmarks:
        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            x_coords = [lm.x for lm in hand_landmarks.landmark]
            y_coords = [lm.y for lm in hand_landmarks.landmark]
            x_min_val = int(min(x_coords) * w)
            x_max_val = int(max(x_coords) * w)
            y_min_val = int(min(y_coords) * h)
            y_max_val = int(max(y_coords) * h)
            cv2.rectangle(frame, (x_min_val, y_min_val), (x_max_val, y_max_val), (0, 255, 0), 2)
            
            if idx == 0:
                first_bbox = (x_min_val, y_min_val, x_max_val, y_max_val)
            
            gesture = detect_static_gesture(hand_landmarks, frame)
            if gesture:
                text_y = y_min_val - 10 if y_min_val - 10 > 20 else y_min_val + 30
                cv2.putText(frame, gesture, (x_min_val, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
            
            if idx == 0:
                if gesture is not None:
                    static_gesture_history.append(gesture)
                else:
                    static_gesture_history.clear()

                if len(static_gesture_history) >= 3:
                    candidate = max(set(static_gesture_history), key=static_gesture_history.count)
                    if static_gesture_history.count(candidate) >= 3:
                        first_hand_confirmed_gesture = candidate
                    else:
                        first_hand_confirmed_gesture = None
                else:
                    first_hand_confirmed_gesture = None

                # For cursor control ("Point"), get index finger tip (landmark 8)
                if first_hand_confirmed_gesture == "Point":
                    index_finger_tip = hand_landmarks.landmark[8]

                # Volume control: Thumbs Up / Thumbs Down (increase/decrease by 6)
                if first_hand_confirmed_gesture == "Thumbs Up" and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
                    volume_up()
                    print("Volume increased")
                    last_volume_gesture_time = current_time
                elif first_hand_confirmed_gesture == "Thumbs Down" and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
                    volume_down()
                    print("Volume decreased")
                    last_volume_gesture_time = current_time

                # Music control: Rock On toggles media only once per gesture transition.
                if first_hand_confirmed_gesture == "Rock On":
                    if not prev_rock_on and (current_time - last_music_gesture_time > music_gesture_cooldown):
                        play_pause_music()
                        print("Music toggled")
                        last_music_gesture_time = current_time
                        cv2.putText(frame, "Music Toggled!", (x_min_val, text_y + 40), font, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
                    prev_rock_on = True
                else:
                    prev_rock_on = False

                # Click action triggered by Open Palm
                if first_hand_confirmed_gesture == "Open Palm" and (current_time - last_click_time > click_cooldown):
                    click_action_generic()
                    print("Click action triggered")
                    last_click_time = current_time

    # Cursor control for "Point" gesture: apply relative movement.
    if first_hand_confirmed_gesture == "Point" and index_finger_tip is not None:
        screen_w, screen_h = get_screen_size()
        current_point = (index_finger_tip.x * screen_w, index_finger_tip.y * screen_h)
        global prev_point_position
        if prev_point_position is None:
            prev_point_position = current_point
        else:
            dx = current_point[0] - prev_point_position[0]
            dy = current_point[1] - prev_point_position[1]
            # Get current cursor position
            if platform.system() == "Windows":
                import ctypes.wintypes
                pt = ctypes.wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                current_cursor = (pt.x, pt.y)
            elif platform.system() == "Darwin":
                current_cursor = pyautogui.position()
            else:
                current_cursor = (0, 0)
            new_cursor = (current_cursor[0] + dx, current_cursor[1] + dy)
            move_cursor_absolute(new_cursor[0], new_cursor[1])
            prev_point_position = current_point
    else:
        prev_point_position = None

    return frame

# -----------------------
# Streaming Function
# -----------------------
def generate_frames():
    cap = cv2.VideoCapture(0)
    try:
        while True:
            success, frame = cap.read()
            if not success:
                break
            
            processed_frame = process_frame(frame)
            ret, buffer = cv2.imencode('.jpg', processed_frame)
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        cap.release()

@app.get("/")
async def root():
    return {
        "message": "Gesture and Speech Control API (Windows Optimized)",
        "instructions": "Access video feed at /video_feed",
        "gestures": {
            "Thumbs Up": "Increase volume",
            "Thumbs Down": "Decrease volume",
            "Rock On": "Play/pause music",
            "Point": "Move cursor",
            "Open Palm": "Click action",
            "Unrecognized": "No clear gesture detected"
        },
        "speech": {
            "Wake word": "Hey Adam",
            "Timeout": "3 seconds of silence"
        }
    }

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# Initialize the speech recognition when the server starts (do not modify)
@app.on_event("startup")
async def startup_event():
    update_speech_recognition()
    threading.Thread(target=start_speech_recognition, daemon=True).start()
    print("Speech recognition initialized with wake word: 'Hey Adam'")
    print("Speech will now be converted to keyboard input")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
