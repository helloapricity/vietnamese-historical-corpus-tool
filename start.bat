@echo off
echo Starting AI Annotation System...

:: Start Backend in a new window
echo Starting FastAPI Backend (Port 8000)...
start cmd /k "cd backend && python -m venv .venv && call .venv\Scripts\activate && pip install -r requirements.txt && uvicorn main:app --reload"

:: Start Frontend in a new window
echo Starting Next.js Frontend (Port 3000)...
start cmd /k "cd frontend && npm run dev"

echo All services are starting up! Please wait a few seconds then open http://localhost:3000
