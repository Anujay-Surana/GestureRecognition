import { useEffect, useRef } from 'react'
import './App.css'

function App() {
  const videoRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.src = 'http://localhost:8001/video_feed'
    }
  }, [])

  return (
    <div className="App">
      <h1>Hand Detection App</h1>
      <div className="video-container">
        <img ref={videoRef} alt="Video feed" style={{ maxWidth: '100%', height: 'auto' }} />
      </div>
    </div>
  )
}

export default App
