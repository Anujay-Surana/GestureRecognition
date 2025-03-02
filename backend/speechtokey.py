import pyautogui

def speech_to_keyboard(text):
    """
    Convert speech text to keyboard input
    This types the text as if it were typed on the keyboard
    
    Args:
        text (str): The recognized speech text to type
    """
    if not text or len(text) == 0:
        return
    
    # Special command handling
    lower_text = text.lower().strip()
    
    # Handle special commands - you can add more commands here
    if lower_text == "press enter":
        pyautogui.press('enter')
        return
    elif lower_text == "press tab":
        pyautogui.press('tab')
        return
    elif lower_text == "press space":
        pyautogui.press('space')
        return
    elif lower_text == "press backspace" or lower_text == "delete":
        pyautogui.press('backspace')
        return
    elif lower_text == "press escape":
        pyautogui.press('escape')
        return
    elif lower_text == "select all":
        pyautogui.hotkey('ctrl', 'a')  # Use command+a on Mac
        return
    elif lower_text == "copy":
        pyautogui.hotkey('ctrl', 'c')  # Use command+c on Mac
        return
    elif lower_text == "paste":
        pyautogui.hotkey('ctrl', 'v')  # Use command+v on Mac
        return
    elif lower_text == "cut":
        pyautogui.hotkey('ctrl', 'x')  # Use command+x on Mac
        return
    elif lower_text == "undo":
        pyautogui.hotkey('ctrl', 'z')  # Use command+z on Mac
        return
    elif lower_text == "new line":
        pyautogui.press('enter')
        return
    
    # If not a special command, type the text
    try:
        # Use typewrite with interval for more reliable typing
        pyautogui.typewrite(text, interval=0.01)  # Small delay between keystrokes
    except Exception as e:
        print(f"Error typing text: {e}")