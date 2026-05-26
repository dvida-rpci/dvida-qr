@echo off
REM ═══════════════════════════════════════════════════════════════════
REM   Lanzador del aplicativo QR Groupe SEB (desde WSL)
REM   Asume distribución Ubuntu en WSL con Python 3.10+ y
REM   `pip3 install --break-system-packages openpyxl nicegui` hecho.
REM ═══════════════════════════════════════════════════════════════════

REM ─── AJUSTAR ESTOS VALORES si difieren ───
set WSL_DISTRO=Ubuntu
set WSL_USER=administrador
set PROJECT_DIR_WSL=/home/%WSL_USER%/google-sites-migrator

REM Lanzar la GUI dentro de WSL en background (nohup + & + redirección)
wsl -d %WSL_DISTRO% bash -c "cd %PROJECT_DIR_WSL% && nohup python3 gui.py > /tmp/gui.log 2>&1 &"

if errorlevel 1 (
    echo.
    echo  X  Fallo al lanzar dentro de WSL.
    echo     Verificar: distro=%WSL_DISTRO%, ruta=%PROJECT_DIR_WSL%
    echo.
    pause
    exit /b 1
)

REM Esperar a que el servidor levante
timeout /t 3 /nobreak >nul

REM Abrir browser de Windows en la GUI (localhost se mapea desde WSL2)
start http://localhost:8080

exit
