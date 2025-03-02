import pyautogui
import platform
import time

# Set fail-safe to False to prevent mouse corner triggering safety feature
pyautogui.FAILSAFE = False

# On Windows, use faster key presses with no delay
if platform.system() == "Windows":
    # Optional: adjust for Windows environment
    pyautogui.PAUSE = 0.01  # Smaller pause between PyAutoGUI commands

def speech_to_keyboard(text):
    """
    Convert speech text to keyboard input for Windows
    This types the text as if it were typed on the keyboard
    
    Args:
        text (str): The recognized speech text to type
    """
    if not text or len(text) == 0:
        print("Warning: Empty text received, nothing to type")
        return
    
    print(f"Processing text for typing: '{text}'")
    
    # Special command handling
    lower_text = text.lower().strip()
    
    # Handle Windows-specific key commands
    if lower_text == "press enter":
        print("Executing command: press enter")
        pyautogui.press('enter')
        return
    elif lower_text == "press tab":
        print("Executing command: press tab")
        pyautogui.press('tab')
        return
    elif lower_text == "press space":
        print("Executing command: press space")
        pyautogui.press('space')
        return
    elif lower_text == "press backspace" or lower_text == "delete":
        print("Executing command: backspace")
        pyautogui.press('backspace')
        return
    elif lower_text == "press escape":
        print("Executing command: escape")
        pyautogui.press('escape')
        return
    elif lower_text == "select all":
        print("Executing command: select all")
        pyautogui.hotkey('ctrl', 'a')  # Windows uses ctrl+a
        return
    elif lower_text == "copy":
        print("Executing command: copy")
        pyautogui.hotkey('ctrl', 'c')  # Windows uses ctrl+c
        return
    elif lower_text == "paste":
        print("Executing command: paste")
        pyautogui.hotkey('ctrl', 'v')  # Windows uses ctrl+v
        return
    elif lower_text == "cut":
        print("Executing command: cut")
        pyautogui.hotkey('ctrl', 'x')  # Windows uses ctrl+x
        return
    elif lower_text == "undo":
        print("Executing command: undo")
        pyautogui.hotkey('ctrl', 'z')  # Windows uses ctrl+z
        return
    elif lower_text == "save":
        print("Executing command: save")
        pyautogui.hotkey('ctrl', 's')  # Windows save shortcut
        return
    elif lower_text == "new tab":
        print("Executing command: new tab")
        pyautogui.hotkey('ctrl', 't')  # Common in browsers
        return
    elif lower_text == "close tab":
        print("Executing command: close tab")
        pyautogui.hotkey('ctrl', 'w')  # Common in browsers
        return
    elif lower_text == "new line":
        print("Executing command: new line")
        pyautogui.press('enter')
        return
    elif lower_text == "alt tab":
        print("Executing command: alt tab")
        pyautogui.hotkey('alt', 'tab')  # Windows app switching
        return
    elif lower_text == "windows key":
        print("Executing command: windows key")
        pyautogui.press('win')  # Open Start menu
        return
    elif lower_text == "delete":
        pyautogui.press('backspace')
        return
    
    # Typing normal text
    try:
        print(f"Typing text: '{text}'")
        if platform.system() == "Windows":
            # Windows often handles typewrite better with a small interval
            pyautogui.write(text, interval=0.01)
        else:
            # Fallback for other systems
            pyautogui.write(text)
        print("Text typed successfully")
    except Exception as e:
        print(f"Error typing text: {e}")
        # Alternative approach if the first method fails
        try:
            print("Trying alternative typing method...")
            for char in text:
                pyautogui.press(char)
                time.sleep(0.01)
            print("Alternative typing completed")
        except Exception as e2:
            print(f"Alternative typing method also failed: {e2}")