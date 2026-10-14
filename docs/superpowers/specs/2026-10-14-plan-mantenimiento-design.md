# Plan de mantenimiento por sábana — diseño

Fecha: 2026-10-14

## Propósito

Que el sistema calcule solo **cuándo toca el próximo mantenimiento** de cada equipo y actividad, a partir de una **sábana** definida por clase de equipo (ej.: "Bomba centrífuga horizontal → Lubricación rodamientos cada 1.300 h o 12 semanas"). Complementa el histórico ([2026-09-20-historico-mantenimientos-design.md](2026-09-20-historico-mantenimientos-design.md)) y la vista pública ([2026-09-21-ultimos-mantenimientos-design.md](2026-09-21-ultimos-mantenimientos-design.md)).

Decisiones tomadas con el usuario:

- La sábana se administra en una **ventana propia de `gui.py`** (rol `oficina` = admin). Las frecuencias son editables.
- La clase de equipo **no** es la letra del TAG: una `P` puede ser centrífuga, neumática de diafragma o dosificadora eléctrica, con planes distintos. Cada TAG se asigna a una clase.
- Excepciones de frecuencia por TAG: **fuera de alcance por ahora** (posible a futuro).
- Frecuencia por **horas de operación y/o semanas, lo que ocurra primero**. No hay horómetro en línea: el técnico **lee las horas en el HMI** y las anota al registrar (opcional; solo algunos equipos tienen contador).
- Pares A/B (principal/stand-by): el **régimen se elige por par** (alternan / principal + reserva). Es solo el estimado inicial; con lecturas del HMI manda el uso real.
- **Un registro puede marcar varias actividades** de la sábana; cada una reinicia su propio conteo.
- **Se repite en N plantas** (cada una con su repo, su proyecto Supabase y sus TAGs). Nada específico de una planta va en código ni migraciones. El conocimiento reutilizable vive en una **biblioteca Excel `sabana_base.xlsx`**.

**Fuera de alcance:** horómetro en línea / integración con PLC-HMI, excepciones de frecuencia por TAG, órdenes de trabajo, notificaciones (correo/WhatsApp), multi-planta en un solo proyecto Supabase.

## Ejemplo de referencia (DVida)

Clase **Bomba centrífuga horizontal**, 24 h/día estimadas. Equipos: `100-P-01A/B`, `200-P-01A/B`, `200-P-02A/B` (pares, régimen inicial *alternan* → 12 h/día cada una) y `500-P-01` (sin par → 24 h/día).

| Código | Actividad | Cada (h) | Cada (semanas) |
| --- | --- | --- | --- |
| `LUB-ROD` | Lubricación rodamientos | 1300 | 12 |
| `REV-SELLO` | Revisión sello mecánico | 4000 | 26 |
| `ALINEACION` | Alineación | 8000 | 52 |

Frecuencias **ilustrativas**: validar con el manual del fabricante antes de usarlas (en bombas monoblock tipo CDX los rodamientos del motor suelen ser sellados de por vida; "Lubricación" podría no aplicar).

Lubricación registrada el 2026-10-14 sin lecturas previas:

- `500-P-01`: 1300 / 24 = 54,2 días → **2026-12-07** (gana horas sobre 12 semanas).
- `200-P-01A` (alterna): 1300 / 12 = 108,3 días; 12 semanas = 84 días → **2027-01-06** (gana calendario).

## Base de datos (migración nueva, genérica)

Archivo `supabase/migrations/<ts>_maintenance_plan.sql`. **No contiene datos de ninguna planta.**

### Tablas

`public.equipment_classes`
- `id uuid pk`, `code text unique not null` (estable, ej. `BOMBA_CENTRIFUGA_H`), `name text not null`, `hours_per_day numeric not null check (hours_per_day > 0 and hours_per_day <= 24)`, `updated_by uuid default auth.uid()`, `updated_at timestamptz default now()`.

`public.maintenance_activities`
- `id uuid pk`, `class_id uuid not null references equipment_classes on delete restrict`, `code text not null`, `name text not null`, `interval_hours numeric check (> 0)`, `interval_weeks int check (> 0)`, `active boolean not null default true`, `updated_by`, `updated_at`.
- `unique (class_id, code)`; `check (interval_hours is not null or interval_weeks is not null)`.
- No se borran actividades usadas: se **desactivan** (`active = false`), así el historial conserva la referencia.

`public.equipment_tags`
- `tag_id text pk` (mismo texto exacto que `maintenance_records.tag_id`), `class_id uuid references equipment_classes on delete restrict` (null = sin clase asignada), `group_key text` (prefijo del par, ej. `200-P-01`; null si no tiene par), `regime text not null default 'normal' check (regime in ('normal','alterna','principal','reserva'))`, `updated_by`, `updated_at`.

`public.maintenance_record_activities`
- `record_id uuid references maintenance_records on delete cascade`, `activity_id uuid references maintenance_activities on delete restrict`, `primary key (record_id, activity_id)`.

`public.maintenance_records` — columna nueva `hmi_hours numeric check (hmi_hours >= 0)` (null = no se leyó).

### Alta atómica de registros

Función `public.create_maintenance_record(p_record jsonb, p_activity_ids uuid[]) returns uuid`, `security invoker` (aplica RLS del usuario). Inserta el registro y sus actividades en una sola transacción: no puede quedar un registro sin sus actividades. Valida que cada actividad pertenezca a la clase del TAG y esté activa. El sitio y la GUI la usan en lugar del `insert` directo; el `insert` directo sigue permitido (registros libres, compatibilidad).

### Cálculo: `public.maintenance_schedule_at(p_today date)` + vista `public.maintenance_schedule`

Fuente única del cálculo; sitio y GUI solo leen. La vista llama a la función con `(now() at time zone 'America/Bogota')::date`; la función con fecha explícita existe para poder testear.

Una fila por cada TAG con clase × cada actividad activa de esa clase:

| Columna | Significado |
| --- | --- |
| `tag_id`, `activity_id`, `activity_name`, `class_name` | Identificación |
| `last_done_at`, `last_record_id`, `last_hmi_hours` | Último registro del TAG con esa actividad (`performed_at desc, created_at desc`) |
| `rate_hours_per_day`, `rate_source` | Ritmo usado y si es `real` o `estimado` |
| `due_hours` | `last_hmi_hours + interval_hours` (si hay lectura y frecuencia en horas) |
| `due_date` | Fecha calculada (ver reglas) |
| `status` | `vencido`, `proximo` (≤ 14 días), `al_dia`, `sin_registro`, `sin_fecha` |

Reglas:

1. **Ritmo real** del TAG: con la lectura más reciente (`hmi_hours` no nulo) y la lectura más antigua dentro de los 180 días previos a esa lectura que esté al menos 7 días antes, `rate = Δhoras / Δdías`, tope 24. Si la más reciente es **menor** que la anterior (reset del contador o cambio de PLC), no hay ritmo real.
2. **Ritmo estimado** (sin ritmo real): `normal` y `principal` → `hours_per_day` de la clase; `alterna` → `hours_per_day / n` (n = TAGs `alterna` con el mismo `group_key`); `reserva` → 0.
3. **Fecha por horas** (si `interval_hours` y ritmo > 0):
   - si el registro base tiene `last_hmi_hours`: se parte de la **lectura más reciente del TAG** (de cualquier registro, incluido el base): `fecha_lectura_más_reciente + (due_hours − lectura_más_reciente) / ritmo`. Si esa lectura es menor que `last_hmi_hours` (reset), se usa la variante sin lectura;
   - si el registro base no tiene lectura: `last_done_at + interval_hours / ritmo`.
   - Los días se truncan (redondeo hacia abajo: mejor temprano que tarde).
4. **Fecha por calendario** (si `interval_weeks`): `last_done_at + 7 × interval_weeks`.
5. `due_date` = la **menor** de las disponibles. Sin ninguna (ej. reserva con frecuencia solo en horas) → `status = sin_fecha`.
6. Sin registro previo de la actividad → `status = sin_registro`, `due_date` null (se lista como pendiente).

### Seguridad (RLS)

- `select` `to anon, authenticated` en las cuatro tablas nuevas (coherente con la lectura pública del histórico). La vista lleva `security_invoker = true`, `revoke all` + `grant select` a `anon`/`authenticated` (misma lección que `author_names`).
- `insert/update/delete` en `equipment_classes`, `maintenance_activities`, `equipment_tags`: solo `is_oficina()`.
- `maintenance_record_activities`: `insert` si `is_member()` y el registro es del usuario (`created_by = auth.uid()`) o `is_oficina()`; `delete` solo `is_oficina()` (para corregir desde la GUI).
- `hmi_hours` sigue las políticas existentes de `maintenance_records` (editar = oficina, queda en `maintenance_audit_log`).

## Programación manual y advertencia de duplicados (agregado 2026-10-14)

Pedido del usuario: poder **programar mantenimientos a mano** y que el sistema **advierta** si ese equipo ya tiene un mantenimiento programado (automático o manual), preguntando si se sobrescribe.

### Datos (migración nueva, fase 2)

`public.maintenance_manual_schedule`
- `id uuid pk`, `tag_id text not null`, `activity_id uuid references maintenance_activities` (null = mantenimiento libre, fuera de la sábana), `scheduled_for date not null`, `note text`, `status text not null default 'pendiente' check (status in ('pendiente','reemplazado','cancelado'))`, `replaced_by uuid references maintenance_manual_schedule`, `created_by uuid not null default auth.uid()`, `created_at timestamptz default now()`.
- **Se cumple solo:** un manual pendiente deja de mostrarse cuando se **carga** un registro de ese TAG después de programarlo (`created_at` posterior; con esa actividad, si la tiene; cualquier registro, si es libre). No se borra: queda como historia.
- RLS: lectura pública; crear y cancelar: `oficina`.

### Agenda unificada: vista `public.maintenance_agenda`

Une las tres fuentes de "lo que está programado", con columna `source`:

| `source` | Origen | Regla |
| --- | --- | --- |
| `automatico` | `maintenance_schedule` (sábana) | Se oculta si hay un manual **pendiente** para el mismo TAG y actividad: el manual lo reemplaza |
| `manual` | `maintenance_manual_schedule` pendiente y no cumplido | — |
| `registro` | `next_scheduled_at` del último registro libre del TAG (el campo que ya existe en el formulario) | Solo si no hay un registro posterior del mismo TAG |

Columnas: `tag_id`, `activity_id`, `activity_name` ("Libre" si no tiene), `due_date`, `status` (mismos estados), `source`, `manual_id`, `note`.

### Advertencia y sobrescritura (lado servidor)

Función `public.schedule_manual(p_tag text, p_activity uuid, p_date date, p_note text, p_replace boolean default false)`:

1. Busca en `maintenance_agenda` lo programado para ese TAG.
2. **Mismo TAG y misma actividad** (o, si es libre, otro manual libre del mismo TAG) y `p_replace = false` → **no guarda** y responde con el conflicto: fecha, origen (automático/manual/registro) y nota.
3. Con `p_replace = true`: si el existente es manual, pasa a `reemplazado` (con `replaced_by`); si es automático, el manual nuevo lo oculta mientras esté pendiente. El cálculo automático vuelve a mandar en cuanto se registra el mantenimiento.
4. Lo programado para **otras actividades** del mismo equipo no bloquea: se devuelve como aviso informativo ("Este equipo también tiene: Revisión sello el 2027-04-14").

En la GUI y en el sitio, el conflicto se muestra así:

> ⚠️ **200-P-01A — Lubricación rodamientos** ya está programado para el **07/12/2026** (automático, según sábana).
> ¿Sobrescribir con el **20/11/2026**? [Sobrescribir] [Cancelar]

El campo "Próximo mantenimiento programado" del formulario de registro libre usa la misma advertencia antes de guardar.

## Ver lo programado: "Esta semana" (agregado 2026-10-14)

La pestaña **Agenda** de la GUI y la pestaña **Programados** de `mantenimientos.html` leen `maintenance_agenda` y tienen filtros rápidos (por defecto **Esta semana**):

- **Atrasados**: `status = vencido` (siempre arriba, en rojo). `sin_registro` va en su propio filtro **Sin historial** (ver "Si la cola de atrasados crece mucho").
- **Esta semana**: `due_date` de lunes a domingo de la semana actual (hora de Colombia).
- **Próxima semana** y **Próximas 4 semanas**.
- **Todo**.

Cada fila muestra el TAG (con link a su ficha en el sitio), el servicio, la actividad, la fecha, el estado y el origen (automático, manual o registro). Se combinan con los tabs de categoría y el buscador existentes. Desde la GUI, una fila se puede **reprogramar a mano** (abre `schedule_manual` con la advertencia de arriba).

## Atrasados: cómo se reportan y qué pasa al reprogramarlos (agregado 2026-10-14, fase 3)

**Qué es atrasado**
- `vencido`: la fecha programada (automática, manual o "próximo" de un registro) ya pasó. Se muestra **"Vencido hace N días"** en rojo (`days_overdue = hoy − due_date`).
- `sin_registro`: la actividad nunca se ha registrado en ese equipo, así que no hay desde dónde contar. Se muestra en gris **"Nunca registrado — registralo para arrancar el conteo"**. Cuenta como atrasado en los filtros, pero no tiene días.

**Dónde se reporta**
- Siempre **primero** en la Agenda (GUI) y en Programados (sitio), vencidos por antigüedad y después los sin registro.
- Contador visible: el selector de `mantenimientos.html` muestra **"Programados · 🔴 N atrasados"**; en la ficha, el bloque "Próximos mantenimientos" pinta en rojo la fila vencida.

**Cuando se hace tarde**
- El próximo se cuenta desde la **fecha real** en que se hizo, no desde la que debió ser (la sábana mide intervalos reales entre intervenciones).
- El registro **guarda la fecha que tenía programada** (`maintenance_record_activities.due_date`, la *original* si fue reprogramada). La tarjeta del historial dice **"Hecho con 12 días de atraso"** o **"A tiempo"**. Esto deja la base lista para medir cumplimiento del plan.

**Cuando se reprograma**
- Solo `oficina` reprograma (GUI y sitio), con la advertencia de siempre. Si lo que se reemplaza está **vencido**, el mensaje lo dice y el **motivo es obligatorio** (el servidor rechaza sin motivo):
  > ⚠️ **200-P-01A — Lubricación rodamientos** estaba programado para el **07/12/2026** y está **vencido hace 12 días**. Reprogramar para el **20/12/2026**. Motivo: [ falta repuesto ]
- El manual nuevo guarda `previous_due_date`, `original_due_date` (la primera fecha de la cadena) y `reschedule_count` (cuántas veces se corrió desde el último mantenimiento hecho). El anterior queda `reemplazado`: nada se borra.
- Mientras está reprogramado, la fila dice **"Reprogramado ×2 · fecha original 07/12/2026 · motivo: falta repuesto"** y su estado sale de la fecha nueva (no aparece como vencido hasta que esa también pase). Si vuelve a vencer: **"Vencido hace N días · reprogramado 2 veces"**.
- Cuando por fin se registra, el atraso se mide contra la **fecha original**, no contra la última reprogramación: reprogramar no maquilla el cumplimiento.

**Si la cola de atrasados crece mucho**
- **"Sin historial" va aparte.** Al arrancar una planta *todas* las actividades salen `sin_registro` (DVida: 7 bombas × 3 = 21; una planta grande, cientos). No son retrasos reales, así que **no** entran en el contador de atrasados ni en "Esta semana": tienen su propio filtro **"Sin historial"**. En la GUI se seleccionan varias y **"Programar primera vez"** les pone fecha de una sola vez (`schedule_manual` por cada una; sin conflicto porque no tienen fecha).
- **Prioridad por antigüedad:** vencidos ordenados de más a menos días; desde **30 días** se marcan **"‼️ crítico"**.
- **Resumen arriba:** "🔴 12 vencidos (4 críticos) · ⚪ 21 sin historial".
- **Agrupado por equipo en el sitio:** una tarjeta por TAG con sus actividades vencidas (no una por actividad) y "Mostrar más" de a 20 tarjetas, para que en el celular no sea una lista infinita.
- **Reprogramar en lote (GUI):** se seleccionan varios vencidos y se reprograman a una fecha con **un solo motivo**; cada uno queda con su propia trazabilidad (`schedule_manual` por fila, con `p_replace`).

**Si olvidan el aplicativo y se vence todo**
- *Que se vea sin buscarlo (fase 3):* la ficha muestra arriba, al escanear el QR, **"🔴 N mantenimientos vencidos en este equipo"** (sin abrir el historial); el inicio del sitio muestra la franja **"🔴 N mantenimientos vencidos (M críticos) → ver"** enlazada a Programados/Atrasados.
- *Recuperarse (fase 3):* "Programar seleccionados" (GUI) tiene **"Repartir en N semanas"**: distribuye los seleccionados en N semanas a partir de la fecha elegida, los más atrasados primero, con un solo motivo. Cada fila conserva su trazabilidad y el atraso se sigue midiendo contra la fecha original.
- *Que el sistema avise solo (fase 4, aparte):* resumen semanal automático (lunes 7 a. m.) "Esta semana: N programados · 🔴 M vencidos (K críticos)" con enlace a la agenda. Canal por definir con el usuario (correo / WhatsApp); requiere configuración por planta.

**Datos (migración `20261016120000_overdue_tracking.sql`)**
- `maintenance_manual_schedule`: `previous_due_date date`, `original_due_date date`, `reschedule_count int not null default 0`.
- `maintenance_record_activities.due_date date` (lo llena `create_maintenance_record` antes de insertar el registro; null si no había fecha).
- `maintenance_agenda_at` agrega `original_due_date`, `reschedule_count`, `days_overdue`.

## "✔ Hecho" (agregado 2026-10-14, pedido del usuario)

Cada fila de **Programados** (`mantenimientos.html`) y de **"Próximos mantenimientos"** (ficha, visible con sesión) tiene un botón **"✔ Hecho"**. Abre el formulario de registro con esa actividad **ya marcada** (y tipo Preventivo); el técnico solo agrega descripción/horas y guarda. Desde Programados el enlace es `<ficha>?hecho=<activity_id>` (`''` = libre): la ficha abre el historial y, apenas hay sesión, el formulario. Al guardar: lo de la sábana **salta a su próxima fecha** (es recurrente) y lo manual/libre **desaparece** (queda cumplido); el registro aparece en Realizados.

## Biblioteca `sabana_base.xlsx` (raíz del repo, versionada)

Conocimiento de RPCI reutilizable entre plantas.

Hoja **`Clases`**: `code` | `nombre` | `horas_dia` | `letras_tag` (ej. `P`; varias separadas por `;`) | `palabras_clave` (separadas por `;`, ej. `centrifuga;centrífuga`).

Hoja **`Actividades`**: `clase_code` | `code` | `nombre` | `cada_horas` | `cada_semanas`.

Contenido inicial: la clase `BOMBA_CENTRIFUGA_H` con las 3 actividades del ejemplo.

## Lógica Python reutilizable: `maintenance_plan.py` (nuevo)

Funciones puras, testeables sin Supabase ni GUI:

- `load_library(path) -> (clases, actividades)` — lee y valida `sabana_base.xlsx` (códigos únicos, al menos una frecuencia, horas_dia en (0, 24]).
- `plan_import(library, current) -> cambios` — merge por `code`: **agrega** clases/actividades nuevas; las existentes **no se tocan** (preserva frecuencias editadas en la planta). Devuelve la lista de altas para mostrar antes de aplicar.
- `suggest_class(tag, props, clases) -> code | None` — letra del TAG (`^\d{3}-([A-Z]+)-`) debe estar en `letras_tag` y alguna palabra clave debe aparecer (sin tildes ni mayúsculas) en `TIPO DE BOMBA`, `TIPO`, `SERVICIO` o `Título`. Primera clase que cumple, en el orden de la hoja.
- `detect_pairs(tags) -> {tag: group_key}` — TAGs que difieren solo en la letra final (`^(.*\d)([A-Z])$`) y comparten prefijo con al menos otro TAG → mismo `group_key`.
- `export_library(clases, actividades, path)` — escribe la sábana actual de la planta en el formato de la biblioteca, en un archivo **nuevo** (`sabana_<proyecto>_<fecha>.xlsx`); reemplazar `sabana_base.xlsx` es decisión manual.

## Ventana "📋 Plan de mantenimiento" (`gui_plan.py`, nuevo)

Se abre desde un botón en `gui.py` como diálogo maximizado (mismo patrón que 🧰 Mantenimientos; no `ui.page`). Login propio; las acciones de escritura requieren rol `oficina` (con `tecnico` se muestra "Requiere rol oficina"). Reutiliza `load_supabase_config`, `friendly_error` y el login de `gui_maintenance.py` (se extrae a función compartida si hace falta, sin cambiar su comportamiento).

Pestañas:

1. **Sábana** — clases (nombre, horas/día) y sus actividades (nombre, cada h, cada semanas, activa). Edición en línea; botón **Importar sábana base** (muestra las altas de `plan_import` y pide confirmar) y **Exportar a biblioteca**.
2. **Equipos** — todos los TAGs de `plantilla_sitio.xlsx`: clase asignada, par y régimen. Botón **Auto-asignar** (aplica `suggest_class` + `detect_pairs` solo a TAGs sin clase; régimen `alterna` por defecto en pares) con vista previa antes de guardar. Por par se elige *alternan* o *principal + reserva* (y cuál es la principal). TAGs que existen en la base pero no en la plantilla se marcan "no está en la plantilla" (TAG renombrado o borrado).
3. **Agenda** — `maintenance_agenda` de toda la planta (ver "Esta semana"): filtro rápido, búsqueda por TAG o servicio, reprogramar y cancelar manuales.

Cada pestaña se **recarga al entrar** (lo importado en Sábana tiene que verse en Equipos sin cerrar la ventana).

Además, en 🧰 Mantenimientos (`gui_maintenance.py`) el alta usa `create_maintenance_record` y suma "Horas HMI" + casillas de actividades; la edición de oficina permite cambiar actividades y horas.

## Sitio (`maintenance.js`, `maintenance_feed.js`)

- **Formulario de alta en la ficha:** campo "Horas HMI" (opcional, numérico) y casillas con las actividades activas de la clase del TAG (si el TAG no tiene clase, la sección no aparece y el formulario funciona como hoy). Con al menos una actividad marcada se oculta "Próximo mantenimiento programado" (lo calcula el sistema). Guarda vía `create_maintenance_record`; el borrador local incluye actividades y horas. Tras guardar, el mensaje indica la próxima fecha de cada actividad (leída de la vista).
- **Ficha:** bloque "Próximos mantenimientos" (de `maintenance_schedule`, sin login) encima del historial. Las tarjetas de registro muestran las actividades hechas y las horas HMI.
- **`mantenimientos.html`:** selector **Realizados | Programados**. *Programados* lista `maintenance_schedule` (vencidos primero), combinable con los tabs de categoría y el buscador existentes.

## Montaje de una planta nueva

Script `setup_supabase_planta.sh`: recibe el `project-ref`, hace `supabase link` + `supabase db push` (aplica **todas** las migraciones en orden y deja el historial sincronizado en ese proyecto) e imprime los pasos manuales restantes: crear usuarios en Auth, insertar sus filas en `profiles` (plantilla SQL con roles), copiar `url`/`anon_key` a `site_config.json`.

Secuencia completa: crear repo + proyecto Supabase → `setup_supabase_planta.sh` → Generar sitio → Plan de mantenimiento: Importar sábana base → Auto-asignar equipos → revisar regímenes de pares.

**DVida (proyecto existente `qgxvukllzuaiyhzegaef`):** su historial remoto de migraciones no está verificado; la migración nueva se aplica con `psql` como las anteriores, **solo con confirmación explícita del usuario**.

## Errores

- Supabase no responde: el bloque "Próximos" y la pestaña *Programados* muestran error con "Reintentar"; el resto de la ficha funciona.
- `create_maintenance_record` rechaza actividades de otra clase o inactivas: mensaje claro, los datos siguen en el formulario.
- Horas HMI menores que la lectura anterior del mismo TAG: se aceptan (puede ser un reset) pero el formulario avisa "Es menor que la última lectura (X h). ¿Se reinició el contador?" antes de guardar.
- Importar con `sabana_base.xlsx` inválido: lista de errores por fila, no se aplica nada.

## Pruebas

- **Cálculo (pytest contra Supabase local):** casos con `maintenance_schedule_at(fecha)` — ejemplo DVida (2026-12-07 y 2027-01-06), ritmo real con dos lecturas, reset de contador, reserva solo-horas → `sin_fecha`, sin registro → `sin_registro`, estados `vencido`/`proximo`/`al_dia`, actividad inactiva excluida.
- **RLS (pytest):** anon lee y no escribe las tablas nuevas; técnico no edita catálogo; técnico agrega actividades solo a sus registros; `create_maintenance_record` respeta RLS y es atómica (falla de actividad → no queda registro).
- **`maintenance_plan.py` (pytest, sin red):** carga/validación de biblioteca, merge que no pisa frecuencias, `suggest_class` con los TAGs reales de la plantilla (centrífugas sí; neumáticas y dosificadoras no), `detect_pairs`.
- **UI:** navegador headless contra Supabase local (formulario con actividades, bloque Próximos, tab Programados, 360/390 px) y prueba manual de la ventana de la GUI.

## Celular primero (requisito del usuario, 2026-10-14)

"Si no se ve bien en el celular no lo van a usar." Toda vista (sitio y GUI NiceGUI/Quasar) se prueba **primero a 360 y 390 px** en navegador headless y después en escritorio:

- Sin desborde horizontal (`scrollWidth <= clientWidth`) en la página, los diálogos y los paneles de pestañas.
- Las pestañas de Quasar deben caber **sin flechas de desplazamiento** (se montan sobre el texto): etiquetas cortas (`Agenda · Sábana · Equipos`), `dense no-caps`, relleno `px-2`.
- Listas como **tarjetas de dos líneas** que se acomodan solas (nada de anchos fijos en fila); textos largos con `truncate w-full`; selectores e inputs `w-full` en celular y ancho fijo desde `sm:`.
- Filtros con `ui.select` en vez de `ui.toggle` (el toggle de 5 opciones no cabe en 360 px).
- Al medir, esperar a que termine la animación de cambio de pestaña (~2,5 s): durante el deslizamiento los elementos aparecen fuera de pantalla.

## Fases (un plan por fase)

Estado: fase 1 ✅ (2026-10-14) · fase 2 ✅ (2026-10-14) · fase 3 ✅ (2026-10-14) · fase 4 (resumen semanal automático) por definir canal. Migraciones aplicadas solo en Supabase local; producción pendiente de confirmación.


1. **Base:** migración, función de alta, cálculo, RLS, `maintenance_plan.py`, `sabana_base.xlsx` inicial, `setup_supabase_planta.sh`, tests. Todo en Supabase local.
2. **GUI:** migración de programación manual (`maintenance_manual_schedule`, `maintenance_agenda`, `schedule_manual`) con sus tests; ventana "Plan de mantenimiento" (con filtro "Esta semana" y reprogramación manual con advertencia) y cambios en 🧰 Mantenimientos.
3. **Sitio:** formulario con actividades, horas y advertencia en "Próximo mantenimiento"; bloque Próximos; tab Programados con filtro "Esta semana". Regenerar sitio, documentar en `CLAUDE.md`, aplicar migración en producción con confirmación.
