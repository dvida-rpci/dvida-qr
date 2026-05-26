@echo off
REM ═══════════════════════════════════════════════════════════════════
REM   Detener el aplicativo QR Groupe SEB (apaga la GUI y el preview)
REM ═══════════════════════════════════════════════════════════════════

echo Buscando procesos en :8080 y :8000...

REM Matar lo que escucha en puerto 8080 (GUI)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do (
    echo  · Matando PID %%a (puerto 8080 - GUI)
    taskkill /F /PID %%a >nul 2>&1
)

REM Matar lo que escucha en puerto 8000 (preview)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo  · Matando PID %%a (puerto 8000 - preview)
    taskkill /F /PID %%a >nul 2>&1
)

REM Tambien matar por titulo de ventana (cubre caso Windows nativo)
taskkill /F /FI "WINDOWTITLE eq QR-GUI*" >nul 2>&1

REM Si estabas usando WSL, matar python3 dentro tambien
wsl -d Ubuntu bash -c "pkill -f 'python3 gui.py' 2>/dev/null; pkill -f 'http.server' 2>/dev/null" 2>nul

echo.
echo  OK  GUI y preview detenidos.
timeout /t 2 /nobreak >nul
exit
