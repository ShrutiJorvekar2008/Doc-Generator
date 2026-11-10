@echo off
REM Setup WITHOUT a virtual environment and WITHOUT Node (for locked-down PCs where pip.exe/venv are blocked).
echo Installing Python packages for your user account...
python -m pip install --user --upgrade pip
python -m pip install --user -r requirements.txt
if errorlevel 1 goto :err
if not exist .env (
  copy .env.example .env >nul
  powershell -Command "(Get-Content .env) -replace '^LLM_PROVIDER=.*','LLM_PROVIDER=mock' -replace '^WEB_SEARCH=.*','WEB_SEARCH=false' | Set-Content .env"
  echo Created .env in MOCK mode - no keys needed.
)
echo Setup done. Now run run_no_venv.bat
goto :eof
:err
echo Setup failed - copy the error above and send it.
