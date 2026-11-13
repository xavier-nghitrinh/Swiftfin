@echo off
echo ==============================================
echo           Starting MyTube Server
echo ==============================================
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting FastAPI / Uvicorn on 0.0.0.0:8000 ...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
