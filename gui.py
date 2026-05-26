#!/usr/bin/env python3
"""
gui.py
======
Interfaz NiceGUI para configurar y generar el sitio QR estático.

El usuario puede:
- Elegir la carpeta destino (donde queda index.html, assets/, etc.).
- Subir el logo del cliente (se guarda en <destino>/assets/logos/LogoCliente.png).
- Elegir un color base de tema (se deriva la paleta completa).
- Subir el archivo de fichas técnicas crudas (.xlsx) → convert_fichas.
- Subir TAG_RESOURCES.xlsx → enlaces de Specifications / Handbook / Maintenance.
- Pulsar "Generar sitio" para correr el pipeline completo.
- Pulsar "Ver sitio" para abrir el sitio en un servidor local (puerto 8000).

Ejecutar:
    python3 gui.py
    # luego abrir http://localhost:8080
"""

from __future__ import annotations

import asyncio
import colorsys
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from nicegui import app, ui

# ─────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent
SITE_CONFIG = REPO_ROOT / "site_config.json"
PLANTILLA = REPO_ROOT / "plantilla_sitio.xlsx"
TAG_RESOURCES = REPO_ROOT / "TAG_RESOURCES.xlsx"
FICHAS_DEFAULT_NAME = "fichas_source.xlsx"

GUI_PORT = 8080
PREVIEW_PORT = 8000

# Servir el repo root como estático para previsualizar logo
app.add_static_files("/files", str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────
# Color helpers (un solo color base → paleta coherente)
# ─────────────────────────────────────────────────────────────────────────
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def adjust_lightness(hex_color: str, delta: float) -> str:
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = max(0.0, min(1.0, l + delta))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex(int(r * 255), int(g * 255), int(b * 255))


def luminance(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)

    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def best_text_on(hex_color: str) -> str:
    return "#ffffff" if luminance(hex_color) < 0.45 else "#1f2328"


def hex_alpha(hex_color: str, alpha: float) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha:.2f})"


def derive_palette(base: str) -> dict:
    """De un solo color base, deriva los 10 vars del tema."""
    accent = base
    return {
        "accent": accent,
        "accent_hover": adjust_lightness(base, -0.10),
        "banner_gradient": (
            f"linear-gradient(135deg, "
            f"{adjust_lightness(base, +0.25)} 0%, "
            f"{accent} 60%, "
            f"{adjust_lightness(base, -0.08)} 100%)"
        ),
        "banner_text": best_text_on(accent),
        "banner_shadow": f"0 4px 14px {hex_alpha(accent, 0.25)}",
        "content_bg": adjust_lightness(base, +0.45),
        "card_bg": "#ffffff",
        "text": "#1f2328",
        "text_muted": "#57606a",
        "border": adjust_lightness(base, +0.40),
    }


# ─────────────────────────────────────────────────────────────────────────
# Estado en memoria
# ─────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────
# Persistencia del config
# ─────────────────────────────────────────────────────────────────────────
def load_or_init_config() -> dict:
    if SITE_CONFIG.exists():
        return json.loads(SITE_CONFIG.read_text(encoding="utf-8"))
    return {}


# Cargar el config al inicio para inicializar `state` con valores reales
_initial_cfg = load_or_init_config()

state = {
    "output_dir": str(REPO_ROOT / "docs"),
    "site_title": _initial_cfg.get("site_title", "QR Groupe SEB"),
    "accent_color": _initial_cfg.get("theme", {}).get("accent", "#7c3aed"),
    "fichas_path": None,        # Path al xlsx crudo subido en esta sesión
    "resources_uploaded": False,
    "logo_uploaded": False,
    "force_regenerate": False,  # checkbox: si True, wipe plantilla y assets antes
    "preview_proc": None,       # subprocess del http.server
}


def save_config(accent: str, site_title: str | None = None):
    """Escribe site_config.json con la paleta derivada del color elegido
    y el título del sitio (si se pasa)."""
    cfg = load_or_init_config()
    if site_title is not None and site_title.strip():
        cfg["site_title"] = site_title.strip()
    else:
        cfg.setdefault("site_title", "QR Groupe SEB")
    cfg.setdefault("banner_title_full", "Documentación Técnica — PTAR STARnD")
    cfg.setdefault("banner_title_short", "PTAR STARnD")
    cfg.setdefault("site_url", "https://jagilren.github.io/groupe_seb_qr/")
    cfg["theme"] = derive_palette(accent)
    SITE_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# Pipeline de generación (async para streaming a ui.log)
# ─────────────────────────────────────────────────────────────────────────
def merge_assets_into(dst_root: Path, log_widget, overwrite_images: bool = False) -> int:
    """Copia archivos faltantes de <repo>/docs/assets/ a <dst_root>/assets/.

    Por defecto: NO pisa archivos existentes (preserva logos recién subidos).
    Si overwrite_images=True: pisa SIEMPRE el contenido de assets/images/
    (útil cuando cambiás de fichas xlsx y no querés que imágenes viejas del
    proyecto anterior queden en el destino).

    Devuelve cuántos archivos se copiaron.
    """
    src = REPO_ROOT / "docs" / "assets"
    if not src.exists():
        return 0
    dst = dst_root / "assets"
    try:
        if dst.resolve() == src.resolve():
            return 0
    except FileNotFoundError:
        pass  # dst aún no existe, ok

    # Si overwrite_images: wipe dst/assets/images antes de copiar
    if overwrite_images:
        dst_images = dst / "images"
        if dst_images.exists():
            shutil.rmtree(dst_images)
            log_widget.push(f"   🗑️  {dst_images} pisado (force_regenerate ON)")

    copied = 0
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                copied += 1
    if copied:
        log_widget.push(f"📂 Copiados {copied} archivos de docs/assets/ → {dst}")
    return copied


async def run_streaming(cmd: list[str], log_widget) -> int:
    """Corre un subprocess y emite cada línea de stdout/stderr al log."""
    log_widget.push(f"$ {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        log_widget.push(line.decode(errors="replace").rstrip())
    return await proc.wait()


# ─────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────
ui.colors(primary="#7c3aed")  # tinta del propio NiceGUI

with ui.column().classes("max-w-3xl mx-auto p-6 gap-4 w-full"):
    ui.label("🛠️  Configurador del sitio QR").classes("text-3xl font-bold")
    ui.label("Sube los archivos, elige color y carpeta destino, y genera el sitio.").classes(
        "text-sm text-gray-600"
    )

    # ── Carpeta destino ────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("📁 Carpeta de destino").classes("font-semibold")
        with ui.row().classes("w-full items-center gap-2"):
            output_input = (
                ui.input(value=state["output_dir"])
                .props('outlined dense')
                .classes("flex-1")
            )
            status_label = ui.label().classes("text-sm")

            def check_output(_=None):
                p = Path(output_input.value).expanduser()
                if p.exists() and p.is_dir():
                    status_label.text = "✓ existe"
                    status_label.classes(replace="text-sm text-green-600")
                else:
                    status_label.text = "⚠ se creará"
                    status_label.classes(replace="text-sm text-amber-600")
                state["output_dir"] = str(p)

            output_input.on("change", check_output)
            check_output()
            ui.button(
                "Usar docs/",
                on_click=lambda: (
                    setattr(output_input, "value", str(REPO_ROOT / "docs")),
                    check_output(),
                ),
            ).props("flat dense")

    # ── Logo del cliente ────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("🖼️  Logo del cliente").classes("font-semibold")
        with ui.row().classes("w-full items-center gap-4"):
            logo_img = ui.image("").classes("h-16 w-auto bg-gray-100 rounded")
            # Si ya existe, mostrarlo
            existing_logo = Path(state["output_dir"]) / "assets" / "logos" / "LogoCliente.png"
            if existing_logo.exists():
                logo_img.set_source(f"/files/docs/assets/logos/LogoCliente.png?ts={int(time.time())}")

            async def on_logo_upload(e):
                # NiceGUI 3.x: e.file es FileUpload async. Antes era e.content (sync).
                target = Path(state["output_dir"]) / "assets" / "logos" / "LogoCliente.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(await e.file.read())
                state["logo_uploaded"] = True
                rel = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
                logo_img.set_source(f"/files/{rel}?ts={int(time.time())}")
                log.push(f"✅ Logo guardado: {target.name}")
                ui.notify("Logo actualizado", type="positive")

            ui.upload(
                on_upload=on_logo_upload,
                auto_upload=True,
                max_files=1,
                label="Selecciona PNG/JPG (sobreescribe el anterior)",
            ).props('accept="image/*"').classes("flex-1")

    # ── Título del sitio ────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("📝 Título del sitio").classes("font-semibold")
        ui.label(
            "Aparece en la pestaña del navegador y como h1 del home. "
            "Reemplaza el texto por defecto 'QR Groupe SEB'."
        ).classes("text-xs text-gray-600")

        def on_title_change(e):
            state["site_title"] = (e.value or "").strip() or "QR Groupe SEB"

        ui.input(
            label="Título del sitio",
            value=state["site_title"],
            on_change=on_title_change,
            placeholder="Ej. QR Alimentos D'vida",
        ).props("outlined dense").classes("w-full")

    # ── Color del tema ─────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("🎨 Color del tema").classes("font-semibold")
        ui.label(
            "De un solo color se derivan: accent, hover, gradient del banner, fondo claro, "
            "borde y contraste de texto."
        ).classes("text-xs text-gray-600")
        with ui.row().classes("w-full items-center gap-4"):
            # Swatches creados UNA vez; el handler solo cambia su background.
            # Los keys de derive_palette() en el orden que mostramos.
            SAMPLE_KEYS = ("accent", "accent_hover", "content_bg", "border")
            SAMPLE_LABELS = ("accent", "hover", "bg", "border")

            swatches: list = []
            with ui.row().classes("gap-2"):
                for label in SAMPLE_LABELS:
                    with ui.column().classes("items-center gap-0"):
                        div = ui.element("div")
                        ui.label(label).classes("text-[10px] text-gray-500")
                        swatches.append(div)

            def _apply_swatches(color: str) -> None:
                pal = derive_palette(color)
                for div, key in zip(swatches, SAMPLE_KEYS):
                    div.style(
                        f"background:{pal[key]};width:36px;height:36px;"
                        f"border-radius:6px;border:1px solid #cbd5e1;"
                        f"box-shadow:0 1px 2px rgba(0,0,0,0.08);"
                    )
                    div.update()  # fuerza re-render en el browser

            def on_color_change(e) -> None:
                # NiceGUI dispara este handler con e.value = nuevo color hex
                if e is None or not getattr(e, "value", None):
                    return
                state["accent_color"] = e.value
                _apply_swatches(e.value)
                log.push(f"🎨 Color seleccionado: {e.value}")

            color_input = ui.color_input(
                value=state["accent_color"],
                on_change=on_color_change,
            ).classes("flex-1")
            # Pintar swatches con el valor inicial
            _apply_swatches(state["accent_color"])

    # ── Fichas técnicas ─────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("📄 Archivo de fichas técnicas (.xlsx)").classes("font-semibold")
        ui.label("Excel crudo del cliente — una hoja por TAG. Opcional si ya hay plantilla generada.").classes(
            "text-xs text-gray-600"
        )

        async def on_fichas_upload(e):
            target = REPO_ROOT / FICHAS_DEFAULT_NAME
            target.write_bytes(await e.file.read())
            state["fichas_path"] = target
            log.push(f"✅ Fichas técnicas guardadas: {target.name} ({e.file.name})")
            ui.notify("Fichas técnicas listas", type="positive")

        ui.upload(
            on_upload=on_fichas_upload,
            auto_upload=True,
            max_files=1,
            label="Selecciona el .xlsx de fichas",
        ).props('accept=".xlsx"').classes("w-full")

    # ── TAG_RESOURCES.xlsx ──────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("📄 TAG_RESOURCES.xlsx").classes("font-semibold")
        ui.label(
            "Excel con columnas TAG_ID, Specifications, Handbook_Manual, Maintenance. "
            "Cada celda con hyperlink genera un botón en la ficha del TAG."
        ).classes("text-xs text-gray-600")

        async def on_resources_upload(e):
            target = TAG_RESOURCES
            target.write_bytes(await e.file.read())
            state["resources_uploaded"] = True
            log.push(f"✅ TAG_RESOURCES guardado")
            ui.notify("TAG_RESOURCES actualizado", type="positive")

        ui.upload(
            on_upload=on_resources_upload,
            auto_upload=True,
            max_files=1,
            label="Selecciona TAG_RESOURCES.xlsx",
        ).props('accept=".xlsx"').classes("w-full")

    # ── Modo de regeneración + Acciones ────────────────────────────────
    with ui.card().classes("w-full"):
        def on_force_change(e):
            state["force_regenerate"] = bool(e.value)
        force_switch = ui.switch(
            "🔄 Forzar regeneración de plantilla desde fichas xlsx",
            value=False,
            on_change=on_force_change,
        )
        ui.label(
            "OFF (default): usa plantilla_sitio.xlsx tal cual está. "
            "ON: corre convert_fichas para re-popular el contenido de la plantilla "
            "(estructura de columnas se preserva) y re-extraer imágenes a docs/assets/images/ "
            "desde la fichas xlsx (subida o auto-detectada en la raíz). "
            "Útil cuando cambias el archivo fuente."
        ).classes("text-xs text-gray-600")

    with ui.row().classes("w-full justify-center gap-4 mt-4"):
        # Lambda con forward reference (generate/open_preview se definen abajo).
        # NiceGUI 3.x await-ea automáticamente la coroutine retornada por el lambda
        # y mantiene el slot context (a diferencia de asyncio.create_task).
        generate_btn = ui.button("🏗️  Generar sitio", on_click=lambda: generate())
        generate_btn.props("color=primary size=lg")

        view_btn = ui.button("🌐 Ver sitio", on_click=lambda: open_preview())
        view_btn.props("color=secondary outline size=lg")

    # ── Log ────────────────────────────────────────────────────────────
    ui.label("📋 Log").classes("font-semibold mt-2")
    log = ui.log(max_lines=400).classes("w-full h-64 bg-gray-900 text-green-300 font-mono text-xs p-3 rounded")
    log.push("Listo. Sube archivos / elige color / pulsa Generar.")


# ─────────────────────────────────────────────────────────────────────────
# Acciones async
# ─────────────────────────────────────────────────────────────────────────
async def generate():
    """Corre el pipeline completo."""
    generate_btn.disable()
    try:
        log.push("─" * 60)
        log.push("⚙️  Iniciando generación…")

        # Sanity check: no permitir destinos dentro de assets/ (wipearían imágenes)
        output_dir = Path(state["output_dir"]).expanduser().resolve()
        suspect_names = {"assets", "images", "logos", "icons"}
        if output_dir.name in suspect_names or "assets" in output_dir.parts:
            log.push(f"❌ Destino inseguro: '{output_dir}' está dentro/es una carpeta de assets.")
            log.push("   Elegí otro destino (ej. docs/, /tmp/mi_sitio/, etc.).")
            ui.notify("Destino inseguro — wipearía imágenes/logos", type="negative")
            return

        # 1. Persistir color en site_config.json
        save_config(state["accent_color"], state.get("site_title"))
        log.push(f"🎨 site_config.json actualizado (accent={state['accent_color']})")

        # 2. (opcional) convert fichas → plantilla
        # Resolución del xlsx de fichas:
        #   - Si subiste vía widget: state["fichas_path"] está set → se usa.
        #   - Si NO subiste pero activaste "Forzar regeneración": auto-detecta el más
        #     reciente en raíz del repo (excluyendo plantilla y TAG_RESOURCES).
        # Si nada de lo anterior aplica → se usa plantilla existente sin tocarla.
        fichas_path = state["fichas_path"]

        if state.get("force_regenerate") and fichas_path is None:
            candidates = sorted(
                (p for p in REPO_ROOT.glob("*.xlsx")
                 if p.name not in ("plantilla_sitio.xlsx", "TAG_RESOURCES.xlsx")
                 and not p.name.startswith("~")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                from datetime import datetime
                log.push(f"🔍 Auto-detectado en raíz del repo (force_regenerate ON):")
                for c in candidates:
                    ts = datetime.fromtimestamp(c.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    log.push(f"   • {c.name}  (mod: {ts})")
                fichas_path = candidates[0]
                log.push(f"   → usando: {fichas_path.name}")
                if len(candidates) > 1:
                    log.push(f"   (si querés otro, borrá los demás de la raíz)")

        if state.get("force_regenerate"):
            log.push("🔄 Forzar regeneración: convert_fichas re-popula plantilla_sitio.xlsx")
            log.push("   (sobrescribe el contenido pero respeta la estructura de columnas;")
            log.push("    re-extrae imágenes a docs/assets/images/ desde el xlsx fuente)")
            if fichas_path is None:
                log.push("❌ Forzar regeneración requiere xlsx de fichas (subila o ponela en raíz)")
                ui.notify("Falta xlsx de fichas para regeneración forzada", type="negative")
                return

        if fichas_path:
            log.push(f"📖 Convirtiendo fichas: {fichas_path.name}")
            rc = await run_streaming(
                ["python3", "convert_fichas_to_template.py", str(fichas_path)],
                log,
            )
            if rc != 0:
                log.push(f"❌ convert_fichas falló (exit {rc})")
                ui.notify("Falló convert_fichas", type="negative")
                return
        else:
            if PLANTILLA.exists():
                log.push(f"ℹ️  Usando plantilla existente: {PLANTILLA.name}")
            else:
                log.push("❌ No hay fichas subidas ni plantilla_sitio.xlsx — abortando")
                ui.notify("Falta archivo de fichas o plantilla", type="negative")
                return

        # 3. excel_migrator → sitio
        output_dir.mkdir(parents=True, exist_ok=True)

        # Asegurar que el destino tiene los assets (imágenes, iconos, logos)
        # Si force_regenerate=ON, también pisa images/ viejas del destino
        # (evita arrastrar imágenes de proyectos anteriores).
        merge_assets_into(
            output_dir, log,
            overwrite_images=bool(state.get("force_regenerate")),
        )

        log.push(f"🏗️  Generando sitio en: {output_dir}")
        rc = await run_streaming(
            ["python3", "excel_migrator.py", str(PLANTILLA), str(output_dir)],
            log,
        )
        if rc != 0:
            log.push(f"❌ excel_migrator falló (exit {rc})")
            ui.notify("Falló excel_migrator", type="negative")
            return

        log.push("✅ Sitio generado.")
        ui.notify("Sitio generado correctamente", type="positive")

        # Si había un preview activo apuntando a otra ruta, descartarlo.
        prev_dir = state.get("preview_dir")
        if prev_dir and prev_dir != str(Path(state["output_dir"]).expanduser().resolve()):
            log.push("ℹ️  Preview previo apuntaba a otro destino; se reiniciará en próximo 'Ver sitio'.")
            _stop_preview()
    finally:
        generate_btn.enable()


def _stop_preview():
    proc = state.get("preview_proc")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    state["preview_proc"] = None
    state["preview_dir"] = None


async def open_preview():
    """Lanza un http.server apuntando al destino actual. Si ya hay uno y el
    destino cambió (o está muerto), lo reinicia."""
    output_dir = Path(state["output_dir"]).expanduser().resolve()
    if not (output_dir / "index.html").exists():
        ui.notify("Primero genera el sitio", type="warning")
        return

    proc = state.get("preview_proc")
    current_dir = state.get("preview_dir")
    needs_restart = (
        proc is None
        or proc.poll() is not None
        or current_dir != str(output_dir)
    )

    if needs_restart:
        if proc is not None:
            log.push(f"⏹  Reiniciando preview (cambió destino: {current_dir} → {output_dir})")
            _stop_preview()
        log.push(f"🚀 Lanzando preview en http://localhost:{PREVIEW_PORT} desde {output_dir}")
        state["preview_proc"] = subprocess.Popen(
            ["python3", "-m", "http.server", str(PREVIEW_PORT), "--bind", "0.0.0.0"],
            cwd=str(output_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        state["preview_dir"] = str(output_dir)
        await asyncio.sleep(0.5)
        # Verificar que arrancó: si murió ya, capturar stderr
        if state["preview_proc"].poll() is not None:
            err = state["preview_proc"].stderr.read().decode(errors="replace") if state["preview_proc"].stderr else ""
            log.push(f"❌ El servidor de preview no arrancó. ¿Puerto {PREVIEW_PORT} ocupado?")
            if err:
                log.push(err.strip())
            ui.notify(f"Puerto {PREVIEW_PORT} ocupado. Cierra el otro servidor.", type="negative")
            state["preview_proc"] = None
            state["preview_dir"] = None
            return

    url = f"http://localhost:{PREVIEW_PORT}/?_t={int(time.time())}"
    ui.navigate.to(url, new_tab=True)


# ─────────────────────────────────────────────────────────────────────────
# Apagado limpio del servidor de preview
# ─────────────────────────────────────────────────────────────────────────
@app.on_shutdown
def _shutdown():
    _stop_preview()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        port=GUI_PORT,
        title="Configurador QR — RPCI",
        favicon="🛠️",
        reload=False,
        show=False,
    )
