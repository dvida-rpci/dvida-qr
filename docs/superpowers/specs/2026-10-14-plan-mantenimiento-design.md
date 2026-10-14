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

La pestaña **Programación** de la GUI y la pestaña **Programados** de `mantenimientos.html` leen `maintenance_agenda` y tienen filtros rápidos (por defecto **Esta semana**):

- **Atrasados**: `status = vencido` y `sin_registro` (siempre arriba, en rojo).
- **Esta semana**: `due_date` de lunes a domingo de la semana actual (hora de Colombia).
- **Próxima semana** y **Próximas 4 semanas**.
- **Todo**.

Cada fila muestra el TAG (con link a su ficha en el sitio), el servicio, la actividad, la fecha, el estado y el origen (automático, manual o registro). Se combinan con los tabs de categoría y el buscador existentes. Desde la GUI, una fila se puede **reprogramar a mano** (abre `schedule_manual` con la advertencia de arriba).

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
3. **Programación** — tabla de `maintenance_schedule` de toda la planta: vencidos primero, luego por `due_date`; filtros por estado y clase; búsqueda por TAG.

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

## Fases (un plan por fase)

1. **Base:** migración, función de alta, cálculo, RLS, `maintenance_plan.py`, `sabana_base.xlsx` inicial, `setup_supabase_planta.sh`, tests. Todo en Supabase local.
2. **GUI:** migración de programación manual (`maintenance_manual_schedule`, `maintenance_agenda`, `schedule_manual`) con sus tests; ventana "Plan de mantenimiento" (con filtro "Esta semana" y reprogramación manual con advertencia) y cambios en 🧰 Mantenimientos.
3. **Sitio:** formulario con actividades, horas y advertencia en "Próximo mantenimiento"; bloque Próximos; tab Programados con filtro "Esta semana". Regenerar sitio, documentar en `CLAUDE.md`, aplicar migración en producción con confirmación.
