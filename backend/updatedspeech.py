from speechtokey import speech_to_keyboard
import speech_recognition as sr
import threading
import time
import queue
import numpy as np
import os
import pyaudio
import wave

speech_queue = queue.Queue()
is_listening = False
listening_active = False
speech_recognition_thread = None
wake_word = "hey adam"
listening_timeout = 1.5  # seconds

from audio import WakeWordDetector

def update_speech_recognition():
    """
    Update the WakeWordDetector class and listen_for_speech method to 
    incorporate keyboard input functionality
    """
    # Replace the listen_for_speech method in the WakeWordDetector class
    
    def listen_for_speech(self):
        """Listen for speech after wake word is detected and convert to keyboard input"""
        global is_listening, listening_active, speech_queue
        
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            last_speech_time = time.time()
            
            while listening_active:
                try:
                    print("Listening for speech input...")
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=10)
                    
                    try:
                        text = self.recognizer.recognize_google(audio)  # Keep original case for typing
                        print(f"Converting to keyboard input: {text}")
                        
                        # Add to speech queue for display
                        speech_queue.put(text)
                        last_speech_time = time.time()
                        
                        # Convert to keyboard input
                        speech_to_keyboard(text)
                        
                    except sr.UnknownValueError:
                        # Check for timeout - stop listening if silence for too long
                        if time.time() - last_speech_time > listening_timeout:
                            print("Silence timeout, stopping listening.")
                            self.play_feedback_sound(False)  # Play stop sound
                            is_listening = False
                            listening_active = False
                            break
                    except sr.RequestError as e:
                        print(f"Could not request results; {e}")
                        
                except (sr.WaitTimeoutError, Exception) as e:
                    # Check for timeout - stop listening if silence for too long
                    if time.time() - last_speech_time > listening_timeout:
                        print("Silence timeout, stopping listening.")
                        self.play_feedback_sound(False)  # Play stop sound
                        is_listening = False
                        listening_active = False
                        break
    
    # Make this method available for use in your application
    WakeWordDetector.listen_for_speech = listen_for_speech

# Call this function before starting the speech recognition
# to update the WakeWordDetector class with the new functionality