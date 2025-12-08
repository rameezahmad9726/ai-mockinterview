---
description: How to run the AI Mock Interview project (Backend + Frontend)
---

Follow these steps to start the application.

## Prerequisites
- Python 3.10+
- Node.js & npm
- FFmpeg (required for audio processing)
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

## 1. Backend Setup

Open a terminal in the root directory:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the Backend Server
python backend/main.py
```
*The backend will run on http://localhost:8000*

## 2. Frontend Setup

Open a **new** terminal window:

```bash
cd frontend

# Install Node dependencies
npm install

# Start the React App
npm start
```
*The frontend will open automatically at http://localhost:3000*

## 3. Verify
- Go to `http://localhost:3000`
- You should see "Backend: ● Active" in the top right corner.
