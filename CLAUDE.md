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

`gui.py` (NiceGUI) — interfaz local en `http://localhost:8080`. Lanza con `./launch_gui.sh` o `python3 gui.py`.

Permite configurar:
- **📁 Carpeta destino** (default `docs/`, editable).
- **🖼️ Logo del cliente** (drag-and-drop, sobrescribe `<dest>/assets/logos/LogoCliente.png`).
- **🔗 Enlace del logo del cliente** (`logos.right_href`) — URL externa que abre en pestaña nueva al clickear el logo del cliente. Vacío → logo no clickeable (se renderiza como `<div>` en vez de `<a>`).
- **📝 Título del sitio** (`site_title`) — reemplaza el texto por defecto "QR Groupe SEB".
- **🎨 Color del tema** (color picker → deriva paleta completa de 10 vars + actualiza swatches de preview en vivo).
- **📄 Archivo de fichas técnicas xlsx** (opcional; se guarda como `fichas_source.xlsx` en raíz).
- **📄 TAG_RESOURCES.xlsx** (opcional; sobrescribe el existente).
- **🔄 Switch "Forzar regeneración"** (ver tabla abajo).

Acciones:
- **Generar sitio** — corre el pipeline completo, log streaming al UI.
- **Ver sitio** — lanza `http.server` en `:8000` apuntando al destino actual, abre browser.

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
- Imágenes: parsea `.xlsx` como ZIP, recorre `xl/drawings/drawing*.xml` y copia las específicas a `docs/assets/images/<TAG>/`. Tres filtros encadenados:
  1. **Posición + tamaño** (`HEADER_ANCHOR_MAX_ROW=2`, `LOGO_MAX_HEIGHT_ROWS=5`): descarta imágenes ancladas en filas Excel 1-3 cuando miden ≤5 filas de alto (logos del header). Si mide ≥6 filas → es foto del equipo y se conserva aunque esté arriba.
  2. **Frecuencia** (`IMAGE_COMMON_THRESHOLD=30`, subido de 5): descarta imágenes presentes en >30 hojas (logos universales que sobreviven el filtro 1).
  3. **Fallback**: si tras los 2 filtros una hoja queda en 0 imágenes, conserva las del filtro 1 (mejor repetir que dejar vacío).
- **Búsqueda recursiva de blips**: `anchor.iter("a:blip")` captura imágenes dentro de `xdr:grpSp` (group shapes) además de `xdr:pic` directas. Sin esto, imágenes agrupadas con captions (caso `400-C-01A/B`) se perdían.
- Flag `--images-only`: re-extrae imágenes sin regenerar `plantilla_sitio.xlsx` (preserva hyperlinks editados a mano).

## UI

- **Acordeón compartido** (`.acc-item / .acc-header / .acc-body`) en 3 niveles: home (por categoría), categoría (por item con preview 3 props), item (por propiedad). Toggle vía `.open`, inician cerrados.
- **Banner** sticky con degradé: `[☰ menú] [🏠 home] [logo RPCI → rpci.com.co ↗] | título centrado | [logo cliente → URL configurable] [🔍 búsqueda]`. Ambos logos son links externos opcionales: el izquierdo siempre lleva un href (default `rpci.com.co`); el derecho solo si `logos.right_href` está set en el config (sino se renderiza como `<div>` no clickeable). El botón home es la navegación interna al index.
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
    "right": "assets/logos/LogoCliente.png", "right_alt": "Cliente",
    "right_href": "https://alimentosdvida.com.co"
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
| `urls.txt` | Listado plano `CATEGORIA_SINGULAR,URL` — una línea por TAG. Categorías en singular: `EQUIPO`, `INSTRUMENTO`, `TANQUE`. **Base URL derivada del `git remote origin`** (no hardcoded): `https://<owner>.github.io/<repo>/`. Si no hay git, cae al `site_url` del config. Esto garantiza que los QRs apunten al destino real del push aunque cambies de repo. Útil para generar stickers QR o auditar enlaces |
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
- **`urls.txt` deriva la base URL del git remote, no del config.** Los QRs físicos deben apuntar al repo real al que se está pusheando. Si cambiás de `jagilren/groupe_seb_qr` a `dvida-rpci/dvida-qr`, las URLs se ajustan solas en la próxima corrida. `site_url` del config sigue gobernando el banner/metadata/README pero NO `urls.txt`.
- **Filtro de logos por posición + tamaño** (mayo 2026). Antes solo había filtro por frecuencia (`IMAGE_COMMON_THRESHOLD`), que descartaba imágenes legítimas reutilizadas en familias de equipos. Ahora la heurística primaria es: anchor en filas 1-3 + altura ≤5 filas = logo del header. Conserva fotos grandes ancladas arriba (caso real: hojas `400-C-01A/B` donde el operador puso la foto del equipo en posición no convencional).
- **Búsqueda recursiva de blips** (`anchor.iter("a:blip")`). El parser viejo solo capturaba `<xdr:pic>` como hijo directo del anchor. Las imágenes dentro de `<xdr:grpSp>` (agrupadas con captions) se perdían silenciosamente. El fix recorre toda la jerarquía del anchor.
- **GUI: upload handlers async**. NiceGUI 3.x cambió la API: `e.content.read()` (sync) → `await e.file.read()` (async). Sin el `async def` + `await`, los uploads fallan silenciosamente y `state["fichas_path"]` queda en None.
- **GUI: `on_click=lambda: f()` en vez de `asyncio.create_task(f())`**. `create_task` desacopla del slot context de NiceGUI → `ui.notify` crashea con "slot stack empty". Lambda + NiceGUI await automático preserva el context.
- **GUI: color picker via `on_change=` en el constructor**. El intento de bindear con `.on("change", ...)` no dispara en `ui.color_input` (Quasar usa otro nombre interno de evento). Pasar el handler como parámetro al constructor es la forma canónica.

## Limitaciones

- Imágenes: solo las embebidas en el Excel. Filtro encadenado posición + frecuencia (ver "Convert fichas → plantilla" arriba).
- Tablas complejas dentro de una propiedad → texto plano.
- INSTRUMENTOS: categoría existe pero los Excel observados aportan 0; agregar hojas para poblarla.
- `convert_fichas_to_template.py` sigue extrayendo imágenes a `docs/assets/images/` (hardcoded). Cuando el destino del migrator no es `docs/`, la GUI hace `merge_assets_into()` para propagar.
- **Auto-recovery de imágenes**: `excel_migrator.py` ejecuta `ensure_images()` al inicio de `main()`. Si `<output>/assets/images/` está vacío, `discover_fichas_xlsx()` escanea cualquier `*.xlsx` en raíz (independiente del nombre, excluyendo plantilla y TAG_RESOURCES) y re-extrae vía import de `extract_images`. Manualmente: `python3 convert_fichas_to_template.py <xlsx> --images-only`.
- `extract_pairs` captura una pareja label-value por fila. Layouts con múltiples pares por fila (tipo grid) perderían pares; no se han observado hasta ahora.
- TAGs sin foto real del equipo en el xlsx (solo logos en filas 1-3 con altura pequeña) salen sin imagen tras el filtro nuevo. Es correcto — la versión anterior mostraba los logos del header como si fueran fotos del equipo (engañoso).

## Recuperación / troubleshooting

- **Imágenes borradas en disco** (working tree) pero presentes en HEAD → `git checkout HEAD -- docs/assets/images/` las restaura. Pasó en mayo 2026 antes del cleanup defensivo. Alternativa: re-correr el migrator — `ensure_images()` las regenera desde la xlsx canonical si está disponible.
- **Puerto 8000 ocupado al pulsar "Ver sitio"** → un `python3 -m http.server` huérfano de otra sesión. `pkill -f "http.server"` lo mata; la GUI ya lo detecta y notifica.
- **El sitio en `localhost:8000` se ve viejo aunque regeneraste** → casi siempre es el preview server apuntando al destino anterior. La GUI lo reinicia al cambiar destino; verificar el log: `🚀 Lanzando preview en http://localhost:8000 desde <ruta>`.
- **El buscador no devuelve resultados al abrir el HTML con doble click** → ya no debería pasar. Si pasa: confirmar que el destino tiene `search-index.js` (no solo `.json`) y que el `<head>` lo carga con `<script src="search-index.js">`.
- **El sitio sale con TAGs/propiedades del proyecto anterior** → la plantilla quedó vieja porque `convert_fichas` no corrió. Activá el switch **🔄 Forzar regeneración** en la GUI y asegurate de tener la xlsx nueva en raíz o subila por el widget.
- **Solo 1 propiedad por TAG en la plantilla** → bug histórico del `extract_pairs` viejo (ventana de búsqueda muy corta). Resuelto en mayo 2026. Si vuelve a pasar con un layout nuevo: verificar que `is_valid_label` no esté rechazando los labels reales y que el value esté efectivamente en la fila (no en celda merged externa).
- **TAG aparece sin imagen aunque la xlsx la tiene** → puede ser una imagen dentro de `<xdr:grpSp>` (agrupada con caption). Resuelto con `anchor.iter("a:blip")`. Si pasa con un xlsx nuevo: verificar que el anchor exista (parsear `xl/drawings/drawingN.xml` con un grep `<a:blip` o `<xdr:grpSp`).
- **Imagen es un logo pero no se filtra** → probablemente está anclada en filas 4+ (fuera de `HEADER_ANCHOR_MAX_ROW=2`) o mide más de `LOGO_MAX_HEIGHT_ROWS=5` filas. Ajustar las constantes en `convert_fichas_to_template.py` o pedirle al usuario que mueva el logo a las primeras 3 filas en el xlsx.
- **El color elegido en la GUI no se aplica** → bug histórico del `color_input.on("change", ...)` que no disparaba. Resuelto pasando `on_change=` en el constructor. Si vuelve a pasar: probar con un browser distinto, o verificar en el log de la GUI que aparece `🎨 Color seleccionado: #...` al cambiar.
- **Upload de la GUI falla silenciosamente** → API de NiceGUI cambió en 3.x. Confirmar que el handler es `async def` y usa `await e.file.read()` en vez de `e.content.read()`.

## Estado de archivos

| Archivo | Estado |
|---|---|
| [docs/](docs/) | ⚠️ Solo `assets/` actualmente (sitio HTML pendiente de regenerar tras el último `convert_fichas`) |
| [convert_fichas_to_template.py](convert_fichas_to_template.py) | ✅ Paso 1 — refactor mayo 2026 (extracción layout-agnóstica + flag `--images-only`) |
| [excel_migrator.py](excel_migrator.py) | ✅ Paso 4 — acepta `output_dir`, `ensure_images()` auto-recovery, cleanup defensivo |
| [update_site_from_excel.sh](update_site_from_excel.sh) | ✅ Wrapper CLI |
| [generate_excel_template.py](generate_excel_template.py) | ✅ Plantilla vacía desde sitio existente |
| [generate_tag_resources_template.py](generate_tag_resources_template.py) | ✅ Bootstrap/merge de TAG_RESOURCES.xlsx |
| [gui.py](gui.py) + [launch_gui.sh](launch_gui.sh) | ✅ GUI NiceGUI (puerto 8080) — input título sitio + input URL logo cliente + color picker live + switch "Forzar regeneración" + auto-detect de xlsx + uploads async |
| [plantilla_sitio.xlsx](plantilla_sitio.xlsx) | ✅ Fuente de datos — última regeneración desde NI00011 (36 TAGs, 96 propiedades) |
| [TAG_RESOURCES.xlsx](TAG_RESOURCES.xlsx) | ✅ Enlaces por TAG |
| [site_config.json](site_config.json) | ✅ Tema editable vía GUI (color picker + título del sitio) |
| [comandos.txt](comandos.txt) | ✅ Cheatsheet de comandos CLI por sección |
| [New_Laptop.txt](New_Laptop.txt) | ✅ Guía de instalación en laptop nuevo (Linux/Windows/macOS/WSL sin VSCode) |
| [windows_launchers/](windows_launchers/) | ✅ 4 `.bat` para Windows: lanzar (nativo/WSL), parar, instalar acceso directo + auto-arranque |
| `NI00011 Fichas Técnicas_Equipos STARnD GROUP SEB V3.xlsx` | ✅ Source xlsx actual en raíz |
| `docs/assets/images/` | ✅ 37 carpetas TAG con imágenes extraídas (filtro posición+frecuencia activo) |
| `docs/assets/logos/LogoCliente.png` | ✅ Logo del cliente |
| `docs/assets/logos/LogoRPCI.png` | ⚠️ Falta — el banner muestra hueco en posición izquierda hasta agregarlo |
| `docs/assets/icons/generic-image.svg` | ✅ Fallback de thumbnail |
| Hyperlinks de recursos | ⚠️ Llenado parcial — algunas celdas vacías |
