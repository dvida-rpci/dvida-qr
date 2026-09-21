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

import json
import os
from pathlib import Path

from nicegui import ui
from supabase import create_client, Client

from generate_tag_resources_template import read_tags_from_plantilla

REPO_ROOT = Path(__file__).parent
SITE_CONFIG = REPO_ROOT / "site_config.json"

MAX_ATTACHMENTS = 5


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

    render_login()
