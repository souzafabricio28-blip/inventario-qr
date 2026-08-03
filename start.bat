@echo off
setlocal

set "PYTHON_DIR=C:\Users\souza\AppData\Local\Temp\opencode\pyfull2\tools"
set "APP_DIR=C:\Users\souza\Documents\Projetos\inventario-qr"
set "PY_EXE=%PYTHON_DIR%\python.exe"

echo.
echo ============================================
echo   INICIAR INVENTARIO-QR (Flask + Neon)
echo ============================================
echo.

cd /d "%APP_DIR%"

rem Variaveis de ambiente
set "DATABASE_URL=postgresql://neondb_owner:npg_tTqPl54bgCdH@ep-late-rain-ay5psyew-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require"
set "PORT=5000"
set "FLASK_DEBUG=0"

echo Iniciando Flask...
"%PY_EXE%" app.py
pause