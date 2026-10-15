# GUI: administración de usuarios y fácil de correr en cualquier laptop — diseño

Fecha: 2026-10-15 · Estado: **diseño, sin implementar**

## Propósito

1. Que el rol **oficina** pueda **crear y administrar usuarios desde la GUI**, sin entrar al panel de Supabase ni escribir SQL.
2. Que la GUI se pueda **instalar y correr en cualquier laptop** con un doble clic, sin saber de Python, terminal ni Git.

Contexto: hoy los usuarios se crean en Supabase → Authentication y su rol con un `insert` en `profiles`; la GUI se instala siguiendo `New_Laptop.txt` (Python + pip + terminal). Ambas cosas dependen de alguien técnico. El producto se replica en N plantas (cada una con su repo y su proyecto Supabase), así que todo debe ser repetible por planta.

Decisiones tomadas con el usuario:
- La administración de usuarios **vive en la GUI** y solo la hace **oficina**.
- La llave de administrador (`service_role`) **nunca** va en la GUI, el repo ni `site_config.json` (decisión vigente del histórico de mantenimientos).

## Parte A — Administración de usuarios desde la GUI

### Arquitectura

La GUI no puede crear usuarios con la `anon_key`. Se agrega una **Edge Function de Supabase** `admin-users` (`supabase/functions/admin-users/index.ts`) que corre en el servidor de Supabase, donde la `service_role` está disponible como variable de entorno propia del proyecto (no se copia a ningún lado):

```
GUI (sesión oficina, JWT) ──► Edge Function admin-users ──► Auth Admin API + tabla profiles
                                    │ verifica: JWT válido, perfil oficina y activo
```

La función **verifica cada llamada**: JWT válido → perfil con `role = 'oficina'` y `active = true`. Si no, responde 403. RLS sigue siendo la única fuente de verdad para los datos de mantenimiento; la función solo administra cuentas.

### Acciones

| Acción | Qué hace | Reglas |
| --- | --- | --- |
| `list` | Usuarios con nombre, correo, rol, estado y último ingreso | — |
| `create` | Crea la cuenta (correo confirmado) + su fila en `profiles` en un paso | Correo único; rol `tecnico` u `oficina`; contraseña temporal generada (formato `Ptar-xxxx-xxxx`) |
| `set_role` | Cambia técnico ↔ oficina | No se puede quitar el rol al **último** oficina activo |
| `reset_password` | Genera una contraseña temporal nueva | Se muestra **una sola vez** en la GUI, con botón Copiar |
| `deactivate` / `reactivate` | Bloquea o reactiva el acceso (`ban_duration` en Auth + `profiles.active`) | No se puede desactivar a sí mismo ni al último oficina activo |

**No hay borrado de usuarios**: sus registros, comentarios y la auditoría apuntan a su `user_id`. Desactivar conserva el historial ("Registrado por Juan Pérez") y corta el acceso.

### Datos (migración nueva)

- `profiles.active boolean not null default true`.
- `is_member()` e `is_oficina()` pasan a exigir `active = true`: un usuario desactivado que todavía tenga una sesión abierta **no puede registrar ni editar** (RLS lo frena aunque su token siga vigente).
- `user_admin_log (id, actor_id, action, target_user_id, details jsonb, created_at)`: auditoría de toda acción de la función. Sin políticas de escritura para nadie (solo la función, con `service_role`); lectura solo oficina.

### Contraseñas

- Temporal generada por la función (no la inventa quien administra), mostrada una vez.
- Nuevo **"🔑 Cambiar mi contraseña"** en la GUI y en el sitio (`auth.updateUser`), para que cada persona reemplace la temporal. Hoy no existe ninguna pantalla para esto.

### Pantalla "👥 Usuarios" (GUI)

Botón propio en `gui.py` (diálogo maximizado, mismo patrón que 📋 Plan). Requiere sesión oficina.

- Lista de **tarjetas** (no tabla ancha): nombre, correo, rol y estado; del 4.º en adelante plegadas con chevron, buscador por nombre o correo, de a 10 con "Cargar más" (reglas de "Celular primero").
- **+ Nuevo usuario**: nombre, correo, rol → muestra la contraseña temporal con Copiar.
- Por usuario (al abrir su tarjeta): Cambiar rol · Restablecer contraseña · Desactivar/Reactivar. Cada acción pide confirmación y dice qué pasa ("Juan no podrá entrar; su historial se conserva").

### Despliegue por planta

`setup_supabase_planta.sh` agrega `supabase functions deploy admin-users --project-ref <ref>`. Para DVida (proyecto existente) la función se despliega igual y la migración va con `psql`/Management API como las anteriores, **con confirmación**.

### Pruebas

- Función contra el stack local (`supabase functions serve`), con pytest: oficina crea/lista/cambia rol/restablece/desactiva; técnico y anónimo reciben 403; no se puede desactivar al último oficina ni a sí mismo; cada acción queda en `user_admin_log`.
- RLS: un usuario desactivado con sesión abierta no puede insertar registros.
- GUI en navegador headless a 360/390 px y escritorio.

## Parte B — GUI fácil de correr en cualquier laptop

### Requisitos

- Windows 10/11 (principal), macOS y Linux.
- **Sin instalar Python a mano y, de ser posible, sin permisos de administrador** (laptops corporativos).
- **Un doble clic** para abrir; el navegador se abre solo en la GUI.
- Actualizar sin reinstalar.
- Configurar la planta (Supabase, repo) **sin editar archivos**.

### Recomendación: instalador con `uv`

[`uv`](https://docs.astral.sh/uv/) es un binario único que instala Python aislado y las dependencias exactas, sin admin y en segundos.

1. **`Instalar_QR_PTAR.bat`** (Windows) / **`instalar.sh`** (macOS/Linux), en la raíz del repo:
   - Descarga `uv` en el perfil del usuario (sin admin).
   - `uv sync` instala Python 3.12 + dependencias con versiones fijas (`pyproject.toml` + `uv.lock`, reemplazan a `requirements.txt` para la GUI).
   - Crea el acceso directo **"QR PTAR"** en escritorio y menú Inicio (en macOS/Linux, el equivalente).
2. **El acceso directo** corre `uv run gui.py`, espera a que responda y abre el navegador en `http://localhost:8080`. Si ya está corriendo, solo abre el navegador.
3. **Actualizar**: botón **"🔄 Buscar actualización"** en la GUI (`git pull` + `uv sync`), o volver a correr el instalador.

### Asistente de primer uso

Si falta la configuración de la planta, la GUI abre un asistente en vez de fallar:
1. URL de Supabase + `anon_key` → prueba la conexión antes de guardar.
2. Repo de GitHub de la planta → verifica que exista y se pueda publicar.
3. Guarda en `site_config.json` y sigue a la pantalla normal.

### Publicar sin terminal

Botón **"🚀 Publicar sitio"** en la GUI: regenera `docs/`, hace commit y push, y espera a que GitHub Pages lo sirva (siguiendo la redirección del dominio propio). Las credenciales de GitHub las guarda Git Credential Manager (viene con Git para Windows); la primera vez abre el navegador para autorizar. Hoy publicar exige terminal (`update_site_from_excel.sh --push`).

### Pantalla "🩺 Estado"

Diagnóstico de un vistazo: versión de la app, Git instalado, conexión a Supabase, permiso para publicar en el repo, puerto 8080 libre. Cada problema con su solución en una línea.

### Alternativas descartadas

- **Ejecutable PyInstaller/nicegui-pack:** pesado, falsos positivos de antivirus en laptops corporativos, hay que reempaquetar en cada versión, y publicar igual necesita Git.
- **Docker:** Docker Desktop es pesado, requiere admin y licencia en empresas grandes. El `Dockerfile` se conserva para correr la GUI en un servidor, no para laptops.

`New_Laptop.txt` y `windows_launchers/` se reemplazan por el instalador (se dejan un tiempo apuntando a él).

### Pruebas

- Instalador en un Windows limpio (Windows Sandbox o VM, usuario sin admin), macOS y Ubuntu: de cero a GUI abierta en menos de 5 minutos con internet; segunda apertura en menos de 10 segundos.
- Asistente: Supabase o repo equivocados → mensaje claro, no guarda.
- Publicar: commit + push + verificación en vivo.

## Fases (un plan por fase)

1. **Usuarios:** migración (`active`, `is_member/is_oficina`, `user_admin_log`), Edge Function, pantalla 👥 Usuarios, "Cambiar mi contraseña" (GUI y sitio), despliegue en `setup_supabase_planta.sh`.
2. **Instalador:** `pyproject.toml` + `uv.lock`, `Instalar_QR_PTAR.bat` / `instalar.sh`, acceso directo, "Buscar actualización".
3. **Primer uso y publicación:** asistente de configuración, "🚀 Publicar sitio", pantalla 🩺 Estado.

## Preguntas abiertas

1. ¿Los laptops de las plantas tienen Windows con o sin permisos de administrador? (El diseño asume *sin*.)
2. ¿Quién publica el sitio en cada planta? Necesita una cuenta de GitHub con permiso sobre el repo de esa planta.
3. ¿Hace falta macOS, o basta Windows (y Linux para RPCI)?
