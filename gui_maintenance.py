#!/usr/bin/env python3
"""
gui_maintenance.py
===================
Pantalla NiceGUI "Mantenimientos" — historial de mantenimientos por TAG
vía Supabase (mismo schema/RLS que el Plan 1 de este feature).

Se abre como diálogo maximizado desde el botón "🧰 Mantenimientos" de gui.py
(open_maintenance_dialog). No es una @ui.page: NiceGUI 3.x no permite páginas
adicionales cuando la UI principal de gui.py está definida en el scope global.
No tiene entrypoint propio — corre dentro del proceso de gui.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import uuid
from datetime import date
from pathlib import Path

from nicegui import ui
from PIL import Image, ImageOps
from supabase import create_client, Client

from generate_tag_resources_template import read_tags_from_plantilla

REPO_ROOT = Path(__file__).parent
SITE_CONFIG = REPO_ROOT / "site_config.json"

MAX_ATTACHMENTS = 5
BUCKET = "maintenance-attachments"
MAX_FILE_BYTES = 10 * 1024 * 1024  # mismo tope que el bucket (migración de endurecimiento)
# Audios que acepta el bucket; el sitio (maintenance.js) graba webm/mp4/ogg.
AUDIO_MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/x-m4a",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


def load_supabase_config() -> dict:
    """Conexión a Supabase: variables de entorno (desarrollo local) y, si no,
    el bloque `supabase` de site_config.json (mismo que usa el sitio)."""
    env_url = os.environ.get("SUPABASE_URL", "").strip()
    env_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if env_url and env_key:
        return {"url": env_url, "anon_key": env_key}
    if not SITE_CONFIG.exists():
        return {"url": "", "anon_key": ""}
    cfg = json.loads(SITE_CONFIG.read_text(encoding="utf-8"))
    return cfg.get("supabase", {"url": "", "anon_key": ""})


def list_tags_from_plantilla() -> list[str]:
    try:
        return read_tags_from_plantilla()
    except FileNotFoundError:
        return []


def friendly_error(e: Exception) -> str:
    """Traduce los errores típicos de Supabase a mensajes accionables."""
    text = str(e)
    low = text.lower()
    if "jwt" in low:
        return "Tu sesión expiró. Cerrá sesión y volvé a entrar."
    if "row-level security" in low or "permission denied" in low:
        return "No tenés permiso para esta acción."
    return text


def compress_image_bytes(raw_bytes: bytes) -> bytes:
    """Redimensiona a max 1600px de ancho y recodifica a JPEG calidad 70 (mismo
    criterio que la compresión client-side del sitio, Plan 2)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw_bytes))).convert("RGB")
    max_width = 1600
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _today_iso() -> str:
    return date.today().isoformat()


class AttachmentsPicker:
    """Selector de adjuntos (fotos + audios desde archivo) para usar dentro de un diálogo.
    `reserved` = adjuntos que el registro ya tiene (el tope de 5 es por registro)."""

    def __init__(self, reserved: int = 0):
        self.reserved = reserved
        self.pending: list[dict] = []  # [{kind, data, mime, ext, name}]
        self.summary = ui.label().classes("text-sm text-gray-600")
        self.chips = ui.row().classes("gap-2 flex-wrap")
        with ui.row().classes("w-full gap-4"):
            self.photo_upload = ui.upload(
                label="📷 Agregar foto", on_upload=self._on_photo, auto_upload=True
            ).props('accept="image/*"').classes("flex-1")
            self.audio_upload = ui.upload(
                label="🎙️ Agregar audio", on_upload=self._on_audio, auto_upload=True
            ).props('accept="audio/*"').classes("flex-1")
        self._refresh()

    def _full(self) -> bool:
        return self.reserved + len(self.pending) >= MAX_ATTACHMENTS

    def _refresh(self):
        self.summary.text = f"Adjuntos: {self.reserved + len(self.pending)}/{MAX_ATTACHMENTS}"
        self.chips.clear()
        with self.chips:
            for item in list(self.pending):
                with ui.row().classes("items-center gap-1 bg-gray-100 rounded px-2"):
                    icon = "📷" if item["kind"] == "photo" else "🎙️"
                    ui.label(f"{icon} {item['name']}").classes("text-xs")
                    ui.button(icon="close", on_click=lambda i=item: self._remove(i)).props(
                        "flat dense round size=xs"
                    )

    def _remove(self, item: dict):
        if item in self.pending:
            self.pending.remove(item)
        self._refresh()

    async def _on_photo(self, e):
        try:
            if self._full():
                ui.notify(f"Ya llegaste al máximo de {MAX_ATTACHMENTS} adjuntos", type="warning")
                return
            raw = await e.file.read()
            # En un hilo: decodificar/recomprimir una foto grande no debe congelar la GUI.
            data = await asyncio.to_thread(compress_image_bytes, raw)
            self.pending.append(
                {"kind": "photo", "data": data, "mime": "image/jpeg", "ext": "jpg", "name": e.file.name}
            )
            self._refresh()
        except Exception as ex:
            ui.notify(f"No se pudo procesar la foto: {ex}", type="negative")
        finally:
            self.photo_upload.reset()

    async def _on_audio(self, e):
        try:
            if self._full():
                ui.notify(f"Ya llegaste al máximo de {MAX_ATTACHMENTS} adjuntos", type="warning")
                return
            ext = Path(e.file.name).suffix.lower()
            if ext not in AUDIO_MIME:
                ui.notify(
                    f"Formato de audio no soportado ({', '.join(AUDIO_MIME)})", type="negative"
                )
                return
            raw = await e.file.read()
            if len(raw) > MAX_FILE_BYTES:
                ui.notify("El audio supera el máximo de 10 MB", type="negative")
                return
            self.pending.append(
                {"kind": "audio", "data": raw, "mime": AUDIO_MIME[ext], "ext": ext[1:], "name": e.file.name}
            )
            self._refresh()
        finally:
            self.audio_upload.reset()


def upload_attachments(client: Client, tag_id: str, record_id: str, items: list[dict]) -> list[str]:
    """Sube los adjuntos uno por uno. Devuelve la lista de errores (vacía = todo bien);
    los que subieron bien quedan asociados al registro aunque otros fallen."""
    storage = client.storage.from_(BUCKET)
    errors: list[str] = []
    for item in items:
        path = f"{tag_id}/{record_id}/{uuid.uuid4().hex}.{item['ext']}"
        try:
            storage.upload(path, item["data"], {"content-type": item["mime"]})
        except Exception as e:
            errors.append(f"{item['name']}: {friendly_error(e)}")
            continue
        try:
            client.table("maintenance_attachments").insert(
                {"record_id": record_id, "kind": item["kind"], "storage_path": path}
            ).execute()
        except Exception as e:
            try:  # el archivo subió pero su fila no: se limpia para no dejar huérfanos
                storage.remove([path])
            except Exception:
                pass
            errors.append(f"{item['name']}: {friendly_error(e)}")
    return errors


def open_maintenance_dialog():
    """Abre la pantalla como diálogo maximizado. Cada apertura arranca sin sesión."""
    with ui.dialog().props("maximized") as dialog, ui.card().classes(
        "w-full h-full overflow-auto"
    ):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("🧰 Mantenimientos").classes("text-3xl font-bold")
            ui.button("Cerrar", on_click=dialog.close).props("flat")
        content = ui.column().classes("max-w-4xl mx-auto p-2 gap-4 w-full")
    dialog.on("hide", dialog.delete)  # descarta el estado (y la sesión) al cerrar
    build_maintenance_screen(content)
    dialog.open()


def build_maintenance_screen(content):
    supa_cfg = load_supabase_config()
    if not supa_cfg.get("url") or not supa_cfg.get("anon_key"):
        with content:
            ui.label(
                '⚠️ Falta configurar Supabase en site_config.json (bloque "supabase").'
            ).classes("text-red-600")
        return

    try:
        client: Client = create_client(supa_cfg["url"], supa_cfg["anon_key"])
    except Exception as e:
        with content:
            ui.label(f"No se pudo inicializar Supabase: {e}").classes("text-red-600")
        return
    session_state: dict = {"user": None, "role": None}

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
                    error_label.text = ""
                    try:
                        result = client.auth.sign_in_with_password(
                            {"email": email_input.value, "password": password_input.value}
                        )
                    except Exception as e:
                        error_label.text = f"No se pudo iniciar sesión: {friendly_error(e)}"
                        return
                    session_state["user"] = result.user
                    load_profile_and_render()

                password_input.on("keydown.enter", do_login)
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
                ui.label(f"No se pudo cargar el perfil: {friendly_error(e)}").classes(
                    "text-red-600"
                )
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
        try:
            client.auth.sign_out()
        except Exception:
            pass  # sin red: igual se descarta la sesión local
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

            tags = list_tags_from_plantilla()
            if not tags:
                ui.label(
                    "No hay TAGs: falta plantilla_sitio.xlsx o está vacía."
                ).classes("text-amber-700 text-sm")
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
                    ui.label(
                        f"No se pudo cargar el historial: {friendly_error(e)}"
                    ).classes("text-red-600")
                    ui.button(
                        "Reintentar", on_click=lambda: render_records(container, tag_id)
                    ).props("flat dense")
            return

        container.clear()
        with container:
            ui.button(
                "+ Registrar mantenimiento",
                on_click=lambda: open_new_record_dialog(tag_id, container),
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
                comments = sorted(
                    record.get("maintenance_comments", []), key=lambda c: c["created_at"]
                )
                for comment in comments:
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
                with ui.row().classes("gap-2 mt-2"):
                    is_owner = record["created_by"] == session_state["user"].id
                    is_oficina = session_state["role"] == "oficina"
                    if is_owner or is_oficina:
                        ui.button(
                            "+ Comentario/adjunto",
                            on_click=lambda r=record: open_add_comment_dialog(r, tag_id, container),
                        ).props("flat dense")
                    if is_oficina:
                        ui.button(
                            "Editar",
                            on_click=lambda r=record: open_edit_dialog(r, tag_id, container),
                        ).props("flat dense")
                        ui.button(
                            "Borrar",
                            on_click=lambda r=record: confirm_delete(r, tag_id, container),
                        ).props("flat dense color=red")


    def _finish(dialog, container, tag_id: str, errors: list[str], ok_msg: str):
        """Cierra el diálogo y recarga la lista. Si algún adjunto falló NO se deja reintentar
        desde el mismo diálogo (re-subiría los que sí subieron o duplicaría el registro)."""
        dialog.close()
        if errors:
            ui.notify(
                f"{ok_msg}, pero {len(errors)} adjunto(s) no se pudieron subir: "
                + "; ".join(errors)
                + ". Podés agregarlos después con \"+ Comentario/adjunto\".",
                type="warning",
                multi_line=True,
                close_button=True,
                timeout=0,
            )
        else:
            ui.notify(ok_msg, type="positive")
        render_records(container, tag_id)

    def open_new_record_dialog(tag_id: str, records_container):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label(f"Registrar mantenimiento — {tag_id}").classes("text-lg font-semibold")

            performed_at_input = ui.input("Fecha del mantenimiento", value=_today_iso()).props(
                "outlined dense type=date"
            ).classes("w-full")
            type_select = ui.select(
                {"preventivo": "Preventivo", "correctivo": "Correctivo"}, value="preventivo"
            ).props("outlined dense").classes("w-full")
            description_input = ui.textarea("Descripción").props("outlined dense").classes("w-full")
            parts_input = ui.textarea("Repuestos / insumos (opcional)").props(
                "outlined dense"
            ).classes("w-full")
            next_input = ui.input("Próximo programado (opcional)").props(
                "outlined dense type=date"
            ).classes("w-full")

            picker = AttachmentsPicker()
            error_label = ui.label("").classes("text-red-600 text-sm")

            def submit():
                error_label.text = ""
                if (
                    not performed_at_input.value
                    or not type_select.value
                    or not (description_input.value or "").strip()
                ):
                    error_label.text = "Completá fecha, tipo y descripción."
                    return
                save_btn.disable()
                payload = {
                    "tag_id": tag_id,
                    "performed_at": performed_at_input.value,
                    "type": type_select.value,
                    "description": description_input.value.strip(),
                    "parts_used": parts_input.value or None,
                    "next_scheduled_at": next_input.value or None,
                }
                try:
                    result = client.table("maintenance_records").insert(payload).execute()
                    record_id = result.data[0]["id"]
                except Exception as e:
                    error_label.text = f"No se pudo guardar: {friendly_error(e)}"
                    save_btn.enable()
                    return
                errors = upload_attachments(client, tag_id, record_id, picker.pending)
                _finish(dialog, records_container, tag_id, errors, "Registro guardado")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                save_btn = ui.button("Guardar", on_click=submit).props("color=primary")

        dialog.open()

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
                error_label.text = ""
                if not (description_input.value or "").strip():
                    error_label.text = "La descripción no puede quedar vacía."
                    return
                try:
                    result = (
                        client.table("maintenance_records")
                        .update(
                            {
                                "description": description_input.value.strip(),
                                "parts_used": parts_input.value or None,
                                "next_scheduled_at": next_input.value or None,
                            }
                        )
                        .eq("id", record["id"])
                        .execute()
                    )
                    if not result.data:  # RLS no dejó tocar ninguna fila
                        raise PermissionError("No tenés permiso para esta acción.")
                except Exception as e:
                    error_label.text = f"No se pudo editar: {friendly_error(e)}"
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
                        result = (
                            client.table("maintenance_records")
                            .delete()
                            .eq("id", record["id"])
                            .execute()
                        )
                        if not result.data:  # RLS no dejó borrar ninguna fila
                            raise PermissionError("No tenés permiso para esta acción.")
                    except Exception as e:
                        ui.notify(f"No se pudo borrar: {friendly_error(e)}", type="negative")
                        return
                    dialog.close()
                    ui.notify("Registro borrado", type="positive")
                    render_records(records_container, tag_id)

                ui.button("Borrar", on_click=do_delete).props("color=red")
        dialog.open()

    def open_add_comment_dialog(record: dict, tag_id: str, records_container):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label("Agregar comentario/adjunto").classes("text-lg font-semibold")
            body_input = ui.textarea("Comentario").props("outlined dense").classes("w-full")
            picker = AttachmentsPicker(reserved=len(record.get("maintenance_attachments", [])))
            error_label = ui.label("").classes("text-red-600 text-sm")

            def submit():
                error_label.text = ""
                body = (body_input.value or "").strip()
                if not body and not picker.pending:
                    error_label.text = "Agregá un comentario o al menos un adjunto."
                    return
                save_btn.disable()
                if body:
                    try:
                        client.table("maintenance_comments").insert(
                            {"record_id": record["id"], "body": body}
                        ).execute()
                    except Exception as e:
                        error_label.text = f"No se pudo guardar: {friendly_error(e)}"
                        save_btn.enable()
                        return
                errors = upload_attachments(client, tag_id, record["id"], picker.pending)
                _finish(dialog, records_container, tag_id, errors, "Guardado")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                save_btn = ui.button("Guardar", on_click=submit).props("color=primary")

        dialog.open()

    render_login()
