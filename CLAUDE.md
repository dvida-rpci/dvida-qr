# CLAUDE.md

Guía para Claude Code en este repositorio.

## Qué es

Generador de sitio estático desde Excel para fichas técnicas industriales, publicado en GitHub Pages.

- **Input:** xlsx con fichas técnicas del cliente (una hoja por TAG). Ejemplos usados: `NP00033 Fichas Técnicas...xlsx` (proyecto PTAR STARnD), `NI00011 Fichas Técnicas_Equipos STARnD GROUP SEB V3.xlsx`.
- **Output:** carpeta destino (default `docs/`) con HTML/CSS/JS vainilla.
- **Live:** https://jagilren.github.io/groupe_seb_qr/

## Config

| Item | Valor |
|---|---|
| Remote | `https://github.com/jagilren/groupe_seb_qr` |
| Branch | `master` |
| Pages serves | `/docs` |
| Stack | Python 3.12 + openpyxl + nicegui (WSL Ubuntu 24) |
| Setup | `pip3 install --break-system-packages openpyxl nicegui` |

**Crítico:** Pages sirve desde `/docs`, no desde la raíz. Solo lo que termina en `docs/` llega a producción. La GUI permite destinos arbitrarios para staging.

## Flujo (CLI)

1. `convert_fichas_to_template.py <xlsx>` — fichas crudas → `plantilla_sitio.xlsx` (+ extrae imágenes a `docs/assets/images/<TAG>/`).
2. `generate_tag_resources_template.py` — crea/actualiza `TAG_RESOURCES.xlsx` (merge: preserva hyperlinks existentes).
3. Edición manual: `plantilla_sitio.xlsx` (Ficha Técnica/Curva) y `TAG_RESOURCES.xlsx` (Specifications/Handbook_Manual/Maintenance) con `Ctrl+K`.
4. `excel_migrator.py plantilla_sitio.xlsx <output_dir>` — genera el sitio (lee también `TAG_RESOURCES.xlsx` + `site_config.json` si existen).
5. `git add docs/ && git commit && git push` → Pages recompila en ~1–2 min.

Wrapper end-to-end:
```bash
./update_site_from_excel.sh                 # regenera docs/
./update_site_from_excel.sh --from-fichas   # re-convierte fichas primero
./update_site_from_excel.sh --push          # regenera + commit + push
```

`comandos.txt` en la raíz tiene los comandos más usados organizados por flujo.

## Flujo (GUI alternativa)

`gui.py` (NiceGUI) — interfaz local en `http://localhost:8080`. Lanza con `./launch_gui.sh`.

Permite: elegir carpeta destino arbitraria, subir logo del cliente, elegir un color base (deriva paleta completa), subir el xlsx de fichas, subir TAG_RESOURCES.xlsx, **Generar**, **Ver sitio** (lanza http.server en `:8000` apuntando al destino actual).

### Switch "🔄 Forzar regeneración" (default OFF)

| Switch | Upload por widget | Comportamiento |
|---|---|---|
| OFF | No | Usa `plantilla_sitio.xlsx` tal cual está; no toca el contenido |
| OFF | Sí | `convert_fichas` corre con el xlsx subido (sobrescribe plantilla) |
| ON | No | **Auto-detecta** xlsx de fichas en raíz del repo (cualquier `*.xlsx` ≠ plantilla/TAG_RESOURCES) y usa el más reciente |
| ON | Sí | `convert_fichas` corre con el xlsx subido |
| ON | Ni upload ni xlsx en raíz | Aborta con error claro |

**No borra archivos físicamente** — `convert_fichas` sobrescribe el contenido de plantilla y extrae imágenes nuevas (la estructura columnar pivotal se preserva).

### Otros detalles de la GUI

- Si el destino difiere de `docs/`, `merge_assets_into()` copia archivos faltantes de `docs/assets/` al destino antes de generar (sin pisar uploads recientes).
- `convert_fichas_to_template.py` sigue extrayendo imágenes a `docs/assets/images/` (canonical); el merge las propaga al destino elegido.
- El servidor de preview se reinicia si cambia el destino. Cuidado con servidores http.server huérfanos en `:8000` — la GUI los detecta y avisa.
- **Validación de destino** (también la hace el migrator): si el campo "Carpeta destino" se llama `assets`/`images`/`logos`/`icons` o tiene `assets/` en su path, la GUI aborta antes de tocar el filesystem.

## Mapping Excel → UI

| Origen | Renderizado |
|---|---|
| `TAG` | slug URL + breadcrumb + parte del h1 |
| `SERVICIO` (columna de propiedades) | parte del h1 y `<title>`: `<TAG> - <SERVICIO\|"no definido">` |
| `Categoría` | carpeta `<output>/<cat>/<tag>.html` + grupo en nav |
| `Título` | usado solo en el index de categoría (no en el h1 de la ficha) |
| Otras columnas con valor | acordeón con label = h2 |
| `Ficha Técnica`, `Curva` (plantilla) | botones en "Documentos y enlaces" (target=_blank) |
| imágenes en `<output>/assets/images/<TAG>/` | botón "Ver N imágenes" con thumbnail (primera imagen) → lightbox. Fallback: `assets/icons/generic-image.svg` |
| `TAG_RESOURCES.xlsx` (`Specifications`, `Handbook_Manual`, `Maintenance`) | botones "Especificaciones / Manual / Mantenimiento" en "Documentos y enlaces" |

## Convert fichas → plantilla (paso 1)

- Layout vertical `LABEL | VALOR` en cada hoja. Tolerante a gaps variables entre label y value (NP00033 tenía adjacente, NI00011 tiene gap de 5 columnas).
- **Estrategia de `extract_pairs`** (refactor mayo 2026): por cada fila → encuentra el **último valor no vacío** (de derecha a izquierda) = VALUE → escanea hacia la izquierda buscando el primer string que pase `is_valid_label()` = LABEL. Una pareja máxima por fila (suficiente para los layouts industriales observados).
- `IGNORE_LABELS` filtra block names puros (`GENERAL`, `EQUIPO`, `TANQUE`, `INSTRUMENTO`, `NOTAS`, `FICHA TÉCNICA`), metadata administrativa (`UBICACIÓN`, `PLANTA`, `VERSIÓN`, `FECHA`, `ELABORÓ`, `REVISÓ`, `APROBÓ`, `SOPORTE`, `REV.`), constantes pegadas (`STARND ETAPA 1 Y 2`, etc.) y `TAG N°`. **`FLUIDO` NO está aquí** porque también es un label legítimo de propiedad ("FLUIDO: ARnD"); se distingue por contexto.
- `is_valid_label` rechaza 2-3 chars todos en mayúscula y solo letras (filtra iniciales como `DG`, `WO` del header de revisores). Mantiene labels mixtos como `pH`.
- **Validación de nombre de hoja**: solo hojas que matchean `^\d{3}-[A-Z]+-` se procesan (filtra `Hoja3`, `Sheet1`, hojas auxiliares). Hojas con 0 propiedades también se descartan.
- Una hoja puede expandirse a múltiples TAGs: `100-P-01 A_B` → `100-P-01A`, `100-P-01B`; `400-MX-01_02_03_04` → 4 TAGs.
- Categoría inferida del tipo: `TK|R|F|SD` → TANQUES, `P|MX|M|C|PS` → EQUIPOS, `AIT|FIT|SV|LT` → INSTRUMENTOS.
- Imágenes: parsea `.xlsx` como ZIP, filtra plantillas (umbral usadas en >5 hojas) y copia las específicas a `docs/assets/images/<TAG>/`.
- Flag `--images-only`: re-extrae imágenes sin regenerar `plantilla_sitio.xlsx` (preserva hyperlinks editados a mano).

## UI

- **Acordeón compartido** (`.acc-item / .acc-header / .acc-body`) en 3 niveles: home (por categoría), categoría (por item con preview 3 props), item (por propiedad). Toggle vía `.open`, inician cerrados.
- **Banner** sticky con degradé: `[☰ menú] [🏠 home] [logo RPCI → rpci.com.co ↗] | título centrado | [logo cliente] [🔍 búsqueda]`. El logo izquierdo es link externo; el botón home es la navegación interna al index.
- **Búsqueda**: índice embebido como `window.__SEARCH_INDEX__` vía `<script src="search-index.js">` (funciona también con `file://`, no depende de `fetch()`). Debounce 80ms, ↑↓ Enter Esc, `<mark>` highlight. Fallback: si la variable no está, `fetch('search-index.json?_t=…')`.
- **Lightbox** imágenes: keyboard arrows, swipe táctil 50px, clase `.single` oculta nav si hay 1 imagen.
- **Mobile-first:** topbar+hamburger <900px, sidebar overlay (transform + backdrop 45%), touch targets ≥44px, grid 3/2/1 cols (desktop/mobile/≤380px), `<400px` oculta `.acc-meta`, thumbnail del botón "Ver imagen" pasa a 18×18 en mobile, Esc cierra sidebar, scroll bloqueado mientras abierto, auto-scroll a item activo del menú.
- **`<body data-rel="...">`** expone path relativo al root para que JS construya URLs.

## Configuración (`site_config.json`)

Archivo opcional en la raíz; sobrescribe defaults sin tocar Python. Schema:

```json
{
  "site_title": "QR Groupe SEB",
  "banner_title_full": "Documentación Técnica — PTAR STARnD",
  "banner_title_short": "PTAR STARnD",
  "site_url": "https://jagilren.github.io/groupe_seb_qr/",
  "theme": {
    "accent": "#7c3aed", "accent_hover": "#5f14df",
    "banner_gradient": "linear-gradient(135deg, #c9aef7 0%, #7c3aed 60%, #6315e8 100%)",
    "banner_text": "#ffffff", "banner_shadow": "0 4px 14px rgba(124,58,237,0.25)",
    "content_bg": "#ffffff", "card_bg": "#ffffff",
    "text": "#1f2328", "text_muted": "#57606a", "border": "#f8f4fe"
  },
  "logos": {
    "left": "assets/logos/LogoRPCI.png", "left_alt": "RPCI", "left_href": "https://rpci.com.co",
    "right": "assets/logos/LogoCliente.png", "right_alt": "Cliente"
  }
}
```

- El bloque `theme` se inyecta como un segundo `:root { ... }` al final del CSS (cascada sobrescribe los defaults).
- El `accent` también se usa para `<meta theme-color>` (barra del navegador móvil).
- La GUI escribe este archivo automáticamente al pulsar **Generar** (deriva los 10 vars desde el color base usando `colorsys` + luminancia WCAG para el `banner_text`).

## Archivos generados por `excel_migrator.py`

Bajo `<output_dir>/`:

| Archivo | Contenido |
|---|---|
| `index.html`, `<cat>/index.html`, `<cat>/<tag>.html` | Páginas |
| `styles.css`, `script.js` | Assets embebidos en el migrator |
| `search-index.json` + `search-index.js` | Mismo contenido; `.js` lo carga el HTML vía `<script>` (file://-safe), `.json` queda para consumo externo |
| `urls.txt` | Listado plano `CATEGORIA_SINGULAR,URL` — una línea por TAG. Categorías en singular: `EQUIPO`, `INSTRUMENTO`, `TANQUE`. URL absoluta usando `site_url`. Útil para generar QR/stickers o auditar enlaces |
| `migration_metadata.json` | Trazabilidad (timestamp, conteos, datos por TAG) |
| `README.md` | Pie de información del deploy |
| `.nojekyll` | Desactiva Jekyll en GitHub Pages |
| `assets/icons/generic-image.svg` | Fallback del thumbnail si la imagen del TAG no carga |

**Cleanup whitelist:** entre corridas el migrador solo borra los archivos de la tabla de arriba + las subcarpetas de categoría (`equipos/`, `instrumentos/`, `tanques/`). Cualquier otro archivo o carpeta en `output_dir` (incluido todo bajo `assets/`) se preserva. Aborta con error si el `output_dir` se llama `assets`/`images`/`logos`/`icons` o tiene `assets/` en su path (evita wipeos accidentales).

## Convenciones

- Idioma: español (logs, docstrings, commits, docs).
- Logs con emojis (📖 📊 ✅ ❌ 🏗️ 📁 📄). Mantener.
- Autor: Jorge Alberto (jagilren@gmail.com) — PROYECTOS CON INGENIERIA S.A.S. (Medellín).
- Branch principal: `master` (no `main`).

## Decisiones tomadas (no revisitar sin causa)

- **No Jekyll.** HTML estático puro; `.nojekyll` desactiva procesamiento. Evaluado y descartado en mayo 2026.
- **`master` (no `main`).** Renombrar requiere reconfigurar Pages.
- **Site title preserva siglas ≤3 letras en mayúsculas** (`QR Groupe Seb`, no `Qr Groupe Seb`).
- **Fuente de datos = Excel.** No scrapear, no CMS.
- **`search-index.js` además del `.json`.** Se evaluó solo `.json` con fetch en mayo 2026 y se descartó: rompe en `file://` (operario que abre el HTML directamente sin servidor). El `.js` cargado vía `<script>` no tiene esa restricción.
- **GUI con NiceGUI (web local).** Evaluado vs Tkinter/Qt en mayo 2026: WSL + Tkinter tiene rendering quirks, NiceGUI usa el browser que el usuario ya tiene abierto.
- **Cleanup whitelist en vez de "borra todo excepto assets/".** El enfoque viejo (skip-by-name) wipeaba contenido foráneo si el destino apuntaba a un subdir tipo `docs/assets/images`: ninguna subcarpeta se llamaba `assets`, así que iban todas al `rmtree`. La whitelist solo borra los archivos generados conocidos + subcarpetas de categoría.
- **`extract_pairs` con "last value, scan left for label" (mayo 2026).** El enfoque viejo (label + value en celdas adyacentes ≤3 cols) fallaba en layouts con gap mayor (NI00011 tiene gap de 5). El nuevo es layout-agnóstico. Tradeoff: solo captura una pareja por fila, pero los xlsx industriales observados siempre tienen una pareja por fila.
- **Switch "Forzar regeneración" NO borra archivos.** El usuario clarificó que "regenerar plantilla" significa re-poblar contenido vía `convert_fichas`, no `unlink()`. La estructura columnar pivotal se preserva automáticamente porque convert_fichas reescribe el xlsx con el mismo esqueleto.

## Limitaciones

- Imágenes: solo las embebidas en el Excel (extracción por frecuencia, umbral 5).
- Tablas complejas dentro de una propiedad → texto plano.
- INSTRUMENTOS: categoría existe pero los Excel observados aportan 0; agregar hojas para poblarla.
- `convert_fichas_to_template.py` sigue extrayendo imágenes a `docs/assets/images/` (hardcoded). Cuando el destino del migrator no es `docs/`, la GUI hace `merge_assets_into()` para propagar.
- **Auto-recovery de imágenes**: `excel_migrator.py` ejecuta `ensure_images()` al inicio de `main()`. Si `<output>/assets/images/` está vacío y existe un xlsx de fichas conocido (`NP00033...xlsx` o `fichas_source.xlsx`) en raíz, re-extrae automáticamente vía import de `extract_images`. Manualmente: `python3 convert_fichas_to_template.py <xlsx> --images-only`.
- `extract_pairs` captura una pareja label-value por fila. Layouts con múltiples pares por fila (tipo grid) perderían pares; no se han observado hasta ahora.

## Recuperación / troubleshooting

- **Imágenes borradas en disco** (working tree) pero presentes en HEAD → `git checkout HEAD -- docs/assets/images/` las restaura. Pasó en mayo 2026 antes del cleanup defensivo. Alternativa: re-correr el migrator — `ensure_images()` las regenera desde la xlsx canonical si está disponible.
- **Puerto 8000 ocupado al pulsar "Ver sitio"** → un `python3 -m http.server` huérfano de otra sesión. `pkill -f "http.server"` lo mata; la GUI ya lo detecta y notifica.
- **El sitio en `localhost:8000` se ve viejo aunque regeneraste** → casi siempre es el preview server apuntando al destino anterior. La GUI lo reinicia al cambiar destino; verificar el log: `🚀 Lanzando preview en http://localhost:8000 desde <ruta>`.
- **El buscador no devuelve resultados al abrir el HTML con doble click** → ya no debería pasar. Si pasa: confirmar que el destino tiene `search-index.js` (no solo `.json`) y que el `<head>` lo carga con `<script src="search-index.js">`.
- **El sitio sale con TAGs/propiedades del proyecto anterior** → la plantilla quedó vieja porque `convert_fichas` no corrió. Activá el switch **🔄 Forzar regeneración** en la GUI y asegurate de tener la xlsx nueva en raíz o subila por el widget.
- **Solo 1 propiedad por TAG en la plantilla** → bug histórico del `extract_pairs` viejo (ventana de búsqueda muy corta). Resuelto en mayo 2026. Si vuelve a pasar con un layout nuevo: verificar que `is_valid_label` no esté rechazando los labels reales y que el value esté efectivamente en la fila (no en celda merged externa).

## Estado de archivos

| Archivo | Estado |
|---|---|
| [docs/](docs/) | ⚠️ Solo `assets/` actualmente (sitio HTML pendiente de regenerar tras el último `convert_fichas`) |
| [convert_fichas_to_template.py](convert_fichas_to_template.py) | ✅ Paso 1 — refactor mayo 2026 (extracción layout-agnóstica + flag `--images-only`) |
| [excel_migrator.py](excel_migrator.py) | ✅ Paso 4 — acepta `output_dir`, `ensure_images()` auto-recovery, cleanup defensivo |
| [update_site_from_excel.sh](update_site_from_excel.sh) | ✅ Wrapper CLI |
| [generate_excel_template.py](generate_excel_template.py) | ✅ Plantilla vacía desde sitio existente |
| [generate_tag_resources_template.py](generate_tag_resources_template.py) | ✅ Bootstrap/merge de TAG_RESOURCES.xlsx |
| [gui.py](gui.py) + [launch_gui.sh](launch_gui.sh) | ✅ GUI NiceGUI (puerto 8080) — switch "Forzar regeneración" + auto-detect de xlsx |
| [plantilla_sitio.xlsx](plantilla_sitio.xlsx) | ✅ Fuente de datos — última regeneración desde NI00011 (36 TAGs, 96 propiedades) |
| [TAG_RESOURCES.xlsx](TAG_RESOURCES.xlsx) | ✅ Enlaces por TAG |
| [site_config.json](site_config.json) | ✅ Tema (paleta lila pastel actual) |
| [comandos.txt](comandos.txt) | ✅ Cheatsheet de comandos CLI por sección |
| `NI00011 Fichas Técnicas_Equipos STARnD GROUP SEB V3.xlsx` | ✅ Source xlsx actual en raíz |
| `docs/assets/images/` | ✅ Carpetas TAG con imágenes extraídas |
| `docs/assets/logos/LogoRPCI.png`, `LogoCliente.png` | ✅ Logos reales |
| `docs/assets/icons/generic-image.svg` | ✅ Fallback de thumbnail |
| Hyperlinks de recursos | ⚠️ Llenado parcial — algunas celdas vacías |
