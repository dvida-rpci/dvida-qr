#!/usr/bin/env python3
"""
gui_plan.py
===========
Ventana NiceGUI "📋 Plan de mantenimiento" (fase 2 del diseño
docs/superpowers/specs/2026-10-14-plan-mantenimiento-design.md).

Pestañas: Sábana (clases/actividades/frecuencias, importar/exportar biblioteca),
Equipos (TAG → clase y régimen de pares) y Programación (agenda con filtro
"Esta semana" y programación manual con advertencia de duplicados).

Se abre como diálogo maximizado desde gui.py (no es una @ui.page, ver gui_maintenance.py).
Escribir requiere rol oficina; RLS es la fuente de verdad.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlparse

from nicegui import ui
from supabase import Client, create_client

import maintenance_plan as mp
from gui_maintenance import (
    REPO_ROOT,
    SOURCE_LABEL,
    confirm_overwrite,
    fetch_tag_activities,
    format_date,
    friendly_error,
    load_supabase_config,
    render_login_card,
)

LIBRARY = REPO_ROOT / "sabana_base.xlsx"
PLANTILLA = REPO_ROOT / "plantilla_sitio.xlsx"
REGIME_LABEL = {"normal": "Normal", "alterna": "Alternan", "principal": "Principal", "reserva": "Reserva"}
STATUS_LABEL = {
    "vencido": "🔴 Vencido",
    "sin_registro": "⚪ Sin registro",
    "proximo": "🟠 Próximo",
    "al_dia": "🟢 Al día",
    "sin_fecha": "— Sin fecha",
}
NO_CLASS = ""  # NiceGUI no maneja bien None como clave de opciones
LIBRE = ""


def open_plan_dialog():
    """Abre la ventana como diálogo maximizado. Cada apertura arranca sin sesión."""
    with ui.dialog().props("maximized") as dialog, ui.card().classes("w-full h-full overflow-auto"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("📋 Plan de mantenimiento").classes("text-3xl font-bold")
            ui.button("Cerrar", on_click=dialog.close).props("flat")
        content = ui.column().classes("max-w-6xl mx-auto p-2 gap-4 w-full")
    dialog.on("hide", dialog.delete)
    build_plan_screen(content)
    dialog.open()


def _plantilla_rows() -> list[dict]:
    try:
        return sorted(mp.load_plantilla_tags(PLANTILLA), key=lambda r: r["TAG"])
    except FileNotFoundError:
        return []


def build_plan_screen(content):
    cfg = load_supabase_config()
    if not cfg.get("url") or not cfg.get("anon_key"):
        with content:
            ui.label('⚠️ Falta configurar Supabase en site_config.json (bloque "supabase").').classes(
                "text-red-600"
            )
        return
    client: Client = create_client(cfg["url"], cfg["anon_key"])
    project_ref = (urlparse(cfg["url"]).hostname or "local").split(".")[0]

    def on_user(user):
        try:
            profile = client.table("profiles").select("role").eq("user_id", user.id).execute().data
        except Exception as e:
            ui.notify(f"No se pudo cargar el perfil: {friendly_error(e)}", type="negative")
            return
        content.clear()
        with content:
            with ui.row().classes("w-full items-center justify-between"):
                role = profile[0]["role"] if profile else "sin perfil"
                ui.label(f"Sesión: {user.email} ({role})").classes("text-sm text-gray-600")
                ui.button("Cerrar sesión", on_click=logout).props("flat dense")
            if role != "oficina":
                ui.label("Esta ventana requiere rol oficina.").classes("text-red-600")
                return
            render_main()

    def logout():
        try:
            client.auth.sign_out()
        except Exception:
            pass  # sin red: igual se descarta la sesión local
        render_login_card(content, client, on_user)

    def update_row(table: str, key: str, key_value, values: dict, ok: str = "Guardado") -> bool:
        try:
            if not client.table(table).update(values).eq(key, key_value).execute().data:
                raise PermissionError("No tenés permiso para esta acción.")
        except Exception as e:
            ui.notify(f"No se pudo guardar: {friendly_error(e)}", type="negative")
            return False
        ui.notify(ok, type="positive")
        return True

    def error_with_retry(panel, message: str, retry):
        panel.clear()
        with panel, ui.row().classes("items-center gap-2"):
            ui.label(message).classes("text-red-600")
            ui.button("Reintentar", on_click=retry).props("flat dense")

    def render_main():
        with content:
            with ui.tabs().props("dense no-caps").classes("w-full") as tabs:
                tab_prog = ui.tab("📅 Agenda").classes("px-2")
                tab_sabana = ui.tab("📋 Sábana").classes("px-2")
                tab_equipos = ui.tab("⚙️ Equipos").classes("px-2")
            with ui.tab_panels(tabs, value=tab_prog).classes("w-full"):
                with ui.tab_panel(tab_prog):
                    prog_panel = ui.column().classes("w-full gap-2")
                with ui.tab_panel(tab_sabana):
                    sabana_panel = ui.column().classes("w-full gap-3")
                with ui.tab_panel(tab_equipos):
                    equipos_panel = ui.column().classes("w-full gap-1")
        # Cada pestaña se recarga al entrar: lo que se cambia en una (ej. importar la
        # sábana) tiene que verse en las otras.
        renderers = {
            tab_prog: lambda: render_programacion(prog_panel),
            tab_sabana: lambda: render_sabana(sabana_panel),
            tab_equipos: lambda: render_equipos(equipos_panel),
        }
        by_name = {tab._props["name"]: fn for tab, fn in renderers.items()}
        tabs.on_value_change(lambda e: (renderers.get(e.value) or by_name[e.value])())
        renderers[tab_prog]()

    # ── Sábana ────────────────────────────────────────────────────────────

    def render_sabana(panel):
        panel.clear()
        try:
            classes = client.table("equipment_classes").select("*").order("name").execute().data
            acts = client.table("maintenance_activities").select("*").order("name").execute().data
        except Exception as e:
            error_with_retry(panel, f"No se pudo leer la sábana: {friendly_error(e)}",
                             lambda: render_sabana(panel))
            return
        with panel:
            with ui.row().classes("gap-2"):
                ui.button("📥 Importar sábana base", on_click=lambda: import_library(panel))
                ui.button("📤 Exportar a biblioteca",
                          on_click=lambda: export_library(classes, acts)).props("outline")
                ui.button("+ Clase", on_click=lambda: new_class_dialog(panel)).props("outline")
            if not classes:
                ui.label("Esta planta todavía no tiene sábana: importá la base.").classes("text-gray-500")
            for c in classes:
                with ui.card().classes("w-full"):
                    with ui.row().classes("items-end gap-2 w-full"):
                        name = ui.input("Clase", value=c["name"]).props("outlined dense").classes("w-full sm:w-auto sm:grow")
                        hpd = ui.number("Horas/día estimadas", value=c["hours_per_day"], min=0.1,
                                        max=24).props("outlined dense").classes("w-44")
                        ui.label(c["code"]).classes("text-xs text-gray-500")
                        ui.button("Guardar", on_click=lambda c=c, name=name, hpd=hpd: save_class(
                            c["id"], name.value, hpd.value)).props("flat dense")
                    for a in (a for a in acts if a["class_id"] == c["id"]):
                        with ui.row().classes("items-end gap-2 w-full"):
                            an = ui.input("Actividad", value=a["name"]).props("outlined dense").classes("w-full sm:w-auto sm:grow")
                            ah = ui.number("Cada (h)", value=a["interval_hours"], min=1).props(
                                "outlined dense").classes("w-28")
                            aw = ui.number("Cada (sem)", value=a["interval_weeks"], min=1,
                                           format="%.0f").props("outlined dense").classes("w-28")
                            active = ui.switch("Activa", value=a["active"])
                            ui.button("Guardar", on_click=lambda a=a, an=an, ah=ah, aw=aw, active=active:
                                      save_activity(a["id"], an.value, ah.value, aw.value, active.value)
                                      ).props("flat dense")
                    ui.button("+ Actividad", on_click=lambda c=c: new_activity_dialog(panel, c)).props(
                        "flat dense")

    def save_class(class_id, name, hours):
        if not (name or "").strip() or not hours or not 0 < hours <= 24:
            ui.notify("Nombre obligatorio y horas/día entre 0 y 24.", type="warning")
            return
        update_row("equipment_classes", "id", class_id, {"name": name.strip(), "hours_per_day": hours})

    def save_activity(activity_id, name, hours, weeks, active):
        if not (name or "").strip() or (not hours and not weeks):
            ui.notify("Nombre obligatorio y al menos una frecuencia (horas o semanas).", type="warning")
            return
        update_row("maintenance_activities", "id", activity_id, {
            "name": name.strip(), "interval_hours": hours or None,
            "interval_weeks": int(weeks) if weeks else None, "active": active,
        })

    def new_class_dialog(panel):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label("Nueva clase de equipo").classes("text-lg font-semibold")
            code = ui.input("Código (MAYÚSCULAS, sin espacios)").props("outlined dense").classes("w-full")
            name = ui.input("Nombre").props("outlined dense").classes("w-full")
            hours = ui.number("Horas/día estimadas", value=24, min=0.1, max=24).props(
                "outlined dense").classes("w-full")

            def save():
                try:
                    client.table("equipment_classes").insert({
                        "code": (code.value or "").strip().upper(), "name": (name.value or "").strip(),
                        "hours_per_day": hours.value,
                    }).execute()
                except Exception as e:
                    ui.notify(f"No se pudo crear: {friendly_error(e)}", type="negative")
                    return
                dialog.close()
                render_sabana(panel)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Crear", on_click=save).props("color=primary")
        dialog.open()

    def new_activity_dialog(panel, cls):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label(f"Nueva actividad — {cls['name']}").classes("text-lg font-semibold")
            code = ui.input("Código (ej. LUB-ROD)").props("outlined dense").classes("w-full")
            name = ui.input("Nombre").props("outlined dense").classes("w-full")
            hours = ui.number("Cada (h)", min=1).props("outlined dense").classes("w-full")
            weeks = ui.number("Cada (semanas)", min=1, format="%.0f").props("outlined dense").classes("w-full")

            def save():
                if not hours.value and not weeks.value:
                    ui.notify("Indicá horas, semanas o ambas.", type="warning")
                    return
                try:
                    client.table("maintenance_activities").insert({
                        "class_id": cls["id"], "code": (code.value or "").strip().upper(),
                        "name": (name.value or "").strip(), "interval_hours": hours.value or None,
                        "interval_weeks": int(weeks.value) if weeks.value else None,
                    }).execute()
                except Exception as e:
                    ui.notify(f"No se pudo crear: {friendly_error(e)}", type="negative")
                    return
                dialog.close()
                render_sabana(panel)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Crear", on_click=save).props("color=primary")
        dialog.open()

    def import_library(panel):
        try:
            lib_classes, lib_acts = mp.load_library(LIBRARY)
        except FileNotFoundError:
            ui.notify(f"No existe {LIBRARY.name} en la raíz del repo.", type="negative")
            return
        except mp.LibraryError as e:
            with ui.dialog() as dialog, ui.card().classes("max-w-xl"):
                ui.label(f"❌ {LIBRARY.name} tiene errores (no se importó nada):").classes("font-semibold")
                for err in e.errors:
                    ui.label(f"• {err}").classes("text-sm")
                ui.button("Cerrar", on_click=dialog.close).props("flat")
            dialog.open()
            return
        try:
            db_classes = client.table("equipment_classes").select("id, code").execute().data
            db_acts = client.table("maintenance_activities").select("class_id, code").execute().data
        except Exception as e:
            ui.notify(f"No se pudo leer la sábana actual: {friendly_error(e)}", type="negative")
            return
        class_ids = {c["code"]: c["id"] for c in db_classes}
        code_by_id = {v: k for k, v in class_ids.items()}
        plan = mp.plan_import(lib_classes, lib_acts, set(class_ids),
                              {(code_by_id[a["class_id"]], a["code"]) for a in db_acts})
        if not plan.new_classes and not plan.new_activities:
            ui.notify("La planta ya tiene todo lo de la biblioteca.", type="info")
            return

        def apply():
            try:
                if plan.new_classes:
                    for row in client.table("equipment_classes").insert([
                        {"code": c.code, "name": c.name, "hours_per_day": c.hours_per_day}
                        for c in plan.new_classes
                    ]).execute().data:
                        class_ids[row["code"]] = row["id"]
                if plan.new_activities:
                    client.table("maintenance_activities").insert([
                        {"class_id": class_ids[a.class_code], "code": a.code, "name": a.name,
                         "interval_hours": a.interval_hours, "interval_weeks": a.interval_weeks}
                        for a in plan.new_activities
                    ]).execute()
            except Exception as e:
                ui.notify(f"No se pudo importar: {friendly_error(e)}", type="negative")
                return
            dialog.close()
            ui.notify("Sábana base importada", type="positive")
            render_sabana(panel)

        with ui.dialog() as dialog, ui.card().classes("max-w-xl"):
            ui.label("Se agregará (lo existente no se toca):").classes("font-semibold")
            for c in plan.new_classes:
                ui.label(f"➕ Clase {c.name} ({c.hours_per_day:g} h/día)").classes("text-sm")
            for a in plan.new_activities:
                ui.label(f"➕ {a.class_code}: {a.name}").classes("text-sm")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Importar", on_click=apply).props("color=primary")
        dialog.open()

    def export_library(classes, acts):
        # letras_tag y palabras_clave no viven en la base: se toman de la biblioteca y,
        # para clases propias de la planta, las letras salen de los TAGs asignados.
        try:
            lib = {c.code: c for c in mp.load_library(LIBRARY)[0]}
        except (FileNotFoundError, mp.LibraryError):
            lib = {}
        tags = client.table("equipment_tags").select("tag_id, class_id").execute().data
        by_id = {c["id"]: c for c in classes}
        out_classes = []
        for c in classes:
            letters = lib[c["code"]].tag_letters if c["code"] in lib else sorted({
                m.group(1) for t in tags if t["class_id"] == c["id"]
                if (m := mp.TAG_TYPE_RE.match(t["tag_id"]))
            })
            keywords = lib[c["code"]].keywords if c["code"] in lib else []
            out_classes.append(mp.EquipmentClass(c["code"], c["name"], c["hours_per_day"],
                                                 letters, keywords))
        out_acts = [mp.Activity(by_id[a["class_id"]]["code"], a["code"], a["name"],
                                a["interval_hours"], a["interval_weeks"]) for a in acts if a["active"]]
        path = REPO_ROOT / f"sabana_{project_ref}_{date.today().isoformat()}.xlsx"
        mp.export_library(out_classes, out_acts, path)
        ui.notify(f"Exportada a {path.name}. Reemplazar sabana_base.xlsx es decisión manual.",
                  type="positive", multi_line=True)

    # ── Equipos ───────────────────────────────────────────────────────────

    def render_equipos(panel):
        panel.clear()
        rows = _plantilla_rows()
        try:
            db_tags = {t["tag_id"]: t for t in client.table("equipment_tags").select("*").execute().data}
            classes = client.table("equipment_classes").select("id, code, name").order("name").execute().data
        except Exception as e:
            error_with_retry(panel, f"No se pudieron leer los equipos: {friendly_error(e)}",
                             lambda: render_equipos(panel))
            return
        pairs = mp.detect_pairs([r["TAG"] for r in rows])
        options = {NO_CLASS: "— sin clase —", **{c["id"]: c["name"] for c in classes}}
        with panel:
            with ui.row().classes("items-center gap-2"):
                ui.button("🪄 Auto-asignar", on_click=lambda: auto_assign(panel, rows, db_tags, classes, pairs))
                ui.label("Sugiere clase a los TAGs sin clase y detecta pares A/B.").classes(
                    "text-sm text-gray-500")
            if not rows:
                ui.label("No hay TAGs: falta plantilla_sitio.xlsx o está vacía.").classes("text-amber-700")
            for r in rows:
                tag = r["TAG"]
                current = db_tags.get(tag, {})
                with ui.row().classes("items-center gap-x-2 gap-y-1 w-full border-b py-2"):
                    with ui.column().classes("gap-0 grow min-w-0 w-full sm:w-auto"):
                        ui.label(tag + (f"  · par {pairs[tag]}" if tag in pairs else "")).classes(
                            "font-mono text-sm")
                        ui.label(r.get("SERVICIO") or "").classes("text-sm text-gray-600 truncate w-full")
                    cls = ui.select(options, value=current.get("class_id") or NO_CLASS).props(
                        "outlined dense").classes("w-full sm:w-64")
                    reg = ui.select(REGIME_LABEL, value=current.get("regime", "normal")).props(
                        "outlined dense").classes("w-full sm:w-36")

                    def handler(_, tag=tag, cls=cls, reg=reg):
                        save_tag(tag, cls.value or None, reg.value, pairs.get(tag))

                    cls.on_value_change(handler)
                    reg.on_value_change(handler)
            orphans = sorted(set(db_tags) - {r["TAG"] for r in rows})
            if orphans:
                ui.label("⚠️ En la base pero no en la plantilla (¿TAG renombrado o borrado?): "
                         + ", ".join(orphans)).classes("text-amber-700 text-sm break-all")

    def save_tag(tag, class_id, regime, group_key):
        try:
            client.table("equipment_tags").upsert({
                "tag_id": tag, "class_id": class_id, "regime": regime, "group_key": group_key,
            }).execute()
        except Exception as e:
            ui.notify(f"No se pudo guardar {tag}: {friendly_error(e)}", type="negative")
            return
        ui.notify(f"{tag} guardado", type="positive", timeout=1000)

    def auto_assign(panel, rows, db_tags, classes, pairs):
        try:
            lib_classes = mp.load_library(LIBRARY)[0]
        except (FileNotFoundError, mp.LibraryError) as e:
            ui.notify(f"No se pudo leer {LIBRARY.name}: {e}", type="negative", multi_line=True)
            return
        id_by_code = {c["code"]: c["id"] for c in classes}
        name_by_code = {c["code"]: c["name"] for c in classes}
        proposals = []
        for r in rows:
            if db_tags.get(r["TAG"], {}).get("class_id"):
                continue
            code = mp.suggest_class(r["TAG"], r, lib_classes)
            if code in id_by_code:
                proposals.append({
                    "tag_id": r["TAG"], "class_id": id_by_code[code], "group_key": pairs.get(r["TAG"]),
                    "regime": "alterna" if r["TAG"] in pairs else "normal", "_name": name_by_code[code],
                })
        if not proposals:
            ui.notify("No hay sugerencias nuevas (¿importaste la sábana base?).", type="info")
            return

        def apply():
            try:
                client.table("equipment_tags").upsert(
                    [{k: v for k, v in p.items() if not k.startswith("_")} for p in proposals]
                ).execute()
            except Exception as e:
                ui.notify(f"No se pudo guardar: {friendly_error(e)}", type="negative")
                return
            dialog.close()
            ui.notify(f"{len(proposals)} equipos asignados", type="positive")
            render_equipos(panel)

        with ui.dialog() as dialog, ui.card().classes("max-w-xl"):
            ui.label("Asignación sugerida (revisá antes de guardar):").classes("font-semibold")
            for p in proposals:
                extra = f" — par {p['group_key']}, {REGIME_LABEL[p['regime']]}" if p["group_key"] else ""
                ui.label(f"{p['tag_id']} → {p['_name']}{extra}").classes("text-sm font-mono")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Guardar", on_click=apply).props("color=primary")
        dialog.open()

    # ── Programación ──────────────────────────────────────────────────────

    def status_text(r: dict) -> str:
        if r["status"] == "vencido":
            days = r.get("days_overdue") or 0
            text = f"🔴 Vencido hace {days} día{'s' if days != 1 else ''}"
            return text + (" · ‼️ crítico" if days >= mp.CRITICAL_DAYS else "")
        if r["status"] == "sin_registro":
            return "⚪ Nunca registrado"
        return STATUS_LABEL.get(r["status"], r["status"])

    def reschedule_text(r: dict) -> str:
        if not r.get("reschedule_count"):
            return ""
        text = f"Reprogramado ×{r['reschedule_count']}"
        if r.get("original_due_date"):
            text += f" · fecha original {format_date(r['original_due_date'])}"
        return text + (f" · motivo: {r['note']}" if r.get("note") else "")

    def render_programacion(panel):
        panel.clear()
        try:
            agenda = client.table("maintenance_agenda").select("*").execute().data
        except Exception as e:
            error_with_retry(panel, f"No se pudo leer la agenda: {friendly_error(e)}",
                             lambda: render_programacion(panel))
            return
        servicio = {r["TAG"]: r.get("SERVICIO") or "" for r in _plantilla_rows()}
        # Solo equipos de la plantilla (los huérfanos se señalan en la pestaña Equipos).
        if servicio:
            agenda = [r for r in agenda if r["tag_id"] in servicio]
        summary = mp.agenda_summary(agenda)
        selected: dict = {}  # (tag, activity_id) → fila, para acciones en lote
        with panel:
            v, c = summary["vencidos"], summary["criticos"]
            ui.label(f"🔴 {v} vencido{'s' if v != 1 else ''}"
                     + (f" ({c} crítico{'s' if c != 1 else ''})" if c else "")
                     + f" · ⚪ {summary['sin_historial']} sin historial").classes("font-semibold")
            with ui.row().classes("items-center gap-2 w-full"):
                mode = ui.select(mp.AGENDA_FILTERS, value="semana", label="Ver").props(
                    "outlined dense").classes("w-full sm:w-52")
                search = ui.input("Buscar TAG o servicio").props("outlined dense clearable").classes(
                    "w-full sm:w-64")
                ui.button("+ Programar manual",
                          on_click=lambda: schedule_dialog(panel)).props("color=primary")
                ui.button(icon="refresh", on_click=lambda: render_programacion(panel)).props("flat")
            bulk_btn = ui.button("Programar seleccionados", on_click=lambda: bulk_dialog(
                panel, list(selected.values()))).props("color=orange")
            bulk_btn.set_visibility(False)
            monday, sunday = mp.week_bounds(date.today())
            ui.label(f"Semana actual: {format_date(monday.isoformat())} – "
                     f"{format_date(sunday.isoformat())}").classes("text-xs text-gray-500")
            listing = ui.column().classes("w-full gap-1")

        def toggle(row, value):
            key = (row["tag_id"], row["activity_id"])
            if value:
                selected[key] = row
            else:
                selected.pop(key, None)
            bulk_btn.text = f"Programar seleccionados ({len(selected)})"
            bulk_btn.set_visibility(bool(selected))

        def draw():
            selected.clear()
            bulk_btn.set_visibility(False)
            text = mp.normalize(search.value)
            rows = [r for r in mp.filter_agenda(agenda, mode.value, date.today())
                    if not text or text in mp.normalize(r["tag_id"] + " " + servicio.get(r["tag_id"], ""))]
            listing.clear()
            with listing:
                if not rows:
                    ui.label("No hay mantenimientos programados para este filtro.").classes("text-gray-500")
                for r in rows:
                    # Dos líneas que se acomodan solas: se lee igual en PC y en celular.
                    color = "text-red-700" if r["status"] == "vencido" else ""
                    with ui.column().classes("w-full gap-0 border-b py-2"):
                        with ui.row().classes("items-center gap-x-3 gap-y-0 w-full"):
                            if r["status"] in ("vencido", "sin_registro"):
                                ui.checkbox(on_change=lambda e, r=r: toggle(r, e.value)).props("dense")
                            ui.label(status_text(r)).classes(f"text-sm {color}")
                            ui.label(format_date(r["due_date"])).classes("font-semibold")
                            ui.label(r["tag_id"]).classes("font-mono text-sm")
                            ui.label(r["source"]).classes("text-xs px-2 rounded-full bg-gray-100")
                        with ui.row().classes("items-center gap-x-3 gap-y-0 w-full"):
                            ui.label(r["activity_name"]).classes("font-medium")
                            ui.label(servicio.get(r["tag_id"], "")).classes(
                                "text-sm text-gray-600 truncate max-w-full")
                            ui.space()
                            ui.button("Reprogramar", on_click=lambda r=r: schedule_dialog(
                                panel, r["tag_id"], r["activity_id"])).props("flat dense no-caps")
                            if r["source"] == "manual":
                                ui.button("Cancelar", on_click=lambda r=r: cancel_manual(panel, r)).props(
                                    "flat dense no-caps color=red")
                        extra = reschedule_text(r)
                        if extra:
                            ui.label(extra).classes("text-xs text-amber-700")

        mode.on_value_change(lambda _: draw())
        search.on_value_change(lambda _: draw())
        draw()

    def cancel_manual(panel, row):
        if update_row("maintenance_manual_schedule", "id", row["manual_id"], {"status": "cancelado"},
                      ok="Programación manual cancelada"):
            render_programacion(panel)

    def bulk_dialog(panel, rows):
        """Programar/reprogramar varias filas a una fecha con un solo motivo (cada una
        queda con su trazabilidad: una llamada a schedule_manual por fila)."""
        overdue = any(r["status"] == "vencido" for r in rows)
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label(f"Programar {len(rows)} mantenimientos").classes("text-lg font-semibold")
            for r in rows[:8]:
                ui.label(f"• {r['tag_id']} — {r['activity_name']}").classes("text-sm")
            if len(rows) > 8:
                ui.label(f"… y {len(rows) - 8} más").classes("text-sm text-gray-500")
            date_in = ui.input("Fecha", value=(date.today() + timedelta(days=7)).isoformat()).props(
                "outlined dense type=date").classes("w-full")
            reason = ui.input("Motivo (obligatorio: hay vencidos)" if overdue else "Motivo (opcional)").props(
                "outlined dense").classes("w-full")
            weeks = ui.number("Repartir en N semanas (1 = todos en esa fecha)", value=1, min=1,
                              format="%.0f").props("outlined dense").classes("w-full")

            def apply():
                if overdue and not (reason.value or "").strip():
                    ui.notify("Escribí el motivo: hay mantenimientos vencidos.", type="warning")
                    return
                start = date.fromisoformat(date_in.value)
                ordered = mp.filter_agenda(rows, "todo", date.today())  # más atrasados primero
                dates = mp.spread_dates(len(ordered), start, int(weeks.value or 1))
                errors = []
                for r, when in zip(ordered, dates):
                    try:
                        client.rpc("schedule_manual", {
                            "p_tag": r["tag_id"], "p_activity": r["activity_id"], "p_date": when.isoformat(),
                            "p_note": (reason.value or "").strip() or None, "p_replace": True,
                        }).execute()
                    except Exception as e:
                        errors.append(f"{r['tag_id']}: {friendly_error(e)}")
                dialog.close()
                if errors:
                    ui.notify(f"{len(rows) - len(errors)} programados; fallaron: " + "; ".join(errors),
                              type="warning", multi_line=True, close_button=True, timeout=0)
                else:
                    ui.notify(f"{len(rows)} mantenimientos programados", type="positive")
                render_programacion(panel)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Programar", on_click=apply).props("color=primary")
        dialog.open()

    def schedule_dialog(panel, tag=None, activity_id=None):
        tags = [r["TAG"] for r in _plantilla_rows()]
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label("Programar mantenimiento").classes("text-lg font-semibold")
            tag_sel = ui.select(tags, value=tag, label="TAG", with_input=True).props(
                "outlined dense").classes("w-full")
            act_sel = ui.select({LIBRE: "Libre (fuera de la sábana)"}, value=LIBRE,
                                label="Actividad").props("outlined dense").classes("w-full")
            default_date = (date.today() + timedelta(days=7)).isoformat()
            date_in = ui.input("Fecha", value=default_date).props("outlined dense type=date").classes("w-full")
            note = ui.input("Nota / motivo (opcional)").props("outlined dense").classes("w-full")

            def load_activities(preselect=None):
                options = {LIBRE: "Libre (fuera de la sábana)"}
                if tag_sel.value:
                    try:
                        options.update({a["id"]: a["name"] for a in fetch_tag_activities(client, tag_sel.value)})
                    except Exception as e:
                        ui.notify(f"No se pudo leer la sábana: {friendly_error(e)}", type="negative")
                act_sel.set_options(options, value=preselect if preselect in options else LIBRE)

            tag_sel.on_value_change(lambda _: load_activities())
            load_activities(activity_id)

            async def save():
                if not tag_sel.value or not date_in.value:
                    ui.notify("Elegí TAG y fecha.", type="warning")
                    return
                params = {"p_tag": tag_sel.value, "p_activity": act_sel.value or None,
                          "p_date": date_in.value, "p_note": note.value or None, "p_replace": False}
                try:
                    result = client.rpc("schedule_manual", params).execute().data
                    if result["status"] == "conflict":
                        reason = await confirm_overwrite(tag_sel.value, result["conflicts"], date_in.value,
                                                         ask_reason=True, reason=note.value or "")
                        if reason is None:
                            return
                        params.update({"p_replace": True, "p_note": reason or None})
                        result = client.rpc("schedule_manual", params).execute().data
                except Exception as e:
                    ui.notify(f"No se pudo programar: {friendly_error(e)}", type="negative")
                    return
                if result.get("others"):
                    ui.notify("Este equipo también tiene: " + "; ".join(
                        f"{o['activity_name']} el {format_date(o['due_date'])} "
                        f"({SOURCE_LABEL.get(o['source'], o['source'])})" for o in result["others"]
                    ), type="info", multi_line=True, close_button=True, timeout=8000)
                ui.notify("Mantenimiento programado", type="positive")
                dialog.close()
                render_programacion(panel)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Programar", on_click=save).props("color=primary")
        dialog.open()

    render_login_card(content, client, on_user)
