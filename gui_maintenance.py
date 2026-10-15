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
HISTORY_PAGE = 10  # historial de a 10 ("Cargar más"): con miles de registros no se baja todo
OPEN_ITEMS = 3     # del 4.º en adelante los registros van plegados (chevron)
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


def render_login_card(container, client: Client, on_user):
    """Formulario de login (compartido con gui_plan.py). Llama on_user(user) al entrar."""
    container.clear()
    with container:
        with ui.card().classes("w-full max-w-sm"):
            ui.label("Iniciar sesión").classes("font-semibold")
            email_input = ui.input("Email").props("outlined dense").classes("w-full")
            password_input = (
                ui.input("Contraseña", password=True).props("outlined dense").classes("w-full")
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
                on_user(result.user)

            password_input.on("keydown.enter", do_login)
            ui.button("Ingresar", on_click=do_login).props("color=primary")


def fetch_tag_activities(client: Client, tag_id: str) -> list[dict]:
    """Actividades activas de la sábana para la clase del TAG ([] si no tiene clase)."""
    tag = client.table("equipment_tags").select("class_id").eq("tag_id", tag_id).execute().data
    if not tag or not tag[0]["class_id"]:
        return []
    return (
        client.table("maintenance_activities")
        .select("id, name, interval_hours, interval_weeks")
        .eq("class_id", tag[0]["class_id"])
        .eq("active", True)
        .order("name")
        .execute()
        .data
    )


SOURCE_LABEL = {"automatico": "automático, según sábana", "manual": "manual", "registro": "próximo de un registro"}


def format_date(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def conflict_text(tag_id: str, c: dict) -> str:
    """Una línea de la advertencia de sobrescritura (markdown)."""
    when = f"**{format_date(c['due_date'])}**"
    if c.get("status") == "vencido" and c.get("days_overdue") is not None:
        return (f"⚠️ **{tag_id} — {c['activity_name']}** estaba programado para el {when} "
                f"y está **vencido hace {c['days_overdue']} días** "
                f"({SOURCE_LABEL.get(c['source'], c['source'])}).")
    return (f"⚠️ **{tag_id} — {c['activity_name']}** ya está programado para el {when} "
            f"({SOURCE_LABEL.get(c['source'], c['source'])}).")


async def confirm_overwrite(tag_id: str, conflicts: list[dict], new_date: str,
                            ask_reason: bool = False, reason: str = ""):
    """Advertencia del spec. Sin `ask_reason` devuelve bool. Con `ask_reason` devuelve el
    motivo (str) o None si se cancela; el motivo es obligatorio si algo está vencido."""
    overdue = any(c.get("status") == "vencido" for c in conflicts)
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        for c in conflicts:
            ui.markdown(conflict_text(tag_id, c))
        ui.markdown(f"¿{'Reprogramar' if overdue else 'Sobrescribir'} para el **{format_date(new_date)}**?")
        reason_input = None
        if ask_reason:
            label = "Motivo (obligatorio: está vencido)" if overdue else "Motivo (opcional)"
            reason_input = ui.input(label, value=reason or "").props("outlined dense").classes("w-full")
        error = ui.label("").classes("text-red-600 text-sm")

        def accept():
            if reason_input is not None and overdue and not (reason_input.value or "").strip():
                error.text = "Escribí el motivo de la reprogramación."
                return
            dialog.submit((reason_input.value or "").strip() if reason_input is not None else True)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Reprogramar" if overdue else "Sobrescribir", on_click=accept).props("color=orange")
    result = await dialog
    dialog.delete()
    if ask_reason:
        return result if isinstance(result, str) else None
    return bool(result)


def activity_checkboxes(activities: list[dict], checked: set[str] = frozenset()) -> dict:
    """Casillas de actividades de la sábana; devuelve {activity_id: checkbox}."""
    boxes = {}
    if activities:
        ui.label("Actividades de la sábana").classes("text-sm font-semibold mt-1")
        for a in activities:
            freq = " / ".join(
                part for part in (
                    f"{a['interval_hours']:g} h" if a.get("interval_hours") else "",
                    f"{a['interval_weeks']} sem" if a.get("interval_weeks") else "",
                ) if part
            )
            boxes[a["id"]] = ui.checkbox(f"{a['name']} (cada {freq})", value=a["id"] in checked)
    return boxes


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
        def on_user(user):
            session_state["user"] = user
            load_profile_and_render()

        render_login_card(content, client, on_user)

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

    def fetch_records_page(tag_id: str, offset: int):
        """Una página del historial (más recientes primero) + el total real."""
        result = (
            client.table("maintenance_records")
            .select(
                "*, maintenance_comments(*), maintenance_attachments(*), "
                "maintenance_record_activities(activity_id, maintenance_activities(name))",
                count="exact",
            )
            .eq("tag_id", tag_id)
            .order("performed_at", desc=True)
            .order("created_at", desc=True)
            .range(offset, offset + HISTORY_PAGE - 1)
            .execute()
        )
        return result.data, (result.count if result.count is not None else len(result.data))

    def render_records(container, tag_id: str):
        container.clear()
        with container:
            ui.label("Cargando…").classes("text-gray-500")
        try:
            rows, total = fetch_records_page(tag_id, 0)
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
            if not rows:
                ui.label("Todavía no hay mantenimientos registrados para este TAG.").classes(
                    "text-gray-500"
                )
            ui.label(f"{total} mantenimientos registrados").classes("text-sm text-gray-500")
            listing = ui.column().classes("w-full gap-3")
            more_row = ui.row().classes("w-full")
        shown = {"n": 0, "total": total}

        def append(page_rows):
            for record in page_rows:
                render_record_card(listing, record, tag_id, container, shown["n"] < OPEN_ITEMS)
                shown["n"] += 1
            more_row.clear()
            if shown["n"] < shown["total"]:
                with more_row:
                    ui.button(f"Cargar más ({shown['total'] - shown['n']} restantes)",
                              on_click=load_more).props("outline").classes("w-full")

        def load_more():
            try:
                page_rows, shown["total"] = fetch_records_page(tag_id, shown["n"])
            except Exception as e:
                ui.notify(f"No se pudo cargar: {friendly_error(e)}", type="negative")
                return
            append(page_rows)

        append(rows)

    def render_record_card(listing, record: dict, tag_id: str, container, open_: bool = True):
        """Tarjeta de un registro. Del 4.º en adelante va plegada (chevron) con lo esencial
        en el encabezado; detalle y botones al abrir."""
        done = [
            link["maintenance_activities"]["name"]
            for link in record.get("maintenance_record_activities", [])
            if link.get("maintenance_activities")
        ]
        essential = ("✅ " + " · ".join(done)) if done else record["description"]
        with listing:
            if open_:
                card = ui.card().classes("w-full")
                with card, ui.row().classes("items-center gap-2"):
                    ui.label(record["performed_at"]).classes("font-bold")
                    ui.label(record["type"]).classes(
                        "text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600"
                    )
                    if record.get("is_date_anomaly"):
                        ui.label("⚠️ revisar fecha").classes("text-red-600 text-xs font-semibold")
                body = card
            else:
                title = f"{record['performed_at']} · {record['type']} — {essential[:70]}"
                body = ui.expansion(title).classes("w-full border rounded")
        with body:
            ui.label(record["description"])
            if done:
                ui.label("✅ " + " · ".join(done)).classes("text-sm text-green-700")
            if record.get("hmi_hours") is not None:
                ui.label(f"Horas HMI: {record['hmi_hours']:g} h").classes("text-sm text-gray-600")
            if record.get("parts_used"):
                ui.label(f"Repuestos: {record['parts_used']}").classes("text-sm text-gray-600")
            if record.get("next_scheduled_at"):
                ui.label(f"Próximo programado: {record['next_scheduled_at']}").classes(
                    "text-sm text-gray-600"
                )
            for comment in sorted(record.get("maintenance_comments", []), key=lambda c: c["created_at"]):
                ui.label(comment["body"]).classes("text-sm bg-gray-50 rounded px-2 py-1 mt-1")
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
        try:
            activities = fetch_tag_activities(client, tag_id)
        except Exception as e:
            ui.notify(f"No se pudo leer la sábana: {friendly_error(e)}", type="negative")
            activities = []
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label(f"Registrar mantenimiento — {tag_id}").classes("text-lg font-semibold")

            performed_at_input = ui.input("Fecha del mantenimiento", value=_today_iso()).props(
                "outlined dense type=date"
            ).classes("w-full")
            hmi_input = ui.number("Horas HMI (opcional)", min=0, format="%.0f").props(
                "outlined dense"
            ).classes("w-full")
            type_select = ui.select(
                {"preventivo": "Preventivo", "correctivo": "Correctivo"}, value="preventivo"
            ).props("outlined dense").classes("w-full")
            boxes = activity_checkboxes(activities)
            description_input = ui.textarea("Descripción").props("outlined dense").classes("w-full")
            parts_input = ui.textarea("Repuestos / insumos (opcional)").props(
                "outlined dense"
            ).classes("w-full")
            next_input = ui.input("Próximo programado (opcional)").props(
                "outlined dense type=date"
            ).classes("w-full")

            def selected_activities() -> list[str]:
                return [aid for aid, box in boxes.items() if box.value]

            def sync_next_visibility():
                # Con actividades de la sábana el próximo lo calcula el sistema.
                next_input.set_visibility(not selected_activities())

            for box in boxes.values():
                box.on_value_change(lambda _: sync_next_visibility())

            picker = AttachmentsPicker()
            error_label = ui.label("").classes("text-red-600 text-sm")

            async def submit():
                error_label.text = ""
                if (
                    not performed_at_input.value
                    or not type_select.value
                    or not (description_input.value or "").strip()
                ):
                    error_label.text = "Completá fecha, tipo y descripción."
                    return
                activity_ids = selected_activities()
                next_date = None if activity_ids else (next_input.value or None)
                replaced_manual = []
                if next_date:
                    try:
                        conflicts = (
                            client.table("maintenance_agenda").select("*")
                            .eq("tag_id", tag_id).is_("activity_id", "null")
                            .not_.is_("due_date", "null").execute().data
                        )
                    except Exception as e:
                        error_label.text = f"No se pudo revisar la agenda: {friendly_error(e)}"
                        return
                    if conflicts:
                        if not await confirm_overwrite(tag_id, conflicts, next_date):
                            return
                        replaced_manual = [c["manual_id"] for c in conflicts if c["manual_id"]]
                save_btn.disable()
                payload = {
                    "tag_id": tag_id,
                    "performed_at": performed_at_input.value,
                    "type": type_select.value,
                    "description": description_input.value.strip(),
                    "parts_used": parts_input.value or None,
                    "next_scheduled_at": next_date,
                    "hmi_hours": hmi_input.value,
                }
                try:
                    record_id = client.rpc(
                        "create_maintenance_record",
                        {"p_record": payload, "p_activity_ids": activity_ids},
                    ).execute().data
                except Exception as e:
                    error_label.text = f"No se pudo guardar: {friendly_error(e)}"
                    save_btn.enable()
                    return
                if replaced_manual and session_state["role"] == "oficina":
                    # El "próximo" nuevo sobrescribe la programación manual libre.
                    client.table("maintenance_manual_schedule").update(
                        {"status": "reemplazado"}
                    ).in_("id", replaced_manual).execute()
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
            hmi_input = ui.number(
                "Horas HMI", value=record.get("hmi_hours"), min=0, format="%.0f"
            ).props("outlined dense").classes("w-full")
            current = {link["activity_id"] for link in record.get("maintenance_record_activities", [])}
            try:
                boxes = activity_checkboxes(fetch_tag_activities(client, tag_id), current)
            except Exception:
                boxes = {}
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
                                "hmi_hours": hmi_input.value,
                            }
                        )
                        .eq("id", record["id"])
                        .execute()
                    )
                    if not result.data:  # RLS no dejó tocar ninguna fila
                        raise PermissionError("No tenés permiso para esta acción.")
                    wanted = {aid for aid, box in boxes.items() if box.value}
                    if boxes and wanted != current:
                        links = client.table("maintenance_record_activities")
                        links.delete().eq("record_id", record["id"]).execute()
                        if wanted:
                            links.insert(
                                [{"record_id": record["id"], "activity_id": a} for a in wanted]
                            ).execute()
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
