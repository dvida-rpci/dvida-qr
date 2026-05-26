@echo off
setlocal enabledelayedexpansion
REM ═══════════════════════════════════════════════════════════════════
REM   Instala accesos directos al lanzador en:
REM     - Escritorio  (siempre)
REM     - Inicio automatico al login (opcional, preguntado)
REM ═══════════════════════════════════════════════════════════════════

set HERE=%~dp0
set LAUNCHER=%HERE%Lanzar_QR_App.bat
set DESKTOP=%USERPROFILE%\Desktop
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

REM ─── Elegir launcher ───
echo.
echo  Cual lanzador queres instalar?
echo     [1] Windows nativo (python instalado en Windows)
echo     [2] WSL (python dentro de Ubuntu)
echo.
set /p MODO="Elegir (1 o 2): "

if "%MODO%"=="2" (
    set LAUNCHER=%HERE%Lanzar_QR_App_WSL.bat
    echo  Usando launcher WSL.
) else (
    set LAUNCHER=%HERE%Lanzar_QR_App.bat
    echo  Usando launcher Windows nativo.
)

if not exist "!LAUNCHER!" (
    echo.
    echo  X  No existe: !LAUNCHER!
    pause
    exit /b 1
)

REM ─── Crear acceso directo .lnk en el Escritorio usando PowerShell ───
echo.
echo  · Creando acceso directo en el Escritorio...
powershell -NoProfile -Command ^
    "$s = (New-Object -COM WScript.Shell).CreateShortcut('%DESKTOP%\QR Groupe SEB.lnk'); ^
     $s.TargetPath = '!LAUNCHER!'; ^
     $s.WorkingDirectory = '%HERE%'; ^
     $s.WindowStyle = 7; ^
     $s.IconLocation = '%SystemRoot%\System32\shell32.dll,13'; ^
     $s.Save()"

if exist "%DESKTOP%\QR Groupe SEB.lnk" (
    echo  OK  Acceso directo creado en el Escritorio.
) else (
    echo  X   Fallo creando el acceso directo del Escritorio.
)

REM ─── Preguntar si quiere auto-arranque ───
echo.
set /p AUTO="Queres que la GUI arranque sola al encender el PC? (S/N): "
if /I "%AUTO%"=="S" (
    copy /Y "%DESKTOP%\QR Groupe SEB.lnk" "%STARTUP%\QR Groupe SEB.lnk" >nul
    if exist "%STARTUP%\QR Groupe SEB.lnk" (
        echo  OK  Auto-arranque configurado.
        echo     Para desactivarlo: borrar el archivo de
        echo     %STARTUP%\QR Groupe SEB.lnk
    ) else (
        echo  X   No se pudo copiar al Startup.
    )
) else (
    echo  Sin auto-arranque. Tenes que hacer doble click al acceso del
    echo  Escritorio cada vez que quieras lanzar la GUI.
)

echo.
echo  Listo. Probalo con doble click en el icono "QR Groupe SEB" del Escritorio.
echo.
pause
