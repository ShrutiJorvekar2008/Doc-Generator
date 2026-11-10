@echo off
call .venv\Scripts\activate
start "backend" cmd /k uvicorn app.main:app --app-dir backend --reload
cd frontend && npm run dev
