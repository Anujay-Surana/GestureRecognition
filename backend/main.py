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

# For macOS cursor control via pyautogui
import pyautogui

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

# Global variables for volume gesture control, dynamic gesture detection, and cursor control
last_volume_gesture_time = 0
volume_gesture_cooldown = 1  # seconds
previous_static_gesture = None  # To avoid repeated volume commands

previous_hand_center = None
dynamic_gesture_last_time = 0
dynamic_gesture_cooldown = 1  # seconds

previous_cursor_center = None  # Used for cursor control with fist

# Detect platform
current_platform = platform.system()

# -----------------------
# Volume & Window Functions
# -----------------------
if current_platform == "Windows":
    # Volume control functions for Windows using ctypes
    def volume_up_windows():
        HWND_BROADCAST = 0xFFFF
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_VOLUME_UP = 0x0a
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_UP << 16)

    def volume_down_windows():
        HWND_BROADCAST = 0xFFFF
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_VOLUME_DOWN = 0x09
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_DOWN << 16)

    def minimize_current_window():
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        # 6 minimizes the window
        ctypes.windll.user32.ShowWindow(hwnd, 6)

    def maximize_current_window():
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        # 3 maximizes the window
        ctypes.windll.user32.ShowWindow(hwnd, 3)

    def volume_up():
        volume_up_windows()

    def volume_down():
        volume_down_windows()

    # Cursor control for Windows using ctypes (win32 API)
    import ctypes.wintypes
    def move_cursor_windows(dx, dy):
        current_pos = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(current_pos))
        new_x = current_pos.x + int(dx)
        new_y = current_pos.y + int(dy)
        ctypes.windll.user32.SetCursorPos(new_x, new_y)

    def move_cursor(dx, dy):
        move_cursor_windows(dx, dy)

elif current_platform == "Darwin":
    # Volume control functions for macOS using AppleScript
    def volume_up_mac():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = min(current_volume + 5, 100)
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)

    def volume_down_mac():
        try:
            current_volume = subprocess.check_output("osascript -e 'output volume of (get volume settings)'", shell=True)
            current_volume = int(current_volume.decode().strip())
        except Exception:
            current_volume = 50
        new_volume = max(current_volume - 5, 0)
        subprocess.run(f"osascript -e 'set volume output volume {new_volume}'", shell=True)

    def minimize_current_window():
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"m\" using {command down}'", shell=True)

    def maximize_current_window():
        print("Maximize window not implemented on macOS in this example.")

    def volume_up():
        volume_up_mac()

    def volume_down():
        volume_down_mac()

    # Cursor control for macOS using pyautogui
    def move_cursor_mac(dx, dy):
        current_x, current_y = pyautogui.position()
        new_x = current_x + int(dx)
        new_y = current_y + int(dy)
        # Slow movement using a short duration
        pyautogui.moveTo(new_x, new_y, duration=0.2)

    def move_cursor(dx, dy):
        move_cursor_mac(dx, dy)

else:
    def volume_up():
        print("Volume up not supported on this platform")
    def volume_down():
        print("Volume down not supported on this platform")
    def minimize_current_window():
        print("Window minimize not supported on this platform")
    def maximize_current_window():
        print("Window maximize not supported on this platform")
    def move_cursor(dx, dy):
        print("Cursor control not supported on this platform")

# -----------------------
# Gesture Detection Functions
# -----------------------
def detect_static_gesture(hand_landmarks, frame):
    """
    Detects static gestures using finger extension and thumb angle.
    Recognizes:
      - "Open Palm": All four non-thumb fingers extended.
      - "Fist": All four non-thumb fingers folded.
      - "Thumbs Up": All non-thumb fingers folded and thumb pointing upward.
      - "Thumbs Down": All non-thumb fingers folded and thumb pointing downward.
    """
    landmarks = hand_landmarks.landmark
    h, w, _ = frame.shape

    def finger_extended(tip_idx, pip_idx):
        return landmarks[tip_idx].y < landmarks[pip_idx].y

    index_extended = finger_extended(8, 6)
    middle_extended = finger_extended(12, 10)
    ring_extended = finger_extended(16, 14)
    pinky_extended = finger_extended(20, 18)
    extended_count = sum([index_extended, middle_extended, ring_extended, pinky_extended])
    
    thumb_mcp = landmarks[2]
    thumb_tip = landmarks[4]
    dx = thumb_tip.x - thumb_mcp.x
    dy = thumb_tip.y - thumb_mcp.y
    angle = math.degrees(math.atan2(dy, dx))
    threshold_angle = 20  # degrees tolerance

    if extended_count == 4:
        return "Open Palm"
    elif extended_count == 0:
        if thumb_tip.y < thumb_mcp.y and abs(angle + 90) < threshold_angle:
            return "Thumbs Up"
        elif thumb_tip.y > thumb_mcp.y and abs(angle - 90) < threshold_angle:
            return "Thumbs Down"
        else:
            return "Fist"
    else:
        return None

def detect_dynamic_gesture(bbox, current_time):
    """
    Detects dynamic (swipe) gestures based on the movement of the hand's center.
    Compares the current center with the previous center.
    """
    global previous_hand_center, dynamic_gesture_last_time

    x_min, y_min, x_max, y_max = bbox
    current_center = ((x_min + x_max) // 2, (y_min + y_max) // 2)

    dynamic_gesture = None
    if previous_hand_center is not None and (current_time - dynamic_gesture_last_time > dynamic_gesture_cooldown):
        dx = current_center[0] - previous_hand_center[0]
        dy = current_center[1] - previous_hand_center[1]
        threshold = 50  # pixel movement threshold

        if abs(dx) > abs(dy):
            if dx > threshold:
                dynamic_gesture = "Swipe Right"
            elif dx < -threshold:
                dynamic_gesture = "Swipe Left"
        else:
            if dy > threshold:
                dynamic_gesture = "Swipe Down"
            elif dy < -threshold:
                dynamic_gesture = "Swipe Up"
        if dynamic_gesture:
            dynamic_gesture_last_time = current_time

    previous_hand_center = current_center
    return dynamic_gesture

# -----------------------
# Frame Processing Function
# -----------------------
def process_frame(frame):
    global last_volume_gesture_time, previous_static_gesture, previous_cursor_center
    current_time = time.time()
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)
    bbox_for_dynamic = None
    h, w, _ = frame.shape

    if results.multi_hand_landmarks:
        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # Draw landmarks and connections
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # Compute bounding box for the hand
            x_coords = [lm.x for lm in hand_landmarks.landmark]
            y_coords = [lm.y for lm in hand_landmarks.landmark]
            x_min = int(min(x_coords) * w)
            x_max = int(max(x_coords) * w)
            y_min = int(min(y_coords) * h)
            y_max = int(max(y_coords) * h)
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
            
            # Use the first detected hand for dynamic gestures.
            if idx == 0:
                bbox_for_dynamic = (x_min, y_min, x_max, y_max)
            
            # Detect static gesture for this hand.
            gesture = detect_static_gesture(hand_landmarks, frame)
            if gesture:
                # Only trigger volume control when the gesture first appears.
                if gesture in ["Thumbs Up", "Open Palm"]:
                    if previous_static_gesture != gesture and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
                        if gesture == "Thumbs Up":
                            volume_up()
                            print("Volume increased")
                        elif gesture == "Open Palm":
                            volume_down()
                            print("Volume decreased")
                        last_volume_gesture_time = current_time
                    previous_static_gesture = gesture
                else:
                    previous_static_gesture = gesture

                # Overlay the static gesture name on the frame.
                font = cv2.FONT_HERSHEY_SIMPLEX
                text_y = y_min - 10 if y_min - 10 > 20 else y_min + 30
                cv2.putText(frame, gesture, (x_min, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
            else:
                previous_static_gesture = None

            # Cursor control: if this is the first detected hand and it shows a "Fist" gesture,
            # use the center of the fist (the bounding box center) to slowly move the cursor.
            if idx == 0:
                if gesture == "Fist":
                    fist_center = ((x_min + x_max) // 2, (y_min + y_max) // 2)
                    if previous_cursor_center is not None:
                        dx = fist_center[0] - previous_cursor_center[0]
                        dy = fist_center[1] - previous_cursor_center[1]
                        # Scale the movement so the cursor moves slowly (like a TV remote)
                        scale_factor = 0.5
                        move_cursor(dx * scale_factor, dy * scale_factor)
                    previous_cursor_center = fist_center
                else:
                    previous_cursor_center = None

    # Dynamic gesture detection (swipe gestures)
    if bbox_for_dynamic is not None:
        dynamic_gesture = detect_dynamic_gesture(bbox_for_dynamic, current_time)
        if dynamic_gesture:
            x_min, y_min, _, _ = bbox_for_dynamic
            cv2.putText(frame, dynamic_gesture, (x_min, y_min - 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 0), 3, cv2.LINE_AA)
            print(dynamic_gesture)
            # Trigger window control based on dynamic gestures.
            if dynamic_gesture == "Swipe Down":
                minimize_current_window()
            elif dynamic_gesture == "Swipe Up":
                maximize_current_window()
    
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

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
