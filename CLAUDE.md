# CLAUDE.md

Guía para Claude Code en este repositorio.

## Qué es

Generador de sitio estático desde Excel para fichas técnicas industriales, publicado en GitHub Pages.

- **Input:** Excel del cliente (`NP00033 Fichas Técnicas...xlsx`), una hoja por TAG.
- **Output:** `docs/` (HTML/CSS/JS vainilla).
- **Live:** https://jagilren.github.io/groupe_seb_qr/ (planta QR Groupe SEB, Itagüí–Medellín).

## Config

| Item | Valor |
|---|---|
| Remote | `https://github.com/jagilren/groupe_seb_qr` |
| Branch | `master` |
| Pages serves | `/docs` |
| Stack | Python 3.12 + openpyxl (WSL Ubuntu 24) |
| Setup | `pip3 install --break-system-packages openpyxl` |

**Crítico:** Pages sirve desde `/docs`, no desde la raíz. Todo cambio del sitio termina ahí.

## Flujo

1. `convert_fichas_to_template.py` — fichas crudas → `plantilla_sitio.xlsx` (+ extrae imágenes a `docs/assets/images/<TAG>/`).
2. `generate_tag_resources_template.py` — crea/actualiza `TAG_RESOURCES.xlsx` con los TAGs actuales (merge: preserva hyperlinks existentes).
3. Edición manual: `plantilla_sitio.xlsx` (Ficha Técnica/Curva) y `TAG_RESOURCES.xlsx` (Specifications/Handbook_Manual/Maintenance) con `Ctrl+K`.
4. `excel_migrator.py plantilla_sitio.xlsx docs/` — genera el sitio (lee también `TAG_RESOURCES.xlsx` si existe).
5. `git add docs/ && git commit && git push` → Pages recompila en ~1–2 min.

Wrapper end-to-end:
```bash
./update_site_from_excel.sh                 # regenera docs/
./update_site_from_excel.sh --from-fichas   # re-convierte fichas primero
./update_site_from_excel.sh --push          # regenera + commit + push
```

### Convert fichas → plantilla (paso 1)

- Layout vertical `LABEL | VALOR` en cada hoja.
- Ignorar: `UBICACIÓN`, `PLANTA`, header (`FICHA TÉCNICA`, `Versión`, `Fecha`, `Elaboró`, `Revisó`), bloque `NOTAS`.
- Bloques relevantes: `GENERAL`, `FLUIDO`, `TANQUE|EQUIPO|INSTRUMENTO`.
- Una hoja puede expandirse a múltiples TAGs: `100-P-01 A_B` → `100-P-01A`, `100-P-01B`; `400-MX-01_02_03_04` → 4 TAGs.
- Categoría inferida del tipo: `TK|R|F|SD` → TANQUES, `P|MX|M|C|PS` → EQUIPOS, `AIT|FIT|SV|LT` → INSTRUMENTOS.
- Imágenes: parsea `.xlsx` como ZIP, filtra plantillas (umbral usadas en >5 hojas) y copia las específicas a `docs/assets/images/<TAG>/`.
- `Ficha Técnica` y `Curva` salen vacías; se llenan a mano con `Ctrl+K`.

### Mapping Excel → UI

| Columna | Renderizado |
|---|---|
| `TAG` | slug URL + breadcrumb + h1 |
| `Categoría` | carpeta `docs/<cat>/<tag>.html` + grupo en nav |
| `Título` | h1 (vacío → usa TAG) |
| Otras columnas con valor | acordeón con label = h2 |
| `Ficha Técnica`, `Curva` | botones "Documentos y enlaces" (target=_blank) |
| imágenes en `docs/assets/images/<TAG>/` | botón "Ver imágenes" → lightbox |
| `TAG_RESOURCES.xlsx` (`Specifications`, `Handbook_Manual`, `Maintenance`) | botones "Especificaciones / Manual / Mantenimiento" en "Documentos y enlaces" |

## UI

- **Acordeón compartido** (`.acc-item / .acc-header / .acc-body`) en 3 niveles: home (por categoría), categoría (por item con preview 3 props), item (por propiedad). Toggle vía `.open`, inician cerrados.
- **Banner** sticky: `[logo RPCI] | título centrado | [logo cliente]` + botón lupa que abre modal de búsqueda (lazy `search-index.json`, debounce 80ms, ↑↓ Enter Esc, `<mark>` highlight).
- **Lightbox** imágenes: keyboard arrows, swipe táctil 50px, clase `.single` oculta nav si hay 1 imagen.
- **Mobile-first:** topbar+hamburger <900px, sidebar overlay (transform + backdrop 45%), touch targets ≥44px, grid 3/2/1 cols (desktop/mobile/≤380px), `<400px` oculta `.acc-meta`, Esc cierra sidebar, scroll bloqueado mientras abierto, auto-scroll a item activo del menú.
- **`<body data-rel="...">`** expone path relativo al root para que JS construya URLs.

## Convenciones

- Idioma: español (logs, docstrings, commits, docs).
- Logs con emojis (📖 📊 ✅ ❌ 🏗️ 📁 📄). Mantener.
- Autor: Jorge Alberto (jagilren@gmail.com) — PROYECTOS CON INGENIERIA S.A.S. (Medellín).
- Branch principal: `master` (no `main`).
- `docs/assets/` se **preserva** entre corridas del migrador (no `rmtree` total).

## Decisiones tomadas (no revisitar sin causa)

- **No Jekyll.** HTML estático puro; `.nojekyll` desactiva procesamiento. Evaluado y descartado en mayo 2026 (requería reescribir migrador para emitir Markdown + front-matter).
- **`master` (no `main`).** Renombrar requiere reconfigurar Pages.
- **Site title preserva siglas ≤3 letras en mayúsculas** (`QR Groupe Seb`, no `Qr Groupe Seb`).
- **Fuente de datos = Excel.** No scrapear, no CMS — el cliente entrega Excel.

## Limitaciones

- Imágenes: solo las embebidas en el Excel (extracción por frecuencia, umbral 5).
- Tablas complejas dentro de una propiedad → texto plano.
- INSTRUMENTOS: categoría existe pero el Excel actual aporta 0; agregar hojas para poblarla.
- Local vs github.io desincronizado: server local suele estar sirviendo una carpeta vieja. Verificar tamaño del CSS con `curl localhost:8000/styles.css | wc -c`.

## Estado de archivos

| Archivo | Estado |
|---|---|
| [docs/](docs/) | ✅ Sitio publicado (40 TAGs, 24 EQUIPOS + 16 TANQUES + 0 INSTRUMENTOS) |
| [convert_fichas_to_template.py](convert_fichas_to_template.py) | ✅ Paso 1 |
| [excel_migrator.py](excel_migrator.py) | ✅ Paso 3 |
| [update_site_from_excel.sh](update_site_from_excel.sh) | ✅ Wrapper |
| [generate_excel_template.py](generate_excel_template.py) | ✅ Plantilla vacía desde sitio existente |
| [generate_tag_resources_template.py](generate_tag_resources_template.py) | ✅ Bootstrap/merge de TAG_RESOURCES.xlsx |
| [plantilla_sitio.xlsx](plantilla_sitio.xlsx) | ✅ Fuente de datos (editable a mano) |
| [TAG_RESOURCES.xlsx](TAG_RESOURCES.xlsx) | ✅ Enlaces por TAG (Specifications/Handbook_Manual/Maintenance) |
| `docs/assets/images/` | ✅ 40 carpetas TAG, ~7.3 MB, manifest.json |
| Logos RPCI y cliente | ⚠️ SVG placeholders en `excel_migrator.py` — pendiente sustituir por archivos reales |
| Hyperlinks Ficha Técnica/Curva en plantilla y Specifications/Handbook_Manual/Maintenance en TAG_RESOURCES | ⚠️ Vacíos por ahora — llenar a mano con Ctrl+K |
| `.vscode/launch.json`, `.vscode/tasks.json` | ⚠️ Revisar que apunten al flujo Excel actual |
