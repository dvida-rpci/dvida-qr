@echo off
REM ═══════════════════════════════════════════════════════════════════
REM   Lanzador del aplicativo QR Groupe SEB (Windows nativo)
REM   Asume que tenés Python 3.10+ y `pip install openpyxl nicegui` hecho.
REM ═══════════════════════════════════════════════════════════════════

REM ─── AJUSTAR ESTA RUTA si tu repo no está en %USERPROFILE%\groupe_seb_qr ───
set PROJECT_DIR=%USERPROFILE%\groupe_seb_qr

REM Validar que la carpeta existe
if not exist "%PROJECT_DIR%\gui.py" (
    echo.
    echo  X  No se encuentra gui.py en: %PROJECT_DIR%
    echo     Editar este .bat y ajustar PROJECT_DIR a la ruta correcta.
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

REM Lanzar la GUI en background, minimizada, con titulo identificable
start "QR-GUI" /MIN python gui.py

REM Esperar a que el servidor levante
timeout /t 3 /nobreak >nul

REM Abrir browser en la GUI
start http://localhost:8080

REM Cerrar esta ventana
exit
