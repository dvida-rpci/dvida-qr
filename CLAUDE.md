# CLAUDE.md

Guía para Claude Code cuando trabaje en este repositorio.

## Qué es este repo

Aplicativo para **generar la estructura de archivos de un sitio web estático a partir de un Excel** (fichas técnicas industriales) y publicarlo en **GitHub Pages**.

- **Input:** un archivo Excel con fichas técnicas (una hoja por TAG) entregado por el cliente.
- **Output:** carpeta `docs/` con HTML/CSS/JS estáticos lista para subir a GitHub y servir vía Pages.
- **Sitio en vivo:** [docs/](docs/) → https://jagilren.github.io/groupe_seb_qr/ (planta industrial QR Groupe SEB, Itagüí–Medellín).

El repo está enlazado a `https://github.com/jagilren/groupe_seb_qr`, branch `master`. GitHub Pages está configurado para servir desde la carpeta `/docs`.

## URLs y configuración

| Item | Valor |
|---|---|
| Remote git | `https://github.com/jagilren/groupe_seb_qr` |
| Branch publicada | `master` |
| Carpeta de Pages | `/docs` (raíz del repo) |
| URL pública | https://jagilren.github.io/groupe_seb_qr/ |
| Usuario GitHub | jagilren |

**Crítico:** el sitio NO se publica desde la raíz del repo, se publica desde [docs/](docs/). Cualquier cambio al sitio debe terminar en esa carpeta para que llegue a producción.

## Flujo de trabajo habitual

```
Excel fichas técnicas (1 hoja/TAG)
        │
        │  (1) convert_fichas_to_template.py
        ▼
plantilla_sitio.xlsx (1 hoja, todos los TAGs)
        │
        │  (2) edición manual (hyperlinks, ajustes)
        ▼
plantilla_sitio.xlsx editada
        │
        │  (3) excel_migrator.py  [⏳ pendiente]
        ▼
docs/  (HTML estático)
        │
        │  (4) git add docs/ && git commit && git push
        ▼
https://jagilren.github.io/groupe_seb_qr/
```

### Paso 1 — Convertir fichas técnicas a plantilla unificada

Formato de entrada esperado (fichas técnicas crudas):

- Excel con **una hoja por TAG**, layout vertical de pares `LABEL | VALOR`.
- **Ignorar** las filas superiores agrupadas (`UBICACIÓN`, `PLANTA`).
- **Ignorar** el encabezado: `FICHA TÉCNICA`, `Versión`, `Fecha`, `Elaboró`, `Revisó`.
- Bloque `GENERAL`: `TAG N°`, `SERVICIO`, `FUNCIÓN`.
- Bloque `FLUIDO`: descripción, fluido, pH, densidad, temperatura.
- Bloque `TANQUE | EQUIPO | INSTRUMENTO`: propiedades técnicas específicas (Tipo, Material, Dimensiones, etc.).
- **Ignorar** el bloque `NOTAS`.

Una hoja puede representar **varios TAGs** cuando aplica a unidades equivalentes:
- `100-P-01 A_B` → expande a `100-P-01A`, `100-P-01B`.
- `400-MX-01_02_03_04` → expande a `400-MX-01`, `400-MX-02`, `400-MX-03`, `400-MX-04`.

Comando:
```bash
python3 convert_fichas_to_template.py "NP00033 Fichas Técnicas Equipos 20250408 DG.xlsx"
# o sin args, usa el default NP00033 si está en la raíz
python3 convert_fichas_to_template.py
```

Genera [plantilla_sitio.xlsx](plantilla_sitio.xlsx) con una sola hoja `Datos`:
- Columnas: `TAG`, `Categoría`, `Título`, `<propiedad 1>`, …, `<propiedad N>`, `Ficha Técnica`, `Curva`.
- Categoría inferida automáticamente del tipo en el TAG:
  - `TK`, `R`, `F`, `SD` → **TANQUES**
  - `P`, `MX`, `M`, `C`, `PS` → **EQUIPOS**
  - `AIT`, `FIT`, `SV`, `LT` → **INSTRUMENTOS**
- Dropdown de categoría en columna B (override manual si la inferencia falla).
- Celdas vacías = no se genera esa sección en el sitio.
- `Ficha Técnica` y `Curva` quedan **vacías** (las fichas crudas no aportan links); se llenan a mano con hyperlinks `Ctrl+K`.

### Paso 2 — Editar la plantilla a mano

Abrir el Excel y:
- **Llenar hyperlinks** de `Ficha Técnica` / `Curva` donde aplique (Ctrl+K en la celda).
- **Consolidar columnas casi-duplicadas** si las hay (ej. `POTENCIA (HP)` vs `POTENCIA (W)` — el convertidor las deja separadas porque vienen así del origen).
- **Agregar TAGs nuevos** simplemente como filas adicionales.
- **Editar el Título** si quieres que difiera del TAG.

### Paso 3 — Generar el sitio desde la plantilla

> ⏳ **Pendiente:** `excel_migrator.py` + `update_site_from_excel.sh`. El flujo será:
>
> ```bash
> ./update_site_from_excel.sh         # regenera docs/ sin pushear
> ./update_site_from_excel.sh --push  # regenera y publica a GitHub Pages
> ```

### Paso 4 — Publicar

```bash
# Ver local antes de pushear
cd docs && python3 -m http.server 8000
# Desde Windows: cmd.exe /c start http://localhost:8000/

# Publicar
git add docs/
git commit -m "Actualizar sitio"
git push
# GitHub Pages recompila en ~1-2 minutos
```

### Mapping de columnas del Excel a la UI del sitio

| Columna del Excel | Cómo se renderiza en el sitio |
|---|---|
| `TAG` | `item_id` (URL slug + breadcrumb + título de página) |
| `Categoría` | carpeta del item (`docs/<cat>/<tag>.html`) y agrupación en nav |
| `Título` | h1 de la página individual (si está vacío, usa `TAG`) |
| Cualquier otra columna con valor | sección colapsable (acordeón) con el label como h2 y el valor como contenido |
| `Ficha Técnica`, `Curva` | botones azules "Documentos y enlaces" al final de la página, `target=_blank` |

## Stack

- **Python 3.12** (probado en WSL Ubuntu 24).
- **openpyxl** — lectura/escritura de Excel.
- **CSS/JS vainilla** en el sitio generado (sin framework, sin build step).

## Setup desde cero

```bash
# Dependencias Python (PEP 668 en Ubuntu 24 requiere --break-system-packages)
pip3 install --break-system-packages openpyxl
```

Sin Chromium, sin libs nativas, sin Node, sin Ruby — solo Python 3 + openpyxl.

## Estructura actual del repo

```
google-sites-migrator/             ← raíz del repo git (remote: groupe_seb_qr)
│
├── docs/                          ← ★ SITIO PUBLICADO (lo que GitHub Pages sirve)
│   ├── index.html                 ← home con acordeones por categoría
│   ├── styles.css                 ← mobile-first, ~11.6KB
│   ├── script.js                  ← sidebar overlay + acordeones
│   ├── .nojekyll                  ← evita procesamiento Jekyll
│   ├── migration_metadata.json    ← trazabilidad
│   ├── README.md
│   ├── equipos/                   ← bombas, mezcladores, motores, compresores
│   ├── instrumentos/              ← AIT, FIT, SV, LT (vacío hasta que se aporten)
│   └── tanques/                   ← tanques, reactores, filtros, separadores
│
├── convert_fichas_to_template.py  ← ★ paso 1: fichas crudas → plantilla unificada
├── generate_excel_template.py     ← genera plantilla vacía a partir del sitio actual
├── plantilla_sitio.xlsx           ← ★ fuente de datos del sitio (editable a mano)
├── NP00033 Fichas...xlsx          ← Excel origen entregado por el cliente
│
├── CLAUDE.md                      ← este archivo
├── .gitignore
├── .nojekyll
│
└── (residuos pendientes de limpieza — ver "Estado de archivos" abajo)
```

## UI del sitio — componente acordeón compartido

Tres lugares usan el mismo componente `.acc-item / .acc-header / .acc-body`:

1. **Home** (`docs/index.html`): un acordeón por categoría. Al expandir: grid de items + link "Ver categoría completa".
2. **Categoría** (`docs/<cat>/index.html`): un acordeón por item. Al expandir: preview de primeras 3 secciones + "Ver ficha completa".
3. **Página individual** (`docs/<cat>/<item>.html`): un acordeón por cada propiedad del Excel. Solo título visible por defecto.

Todos los acordeones empiezan **cerrados**. JS en `script.js` toggle vía clase `.open` en `.acc-item`.

## Diseño mobile-first

- **Topbar fijo en móvil** con hamburger + título de página.
- **Sidebar overlay** con `transform` + backdrop oscuro 45% opacidad.
- **Touch targets ≥44px** en botones e items.
- **Grid responsivo:** 3 cols desktop, 2 cols mobile, 1 col ≤380px.
- **`<400px`:** oculta `.acc-meta`.
- **Sidebar cierra automáticamente** al click en link móvil (`matchMedia('(max-width: 900px)')`).
- **Escape cierra sidebar**, scroll del body se bloquea cuando está abierto.
- **Auto-scroll al ítem activo** del menú al cargar.

## Convenciones

- **Idioma:** todo en español — logs, docstrings, commits, documentación.
- **Logs con emojis** (📖 📊 ✅ ❌ 🏗️ 📁 📄). Mantener.
- **Entorno:** WSL2 Ubuntu 24 + VSCode Remote-WSL. Autor: Jorge Alberto (jagilren@gmail.com) — PROYECTOS CON INGENIERIA S.A.S. (Medellín).
- **Branch principal del repo:** `master` (no `main`). No renombrar sin actualizar la config de Pages.

## Estado de archivos del repo

| Archivo | Estado |
|---|---|
| [docs/](docs/) | ✅ Sitio publicado |
| [convert_fichas_to_template.py](convert_fichas_to_template.py) | ✅ Convierte Excel de fichas técnicas → plantilla unificada |
| [generate_excel_template.py](generate_excel_template.py) | ✅ Genera plantilla vacía a partir del sitio existente |
| [plantilla_sitio.xlsx](plantilla_sitio.xlsx) | ✅ Plantilla unificada — fuente de datos del sitio |
| `excel_migrator.py` | ⏳ Pendiente: leer `plantilla_sitio.xlsx` y generar `docs/` |
| `update_site_from_excel.sh` | ⏳ Pendiente: wrapper Excel → sitio |
| [.vscode/launch.json](.vscode/launch.json), [.vscode/tasks.json](.vscode/tasks.json) | ⚠️ Apuntan al flujo legacy — actualizar cuando exista `excel_migrator.py` |
| Carpetas `migrated_*` | 🗑️ Residuos de iteraciones previas — eliminar |
| `index.html`, `equipos/`, `instrumentos/`, etc. en raíz | 🗑️ Duplicados sueltos del sitio (Pages sirve `/docs`) — eliminar |
| `google_sites_migrator.py`, `update_site.sh`, `quick_migrate.sh`, `setup.sh` | 🗑️ Scripts del flujo abandonado — eliminar |
| `README.md`, `QUICKSTART.md`, `GUIA_USO.md`, `VSCODE_README.md`, `INDICE.md`, `examples/`, `tests/`, `requirements.txt` | 🗑️ Documentación y artefactos del flujo abandonado — eliminar o reescribir |

## Mejoras pendientes

- **Crítico: implementar `excel_migrator.py`** que lea [plantilla_sitio.xlsx](plantilla_sitio.xlsx) y genere `docs/` con la misma UI actual (acordeones, mobile-first). Reusar el template HTML/CSS/JS del sitio actual.
- **Crítico: crear `update_site_from_excel.sh`** wrapper end-to-end (regenerar `docs/` + opcionalmente commit/push).
- Limpiar todos los archivos marcados como 🗑️ en la tabla de arriba.
- Considerar consolidar columnas casi-duplicadas (mismas propiedades con distintas unidades) en el convertidor.
- Reescribir / eliminar la documentación `.md` heredada del flujo abandonado.

## Decisiones tomadas (no revisitar sin causa)

- **No usar Jekyll.** El sitio es HTML estático puro generado por el migrador Python. `docs/.nojekyll` desactiva intencionalmente el procesamiento Jekyll de GitHub Pages. Se evaluó agregar Jekyll (themes, layouts, posts) en mayo 2026 y se descartó: el diseño mobile-first con acordeones ya cumple, y Jekyll requeriría reescribir el migrador para emitir Markdown con front-matter.
- **Branch `master` (no `main`).** Cambiar el nombre requiere actualizar la config de GitHub Pages.
- **Site title preserva siglas ≤3 letras en mayúsculas** (`qr-groupe-seb` → `QR Groupe Seb`, no `Qr Groupe Seb`).
- **Fuente de datos = Excel.** Cualquier propuesta de "scrapear", "extraer de otro sitio" o "leer de un CMS" debe descartarse: el cliente entrega Excel y eso es lo único que el aplicativo debe leer.

## Limitaciones conocidas

- **Imágenes no se incluyen en el sitio.** El Excel no aporta imágenes; si en el futuro se quieren fotos del equipo, hay que extender la plantilla con una columna de URL/path.
- **Tablas complejas dentro de una propiedad no se preservan.** El valor de cada propiedad es texto plano (lo que esté en la celda Excel).
- **Local vs github.io:** si `localhost:8000` se ve diferente al sitio publicado, casi seguro es porque el server local se lanzó desde una carpeta vieja. Verifica con `curl http://localhost:8000/styles.css | wc -c` — debe coincidir con el tamaño del CSS actual (~11671 bytes). Si es menor, el server está sirviendo una carpeta sin sitio o desactualizada.
