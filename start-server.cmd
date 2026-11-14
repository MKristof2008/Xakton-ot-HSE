@echo off
cd /d "C:\Users\beliy\Xakton-ot-HSE\backend"
"..\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
