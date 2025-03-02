import cv2
import mediapipe as mp
import math
import platform
import subprocess
import ctypes
import time
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
from collections import deque
import threading
import pyautogui

# Speech recognition and keyboard control imports
from audio import start_speech_recognition, get_recognized_speech

app = FastAPI()
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
volume_gesture_cooldown = 1.0 if platform.system() == "Windows" else 0.3
last_music_gesture_time = 0
music_gesture_cooldown = 2.0  # seconds
last_click_time = 0
click_cooldown = 1.0  # seconds

# Separate gesture history for left and right hands
left_gesture_history = deque(maxlen=5)
right_gesture_history = deque(maxlen=5)

prev_point_position = None        # For right-hand pointer (cursor)
prev_right_point_position = None  # For scrolling via right-hand pointer
prev_rock_on = False

# Speech recognition globals
speech_recognition_active = False
last_speech_text = None
last_speech_time = 0
speech_display_duration = 5.0  # seconds

# -----------------------
# OS Control Functions
# -----------------------
if platform.system() == "Windows":
    def volume_up_windows():
        VK_VOLUME_UP = 0xAF
        KEYEVENTF_EXTENDEDKEY = 0x1
        KEYEVENTF_KEYUP = 0x2
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

    def click_action_windows():
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def volume_up():
        for _ in range(3):
            volume_up_windows()
            time.sleep(0.05)

    def volume_down():
        for _ in range(3):
            volume_down_windows()
            time.sleep(0.05)
        
    def play_pause_music():
        play_pause_music_windows()

    def move_cursor_absolute(x, y):
        ctypes.windll.user32.SetCursorPos(int(x), int(y))

elif platform.system() == "Darwin":
    def volume_up():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = min(current_volume + 6, 100)
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)

    def volume_down():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = max(current_volume - 6, 0)
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)
        
    def play_pause_music():
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke space'", shell=True)

    def click_action():
        pyautogui.click()

    def move_cursor_absolute(x, y):
        pyautogui.moveTo(x, y, duration=0.1)
else:
    def volume_up():
        print("Volume up not supported on this platform")
    def volume_down():
        print("Volume down not supported on this platform")
    def play_pause_music():
        print("Play/pause music not supported on this platform")
    def click_action():
        print("Click action not supported on this platform")
    def move_cursor_absolute(x, y):
        print("Cursor control not supported on this platform")

def click_action_generic():
    if platform.system() == "Windows":
        click_action_windows()
    elif platform.system() == "Darwin":
        click_action()
        
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
# Gesture Detection Function (MediaPipe-based)
# -----------------------
def detect_static_gesture(hand_landmarks, frame):
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
    thumb_tip = landmarks[4]
    delta_thumb = 0.025
    thumb_up = (thumb_tip.y < thumb_mcp.y - delta_thumb) and (abs((thumb_tip.x * w) - hand_center_x) < hand_width * 0.3)
    thumb_down = (thumb_tip.y > thumb_mcp.y + delta_thumb) and (abs((thumb_tip.x * w) - hand_center_x) < hand_width * 0.3)

    # Define gestures
    if index_ext and middle_ext and ring_ext and pinky_ext:
        return "Open Palm"
    elif index_ext and middle_ext and (not ring_ext) and (not pinky_ext):
        return "Peace"
    elif index_ext and pinky_ext and middle_folded and ring_folded:
        return "Rock On"
    elif (not index_ext and not middle_ext and not ring_ext and not pinky_ext) and thumb_up:
        return "Thumbs Up"
    elif (not index_ext and not middle_ext and not ring_ext and not pinky_ext) and thumb_down:
        return "Thumbs Down"
    elif index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext):
        return "Point"
    else:
        return "Unrecognized"

# -----------------------
# Frame Processing Function with Dual-Hand and Scroll Mode
# -----------------------
def process_frame(frame):
    global last_volume_gesture_time, last_click_time, last_music_gesture_time
    global last_speech_text, last_speech_time, prev_point_position, prev_right_point_position, prev_rock_on
    global left_gesture_history, right_gesture_history

    current_time = time.time()
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)
    h, w, _ = frame.shape

    new_speech = get_recognized_speech()
    if new_speech:
        last_speech_text = new_speech
        last_speech_time = current_time
        print(f"New speech recognized: {new_speech}")

    # Display speech recognition status and results
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    # Display wake word instruction
    cv2.putText(frame, "Say 'Hey Adam' to activate speech recognition", (10, h - 60), font, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    
    # Display the recognized speech if it's recent
    if last_speech_text and (current_time - last_speech_time < speech_display_duration):
        # Display recognition result with a background
        text = f"Speech: {last_speech_text}"
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        
        # Draw semi-transparent background for text
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, h - 40), (10 + text_size[0] + 20, h - 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        cv2.putText(frame, text, (20, h - 20), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)


    # Gesture instructions overlay
    cv2.putText(frame, "Vol Up/Down: Thumbs | Music: Rock On | Click: Open Palm | Cursor: Point | Scroll Mode: Left Peace + Right Point",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)

    left_confirmed = None
    right_confirmed = None
    right_index_tip = None

    if results.multi_hand_landmarks and results.multi_handedness:
        for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            xs = [lm.x for lm in hand_landmarks.landmark]
            ys = [lm.y for lm in hand_landmarks.landmark]
            x_min_val = int(min(xs) * w)
            x_max_val = int(max(xs) * w)
            y_min_val = int(min(ys) * h)
            y_max_val = int(max(ys) * h)
            cv2.rectangle(frame, (x_min_val, y_min_val), (x_max_val, y_max_val), (0,255,0), 2)
            
            # Get handedness label ("Left" or "Right")
            handedness = results.multi_handedness[i].classification[0].label
            gesture = detect_static_gesture(hand_landmarks, frame)
            cv2.putText(frame, f"{handedness}: {gesture}", (x_min_val, y_min_val - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)
            if handedness == "Left":
                left_gesture_history.append(gesture)
            elif handedness == "Right":
                right_gesture_history.append(gesture)
                if gesture == "Point":
                    right_index_tip = hand_landmarks.landmark[8]
        
        # Confirm gestures with multi-frame smoothing (at least 3 of last 5 frames)
        if len(left_gesture_history) >= 3:
            candidate = max(set(left_gesture_history), key=left_gesture_history.count)
            if left_gesture_history.count(candidate) >= 3:
                left_confirmed = candidate
        if len(right_gesture_history) >= 3:
            candidate = max(set(right_gesture_history), key=right_gesture_history.count)
            if right_gesture_history.count(candidate) >= 3:
                right_confirmed = candidate

        # Trigger actions based on right hand confirmed gesture
        if right_confirmed == "Thumbs Up" and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
            volume_up()
            print("Volume increased")
            last_volume_gesture_time = current_time
        elif right_confirmed == "Thumbs Down" and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
            volume_down()
            print("Volume decreased")
            last_volume_gesture_time = current_time

        if right_confirmed == "Rock On":
            if not prev_rock_on and (current_time - last_music_gesture_time > music_gesture_cooldown):
                play_pause_music()
                print("Music toggled")
                last_music_gesture_time = current_time
            prev_rock_on = True
        else:
            prev_rock_on = False

        if right_confirmed == "Open Palm" and (current_time - last_click_time > click_cooldown):
            click_action_generic()
            print("Click action triggered")
            last_click_time = current_time

        # Determine if scroll mode is active: left hand is "Peace" and right hand is "Point"
        scroll_mode = (left_confirmed == "Peace" and right_confirmed == "Point")
        if scroll_mode:
            cv2.putText(frame, "Scroll Mode Active", (10, h - 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2, cv2.LINE_AA)
            if right_index_tip is not None:
                current_right_point = (right_index_tip.x * w, right_index_tip.y * h)
                if prev_right_point_position is not None:
                    dy = current_right_point[1] - prev_right_point_position[1]
                    scroll_amount = int(-dy * 2)  # Adjust scaling factor as needed
                    if scroll_amount != 0:
                        pyautogui.scroll(scroll_amount)
                        print("Scrolling", scroll_amount)
                prev_right_point_position = current_right_point
        else:
            prev_right_point_position = None

        # If not in scroll mode and right hand is "Point", use its movement to control the cursor
        if (not scroll_mode) and (right_confirmed == "Point") and (right_index_tip is not None):
            screen_w, screen_h = get_screen_size()
            current_point = (right_index_tip.x * screen_w, right_index_tip.y * screen_h)
            global prev_point_position
            if prev_point_position is None:
                prev_point_position = current_point
            else:
                dx = current_point[0] - prev_point_position[0]
                dy = current_point[1] - prev_point_position[1]
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
# Video Streaming
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
    return {"message": "Hand Gesture App with Dual-Hand Scroll Mode"}

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.on_event("startup")
async def startup_event():
    
    # Start speech recognition in a background thread
    threading.Thread(target=start_speech_recognition, daemon=True).start()
    print("Speech recognition initialized with wake word: 'Hey Adam'")
    print("Speech will now be converted to keyboard input")


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8001)