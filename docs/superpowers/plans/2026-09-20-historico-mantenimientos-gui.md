# Histórico de Mantenimientos — Plan 3: Pantalla en `gui.py`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar a la GUI de oficina una pantalla "Mantenimientos" — login contra las mismas cuentas de Supabase Auth, selector de TAG, tabla del historial, alta de registros (con compresión de fotos vía Pillow y carga de audio desde archivo), y edición/borrado restringido a `oficina` — usando el mismo schema/RLS del Plan 1.

**Architecture:** Vive en un módulo nuevo `gui_maintenance.py`, **no** dentro de `gui.py` (que ya tiene 641 líneas dedicadas al generador del sitio; mezclar ahí una pantalla completa de CRUD contra Supabase sería una responsabilidad distinta en el mismo archivo). `gui.py` solo importa el módulo (para registrar la página) y agrega un botón de navegación. `gui_maintenance.py` es un cliente más de Supabase — igual que el sitio (Plan 2), habla directo con Supabase vía `supabase-py`, sin backend propio.

**Tech Stack:** NiceGUI (`@ui.page`, mismo framework que `gui.py`), `supabase-py`, `Pillow` (compresión de fotos), `openpyxl` (leer TAGs de `plantilla_sitio.xlsx`, reutilizando el mismo patrón que `generate_tag_resources_template.py:read_tags_from_plantilla()`).

**Testing:** manual, siguiendo la convención ya establecida para `gui.py` (sin suite automatizada — ver spec, sección "Testing": *"`gui.py`: verificación manual, como el resto de la GUI hoy"*).

**Prerequisito:** Plan 1 aplicado (schema+RLS+Storage, al menos en local vía `supabase start`) y Plan 1's Task 1 ya instaló `supabase` en `requirements.txt`. Este plan no depende de que el Plan 2 (sitio) esté terminado — ambos leen el mismo bloque `supabase` de `site_config.json` de forma independiente.

---

### Task 1: Esqueleto de la página + login

**Files:**
- Create: `gui_maintenance.py`
- Modify: `requirements.txt`
- Modify: `gui.py:32` (import) y agregar botón de navegación cerca de la línea 447-448

- [ ] **Step 1: Agregar `Pillow` a las dependencias**

Modify `requirements.txt`:
```
nicegui
openpyxl
python-multipart
supabase
Pillow
```

Run:
```bash
pip3 install --break-system-packages -r requirements.txt
```
Expected: instala `Pillow` sin errores (`supabase` ya debería estar si corriste el Plan 1).

- [ ] **Step 2: Crear `gui_maintenance.py` con el esqueleto + login**

Create `gui_maintenance.py`:
```python
#!/usr/bin/env python3
"""
gui_maintenance.py
===================
Pantalla NiceGUI "Mantenimientos" — historial de mantenimientos por TAG
vía Supabase (mismo schema/RLS que el Plan 1 de este feature).

Se registra como página nueva (/mantenimientos), importada desde gui.py.
No tiene entrypoint propio — corre dentro del proceso de gui.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from nicegui import ui
from openpyxl import load_workbook
from supabase import create_client, Client

REPO_ROOT = Path(__file__).parent
SITE_CONFIG = REPO_ROOT / "site_config.json"
PLANTILLA = REPO_ROOT / "plantilla_sitio.xlsx"

MAX_ATTACHMENTS = 5


def load_supabase_config() -> dict:
    if not SITE_CONFIG.exists():
        return {"url": "", "anon_key": ""}
    cfg = json.loads(SITE_CONFIG.read_text(encoding="utf-8"))
    return cfg.get("supabase", {"url": "", "anon_key": ""})


def list_tags_from_plantilla() -> list[str]:
    """Mismo patrón que generate_tag_resources_template.py:read_tags_from_plantilla()."""
    if not PLANTILLA.exists():
        return []
    wb = load_workbook(PLANTILLA, data_only=True)
    ws = wb["Datos"] if "Datos" in wb.sheetnames else wb.active
    tags = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        tag = row[0]
        if tag:
            tags.append(str(tag).strip())
    return tags


@ui.page("/mantenimientos")
def maintenance_page():
    supa_cfg = load_supabase_config()
    if not supa_cfg.get("url") or not supa_cfg.get("anon_key"):
        ui.label(
            '⚠️ Falta configurar Supabase en site_config.json (bloque "supabase").'
        ).classes("text-red-600 p-6")
        return

    client: Client = create_client(supa_cfg["url"], supa_cfg["anon_key"])
    session_state: dict = {"user": None, "role": None}

    ui.label("🧰 Mantenimientos").classes("text-3xl font-bold px-6 pt-6")
    content = ui.column().classes("max-w-4xl mx-auto p-6 gap-4 w-full")

    def render_login():
        content.clear()
        with content:
            with ui.card().classes("w-full max-w-sm"):
                ui.label("Iniciar sesión").classes("font-semibold")
                email_input = ui.input("Email").props("outlined dense").classes("w-full")
                password_input = (
                    ui.input("Contraseña", password=True)
                    .props("outlined dense")
                    .classes("w-full")
                )
                error_label = ui.label("").classes("text-red-600 text-sm")

                def do_login():
                    try:
                        result = client.auth.sign_in_with_password(
                            {"email": email_input.value, "password": password_input.value}
                        )
                    except Exception as e:
                        error_label.text = f"No se pudo iniciar sesión: {e}"
                        return
                    session_state["user"] = result.user
                    load_profile_and_render()

                ui.button("Ingresar", on_click=do_login).props("color=primary")

    def load_profile_and_render():
        try:
            profile = (
                client.table("profiles")
                .select("*")
                .eq("user_id", session_state["user"].id)
                .execute()
            )
        except Exception as e:
            content.clear()
            with content:
                ui.label(f"No se pudo cargar el perfil: {e}").classes("text-red-600")
            return
        if not profile.data:
            content.clear()
            with content:
                ui.label(
                    "Tu usuario no tiene un perfil asignado (tabla profiles). "
                    "Contactá al administrador del proyecto Supabase."
                ).classes("text-red-600")
            return
        session_state["role"] = profile.data[0]["role"]
        render_main_screen()

    def do_logout():
        client.auth.sign_out()
        session_state["user"] = None
        session_state["role"] = None
        render_login()

    def render_main_screen():
        content.clear()
        with content:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(
                    f"Sesión: {session_state['user'].email} ({session_state['role']})"
                ).classes("text-sm text-gray-600")
                ui.button("Cerrar sesión", on_click=do_logout).props("flat dense")
            ui.label("(selector de TAG + historial: Task 2)").classes("text-gray-400 italic")

    render_login()
```

- [ ] **Step 3: Registrar la página desde `gui.py` + botón de navegación**

En `gui.py`, agregar el import junto a los otros imports (línea ~32):
```python
from nicegui import app, ui

import gui_maintenance  # noqa: F401 — el import registra la página /mantenimientos
```

Y agregar un botón de navegación en la fila de acciones existente (línea ~440-448, junto a `generate_btn`/`view_btn`):
```python
    with ui.row().classes("w-full justify-center gap-4 mt-4"):
        generate_btn = ui.button("🏗️  Generar sitio", on_click=lambda: generate())
        generate_btn.props("color=primary size=lg")

        view_btn = ui.button("🌐 Ver sitio", on_click=lambda: open_preview())
        view_btn.props("color=secondary outline size=lg")

        ui.button(
            "🧰 Mantenimientos", on_click=lambda: ui.navigate.to("/mantenimientos", new_tab=True)
        ).props("color=secondary outline size=lg")
```

- [ ] **Step 4: Verificación manual**

Prerequisito: en `site_config.json`, el bloque `supabase` debe tener la `url`/`anon_key` de tu instancia local (mismo valor que usaste en el Plan 2, Task 1, Step 4).

Run: `python3 gui.py` y abrir `http://localhost:8080`.
Expected: aparece el botón "🧰 Mantenimientos". Al tocarlo, abre `http://localhost:8080/mantenimientos` en una pestaña nueva con el formulario de login. Con `oficina@test.local` / `Test1234!` (los usuarios de test del Plan 1), entra y muestra "Sesión: oficina@test.local (oficina)" + botón "Cerrar sesión". Con credenciales inválidas, muestra el error sin crashear la página.

- [ ] **Step 5: Commit**

```bash
git add gui_maintenance.py gui.py requirements.txt
git commit -m "feat: pantalla Mantenimientos en gui.py — esqueleto + login"
```

---

### Task 2: Selector de TAG + tabla de historial (lectura)

**Files:**
- Modify: `gui_maintenance.py`

- [ ] **Step 1: Reemplazar el placeholder de `render_main_screen` por el selector + tabla**

En `gui_maintenance.py`, reemplazar:
```python
    def render_main_screen():
        content.clear()
        with content:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(
                    f"Sesión: {session_state['user'].email} ({session_state['role']})"
                ).classes("text-sm text-gray-600")
                ui.button("Cerrar sesión", on_click=do_logout).props("flat dense")
            ui.label("(selector de TAG + historial: Task 2)").classes("text-gray-400 italic")
```
por:
```python
    def render_main_screen():
        content.clear()
        with content:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(
                    f"Sesión: {session_state['user'].email} ({session_state['role']})"
                ).classes("text-sm text-gray-600")
                ui.button("Cerrar sesión", on_click=do_logout).props("flat dense")

            tags = list_tags_from_plantilla()
            records_container = ui.column().classes("w-full gap-3")

            def on_tag_change(e):
                if e.value:
                    render_records(records_container, e.value)
                else:
                    records_container.clear()

            ui.select(
                tags, label="TAG", with_input=True, on_change=on_tag_change
            ).props("outlined dense").classes("w-full max-w-xs")

    def render_records(container, tag_id: str):
        container.clear()
        with container:
            ui.label("Cargando…").classes("text-gray-500")
        try:
            result = (
                client.table("maintenance_records")
                .select("*, maintenance_comments(*), maintenance_attachments(*)")
                .eq("tag_id", tag_id)
                .order("performed_at", desc=True)
                .execute()
            )
        except Exception as e:
            container.clear()
            with container:
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"No se pudo cargar el historial: {e}").classes("text-red-600")
                    ui.button(
                        "Reintentar", on_click=lambda: render_records(container, tag_id)
                    ).props("flat dense")
            return

        container.clear()
        with container:
            ui.button(
                "+ Registrar mantenimiento",
                on_click=lambda: ui.notify("Implementado en el Task 3", type="info"),
            ).props("color=primary")
            if not result.data:
                ui.label("Todavía no hay mantenimientos registrados para este TAG.").classes(
                    "text-gray-500"
                )
            for record in result.data:
                render_record_card(container, record, tag_id)

    def render_record_card(container, record: dict, tag_id: str):
        with container:
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(record["performed_at"]).classes("font-bold")
                    ui.label(record["type"]).classes(
                        "text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600"
                    )
                    if record.get("is_date_anomaly"):
                        ui.label("⚠️ revisar fecha").classes("text-red-600 text-xs font-semibold")
                ui.label(record["description"])
                if record.get("parts_used"):
                    ui.label(f"Repuestos: {record['parts_used']}").classes(
                        "text-sm text-gray-600"
                    )
                if record.get("next_scheduled_at"):
                    ui.label(f"Próximo programado: {record['next_scheduled_at']}").classes(
                        "text-sm text-gray-600"
                    )
                for comment in record.get("maintenance_comments", []):
                    ui.label(comment["body"]).classes(
                        "text-sm bg-gray-50 rounded px-2 py-1 mt-1"
                    )
                attachments = record.get("maintenance_attachments", [])
                if attachments:
                    with ui.row().classes("gap-2 mt-2 flex-wrap"):
                        for attachment in attachments:
                            ui.label(
                                f"📎 {attachment['kind']} ({attachment['storage_path'].split('/')[-1]})"
                            ).classes("text-xs bg-gray-100 rounded px-2 py-1")
```

- [ ] **Step 2: Verificación manual**

Con el registro de prueba que creaste en el Plan 2 Task 4 (o creando uno nuevo desde Supabase Studio), logueate en `/mantenimientos` como `oficina@test.local`, elegí ese TAG en el selector. Expected: aparece la tarjeta del evento con fecha/tipo/descripción/badge de anomalía si corresponde, comentarios y una lista simple de adjuntos (todavía sin preview de imagen — eso no está en el alcance del spec para `gui.py`, que solo pide poder ver que existen). Probá también con un TAG sin mantenimientos: debe mostrar "Todavía no hay mantenimientos registrados".

- [ ] **Step 3: Commit**

```bash
git add gui_maintenance.py
git commit -m "feat: selector de TAG + lectura del historial en gui.py"
```

---

### Task 3: Alta de registro (con compresión de fotos y audio desde archivo)

**Files:**
- Modify: `gui_maintenance.py`

- [ ] **Step 1: Helper de compresión de imágenes (Pillow)**

En `gui_maintenance.py`, agregar el import de Pillow y `io` al principio del archivo:
```python
import io
import json
from pathlib import Path

from nicegui import ui
from openpyxl import load_workbook
from PIL import Image
from supabase import create_client, Client
```

Y agregar la función de compresión, cerca de `list_tags_from_plantilla`:
```python
def compress_image_bytes(raw_bytes: bytes) -> bytes:
    """Redimensiona a max 1600px de ancho y recodifica a JPEG calidad 70 (mismo
    criterio que la compresión client-side del sitio, Plan 2)."""
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    max_width = 1600
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()
```

- [ ] **Step 2: Reemplazar el botón placeholder por el diálogo de alta**

En `gui_maintenance.py`, dentro de `render_records`, reemplazar:
```python
            ui.button(
                "+ Registrar mantenimiento",
                on_click=lambda: ui.notify("Implementado en el Task 3", type="info"),
            ).props("color=primary")
```
por:
```python
            ui.button(
                "+ Registrar mantenimiento",
                on_click=lambda: open_new_record_dialog(tag_id, container),
            ).props("color=primary")
```

- [ ] **Step 3: El diálogo de alta**

Agregar la función `open_new_record_dialog` en `gui_maintenance.py`, después de `render_record_card`:
```python
    def open_new_record_dialog(tag_id: str, records_container):
        pending_attachments: list[dict] = []  # [{"kind": "photo"|"audio", "data": bytes}]

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label(f"Registrar mantenimiento — {tag_id}").classes("text-lg font-semibold")

            performed_at_input = ui.input("Fecha del mantenimiento", value=_today_iso()).props(
                "outlined dense type=date"
            ).classes("w-full")
            type_select = ui.select(
                {"preventivo": "Preventivo", "correctivo": "Correctivo"}, value="preventivo"
            ).props("outlined dense").classes("w-full")
            description_input = ui.textarea("Descripción").props("outlined dense").classes(
                "w-full"
            )
            parts_input = ui.textarea("Repuestos / insumos (opcional)").props(
                "outlined dense"
            ).classes("w-full")
            next_input = ui.input("Próximo programado (opcional)").props(
                "outlined dense type=date"
            ).classes("w-full")

            attachments_label = ui.label("Adjuntos: 0/5").classes("text-sm text-gray-600")
            error_label = ui.label("").classes("text-red-600 text-sm")

            def refresh_attachments_label():
                attachments_label.text = f"Adjuntos: {len(pending_attachments)}/{MAX_ATTACHMENTS}"

            async def on_photo_upload(e):
                if len(pending_attachments) >= MAX_ATTACHMENTS:
                    ui.notify("Ya llegaste al máximo de 5 adjuntos", type="warning")
                    return
                raw = await e.file.read()
                compressed = compress_image_bytes(raw)
                pending_attachments.append({"kind": "photo", "data": compressed})
                refresh_attachments_label()
                ui.notify(f"Foto agregada ({e.file.name})", type="positive")

            async def on_audio_upload(e):
                if len(pending_attachments) >= MAX_ATTACHMENTS:
                    ui.notify("Ya llegaste al máximo de 5 adjuntos", type="warning")
                    return
                raw = await e.file.read()
                pending_attachments.append({"kind": "audio", "data": raw})
                refresh_attachments_label()
                ui.notify(f"Audio agregado ({e.file.name})", type="positive")

            with ui.row().classes("w-full gap-4"):
                ui.upload(on_upload=on_photo_upload, auto_upload=True, max_files=1).props(
                    'accept="image/*"'
                ).classes("flex-1")
                ui.upload(on_upload=on_audio_upload, auto_upload=True, max_files=1).props(
                    'accept="audio/*"'
                ).classes("flex-1")

            def submit():
                error_label.text = ""
                if not type_select.value or not description_input.value:
                    error_label.text = "Completá al menos tipo y descripción."
                    return
                payload = {
                    "tag_id": tag_id,
                    "performed_at": performed_at_input.value,
                    "type": type_select.value,
                    "description": description_input.value,
                    "parts_used": parts_input.value or None,
                    "next_scheduled_at": next_input.value or None,
                }
                try:
                    result = client.table("maintenance_records").insert(payload).execute()
                    record_id = result.data[0]["id"]
                    for item in pending_attachments:
                        ext = "jpg" if item["kind"] == "photo" else "webm"
                        path = f"{tag_id}/{record_id}/{_random_suffix()}.{ext}"
                        client.storage.from_("maintenance-attachments").upload(
                            path, item["data"]
                        )
                        client.table("maintenance_attachments").insert(
                            {"record_id": record_id, "kind": item["kind"], "storage_path": path}
                        ).execute()
                except Exception as e:
                    error_label.text = f"No se pudo guardar: {e}"
                    return
                ui.notify("Registro guardado", type="positive")
                dialog.close()
                render_records(records_container, tag_id)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Guardar", on_click=submit).props("color=primary")

        dialog.open()
```

- [ ] **Step 4: Helpers de fecha/nombre de archivo**

Agregar, cerca de `compress_image_bytes`:
```python
import random
import string
from datetime import date


def _today_iso() -> str:
    return date.today().isoformat()


def _random_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
```

(Ajustar el bloque de imports al principio del archivo para incluir `random`, `string` y `from datetime import date` junto a los demás.)

- [ ] **Step 5: Verificación manual**

Logueado como `tecnico@test.local` en `/mantenimientos`, elegí un TAG, tocá "+ Registrar mantenimiento", completá el formulario, subí una foto (confirmá que el archivo que termina en el bucket de Supabase Storage — revisalo desde Supabase Studio — pesa menos que el original) y un archivo de audio cualquiera. Guardá y confirmá que el nuevo registro aparece en la lista. Intentá subir una 6ta imagen y confirmá que el aviso "Ya llegaste al máximo" aparece y no se agrega.

- [ ] **Step 6: Commit**

```bash
git add gui_maintenance.py
git commit -m "feat: alta de mantenimiento en gui.py (fotos comprimidas + audio)"
```

---

### Task 4: Editar/borrar (solo oficina) + agregar comentario/adjunto a evento propio

**Files:**
- Modify: `gui_maintenance.py`

- [ ] **Step 1: Botones de acción condicionados por rol en `render_record_card`**

En `gui_maintenance.py`, dentro de `render_record_card`, después del bloque que renderiza `attachments` (antes de que termine el `with ui.card()`), agregar:
```python
                with ui.row().classes("gap-2 mt-2"):
                    is_owner = record["created_by"] == session_state["user"].id
                    if is_owner or session_state["role"] == "oficina":
                        ui.button(
                            "+ Comentario/adjunto",
                            on_click=lambda r=record: open_add_comment_dialog(r, tag_id, container),
                        ).props("flat dense")
                    if session_state["role"] == "oficina":
                        ui.button(
                            "Editar",
                            on_click=lambda r=record: open_edit_dialog(r, tag_id, container),
                        ).props("flat dense")
                        ui.button(
                            "Borrar",
                            on_click=lambda r=record: confirm_delete(r, tag_id, container),
                        ).props("flat dense color=red")
```

(`is_owner` cubre la regla del spec "técnico solo agrega a lo propio"; el botón de comentario/adjunto también se muestra a oficina en cualquier registro, ya que oficina tiene permiso total.)

- [ ] **Step 2: Diálogo de edición (solo oficina, RLS lo respalda igual)**

Agregar después de `open_new_record_dialog`:
```python
    def open_edit_dialog(record: dict, tag_id: str, records_container):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label(f"Editar mantenimiento — {tag_id}").classes("text-lg font-semibold")
            description_input = ui.textarea("Descripción", value=record["description"]).props(
                "outlined dense"
            ).classes("w-full")
            parts_input = ui.textarea(
                "Repuestos / insumos", value=record.get("parts_used") or ""
            ).props("outlined dense").classes("w-full")
            next_input = ui.input(
                "Próximo programado", value=record.get("next_scheduled_at") or ""
            ).props("outlined dense type=date").classes("w-full")
            error_label = ui.label("").classes("text-red-600 text-sm")

            def submit():
                try:
                    client.table("maintenance_records").update(
                        {
                            "description": description_input.value,
                            "parts_used": parts_input.value or None,
                            "next_scheduled_at": next_input.value or None,
                        }
                    ).eq("id", record["id"]).execute()
                except Exception as e:
                    error_label.text = f"No se pudo editar: {e}"
                    return
                ui.notify("Registro actualizado (la edición queda en auditoría)", type="positive")
                dialog.close()
                render_records(records_container, tag_id)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Guardar", on_click=submit).props("color=primary")

        dialog.open()

    def confirm_delete(record: dict, tag_id: str, records_container):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"¿Borrar el registro del {record['performed_at']}? Queda en auditoría.")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")

                def do_delete():
                    try:
                        client.table("maintenance_records").delete().eq(
                            "id", record["id"]
                        ).execute()
                    except Exception as e:
                        ui.notify(f"No se pudo borrar: {e}", type="negative")
                        return
                    dialog.close()
                    ui.notify("Registro borrado", type="positive")
                    render_records(records_container, tag_id)

                ui.button("Borrar", on_click=do_delete).props("color=red")
        dialog.open()
```

- [ ] **Step 3: Diálogo de comentario/adjunto**

Agregar después de `confirm_delete`:
```python
    def open_add_comment_dialog(record: dict, tag_id: str, records_container):
        current_attachment_count = len(record.get("maintenance_attachments", []))
        pending_attachments: list[dict] = []

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label("Agregar comentario/adjunto").classes("text-lg font-semibold")
            body_input = ui.textarea("Comentario").props("outlined dense").classes("w-full")
            attachments_label = ui.label(
                f"Adjuntos: {current_attachment_count}/{MAX_ATTACHMENTS}"
            ).classes("text-sm text-gray-600")
            error_label = ui.label("").classes("text-red-600 text-sm")

            def slots_left() -> int:
                return MAX_ATTACHMENTS - current_attachment_count - len(pending_attachments)

            def refresh_label():
                attachments_label.text = (
                    f"Adjuntos: {current_attachment_count + len(pending_attachments)}/{MAX_ATTACHMENTS}"
                )

            async def on_photo_upload(e):
                if slots_left() <= 0:
                    ui.notify("Ya llegaste al máximo de 5 adjuntos", type="warning")
                    return
                raw = await e.file.read()
                pending_attachments.append({"kind": "photo", "data": compress_image_bytes(raw)})
                refresh_label()

            async def on_audio_upload(e):
                if slots_left() <= 0:
                    ui.notify("Ya llegaste al máximo de 5 adjuntos", type="warning")
                    return
                raw = await e.file.read()
                pending_attachments.append({"kind": "audio", "data": raw})
                refresh_label()

            with ui.row().classes("w-full gap-4"):
                ui.upload(on_upload=on_photo_upload, auto_upload=True, max_files=1).props(
                    'accept="image/*"'
                ).classes("flex-1")
                ui.upload(on_upload=on_audio_upload, auto_upload=True, max_files=1).props(
                    'accept="audio/*"'
                ).classes("flex-1")

            def submit():
                if not body_input.value and not pending_attachments:
                    error_label.text = "Agregá un comentario o al menos un adjunto."
                    return
                try:
                    if body_input.value:
                        client.table("maintenance_comments").insert(
                            {"record_id": record["id"], "body": body_input.value}
                        ).execute()
                    for item in pending_attachments:
                        ext = "jpg" if item["kind"] == "photo" else "webm"
                        path = f"{tag_id}/{record['id']}/{_random_suffix()}.{ext}"
                        client.storage.from_("maintenance-attachments").upload(
                            path, item["data"]
                        )
                        client.table("maintenance_attachments").insert(
                            {
                                "record_id": record["id"],
                                "kind": item["kind"],
                                "storage_path": path,
                            }
                        ).execute()
                except Exception as e:
                    error_label.text = f"No se pudo guardar: {e}"
                    return
                ui.notify("Guardado", type="positive")
                dialog.close()
                render_records(records_container, tag_id)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Guardar", on_click=submit).props("color=primary")

        dialog.open()
```

- [ ] **Step 4: Verificación manual**

Como `tecnico@test.local`: en un evento propio, "+ Comentario/adjunto" funciona; los botones "Editar"/"Borrar" **no aparecen**. En un evento ajeno, ni siquiera aparece "+ Comentario/adjunto". Cerrá sesión, entrá como `oficina@test.local`: en cualquier evento aparecen los 3 botones. Editá un registro, confirmá que el cambio se refleja al recargar la lista. Borrá un registro, confirmá que desaparece de la lista. Desde Supabase Studio → Table Editor → `maintenance_audit_log`, confirmá que la edición y el borrado quedaron registrados con `changed_by` = el uid de oficina.

- [ ] **Step 5: Commit**

```bash
git add gui_maintenance.py
git commit -m "feat: editar/borrar (oficina) + comentario/adjunto en gui.py"
```

---

### Task 5: Manejo de errores de conexión + checklist final + documentación

**Files:**
- Modify: `gui_maintenance.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Sesión expirada al guardar (re-login sin perder el diálogo abierto)**

En `gui_maintenance.py`, en cada `except Exception as e:` de los `submit()`/`do_delete()` (Tasks 3 y 4), el mensaje de error genérico ya cubre el caso de sesión expirada — `supabase-py` no reintenta el request automáticamente, así que el usuario ve el error tal cual lo devuelve Supabase (típicamente algo con "JWT" en el mensaje) y puede cerrar el diálogo, tocar "Cerrar sesión" arriba y volver a entrar. A diferencia del sitio (Plan 2, que sí implementa un modal de re-login automático porque el técnico en el celular no tiene otra forma cómoda de volver a loguearse sin perder el formulario), acá **no** se justifica la misma complejidad: es una app de escritorio de oficina donde perder un formulario y volver a completarlo no es una fricción real. Este paso es solo para dejar esa decisión explícita — no hay código nuevo que escribir.

- [ ] **Step 2: Checklist manual final**

- [ ] Con Supabase local apagado (`supabase stop`), abrir `/mantenimientos`: el login muestra un error claro (no un crash de NiceGUI).
- [ ] Con Supabase corriendo pero `site_config.json` sin bloque `supabase`, `/mantenimientos` muestra el aviso de configuración faltante en vez de un traceback.
- [ ] Subir una foto grande (>5MB) confirma que el archivo resultante en Storage es sensiblemente más chico (Pillow la comprimió).
- [ ] El botón "🧰 Mantenimientos" de la página principal de `gui.py` sigue funcionando después de generar un sitio (no hay interferencia entre el pipeline de generación y esta pantalla nueva, son independientes).

- [ ] **Step 3: Documentar en `CLAUDE.md`**

Agregar en la tabla "Estado de archivos":
```markdown
| [gui_maintenance.py](gui_maintenance.py) | ✅ Pantalla "Mantenimientos" en gui.py (Plan 3) — login, alta/edición/borrado según rol |
```

Y agregar al final de la sección "Histórico de mantenimientos (Supabase)" (creada en el Plan 2):
```markdown
- La pantalla de oficina vive en `gui_maintenance.py`, registrada como `/mantenimientos` e importada desde `gui.py`. Usa las mismas cuentas y el mismo schema/RLS que el sitio — un técnico logueado ahí ve exactamente los mismos permisos que en el celular (RLS es la única fuente de verdad, no hay lógica de rol duplicada del lado del cliente más allá de qué botones mostrar).
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: documentar pantalla de mantenimientos en gui.py"
```

Con esto los 3 planes del feature "Histórico de mantenimientos" quedan completos: Plan 1 (schema/RLS/Storage), Plan 2 (sitio), Plan 3 (`gui.py`). Los Planes 2 y 3 son independientes entre sí y pueden ejecutarse en paralelo una vez aplicado el Plan 1.
