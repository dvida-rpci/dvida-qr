# CLAUDE.md

Guía para Claude Code en este repositorio. RPCI

## Qué es

Generador de sitio estático desde Excel para fichas técnicas industriales, publicado en GitHub Pages.

- **Input:** xlsx con fichas técnicas del cliente (una hoja por TAG). Ejemplos usados: `NP00033 Fichas Técnicas...xlsx` (proyecto PTAR STARnD), `NI00011 Fichas Técnicas_Equipos STARnD GROUP SEB V3.xlsx`.
- **Output:** carpeta destino (default `docs/`) con HTML/CSS/JS vainilla.
- **Live:** https://<username>.github.io/<repo_name>>/

## Config

| Item         | Valor                                                   |
| ------------ | ------------------------------------------------------- |
| Remote       | `https://github.com/<username>>/<repo_name>>`           |
| Branch       | `master`                                                |
| Pages serves | `/docs`                                                 |
| Stack        | Python 3.12 + openpyxl + nicegui (WSL Ubuntu 24)        |
| Setup        | `pip3 install --break-system-packages openpyxl nicegui` |

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
- **📝 Título del sitio** (`site_title`) — reemplaza el texto por defecto "QR PTAR".
- **🎨 Color del tema** (color picker → deriva paleta completa de 10 vars + actualiza swatches de preview en vivo).
- **📄 Archivo de fichas técnicas xlsx** (opcional; se guarda como `fichas_source.xlsx` en raíz).
- **📄 TAG_RESOURCES.xlsx** (opcional; sobrescribe el existente).
- **🔄 Switch "Forzar regeneración"** (ver tabla abajo).

Acciones:
- **Generar sitio** — corre el pipeline completo, log streaming al UI.
- **Ver sitio** — lanza `http.server` en `:8190` apuntando al destino actual, abre browser.

### Switch "🔄 Forzar regeneración" (default OFF)

| Switch | Upload por widget         | Comportamiento                                                                                                        |
| ------ | ------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| OFF    | No                        | Usa `plantilla_sitio.xlsx` tal cual está; no toca el contenido                                                        |
| OFF    | Sí                        | `convert_fichas` corre con el xlsx subido (sobrescribe plantilla)                                                     |
| ON     | No                        | **Auto-detecta** xlsx de fichas en raíz del repo (cualquier `*.xlsx` ≠ plantilla/TAG_RESOURCES) y usa el más reciente |
| ON     | Sí                        | `convert_fichas` corre con el xlsx subido                                                                             |
| ON     | Ni upload ni xlsx en raíz | Aborta con error claro                                                                                                |

**No borra archivos físicamente** — `convert_fichas` sobrescribe el contenido de plantilla y extrae imágenes nuevas (la estructura columnar pivotal se preserva).

### Otros detalles de la GUI

- Si el destino difiere de `docs/`, `merge_assets_into()` copia archivos faltantes de `docs/assets/` al destino antes de generar (sin pisar uploads recientes).
- `convert_fichas_to_template.py` sigue extrayendo imágenes a `docs/assets/images/` (canonical); el merge las propaga al destino elegido.
- El servidor de preview se reinicia si cambia el destino. Cuidado con servidores http.server huérfanos en `:8190` — la GUI los detecta y avisa.
- **Validación de destino** (también la hace el migrator): si el campo "Carpeta destino" se llama `assets`/`images`/`logos`/`icons` o tiene `assets/` en su path, la GUI aborta antes de tocar el filesystem.

## Mapping Excel → UI

| Origen                                                                    | Renderizado                                                                                                  |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `TAG`                                                                     | slug URL + breadcrumb + parte del h1                                                                         |
| `SERVICIO` (columna de propiedades)                                       | parte del h1 y `<title>`: `<TAG> - <SERVICIO\|"no definido">`                                                |
| `Categoría`                                                               | carpeta `<output>/<cat>/<tag>.html` + grupo en nav                                                           |
| `Título`                                                                  | usado solo en el index de categoría (no en el h1 de la ficha)                                                |
| Otras columnas con valor                                                  | acordeón con label = h2                                                                                      |
| `Ficha Técnica`, `Curva` (plantilla)                                      | botones en "Documentos y enlaces" (target=_blank)                                                            |
| imágenes en `<output>/assets/images/<TAG>/`                               | botón "Ver N imágenes" con thumbnail (primera imagen) → lightbox. Fallback: `assets/icons/generic-image.svg` |
| `TAG_RESOURCES.xlsx` (`Specifications`, `Handbook_Manual`, `Maintenance`) | botones "Especificaciones / Manual / Mantenimiento" en "Documentos y enlaces"                                |

### Origen exacto de Specifications / Handbook_Manual / Maintenance (por TAG)

Estos 3 botones **no** vienen de `plantilla_sitio.xlsx` — vienen de un archivo separado: `TAG_RESOURCES.xlsx`.

- **Archivo:** `TAG_RESOURCES.xlsx` en la raíz del repo, hoja `TAG_RESOURCES` (si no existe esa hoja, toma la hoja activa).
- **Columnas:** `TAG_ID` (col. A, debe llamarse exactamente así) + `Specifications`, `Handbook_Manual`, `Maintenance` (cualquiera de estas 3 puede faltar; las que existan se leen).
- **Match:** una fila por TAG; `load_tag_resources()` (`excel_migrator.py`) empareja por el valor exacto de `TAG_ID` contra el `TAG` de cada ficha.
- **Lo que cuenta como "hay recurso" es el HYPERLINK de la celda, no el texto.** `cell_hyperlink()` lee `cell.hyperlink.target` (lo que Excel guarda cuando insertás el link con `Ctrl+K` sobre la celda). Solo si no hay hyperlink, hace fallback a tomar el valor de la celda si literalmente empieza con `http://` o `https://`. **Escribir una URL como texto plano sin usar Ctrl+K puede no funcionar si no empieza con http(s)://** — siempre usar `Ctrl+K` para asignar el link.
- Si una celda no tiene hyperlink ni URL en texto, ese botón simplemente no se renderiza para ese TAG (no hay error).
- **Cómo se puebla/actualiza el archivo:** `generate_tag_resources_template.py` — crea `TAG_RESOURCES.xlsx` la primera vez (una fila por cada TAG de `plantilla_sitio.xlsx`, hoja `Datos`) o hace *merge* en corridas posteriores (agrega TAGs nuevos, preserva hyperlinks ya cargados a mano). Después de correrlo, la edición de los links es manual: abrir el archivo, seleccionar la celda del TAG/columna correspondiente, `Ctrl+K` → pegar URL.
- Si `TAG_RESOURCES.xlsx` no existe en absoluto al correr `excel_migrator.py`, simplemente no se renderiza ninguno de los 3 botones (no es un error, solo un aviso en el log).

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
  "site_title": "QR  PTAR INDUSTRIAL",
  "banner_title_full": "Documentación Técnica — PTAR STARnD",
  "banner_title_short": "PTAR STARnD",
  "site_url": "https://<username>.github.io/<repo_name>/",
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

## Histórico de mantenimientos (Supabase)

Ver [docs/superpowers/specs/2026-09-20-historico-mantenimientos-design.md](docs/superpowers/specs/2026-09-20-historico-mantenimientos-design.md) para el diseño completo. Resumen operativo:

- Todo el código vive en `maintenance.js`/`maintenance.css` (no en `excel_migrator.py` — ese archivo solo inyecta la config y los `<link>/<script>` tags).
- La config de conexión (`url`/`anon_key`) vive en `site_config.json` → bloque `supabase`. La `anon_key` es pública a propósito (protegida por RLS), pero la `service_role key` **nunca** va acá ni al repo.
- Schema, RLS, triggers de auditoría y Storage: ver `supabase/migrations/` (Plan 1 del feature).
- Para desarrollar/probar local: `supabase start` (requiere Docker) y usar la URL/key que imprime, no las de producción.
- Desde el sitio solo el **autor** de un evento puede sumarle comentarios/adjuntos; editar/borrar (oficina) se hace desde `gui.py` (Plan 3).
- Si la sesión expira a mitad de un submit, `maintenance.js` muestra un modal de re-login y reintenta solo (los datos del formulario no se pierden). Si Supabase no responde, solo la sección de historial muestra el error con "Reintentar"; la ficha sigue funcionando.
- La pantalla de oficina vive en `gui_maintenance.py` y se abre desde el botón **🧰 Mantenimientos** de `gui.py` como **diálogo maximizado** (`open_maintenance_dialog()`); cada apertura arranca sin sesión. Usa las mismas cuentas y el mismo schema/RLS que el sitio — RLS es la única fuente de verdad, el cliente solo decide qué botones mostrar.
- **No es una `@ui.page`**: NiceGUI 3.x lanza `RuntimeError` si se registra `ui.page` mientras la UI principal (`gui.py`) está en el scope global. Para tener rutas reales habría que mover toda la UI de `gui.py` a funciones de página o usar `ui.sub_pages`.
- Conexión: variables de entorno `SUPABASE_URL` + `SUPABASE_ANON_KEY` (tienen prioridad; sirven para apuntar a `supabase start` sin tocar `site_config.json`) y, si no están, el bloque `supabase` de `site_config.json`.
- Fotos: Pillow (1600px máx, JPEG q70, `exif_transpose`) en un hilo aparte para no congelar la GUI. Audio: solo archivos `.webm/.ogg/.mp4/.m4a/.mp3/.wav` (los MIME que acepta el bucket; máx 10 MB). Tope de 5 adjuntos por registro.
- Si un adjunto falla al subir, el registro/comentario ya quedó guardado: se avisa y el diálogo se cierra (no hay reintento para no duplicar). Se agregan después con "+ Comentario/adjunto".
- Al borrar un registro los archivos del bucket **no se eliminan** (quedan como evidencia junto al `maintenance_audit_log`); solo se borran las filas.
- Sesión expirada en la GUI: el error se traduce a "Tu sesión expiró. Cerrá sesión y volvé a entrar." (sin modal de re-login: es app de escritorio, perder el formulario no es fricción real).
- ~~Límite conocido: a 360px el botón de búsqueda del banner desbordaba ~30px.~~ Resuelto 2026-10-14: a ≤480 px los logos ceden ancho (`max-width: 28vw`). Verificado sin desborde a 360/390 en inicio, ficha y `mantenimientos.html`.
- **Lectura pública (2026-09-21):** el histórico completo (registros, comentarios, adjuntos, autor) es legible sin sesión con la `anon_key`; la escritura sigue exigiendo login + perfil. Migración `20260921210000_public_read.sql`: una policy `select` `to anon, authenticated` por tabla y por el bucket (reemplaza a las `select_member`), y la vista `author_names(user_id, full_name)` (sin correo ni rol). Esa vista lleva `revoke all` a anon/authenticated + `grant select`: Supabase concede ALL por defecto sobre objetos nuevos de `public` y una vista simple es auto-actualizable, así que sin el revoke anon podría escribir en `profiles`.
- **Aplicar migraciones en el stack local:** `psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -v ON_ERROR_STOP=1 -1 -f <archivo>`. `supabase db query -f` NO sirve para archivos con varias sentencias, y el historial local de migraciones no está sincronizado (no usar `migration up` ni `db reset`).
- **Vista de últimos mantenimientos:** `mantenimientos.html` (la genera `excel_migrator.py`; lógica y estilos en `maintenance_feed.js/.css`). Los 10 más recientes por `performed_at desc` (desempate `created_at desc`), "Mostrar más" de a 10, tabs Todos/EQUIPOS/TANQUES/INSTRUMENTOS y buscador por TAG o SERVICIO (sin tildes ni mayúsculas, combinable con el tab). La categoría no está en la base: el generador incrusta `window.__TAG_INDEX__` (`tag`, `categoria`, `servicio`, `filename`) y el filtro consulta con `tag_id in (...)`. Popup de fotos/audio con ✕, Esc, flechas, teclado y swipe; las URLs firmadas (1 h) se piden en lote al renderizar cada página. Acceso: primer ítem del menú lateral y botón en el inicio (no va en el banner, que ya está al límite).
- **Historial de la ficha:** se lee sin login; el botón de alta y "+ Comentario/adjunto" solo aparecen con sesión y sin ella hay un "Iniciar sesión para agregar".
- **El TAG es la clave de negocio y se empareja por texto exacto** (`maintenance_records.tag_id`, sin FK contra nada del xlsx). Consecuencias al editar `plantilla_sitio.xlsx`:
  - **Agregar un TAG nuevo:** inofensivo. Los históricos existentes no se tocan (viven en Supabase; regenerar solo reescribe HTML) y el TAG nuevo arranca en cero. La primera carga lo "crea" sola: no hay que registrarlo en la base.
  - **Renombrar o borrar un TAG:** deja el historial viejo huérfano. La ficha renombrada aparece vacía y los registros anteriores solo se ven en el tab **Todos** del feed, sin link ni servicio (`renderCard` cae al `<span>` cuando `byTag[tag_id]` es `undefined`) y fuera de los tabs por categoría (la categoría sale de `__TAG_INDEX__`, no de la base). Arreglo: `update public.maintenance_records set tag_id = '<nuevo>' where tag_id = '<viejo>';` (dispara el trigger de auditoría, queda en `maintenance_audit_log`). No verificado en producción — hacerlo con backup.
- **Tests de este feature:** RLS `python3 -m pytest tests/supabase -v` (50 tests, requiere `supabase start`); lógica pura del feed `/home/administrador/.codegpt/bin/node --test tests/js/*.test.js` (Node 22: pasar el glob, no la carpeta); generador `python3 -m pytest tests/test_generator_feed.py`. Los tests de RLS dejan registros `TEST-*` en la base local y no se pueden borrar con `service_role` (el trigger de auditoría exige `changed_by`): borrar como usuario `oficina`.
- **Verificación en navegador:** la skill browser-automation usa patchright, que evalúa en un mundo aislado: `page.evaluate` NO ve las variables `window` de la página (p. ej. `window.__TAG_INDEX__`); leer el DOM o el texto del `<script>`.

## Plan de mantenimiento por sábana

Ver [docs/superpowers/specs/2026-10-14-plan-mantenimiento-design.md](docs/superpowers/specs/2026-10-14-plan-mantenimiento-design.md). Fases 1 (base), 2 (GUI) y 3 (sitio + atrasados) hechas; fase 4 (resumen semanal automático) pendiente de canal.

- **Se repite por planta:** la migración `20261014120000_maintenance_plan.sql` es genérica (sin datos). El conocimiento reutilizable vive en `sabana_base.xlsx` (hojas `Clases`, `Actividades`, `Instrucciones`); cada planta lo importa y ajusta sus frecuencias en su propio Supabase.
- **Tablas:** `equipment_classes` (horas/día estimadas), `maintenance_activities` (cada X h y/o Y semanas, `active`), `equipment_tags` (TAG → clase, `group_key` del par A/B, `regime` normal/alterna/principal/reserva), `maintenance_record_activities` (varias por registro) y `maintenance_records.hmi_hours` (lectura opcional del HMI).
- **Alta:** `rpc('create_maintenance_record', {p_record, p_activity_ids})` inserta registro + actividades en una transacción. Un trigger rechaza actividades inactivas o de otra clase que la del TAG.
- **Cálculo (fuente única):** `maintenance_schedule_at(p_today)` / vista `maintenance_schedule`. Gana lo que ocurra primero (horas o semanas). Ritmo real con dos lecturas del HMI separadas ≥7 días (ventana 180 días, tope 24 h/día); si el contador bajó (reset) o no hay lecturas, usa el estimado: clase × régimen (`alterna` divide entre los `alterna` del mismo `group_key`, `reserva` = 0). Días truncados hacia abajo. Estados: `vencido`, `proximo` (≤14 días), `al_dia`, `sin_registro`, `sin_fecha`.
- **RLS:** todo lectura pública; catálogo solo `oficina`; actividades de un registro las agrega su autor (u oficina) y solo oficina las quita.
- **`maintenance_plan.py`** (puro, sin red): `load_library` (valida y reporta errores con hoja/fila), `plan_import` (merge por `code`, no pisa lo existente), `suggest_class` (letra del TAG + palabras clave en TIPO DE BOMBA/TIPO/SERVICIO/Título), `detect_pairs`, `load_plantilla_tags`, `export_library`.
- **Planta nueva:** `./setup_supabase_planta.sh <project-ref>` (`supabase link` + `db push` + pasos manuales). **No usarlo en DVida**: su historial remoto no está sincronizado; ahí las migraciones van con `psql`.
- **Tests:** `python3 -m pytest tests/supabase/test_maintenance_plan.py` (18, requiere `supabase start` y la migración aplicada en local) y `python3 -m pytest tests/test_maintenance_plan_lib.py` (10, sin red).
- **Programación manual (fase 2):** migración `20261015120000_maintenance_manual_schedule.sql`. `rpc('schedule_manual', {p_tag, p_activity, p_date, p_note, p_replace})` devuelve `{status: 'conflict', conflicts, others}` si ya hay algo programado para ese TAG + actividad (o libre + libre); con `p_replace` el manual anterior queda `reemplazado` o el automático queda oculto. Un manual se cumple con un registro **cargado después** (`created_at`), no por fecha. Vista `maintenance_agenda` = automático + manual + "próximo" de registros libres (`source`). Tests: `tests/supabase/test_manual_schedule.py` (7).
- **GUI:** botón **📋 Plan de mantenimiento** → `gui_plan.py` (pestañas Agenda con filtro "Esta semana" vía `maintenance_plan.filter_agenda`, Sábana, Equipos con Auto-asignar). Cada pestaña se recarga al entrar. 🧰 Mantenimientos registra vía `create_maintenance_record` con horas HMI + casillas de actividades y avisa antes de sobrescribir un "próximo". Login compartido: `gui_maintenance.render_login_card`. Probada en headless a 360/390 px (sin overflow, pestañas sin flechas) y escritorio; las vistas principal y Mantenimientos también.
- **Atrasados (fase 3):** migración `20261016120000_overdue_tracking.sql`. `maintenance_agenda` trae `days_overdue`, `original_due_date`, `reschedule_count`. Reprogramar algo vencido exige motivo (servidor). `create_maintenance_record` guarda en `maintenance_record_activities.due_date` la fecha que tenía programada (la original si se reprogramó) → la tarjeta dice "Hecho con N días de atraso". `sin_registro` no cuenta como atrasado (filtro "Sin historial"); ≥30 días = crítico. GUI: resumen, selección y "Programar seleccionados" con "Repartir en N semanas". Tests: `tests/supabase/test_overdue.py` (5).
- **Sitio (fase 3):** `maintenance_agenda.js` (lógica pura compartida, `window.MaintAgenda`, tests `tests/js/agenda_logic.test.js`; espejo de `maintenance_plan.filter_agenda`). Ficha: aviso "🔴 N vencidos en este equipo" al escanear, bloque "Próximos mantenimientos" (oficina reprograma con motivo), formulario con horas HMI + actividades. `mantenimientos.html`: Realizados | Programados (`?vista=programados&filtro=atrasados`), una tarjeta por equipo, 20 por página. Inicio: franja de vencidos. Todo filtrado a los TAGs del sitio (los de prueba o huérfanos no inflan contadores).
- **Off-plan:** lo programado sin actividad de la sábana ya no dice "Libre": "Off-plan · <descripción del registro>" (próximo de un registro), "Off-plan · <nota>" o "Off-plan" (manual). Lo arma `maintenance_agenda_at` (migración `20261017120000_agenda_labels.sql`).
- **Pestañas de la ficha:** Programados (contador rojo si hay vencidos) · Realizados · Plan (clase, régimen, ritmo, actividades con frecuencia), con aviso si están vacías (`buildTabs`, `renderUpcoming`, `renderPlan` en `maintenance.js`). Verificado sin cortes a 320/360/390 px.
- **📝 Registrar:** botón en cada fila de Programados y de Próximos (con sesión) → formulario con la actividad ya marcada. Enlace profundo `equipos/<TAG>.html?registrar=<activity_id>` (`pendingDone` en `maintenance.js`, `doneHref` en `maintenance_feed.js`).
- **Probar el sitio contra Supabase local:** generar a una carpeta temporal, reemplazar en los HTML la URL/anon key de producción por las de `.env.test` y servir con `python3 -m http.server`.
- **Producción (`qgxvukllzuaiyhzegaef`):** ninguna de las tres migraciones del plan está aplicada todavía.

## Archivos generados por `excel_migrator.py`

Bajo `<output_dir>/`:

| Archivo                                              | Contenido                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `index.html`, `<cat>/index.html`, `<cat>/<tag>.html` | Páginas                                                                                                                                                                                                                                                                                                                                                                                                    |
| `styles.css`, `script.js`                            | Assets embebidos en el migrator                                                                                                                                                                                                                                                                                                                                                                            |
| `search-index.json` + `search-index.js`              | Mismo contenido; `.js` lo carga el HTML vía `<script>` (file://-safe), `.json` queda para consumo externo                                                                                                                                                                                                                                                                                                  |
| `urls.txt`                                           | Listado plano `CATEGORIA_SINGULAR,URL` — una línea por TAG. Categorías en singular: `EQUIPO`, `INSTRUMENTO`, `TANQUE`. **Base URL derivada del `git remote origin`** (no hardcoded): `https://<owner>.github.io/<repo>/`. Si no hay git, cae al `site_url` del config. Esto garantiza que los QRs apunten al destino real del push aunque cambies de repo. Útil para generar stickers QR o auditar enlaces |
| `mantenimientos.html`, `maintenance.css/js`, `maintenance_feed.css/js` | Vista pública de últimos mantenimientos y su código (los `.css/.js` se copian tal cual desde la raíz del repo) |
| `migration_metadata.json`                            | Trazabilidad (timestamp, conteos, datos por TAG)                                                                                                                                                                                                                                                                                                                                                           |
| `README.md`                                          | Pie de información del deploy                                                                                                                                                                                                                                                                                                                                                                              |
| `.nojekyll`                                          | Desactiva Jekyll en GitHub Pages                                                                                                                                                                                                                                                                                                                                                                           |
| `assets/icons/generic-image.svg`                     | Fallback del thumbnail si la imagen del TAG no carga                                                                                                                                                                                                                                                                                                                                                       |

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
- **Puerto 8190 ocupado al pulsar "Ver sitio"** → un `python3 -m http.server` huérfano de otra sesión. `pkill -f "http.server"` lo mata; la GUI ya lo detecta y notifica.
- **El sitio en `localhost:8190` se ve viejo aunque regeneraste** → casi siempre es el preview server apuntando al destino anterior. La GUI lo reinicia al cambiar destino; verificar el log: `🚀 Lanzando preview en http://localhost:8190 desde <ruta>`.
- **El buscador no devuelve resultados al abrir el HTML con doble click** → ya no debería pasar. Si pasa: confirmar que el destino tiene `search-index.js` (no solo `.json`) y que el `<head>` lo carga con `<script src="search-index.js">`.
- **El sitio sale con TAGs/propiedades del proyecto anterior** → la plantilla quedó vieja porque `convert_fichas` no corrió. Activá el switch **🔄 Forzar regeneración** en la GUI y asegurate de tener la xlsx nueva en raíz o subila por el widget.
- **Solo 1 propiedad por TAG en la plantilla** → bug histórico del `extract_pairs` viejo (ventana de búsqueda muy corta). Resuelto en mayo 2026. Si vuelve a pasar con un layout nuevo: verificar que `is_valid_label` no esté rechazando los labels reales y que el value esté efectivamente en la fila (no en celda merged externa).
- **TAG aparece sin imagen aunque la xlsx la tiene** → puede ser una imagen dentro de `<xdr:grpSp>` (agrupada con caption). Resuelto con `anchor.iter("a:blip")`. Si pasa con un xlsx nuevo: verificar que el anchor exista (parsear `xl/drawings/drawingN.xml` con un grep `<a:blip` o `<xdr:grpSp`).
- **Imagen es un logo pero no se filtra** → probablemente está anclada en filas 4+ (fuera de `HEADER_ANCHOR_MAX_ROW=2`) o mide más de `LOGO_MAX_HEIGHT_ROWS=5` filas. Ajustar las constantes en `convert_fichas_to_template.py` o pedirle al usuario que mueva el logo a las primeras 3 filas en el xlsx.
- **El color elegido en la GUI no se aplica** → bug histórico del `color_input.on("change", ...)` que no disparaba. Resuelto pasando `on_change=` en el constructor. Si vuelve a pasar: probar con un browser distinto, o verificar en el log de la GUI que aparece `🎨 Color seleccionado: #...` al cambiar.
- **Upload de la GUI falla silenciosamente** → API de NiceGUI cambió en 3.x. Confirmar que el handler es `async def` y usa `await e.file.read()` en vez de `e.content.read()`.

## Estado de archivos

| Archivo                                                                  | Estado                                                                                                                                                             |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [docs/](docs/)                                                           | ⚠️ Solo `assets/` actualmente (sitio HTML pendiente de regenerar tras el último `convert_fichas`)                                                                   |
| [convert_fichas_to_template.py](convert_fichas_to_template.py)           | ✅ Paso 1 — refactor mayo 2026 (extracción layout-agnóstica + flag `--images-only`)                                                                                 |
| [excel_migrator.py](excel_migrator.py)                                   | ✅ Paso 4 — acepta `output_dir`, `ensure_images()` auto-recovery, cleanup defensivo                                                                                 |
| [update_site_from_excel.sh](update_site_from_excel.sh)                   | ✅ Wrapper CLI                                                                                                                                                      |
| [generate_excel_template.py](generate_excel_template.py)                 | ✅ Plantilla vacía desde sitio existente                                                                                                                            |
| [generate_tag_resources_template.py](generate_tag_resources_template.py) | ✅ Bootstrap/merge de TAG_RESOURCES.xlsx                                                                                                                            |
| [gui.py](gui.py) + [launch_gui.sh](launch_gui.sh)                        | ✅ GUI NiceGUI (puerto 8080) — input título sitio + input URL logo cliente + color picker live + switch "Forzar regeneración" + auto-detect de xlsx + uploads async |
| [plantilla_sitio.xlsx](plantilla_sitio.xlsx)                             | ✅ Fuente de datos — última regeneración desde NI00011 (36 TAGs, 96 propiedades)                                                                                    |
| [TAG_RESOURCES.xlsx](TAG_RESOURCES.xlsx)                                 | ✅ Enlaces por TAG                                                                                                                                                  |
| [site_config.json](site_config.json)                                     | ✅ Tema editable vía GUI (color picker + título del sitio)                                                                                                          |
| [comandos.txt](comandos.txt)                                             | ✅ Cheatsheet de comandos CLI por sección                                                                                                                           |
| [New_Laptop.txt](New_Laptop.txt)                                         | ✅ Guía de instalación en laptop nuevo (Linux/Windows/macOS/WSL sin VSCode)                                                                                         |
| [windows_launchers/](windows_launchers/)                                 | ✅ 4 `.bat` para Windows: lanzar (nativo/WSL), parar, instalar acceso directo + auto-arranque                                                                       |
| [gui_maintenance.py](gui_maintenance.py)                                 | ✅ Pantalla "Mantenimientos" en gui.py (Plan 3) — diálogo maximizado con login, selector de TAG, alta/edición/borrado según rol |
| [maintenance.js](maintenance.js), [maintenance.css](maintenance.css)   | ✅ Histórico de mantenimientos (Plan 2) — cliente Supabase, login, lectura/carga de historial, fotos+audio, comentarios, re-login por sesión expirada |
| [supabase/migrations/](supabase/migrations/)                             | ✅ Schema + RLS + triggers + Storage del histórico de mantenimientos (Plan 1)                                                                                       |
| [maintenance_plan.py](maintenance_plan.py), [sabana_base.xlsx](sabana_base.xlsx) | ✅ Plan de mantenimiento fase 1 — lógica pura + biblioteca de sábanas (frecuencias de ejemplo, validar con fabricante) |
| [gui_plan.py](gui_plan.py)                                               | ✅ Ventana "📋 Plan de mantenimiento" (fase 2) — agenda/Esta semana, sábana, equipos, programación manual con advertencia |
| [setup_supabase_planta.sh](setup_supabase_planta.sh)                     | ✅ Aplica todas las migraciones a un proyecto Supabase nuevo (no usar en DVida) |
| [tests/supabase/](tests/supabase/)                                       | ✅ Suite pytest de RLS (40 tests, incl. `test_hardening.py`) — requiere `supabase start` (Docker) corriendo localmente; correr con `python3 -m pytest tests/supabase -v`                        |
| `NI00011 Fichas Técnicas_Equipos STARnD GROUP SEB V3.xlsx`               | ✅ Source xlsx actual en raíz                                                                                                                                       |
| `docs/assets/images/`                                                    | ✅ 37 carpetas TAG con imágenes extraídas (filtro posición+frecuencia activo)                                                                                       |
| `docs/assets/logos/LogoCliente.png`                                      | ✅ Logo del cliente                                                                                                                                                 |
| `docs/assets/logos/LogoRPCI.png`                                         | ⚠️ Falta — el banner muestra hueco en posición izquierda hasta agregarlo                                                                                            |
| `docs/assets/icons/generic-image.svg`                                    | ✅ Fallback de thumbnail                                                                                                                                            |
| Hyperlinks de recursos                                                   | ⚠️ Llenado parcial — algunas celdas vacías                                                                                                                          |
