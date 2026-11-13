@echo off
chcp 65001 >nul
title Свидетель — запуск
cd /d "%~dp0"

echo ==========================================
echo   Свидетель: запуск демо
echo ==========================================
echo.

REM --- остановить старые копии ---
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo [1/3] Проверяю зависимости...
py -3 -c "import fastapi, PIL, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo     Устанавливаю...
  py -3 -m pip install -q -r backend\requirements.txt
)

echo [2/3] Запускаю сервер на http://localhost:8000 ...
start "Свидетель API :8000" /min cmd /k "cd /d %~dp0 && py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo [3/3] Запускаю интерфейс на http://localhost:5173 ...
if not exist "frontend\node_modules" (
  echo     Первый запуск: ставлю npm-пакеты, это займёт минуту...
  pushd frontend && call npm install --silent && popd
)
start "Свидетель UI :5173" /min cmd /k "cd /d %~dp0frontend && set VITE_API_MODE=live&& npm run dev"

echo.
echo Жду, пока поднимется сервер...
:wait
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1
if errorlevel 1 goto wait

echo.
echo Готово. Открываю интерфейс...
start "" http://localhost:5173

echo.
echo ------------------------------------------
echo  Стенд без сервера (работает всегда):
echo    demo\witness-demo.html — откройте двойным щелчком
echo.
echo  Остановить: закройте окна "Свидетель API" и "Свидетель UI"
echo ------------------------------------------
echo.
pause
