#!/usr/bin/env python3
"""
excel_migrator.py
=================
Genera la estructura de archivos del sitio QR Groupe SEB a partir de
plantilla_sitio.xlsx y la escribe en docs/ (lista para GitHub Pages).

Uso:
    python3 excel_migrator.py                       # default: plantilla_sitio.xlsx → docs/
    python3 excel_migrator.py <plantilla> <output>  # rutas custom
"""

import html
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook

# ─────────────────────────────────────────────────────────────────────────
# Configuración del sitio
# ─────────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent
DEFAULT_INPUT = REPO_ROOT / "plantilla_sitio.xlsx"
DEFAULT_OUTPUT = REPO_ROOT / "docs"

SITE_TITLE = "QR Groupe SEB"
SITE_SUBTITLE = "Documentación técnica"
SITE_URL = "https://jagilren.github.io/groupe_seb_qr/"

# Orden fijo de las categorías en el sitio
CATEGORY_ORDER = ["EQUIPOS", "INSTRUMENTOS", "TANQUES"]

# Columnas fijas en la plantilla (las demás son propiedades dinámicas)
FIXED_COLS_HEAD = ["TAG", "Categoría", "Título"]
FIXED_COLS_TAIL = ["Ficha Técnica", "Curva"]


# ─────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Item:
    tag: str
    category: str
    title: str  # default = tag si está vacío
    properties: dict[str, str] = field(default_factory=dict)
    ficha_tecnica_url: Optional[str] = None
    curva_url: Optional[str] = None

    @property
    def filename(self) -> str:
        # Slug del TAG para archivo: quita espacios y barras
        return self.tag.replace(" ", "").replace("/", "_") + ".html"


# ─────────────────────────────────────────────────────────────────────────
# Lectura de la plantilla
# ─────────────────────────────────────────────────────────────────────────
def cell_value(cell) -> str:
    """Convierte un valor de celda a string limpio."""
    v = cell.value
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def cell_hyperlink(cell) -> Optional[str]:
    """Devuelve el target del hyperlink si la celda tiene uno."""
    if cell.hyperlink is not None:
        target = cell.hyperlink.target or cell.hyperlink.location
        if target:
            return str(target).strip()
    # Fallback: si el valor de la celda parece URL
    v = cell_value(cell)
    if v.startswith(("http://", "https://")):
        return v
    return None


def load_items(xlsx_path: Path) -> tuple[list[Item], list[str]]:
    """Lee plantilla_sitio.xlsx → (items, lista de propiedades en orden)."""
    print(f"📖 Leyendo: {xlsx_path}")
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb["Datos"] if "Datos" in wb.sheetnames else wb.active

    # Headers (fila 1)
    headers = [cell_value(c) for c in ws[1]]
    if not headers or headers[0] != "TAG":
        raise ValueError(f"La primera columna debe ser 'TAG', pero es {headers[0]!r}")

    # Identificar columnas: TAG, Categoría, Título → propiedades → Ficha Técnica, Curva
    try:
        idx_tag = headers.index("TAG")
        idx_cat = headers.index("Categoría")
        idx_tit = headers.index("Título")
        idx_ft = headers.index("Ficha Técnica") if "Ficha Técnica" in headers else None
        idx_curva = headers.index("Curva") if "Curva" in headers else None
    except ValueError as e:
        raise ValueError(f"Falta columna obligatoria: {e}")

    # Columnas de propiedades = entre Título y Ficha Técnica (o hasta el final)
    prop_start = idx_tit + 1
    prop_end = idx_ft if idx_ft is not None else len(headers)
    prop_columns = [h for h in headers[prop_start:prop_end] if h]

    items: list[Item] = []
    for row in ws.iter_rows(min_row=2):
        tag = cell_value(row[idx_tag])
        if not tag:
            continue  # fila vacía
        category = cell_value(row[idx_cat]).upper()
        if category not in CATEGORY_ORDER:
            print(f"  ⚠️  TAG {tag}: categoría '{category}' no reconocida; se asigna EQUIPOS")
            category = "EQUIPOS"
        title = cell_value(row[idx_tit]) or tag

        # Propiedades: solo las que tengan valor
        props = {}
        for i, col_name in enumerate(headers[prop_start:prop_end]):
            if not col_name:
                continue
            val = cell_value(row[prop_start + i])
            if val:
                props[col_name] = val

        ficha_url = cell_hyperlink(row[idx_ft]) if idx_ft is not None else None
        curva_url = cell_hyperlink(row[idx_curva]) if idx_curva is not None else None

        items.append(Item(
            tag=tag,
            category=category,
            title=title,
            properties=props,
            ficha_tecnica_url=ficha_url,
            curva_url=curva_url,
        ))

    print(f"   {len(items)} TAGs cargados, {len(prop_columns)} propiedades posibles")
    return items, prop_columns


# ─────────────────────────────────────────────────────────────────────────
# Helpers de HTML
# ─────────────────────────────────────────────────────────────────────────
def h(s: str) -> str:
    """HTML escape."""
    return html.escape(s, quote=True)


def group_by_category(items: list[Item]) -> dict[str, list[Item]]:
    """Devuelve dict {categoría: [items ordenados por TAG]}."""
    grouped: dict[str, list[Item]] = {c: [] for c in CATEGORY_ORDER}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    for cat in grouped:
        grouped[cat].sort(key=lambda i: i.tag)
    return grouped


def build_nav(grouped: dict[str, list[Item]], rel_prefix: str, active_tag: Optional[str] = None) -> str:
    """Construye el <nav> del sidebar con paths relativos según ubicación."""
    out = ['<nav class="nav"><ul class="nav-list">']
    for cat in CATEGORY_ORDER:
        items = grouped.get(cat, [])
        if not items:
            continue
        cat_slug = cat.lower()
        out.append('<li class="nav-group">')
        out.append('<div class="nav-cat-row">')
        out.append(f'<button class="nav-cat" aria-expanded="false">{h(cat)}</button>')
        out.append('</div>')
        out.append(f'<a class="nav-cat-link" href="{rel_prefix}{cat_slug}/index.html">Ver categoría completa →</a>')
        out.append('<ul class="nav-items">')
        for item in items:
            active_cls = ' class="active"' if active_tag == item.tag else ""
            out.append(
                f'<li><a{active_cls} href="{rel_prefix}{cat_slug}/{item.filename}">{h(item.tag)}</a></li>'
            )
        out.append('</ul></li>')
    out.append('</ul></nav>')
    return "\n".join(out)


def page_skeleton(
    page_title: str,
    topbar_title: str,
    sidebar_html: str,
    content_html: str,
    rel_prefix: str,
) -> str:
    """Skeleton HTML completo (head + topbar + sidebar + content)."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#0969da">
    <title>{h(page_title)} — {h(SITE_TITLE)}</title>
    <link rel="stylesheet" href="{rel_prefix}styles.css">
</head>
<body>
    <div class="sidebar-backdrop" aria-hidden="true"></div>
    <header class="topbar">
        <button class="menu-toggle" aria-label="Abrir menú" aria-controls="sidebar" aria-expanded="false">☰</button>
        <span class="topbar-title">{h(topbar_title)}</span>
    </header>
    <div class="layout">
        <aside class="sidebar" id="sidebar">
            <div class="brand">
                <a href="{rel_prefix}index.html">
                    <h1>{h(SITE_TITLE)}</h1>
                </a>
                <button class="sidebar-close" aria-label="Cerrar menú">✕</button>
            </div>
            {sidebar_html}
        </aside>
        <main class="content">
            <article>
{content_html}
            </article>
        </main>
    </div>
    <script src="{rel_prefix}script.js"></script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────
# Renderizado de cada tipo de página
# ─────────────────────────────────────────────────────────────────────────
def render_home(grouped: dict[str, list[Item]]) -> str:
    parts = [
        f'<header class="page-header"><h1>{h(SITE_TITLE)}</h1>',
        f'<p class="subtitle">{h(SITE_SUBTITLE)}</p></header>',
        '<div class="accordion">',
    ]
    for cat in CATEGORY_ORDER:
        items = grouped.get(cat, [])
        if not items:
            continue
        cat_slug = cat.lower()
        parts.append('<div class="acc-item">')
        parts.append(
            f'<button class="acc-header" aria-expanded="false">'
            f'<span class="acc-title">{h(cat)}</span>'
            f'<span class="acc-meta">{len(items)} elementos</span>'
            f'<span class="acc-chevron" aria-hidden="true">›</span></button>'
        )
        parts.append('<div class="acc-body">')
        parts.append('<ul class="acc-list">')
        for item in items:
            parts.append(
                f'<li><a href="{cat_slug}/{item.filename}">{h(item.tag)}</a></li>'
            )
        parts.append('</ul>')
        parts.append(f'<a class="acc-cta" href="{cat_slug}/index.html">Ver categoría completa →</a>')
        parts.append('</div></div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_category_index(category: str, items: list[Item]) -> str:
    parts = [
        f'<header class="page-header"><h1>{h(category)}</h1>',
        f'<p class="breadcrumb"><a href="../index.html">Inicio</a> / <span>{h(category)}</span></p>',
        f'<p class="count">{len(items)} elementos</p></header>',
        '<div class="accordion">',
    ]
    for item in items:
        # Preview: primeras 3 propiedades con valor
        preview_rows = []
        for k, v in list(item.properties.items())[:3]:
            preview_rows.append(
                f'<div class="acc-row"><span class="acc-row-label">{h(k)}</span>'
                f'<span class="acc-row-value">{h(v)}</span></div>'
            )
        preview_html = "".join(preview_rows) if preview_rows else '<p class="empty">Sin datos previos.</p>'
        # Meta: título si difiere del TAG
        meta = h(item.title) if item.title != item.tag else ""
        parts.append('<div class="acc-item">')
        parts.append(
            f'<button class="acc-header" aria-expanded="false">'
            f'<span class="acc-title">{h(item.tag)}</span>'
            f'<span class="acc-meta">{meta}</span>'
            f'<span class="acc-chevron" aria-hidden="true">›</span></button>'
        )
        parts.append(
            f'<div class="acc-body">{preview_html}'
            f'<a class="acc-cta" href="{item.filename}">Ver ficha completa →</a></div>'
        )
        parts.append('</div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_item_page(item: Item) -> str:
    parts = [
        f'<header class="page-header"><h1>{h(item.title)}</h1>',
        f'<p class="breadcrumb">'
        f'<a href="../index.html">Inicio</a> / '
        f'<a href="index.html">{h(item.category)}</a> / '
        f'<span>{h(item.tag)}</span></p>',
        '</header>',
    ]

    if item.properties:
        parts.append('<div class="accordion">')
        for label, value in item.properties.items():
            parts.append('<div class="acc-item">')
            parts.append(
                f'<button class="acc-header" aria-expanded="false">'
                f'<span class="acc-title">{h(label)}</span>'
                f'<span class="acc-chevron" aria-hidden="true">›</span></button>'
            )
            # Multiline support: dividir por saltos de línea en párrafos
            paragraphs = []
            for line in value.split("\n"):
                line = line.strip()
                if line:
                    paragraphs.append(f'<p>{h(line)}</p>')
            body = "\n".join(paragraphs) if paragraphs else '<p class="empty">—</p>'
            parts.append(f'<div class="acc-body">{body}</div></div>')
        parts.append('</div>')
    else:
        parts.append('<p class="empty">Esta ficha no tiene propiedades cargadas.</p>')

    # Documentos y enlaces
    if item.ficha_tecnica_url or item.curva_url:
        parts.append('<section class="external-links">')
        parts.append('<h2>Documentos y enlaces</h2>')
        parts.append('<ul class="link-list">')
        if item.ficha_tecnica_url:
            parts.append(
                f'<li><a class="link-btn" href="{h(item.ficha_tecnica_url)}" '
                f'target="_blank" rel="noopener">Ficha Técnica ↗</a></li>'
            )
        if item.curva_url:
            parts.append(
                f'<li><a class="link-btn" href="{h(item.curva_url)}" '
                f'target="_blank" rel="noopener">Curva ↗</a></li>'
            )
        parts.append('</ul></section>')

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Assets estáticos (CSS + JS) embebidos
# ─────────────────────────────────────────────────────────────────────────
STYLES_CSS = r""":root {
    --bg: #ffffff;
    --bg-alt: #f6f8fa;
    --border: #e1e4e8;
    --text: #1f2328;
    --text-muted: #57606a;
    --accent: #0969da;
    --accent-hover: #0550ae;
    --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-hover: 0 4px 12px rgba(0,0,0,0.08);
    --radius: 8px;
    --topbar-h: 56px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-text-size-adjust: 100%; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
    -webkit-tap-highlight-color: rgba(9,105,218,0.15);
}

.layout { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }

/* ---------------- Topbar (sólo móvil) ---------------- */
.topbar {
    display: none;
    position: sticky;
    top: 0;
    z-index: 8;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    height: var(--topbar-h);
    align-items: center;
    padding: 0 12px;
    gap: 8px;
}
.topbar .topbar-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.menu-toggle {
    display: none;
    background: transparent;
    border: 0;
    width: 44px;
    height: 44px;
    font-size: 22px;
    cursor: pointer;
    border-radius: var(--radius);
    color: var(--text);
    line-height: 1;
}
.menu-toggle:hover { background: var(--bg-alt); }

.sidebar-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 9;
    opacity: 0;
    transition: opacity 0.2s ease;
}
.sidebar-backdrop.show { display: block; opacity: 1; }

/* ---------------- Sidebar ---------------- */
.sidebar {
    background: var(--bg-alt);
    border-right: 1px solid var(--border);
    padding: 24px 0;
    overflow-y: auto;
    position: sticky;
    top: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
}

.brand { padding: 0 24px 20px; border-bottom: 1px solid var(--border); }
.brand a { color: var(--text); text-decoration: none; }
.brand h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }

.sidebar-close {
    display: none;
    background: transparent;
    border: 0;
    width: 40px;
    height: 40px;
    font-size: 20px;
    cursor: pointer;
    border-radius: 6px;
    color: var(--text-muted);
    line-height: 1;
}
.sidebar-close:hover { background: rgba(0,0,0,0.06); color: var(--text); }

.nav { flex: 1; padding: 12px 12px 8px; }
.nav-list { list-style: none; }
.nav-group { margin-bottom: 6px; }

.nav-cat-row {
    display: flex;
    align-items: center;
    gap: 4px;
}
.nav-cat {
    flex: 1;
    text-align: left;
    background: none;
    border: 0;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    cursor: pointer;
    border-radius: 6px;
    font-family: inherit;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.nav-cat::after {
    content: "›";
    transform: rotate(90deg);
    transition: transform 0.2s ease;
    font-size: 18px;
    margin-left: 8px;
    color: var(--text-muted);
}
.nav-group.open .nav-cat::after { transform: rotate(-90deg); }
.nav-cat:hover { background: rgba(9,105,218,0.08); color: var(--accent); }

.nav-cat-link {
    padding: 4px 12px 8px;
    font-size: 11px;
    color: var(--accent);
    text-decoration: none;
    display: block;
}
.nav-cat-link:hover { text-decoration: underline; }

.nav-items {
    list-style: none;
    padding-left: 6px;
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.25s ease;
}
.nav-group.open .nav-items { max-height: 6000px; }
.nav-items li a {
    display: block;
    padding: 10px 12px;
    font-size: 14px;
    color: var(--text);
    text-decoration: none;
    border-radius: 6px;
    border-left: 2px solid transparent;
    margin-bottom: 2px;
}
.nav-items li a:hover { background: rgba(9,105,218,0.08); color: var(--accent); }
.nav-items li a.active {
    background: rgba(9,105,218,0.12);
    color: var(--accent);
    border-left-color: var(--accent);
    font-weight: 600;
}

.sidebar-footer {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    font-size: 12px;
}
.sidebar-footer a { color: var(--text-muted); text-decoration: none; }
.sidebar-footer a:hover { color: var(--accent); }

/* ---------------- Content ---------------- */
.content { padding: 48px 56px; max-width: 960px; }
.page-header { margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid var(--border); }
.page-header h1 {
    font-size: 32px;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: 8px;
    word-break: break-word;
}
.page-header .subtitle { color: var(--text-muted); font-size: 16px; }
.page-header .count { color: var(--text-muted); font-size: 14px; margin-top: 4px; }

.breadcrumb { font-size: 13px; color: var(--text-muted); }
.breadcrumb a { color: var(--accent); text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.breadcrumb span { color: var(--text); }

.external-links {
    margin-top: 32px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
}
.external-links h2 { font-size: 18px; margin-bottom: 16px; }
.link-list { list-style: none; display: flex; flex-wrap: wrap; gap: 12px; }
.link-btn {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    padding: 12px 20px;
    background: var(--accent);
    color: white;
    text-decoration: none;
    border-radius: var(--radius);
    font-size: 15px;
    font-weight: 500;
    transition: background 0.15s ease;
}
.link-btn:hover, .link-btn:active { background: var(--accent-hover); }

/* ---------------- Acordeones (cards colapsables) ---------------- */
.accordion {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 16px;
}

.acc-item {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.acc-item:hover { border-color: var(--accent); }
.acc-item.open { box-shadow: var(--shadow-hover); }

.acc-header {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 16px 18px;
    background: transparent;
    border: 0;
    cursor: pointer;
    text-align: left;
    font-family: inherit;
    color: var(--text);
    min-height: 56px;
}
.acc-header:hover { background: var(--bg-alt); }

.acc-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    flex: 1;
}
.acc-meta {
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 400;
    margin-right: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 50%;
}
.acc-chevron {
    font-size: 22px;
    line-height: 1;
    color: var(--text-muted);
    transition: transform 0.2s ease;
    flex-shrink: 0;
}
.acc-item.open .acc-chevron { transform: rotate(90deg); color: var(--accent); }

.acc-body {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease;
    padding: 0 18px;
    border-top: 1px solid transparent;
}
.acc-item.open .acc-body {
    max-height: 4000px;
    padding: 14px 18px 18px;
    border-top-color: var(--border);
}

.acc-row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
}
.acc-row:last-of-type { border-bottom: 0; }
.acc-row-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.acc-row-value { font-size: 14px; color: var(--text); }

.acc-list {
    list-style: none;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 6px;
    margin-bottom: 14px;
}
.acc-list li a {
    display: block;
    padding: 8px 10px;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    text-align: center;
    transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}
.acc-list li a:hover, .acc-list li a:active {
    background: rgba(9,105,218,0.08);
    border-color: var(--accent);
    color: var(--accent);
}

.acc-cta {
    display: inline-block;
    margin-top: 8px;
    color: var(--accent);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
}
.acc-cta:hover { text-decoration: underline; }

.acc-body .empty {
    color: var(--text-muted);
    font-style: italic;
    font-size: 13px;
    padding: 4px 0 8px;
}
.acc-body p {
    font-size: 15px;
    color: var(--text);
    margin-bottom: 6px;
    line-height: 1.5;
}
.acc-body p:last-child { margin-bottom: 0; }

/* ---------------- Mobile (<= 900px) ---------------- */
@media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }

    .topbar { display: flex; }
    .menu-toggle { display: flex; align-items: center; justify-content: center; }

    .sidebar {
        position: fixed;
        top: 0; left: 0;
        width: min(86vw, 320px);
        height: 100dvh;
        z-index: 10;
        transform: translateX(-100%);
        transition: transform 0.25s ease;
        padding: 16px 0 12px;
        box-shadow: 4px 0 16px rgba(0,0,0,0.08);
    }
    .sidebar.open { transform: translateX(0); }

    .brand {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 4px 16px 16px;
    }
    .brand h1 { font-size: 17px; }
    .sidebar-close { display: flex; align-items: center; justify-content: center; }

    .nav-items li a { padding: 12px 14px; font-size: 15px; }

    .content {
        padding: 20px 16px 40px;
        max-width: 100%;
    }
    .page-header { margin-bottom: 20px; padding-bottom: 16px; }
    .page-header h1 { font-size: 26px; }
    .page-header .subtitle { font-size: 15px; }

    .breadcrumb { font-size: 14px; margin-top: 4px; }

    .accordion { gap: 6px; margin-top: 12px; }
    .acc-header { padding: 14px 14px; min-height: 56px; }
    .acc-title { font-size: 15px; }
    .acc-meta { font-size: 12px; max-width: 45%; }
    .acc-item.open .acc-body { padding: 12px 14px 14px; }
    .acc-list { grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
    .acc-list li a { padding: 10px 8px; font-size: 13px; min-height: 38px; display: flex; align-items: center; justify-content: center; }

    .external-links { margin-top: 24px; padding-top: 18px; }
    .link-list { flex-direction: column; gap: 10px; }
    .link-btn { width: 100%; justify-content: center; font-size: 16px; }
}

@media (max-width: 380px) {
    .page-header h1 { font-size: 22px; }
    .acc-meta { display: none; }
}
"""

SCRIPT_JS = r"""document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.querySelector('.sidebar');
    var backdrop = document.querySelector('.sidebar-backdrop');
    var toggle = document.querySelector('.menu-toggle');
    var closeBtn = document.querySelector('.sidebar-close');

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('open');
        if (backdrop) backdrop.classList.add('show');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }
    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.remove('show');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }

    if (toggle) toggle.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (backdrop) backdrop.addEventListener('click', closeSidebar);

    // Cerrar al navegar (en móvil)
    document.querySelectorAll('.sidebar a').forEach(function (a) {
        a.addEventListener('click', function () {
            if (window.matchMedia('(max-width: 900px)').matches) closeSidebar();
        });
    });

    // Cerrar con tecla Escape
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeSidebar();
    });

    // Toggle de categorías
    document.querySelectorAll('.nav-cat').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var group = btn.closest('.nav-group');
            var open = group.classList.toggle('open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });

    // Abrir automáticamente la categoría con link activo (o todas si no hay activo)
    var active = document.querySelector('.nav-items a.active');
    if (active) {
        var group = active.closest('.nav-group');
        if (group) {
            group.classList.add('open');
            var b = group.querySelector('.nav-cat');
            if (b) b.setAttribute('aria-expanded', 'true');
        }
    } else {
        document.querySelectorAll('.nav-group').forEach(function (g) {
            g.classList.add('open');
            var b = g.querySelector('.nav-cat');
            if (b) b.setAttribute('aria-expanded', 'true');
        });
    }

    // Scroll al ítem activo dentro del sidebar
    if (active) {
        setTimeout(function () {
            active.scrollIntoView({ block: 'center', behavior: 'instant' });
        }, 30);
    }

    // Acordeones de contenido (cards colapsables)
    document.querySelectorAll('.acc-header').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var item = btn.closest('.acc-item');
            if (!item) return;
            var open = item.classList.toggle('open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });
});
"""


# ─────────────────────────────────────────────────────────────────────────
# Generación del sitio
# ─────────────────────────────────────────────────────────────────────────
def generate_site(items: list[Item], output_dir: Path):
    print(f"🏗️  Generando sitio en: {output_dir}")
    grouped = group_by_category(items)

    # Limpiar y crear docs/
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Assets estáticos
    (output_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (output_dir / "script.js").write_text(SCRIPT_JS, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    print("   ✅ styles.css + script.js + .nojekyll")

    # Home
    sidebar_home = build_nav(grouped, rel_prefix="")
    home_html = page_skeleton(
        page_title="Inicio",
        topbar_title="Inicio",
        sidebar_html=sidebar_home,
        content_html=render_home(grouped),
        rel_prefix="",
    )
    (output_dir / "index.html").write_text(home_html, encoding="utf-8")
    print("   ✅ index.html")

    # Páginas por categoría y por item
    total_items = 0
    for cat, cat_items in grouped.items():
        if not cat_items:
            continue
        cat_dir = output_dir / cat.lower()
        cat_dir.mkdir(exist_ok=True)

        # Index de categoría
        sidebar_cat = build_nav(grouped, rel_prefix="../")
        cat_index_html = page_skeleton(
            page_title=cat,
            topbar_title=cat,
            sidebar_html=sidebar_cat,
            content_html=render_category_index(cat, cat_items),
            rel_prefix="../",
        )
        (cat_dir / "index.html").write_text(cat_index_html, encoding="utf-8")

        # Páginas individuales
        for item in cat_items:
            sidebar_item = build_nav(grouped, rel_prefix="../", active_tag=item.tag)
            item_html = page_skeleton(
                page_title=item.title,
                topbar_title=item.tag,
                sidebar_html=sidebar_item,
                content_html=render_item_page(item),
                rel_prefix="../",
            )
            (cat_dir / item.filename).write_text(item_html, encoding="utf-8")
            total_items += 1

        print(f"   ✅ {cat.lower()}/ ({len(cat_items)} páginas)")

    # README + metadata
    readme = (
        f"# {SITE_TITLE}\n\n"
        f"Sitio generado automáticamente desde `plantilla_sitio.xlsx`.\n\n"
        f"- **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- **TAGs publicados:** {total_items}\n"
        f"- **Categorías:** {', '.join(c for c in CATEGORY_ORDER if grouped.get(c))}\n\n"
        f"URL pública: {SITE_URL}\n"
    )
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    metadata = {
        "source": "plantilla_sitio.xlsx",
        "generated_at": datetime.now().isoformat(),
        "site_title": SITE_TITLE,
        "site_url": SITE_URL,
        "total_tags": total_items,
        "categories": {c: len(grouped.get(c, [])) for c in CATEGORY_ORDER},
        "tags": [
            {
                "tag": i.tag,
                "category": i.category,
                "title": i.title,
                "properties": i.properties,
                "ficha_tecnica_url": i.ficha_tecnica_url,
                "curva_url": i.curva_url,
            }
            for i in items
        ],
    }
    (output_dir / "migration_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("   ✅ README.md + migration_metadata.json")
    print()
    print(f"✅ {total_items} TAGs publicados en {output_dir}/")
    print(f"   Por categoría: " + ", ".join(
        f"{c}={len(grouped.get(c, []))}" for c in CATEGORY_ORDER if grouped.get(c)
    ))


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    if not input_path.exists():
        print(f"❌ No existe: {input_path}", file=sys.stderr)
        sys.exit(1)

    items, _ = load_items(input_path)
    if not items:
        print("❌ No hay TAGs en la plantilla", file=sys.stderr)
        sys.exit(1)

    generate_site(items, output_dir)


if __name__ == "__main__":
    main()
