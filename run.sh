#!/usr/bin/env bash
# Starts backend (:8000) and frontend (:5173). Ctrl+C stops both.
. .venv/bin/activate
uvicorn app.main:app --app-dir backend --reload &
API=$!
trap "kill $API" EXIT
(cd frontend && npm run dev)
