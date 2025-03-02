import speech_recognition as sr
import threading
import time
import queue
import numpy as np
import os
import pyaudio
import wave

from speechtokey import speech_to_keyboard

# Speech detection and wake word globals
speech_queue = queue.Queue()
is_listening = False
listening_active = False
speech_recognition_thread = None
wake_word = "hey adam"
listening_timeout = 3  # seconds

class WakeWordDetector:
    def __init__(self, wake_word="hey adam", sensitivity=0.5):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000  # Adjust this based on your environment
        self.recognizer.dynamic_energy_threshold = True
        self.wake_word = wake_word.lower()
        self.sensitivity = sensitivity
        
        # Sound for feedback
        if os.path.exists("listening_start.wav"):
            self.start_sound = True
        else:
            self.start_sound = False
            
        if os.path.exists("listening_stop.wav"):
            self.stop_sound = True
        else:
            self.stop_sound = False
    
    def play_feedback_sound(self, is_start_sound):
        """Play audio feedback using simple wave playback"""
        if (is_start_sound and self.start_sound) or (not is_start_sound and self.stop_sound):
            try:
                filename = "listening_start.wav" if is_start_sound else "listening_stop.wav"
                wf = wave.open(filename, 'rb')
                p = pyaudio.PyAudio()
                
                stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                                channels=wf.getnchannels(),
                                rate=wf.getframerate(),
                                output=True)
                
                data = wf.readframes(1024)
                while len(data) > 0:
                    stream.write(data)
                    data = wf.readframes(1024)
                
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception as e:
                print(f"Error playing feedback sound: {e}")
    
    def listen_for_wake_word(self):
        """Continuously listen for the wake word"""
        global is_listening, listening_active
        
        print("Listening for wake word...")
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            
            while True:
                if is_listening:
                    time.sleep(0.1)
                    continue
                    
                try:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                    try:
                        text = self.recognizer.recognize_google(audio).lower()
                        print(f"Heard: {text}")
                        
                        if self.wake_word in text:
                            print("Wake word detected! Starting to listen...")
                            self.play_feedback_sound(True)  # Play start sound
                            is_listening = True
                            listening_active = True
                            # Start the speech recognition in a separate thread
                            speech_thread = threading.Thread(target=self.listen_for_speech)
                            speech_thread.daemon = True
                            speech_thread.start()
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print(f"Could not request results; {e}")
                except (sr.WaitTimeoutError, Exception) as e:
                    pass
                    
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
    
    def stop_listening(self):
        """Force stop listening"""
        global is_listening, listening_active
        is_listening = False
        listening_active = False
        self.play_feedback_sound(False)  # Play stop sound


def create_speech_feedback_sounds():
    """Create audio feedback sounds for listening start/stop"""
    
    # Check if sound files already exist
    if os.path.exists("listening_start.wav") and os.path.exists("listening_stop.wav"):
        return
    
    # Create listening start sound - rising tone
    p = pyaudio.PyAudio()
    
    # Start sound (rising tone)
    duration = 0.3  # seconds
    volume = 0.5     # range [0.0, 1.0]
    fs = 44100       # sampling rate, Hz
    
    samples = []
    for i in range(int(fs * duration)):
        # Rising frequency from 440 to 880 Hz
        f = 440 + (880 - 440) * i / (fs * duration)
        sample = volume * np.sin(2 * np.pi * f * i / fs)
        samples.append(sample)
    
    samples = np.array(samples)
    samples = (samples * 32767).astype(np.int16)
    
    with wave.open("listening_start.wav", 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(fs)
        wf.writeframes(samples.tobytes())
    
    # Stop sound (falling tone)
    samples = []
    for i in range(int(fs * duration)):
        # Falling frequency from 880 to 440 Hz
        f = 880 - (880 - 440) * i / (fs * duration)
        sample = volume * np.sin(2 * np.pi * f * i / fs)
        samples.append(sample)
    
    samples = np.array(samples)
    samples = (samples * 32767).astype(np.int16)
    
    with wave.open("listening_stop.wav", 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(fs)
        wf.writeframes(samples.tobytes())
    
    p.terminate()


def start_speech_recognition():
    """Initialize and start speech recognition in a separate thread"""
    global speech_recognition_thread
    
    # Create sound files for feedback
    try:
        create_speech_feedback_sounds()
    except Exception as e:
        print(f"Could not create feedback sounds: {e}")
    
    # Initialize wake word detector
    detector = WakeWordDetector(wake_word=wake_word)
    
    # Start wake word detection in a background thread
    speech_recognition_thread = threading.Thread(target=detector.listen_for_wake_word)
    speech_recognition_thread.daemon = True
    speech_recognition_thread.start()
    
    print("Speech recognition initialized with wake word:", wake_word)


def get_recognized_speech():
    """Get any text recognized since last call, non-blocking"""
    global speech_queue
    
    collected_text = []
    while not speech_queue.empty():
        try:
            text = speech_queue.get_nowait()
            collected_text.append(text)
        except queue.Empty:
            break
    
    return " ".join(collected_text) if collected_text else None