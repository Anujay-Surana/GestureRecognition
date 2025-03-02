import { useEffect, useRef, useState } from 'react';
import './App.css';

function App() {
  const videoRef = useRef(null);
  const [gestureText, setGestureText] = useState("Vol Up/Down: Thumbs | Music: Rock On | Click: Open Palm | Cursor: Pointing");

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.src = 'http://localhost:8001/video_feed';
    }
  }, []);

  return (
    <div className="App">
      <h1>Hand Detection App</h1>

      <div className="video-container">
        <img ref={videoRef} alt="Video feed" />

        {/* Floating Captions Explaining Gestures */}
        <div className="captions">
          {gestureText}
        </div>
      </div>

      <p className="speech-command">Say 'Hey Adam' to activate speech recognition</p>
    </div>
  );
}

export default App;
