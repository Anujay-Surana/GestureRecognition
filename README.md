# Hand Detection Web App

This is a real-time hand detection web application that uses your webcam to detect and draw boxes around hands. It's built with Python (FastAPI + OpenCV + MediaPipe) for the backend and React for the frontend.

## Prerequisites

- Python 3.8+
- Node.js 16+
- npm or yarn
- Webcam

## Setup

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Activate the virtual environment:
```bash
source venv/bin/activate  # On Unix/macOS
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

4. Run the backend server:
```bash
python main.py
```

The backend server will start at http://localhost:8000

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will be available at http://localhost:5173

## Usage

1. Make sure both backend and frontend servers are running
2. Open your browser and navigate to http://localhost:5173
3. Allow camera access when prompted
4. Move your hands in front of the camera to see the detection boxes

## Features

- Real-time hand detection
- Visual bounding boxes around detected hands
- Support for multiple hand detection
- Responsive web interface

## Technologies Used

- Backend:
  - FastAPI
  - OpenCV
  - MediaPipe
  - Python

- Frontend:
  - React
  - TypeScript
  - Vite 