@echo off
setlocal
cd /d "G:\inventario-qr"

echo.
echo ============================================
echo   INVENTARIO-QR (Flask)
echo ============================================
echo.

set "PORT=5000"
set "FLASK_DEBUG=0"

echo Iniciando em http://127.0.0.1:5000 ...
py app.py
pause
