@echo off
rem PINWISE public demo: build the Vue site, start the backend (port 8080), then open the ngrok tunnel.
rem Double-click to run. Close the two windows it opens to stop the site.
cd /d "%~dp0"
set PYTHONUTF8=1
set PUBLIC_URL=https://suing-previous-harsh.ngrok-free.dev

echo [1/3] Building website (frontend-vue\dist) ...
pushd frontend-vue
call npm.cmd run build
if errorlevel 1 (
  echo Build failed. Check the messages above.
  popd
  pause
  exit /b 1
)
popd

echo [2/3] Starting backend on http://127.0.0.1:8080 ...
start "PINWISE backend" cmd /k ".venv\Scripts\python -m backend.run"
timeout /t 10 /nobreak >nul

echo [3/3] Opening ngrok tunnel ...
start "PINWISE ngrok" cmd /k "ngrok http 8080 --url=%PUBLIC_URL%"

echo.
echo Done. Public site: %PUBLIC_URL%
echo Keep the "PINWISE backend" and "PINWISE ngrok" windows open.
timeout /t 15
