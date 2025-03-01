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

# Global variables for gesture control
last_volume_gesture_time = 0
volume_gesture_cooldown = 1  # seconds
previous_static_gesture = None  # To avoid repeated volume commands

previous_hand_center = None
dynamic_gesture_last_time = 0
dynamic_gesture_cooldown = 1  # seconds

previous_cursor_center = None  # Used for cursor control with fist

# Added for Rock On gesture for music control
last_music_gesture_time = 0
music_gesture_cooldown = 3.0  # Increased to 3 seconds
rock_on_start_time = 0  # When the Rock On gesture was first detected
rock_on_hold_threshold = 1.5  # Hold the gesture for 1.5 seconds to activate
rock_on_state = "none"  # Track the state of rock on detection: "none", "holding", "triggered"

# Detect platform
current_platform = platform.system()

# -----------------------
# Media Control Functions
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
        
    def play_pause_music_windows():
        HWND_BROADCAST = 0xFFFF
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_MEDIA_PLAY_PAUSE = 0x0E
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_MEDIA_PLAY_PAUSE << 16)

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
        
    def play_pause_music():
        play_pause_music_windows()

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
        
    def play_pause_music_mac():
        # Using AppleScript to send play/pause to the current music app
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke space'", shell=True)

    def minimize_current_window():
        subprocess.run("osascript -e 'tell application \"System Events\" to keystroke \"m\" using {command down}'", shell=True)

    def maximize_current_window():
        print("Maximize window not implemented on macOS in this example.")

    def volume_up():
        volume_up_mac()

    def volume_down():
        volume_down_mac()
        
    def play_pause_music():
        play_pause_music_mac()

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
    def play_pause_music():
        print("Play/pause music not supported on this platform")
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
      - "Rock On": Index and pinky fingers extended, other fingers folded.
    """
    landmarks = hand_landmarks.landmark
    h, w, _ = frame.shape

    def finger_extended(tip_idx, pip_idx):
        return landmarks[tip_idx].y < landmarks[pip_idx].y

    # Check extension of each finger
    index_extended = finger_extended(8, 6)
    middle_extended = finger_extended(12, 10)
    ring_extended = finger_extended(16, 14)
    pinky_extended = finger_extended(20, 18)
    
    # Calculate thumb position for thumb gestures
    thumb_mcp = landmarks[2]
    thumb_tip = landmarks[4]
    dx = thumb_tip.x - thumb_mcp.x
    dy = thumb_tip.y - thumb_mcp.y
    angle = math.degrees(math.atan2(dy, dx))
    threshold_angle = 20  # degrees tolerance
    
    # Rock On gesture: index and pinky extended, others folded
    if index_extended and not middle_extended and not ring_extended and pinky_extended:
        return "Rock On"
    
    # Open Palm: all four fingers extended
    elif index_extended and middle_extended and ring_extended and pinky_extended:
        return "Open Palm"
    
    # Fist, Thumbs Up, Thumbs Down: no fingers extended, thumb position matters
    elif not index_extended and not middle_extended and not ring_extended and not pinky_extended:
        if thumb_tip.y < thumb_mcp.y and abs(angle + 90) < threshold_angle:
            return "Thumbs Up"
        elif thumb_tip.y > thumb_mcp.y and abs(angle - 90) < threshold_angle:
            return "Thumbs Down"
        else:
            return "Fist"
    
    # None of the above patterns matched
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
    global last_music_gesture_time, rock_on_start_time, rock_on_state
    current_time = time.time()
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)
    bbox_for_dynamic = None
    h, w, _ = frame.shape

    # Add instruction text at the top of the frame
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, "Thumbs Up: Volume Up | Open Palm: Volume Down | Rock On: Play/Pause", 
                (10, 30), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

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
                # Overlay the static gesture name on the frame.
                text_y = y_min - 10 if y_min - 10 > 20 else y_min + 30
                cv2.putText(frame, gesture, (x_min, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
                
                # Handle volume control gestures
                if gesture in ["Thumbs Up", "Open Palm"]:
                    if previous_static_gesture != gesture and (current_time - last_volume_gesture_time > volume_gesture_cooldown):
                        if gesture == "Thumbs Up":
                            volume_up()
                            print("Volume increased")
                        elif gesture == "Open Palm":
                            volume_down()
                            print("Volume decreased")
                        last_volume_gesture_time = current_time
                
                # Handle Rock On gesture for music play/pause with hold detection
                elif gesture == "Rock On":
                    # Check cooldown first - don't even start the hold timer if we're in cooldown
                    if current_time - last_music_gesture_time <= music_gesture_cooldown:
                        # We're in cooldown period, show remaining time
                        remaining = round(music_gesture_cooldown - (current_time - last_music_gesture_time), 1)
                        cv2.putText(frame, f"Cooldown: {remaining}s", (x_min, text_y + 40),
                                    font, 0.9, (0, 165, 255), 2, cv2.LINE_AA)
                    else:
                        # Past cooldown period, now handle the gesture states
                        if rock_on_state == "none":
                            # First detection of Rock On after cooldown
                            rock_on_state = "holding"
                            rock_on_start_time = current_time
                            cv2.putText(frame, "Hold for play/pause...", (x_min, text_y + 40),
                                        font, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
                        
                        elif rock_on_state == "holding":
                            # Continuing to hold the Rock On gesture
                            hold_time = current_time - rock_on_start_time
                            
                            if hold_time < rock_on_hold_threshold:
                                # Still holding, but not long enough yet
                                progress = int((hold_time / rock_on_hold_threshold) * 100)
                                cv2.putText(frame, f"Hold: {progress}%", (x_min, text_y + 40),
                                            font, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
                                
                                # Draw progress bar
                                bar_width = 100
                                bar_height = 10
                                bar_x = x_min
                                bar_y = text_y + 60
                                # Background bar (gray)
                                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), 
                                            (100, 100, 100), -1)
                                # Progress bar (yellow)
                                progress_width = int((hold_time / rock_on_hold_threshold) * bar_width)
                                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height), 
                                            (0, 255, 255), -1)
                            else:
                                # Held long enough - trigger the media control
                                play_pause_music()
                                print("Music play/pause toggled")
                                last_music_gesture_time = current_time
                                rock_on_state = "triggered"
                                
                                # Add visual feedback for music toggle
                                cv2.putText(frame, "Music Toggled!", (x_min, text_y + 40),
                                            font, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
                        
                        elif rock_on_state == "triggered":
                            # Already triggered, still showing the Rock On gesture
                            cv2.putText(frame, "Command triggered", (x_min, text_y + 40),
                                        font, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
                
                previous_static_gesture = gesture
            else:
                previous_static_gesture = None
                # If no longer making Rock On gesture, reset the state
                if gesture != "Rock On" and rock_on_state != "none":
                    rock_on_state = "none"

            # Cursor control: if this is the first detected hand and it shows a "Fist" gesture,
            # use the center of the fist (the bounding box center) to slowly move the cursor.
            if idx == 0 and gesture == "Fist":
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

@app.get("/")
async def root():
    return {
        "message": "Gesture Control API",
        "instructions": "Access video feed at /video_feed",
        "gestures": {
            "Thumbs Up": "Increase volume",
            "Open Palm": "Decrease volume",
            "Rock On": "Play/pause music",
            "Fist": "Move cursor",
            "Swipe Up": "Maximize window",
            "Swipe Down": "Minimize window"
        }
    }

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)