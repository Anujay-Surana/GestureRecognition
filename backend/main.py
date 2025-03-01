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

# Global variables for volume gesture cooldown
last_volume_gesture_time = 0
volume_gesture_cooldown = 1  # seconds

# Detect platform (Windows, Darwin for macOS, etc.)
current_platform = platform.system()

# Define volume control functions for Windows
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

# Define volume control functions for macOS
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

# Unified volume control functions based on platform
if current_platform == "Windows":
    def volume_up():
        volume_up_windows()
    def volume_down():
        volume_down_windows()
elif current_platform == "Darwin":
    def volume_up():
        volume_up_mac()
    def volume_down():
        volume_down_mac()
else:
    def volume_up():
        print("Volume up not supported on this platform")
    def volume_down():
        print("Volume down not supported on this platform")

def detect_gesture(hand_landmarks, frame):
    """
    Improved gesture detection using both finger state and thumb angle.
    Recognizes:
      - "Open Palm": All four non-thumb fingers extended.
      - "Fist": All four non-thumb fingers folded.
      - "Thumbs Up": All non-thumb fingers folded and thumb pointing upward.
      - "Thumbs Down": All non-thumb fingers folded and thumb pointing downward.
    """
    landmarks = hand_landmarks.landmark
    h, w, _ = frame.shape

    # Helper to decide if a finger (non-thumb) is extended.
    def finger_extended(tip_idx, pip_idx):
        return landmarks[tip_idx].y < landmarks[pip_idx].y

    index_extended = finger_extended(8, 6)
    middle_extended = finger_extended(12, 10)
    ring_extended = finger_extended(16, 14)
    pinky_extended = finger_extended(20, 18)
    extended_count = sum([index_extended, middle_extended, ring_extended, pinky_extended])
    
    # Calculate thumb angle using MCP (2) to tip (4)
    thumb_mcp = landmarks[2]
    thumb_tip = landmarks[4]
    dx = thumb_tip.x - thumb_mcp.x
    dy = thumb_tip.y - thumb_mcp.y
    angle = math.degrees(math.atan2(dy, dx))
    # For a thumbs up, we expect thumb pointing upward (angle near -90 degrees)
    # For thumbs down, expect angle near 90 degrees.
    threshold_angle = 20  # degrees tolerance

    if extended_count == 4:
        return "Open Palm"
    elif extended_count == 0:
        # All non-thumb fingers are folded.
        if thumb_tip.y < thumb_mcp.y and abs(angle + 90) < threshold_angle:
            return "Thumbs Up"
        elif thumb_tip.y > thumb_mcp.y and abs(angle - 90) < threshold_angle:
            return "Thumbs Down"
        else:
            return "Fist"
    else:
        return None

def process_frame(frame):
    global last_volume_gesture_time
    # Flip frame horizontally (mirror effect)
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Process frame with MediaPipe Hands
    results = hands.process(rgb_frame)
    
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            h, w, _ = frame.shape
            # Draw hand landmarks and connections
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # Compute bounding box around the hand
            x_coords = [landmark.x for landmark in hand_landmarks.landmark]
            y_coords = [landmark.y for landmark in hand_landmarks.landmark]
            x_min = int(min(x_coords) * w)
            x_max = int(max(x_coords) * w)
            y_min = int(min(y_coords) * h)
            y_max = int(max(y_coords) * h)
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
            
            # Detect gesture from the hand landmarks
            gesture = detect_gesture(hand_landmarks, frame)
            if gesture:
                print(gesture)  # Print the gesture to the terminal
                
                # Overlay the gesture name on the frame in large white font
                font = cv2.FONT_HERSHEY_SIMPLEX
                text_y = y_min - 10 if y_min - 10 > 20 else y_min + 30
                cv2.putText(frame, gesture, (x_min, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
                
                # If gesture is Thumbs Up/Down, trigger volume change with cooldown
                current_time = time.time()
                if current_time - last_volume_gesture_time > volume_gesture_cooldown:
                    if gesture == "Thumbs Up":
                        volume_up()
                        print("Volume increased")
                        last_volume_gesture_time = current_time
                    elif gesture == "Open Palm":
                        volume_down()
                        print("Volume decreased")
                        last_volume_gesture_time = current_time
    
    return frame

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
