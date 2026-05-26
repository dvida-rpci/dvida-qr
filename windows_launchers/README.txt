═══════════════════════════════════════════════════════════════════════
  ACCESOS DIRECTOS PARA WINDOWS
  Aplicativo QR Groupe SEB
═══════════════════════════════════════════════════════════════════════


───────────────────────────────────────────────────────────────────────
  ARCHIVOS EN ESTA CARPETA
───────────────────────────────────────────────────────────────────────

  Lanzar_QR_App.bat            Lanza la GUI cuando Python está instalado
                               directamente en Windows.

  Lanzar_QR_App_WSL.bat        Lanza la GUI cuando Python vive dentro
                               de WSL (Ubuntu).

  Parar_QR_App.bat             Detiene la GUI y el servidor de preview.
                               Mata procesos en puertos :8080 y :8000.

  Instalar_acceso_directo.bat  Crea un acceso directo "QR Groupe SEB"
                               en el Escritorio y opcionalmente lo
                               configura para auto-arranque al login.


───────────────────────────────────────────────────────────────────────
  USO RAPIDO
───────────────────────────────────────────────────────────────────────

  1. Editar Lanzar_QR_App.bat (o el _WSL.bat) y ajustar la ruta
     PROJECT_DIR a donde tengas el repo del aplicativo.

     Por defecto asume:  %USERPROFILE%\groupe_seb_qr
     (que se traduce en:  C:\Users\TU_USUARIO\groupe_seb_qr)

  2. Doble click en Instalar_acceso_directo.bat
     Te pregunta:
         - Windows nativo o WSL?
         - Queres auto-arranque al login? (S/N)
     Crea "QR Groupe SEB.lnk" en el Escritorio.

  3. Doble click en el icono del Escritorio → la GUI arranca y
     abre el browser en http://localhost:8080 automaticamente.

  4. Para detener: doble click en Parar_QR_App.bat


───────────────────────────────────────────────────────────────────────
  CONFIGURACION POR ESCENARIO
───────────────────────────────────────────────────────────────────────

ESCENARIO 1 — Python en Windows nativo:

  Editar Lanzar_QR_App.bat:
      set PROJECT_DIR=C:\Users\TU_USUARIO\groupe_seb_qr

  Verificar que "python" funcione en CMD/PowerShell:
      python --version          (debe decir 3.10+)
      pip install openpyxl nicegui

ESCENARIO 2 — Python en WSL (Ubuntu):

  Editar Lanzar_QR_App_WSL.bat:
      set WSL_DISTRO=Ubuntu
      set WSL_USER=TU_USUARIO_LINUX
      set PROJECT_DIR_WSL=/home/TU_USUARIO_LINUX/google-sites-migrator

  Verificar dentro de WSL:
      python3 --version
      pip3 install --break-system-packages openpyxl nicegui


───────────────────────────────────────────────────────────────────────
  PROBLEMAS COMUNES
───────────────────────────────────────────────────────────────────────

• "No se encuentra gui.py"
    El PROJECT_DIR en el .bat no apunta a la carpeta correcta.
    Editar el .bat con Bloc de notas y corregir la ruta.

• El browser abre pero dice "no se puede establecer conexion"
    La GUI no arranco. Posibles causas:
      - Python no esta en el PATH (Windows nativo)
      - Falta instalar openpyxl/nicegui:
            pip install openpyxl nicegui
      - Puerto 8080 ya ocupado por otro proceso
            (ejecutar Parar_QR_App.bat primero)

• Aparece y desaparece la ventana de CMD rapido
    El .bat tuvo un error pero se cerro. Para depurar, abrir CMD
    manualmente y ejecutar el .bat desde ahi para ver el error.

• Auto-arranque no funciona
    Verificar que el .lnk este en:
        %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
    Win + R → escribir "shell:startup" → Enter (te abre ese folder).


───────────────────────────────────────────────────────────────────────
  DESINSTALAR
───────────────────────────────────────────────────────────────────────

  - Borrar  %USERPROFILE%\Desktop\QR Groupe SEB.lnk
  - Borrar  %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\QR Groupe SEB.lnk
  - (Opcional) borrar esta carpeta windows_launchers/

  El repo del aplicativo en si NO se toca.
