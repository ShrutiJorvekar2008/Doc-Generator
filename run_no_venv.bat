@echo off
echo Open http://localhost:8000 in your browser. Press Ctrl+C to stop.
python -m uvicorn app.main:app --app-dir backend --port 8000
