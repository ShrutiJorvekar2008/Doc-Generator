@echo off
REM One-time setup (Windows)
python -m venv .venv || goto :err
call .venv\Scripts\activate
pip install -r requirements.txt || goto :err
if not exist .env (
  copy .env.example .env >nul
  powershell -Command "(Get-Content .env) -replace '^LLM_PROVIDER=.*','LLM_PROVIDER=mock' -replace '^WEB_SEARCH=.*','WEB_SEARCH=false' | Set-Content .env"
  echo Created .env in MOCK mode - no keys needed.
)
cd frontend && npm install && cd ..
echo Setup done. Run run.bat
goto :eof
:err
echo Setup failed.
