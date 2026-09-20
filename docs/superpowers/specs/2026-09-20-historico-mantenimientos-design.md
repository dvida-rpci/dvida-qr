# Histórico de mantenimientos por TAG (fase 1) — diseño

Fecha: 2026-09-20

## Propósito

Hoy el sitio muestra fichas técnicas estáticas por TAG (generadas desde Excel), pero no hay forma de registrar ni consultar los mantenimientos realizados sobre cada equipo. Este diseño agrega una sección de **historial de mantenimientos**, cargable por técnicos de campo (desde el celular, escaneando el mismo QR que ya lleva a la ficha) y por personal de oficina (desde `gui.py`), con lectura del histórico completo por equipo.

**Fuera de alcance de este diseño (fase 2, a brainstormear después):**
- Predicción de próximo mantenimiento en base a una matriz/sábana de frecuencias por tipo de equipo, y alarmas automáticas. Depende de tener datos reales cargados con este sistema primero.
- Migración del hosting del sitio de GitHub Pages a Cloudflare Pages. Es independiente (solo afecta dónde se sirven los archivos estáticos; Supabase se consume igual desde cualquier origen, ajustando la lista de *redirect/auth URLs* permitidas en el proyecto Supabase).

## Arquitectura

```
Ficha del TAG (HTML/JS estático, GitHub Pages)
   └── Sección "Historial de Mantenimiento" (nueva, visible solo logueado)
         └── Supabase JS SDK (browser) ──┐
                                          ├──> Supabase (Postgres + Auth + Storage)
gui.py (NiceGUI, oficina)                │
   └── Pantalla nueva "Mantenimientos"   │
         └── supabase-py (Python) ───────┘
```

Ni el sitio ni `gui.py` se comunican entre sí — ambos son clientes independientes de la misma base Supabase. No hay backend propio: el control de acceso lo resuelve Supabase (Auth + Row Level Security), consistente con la decisión ya tomada en el proyecto de "sitio estático puro, no CMS" (ver CLAUDE.md).

La sección de historial está **aislada del resto de la ficha**: si Supabase no responde, solo esa sección muestra error — el resto de la página (specs, documentos, imágenes) sigue funcionando igual que hoy, incluso offline/`file://`.

## Modelo de datos (Supabase / Postgres)

### `profiles`

| Columna | Tipo | Notas |
|---|---|---|
| `user_id` | uuid, PK | FK a `auth.users.id` |
| `full_name` | text | nombre para mostrar |
| `role` | text | `tecnico` \| `oficina` |

Las cuentas (Auth + fila en `profiles`) las crea manualmente el administrador del proyecto desde el dashboard de Supabase. No hay auto-registro público.

### `maintenance_records`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid, PK | default `gen_random_uuid()` |
| `tag_id` | text | el `TAG` del equipo (mismo identificador que usa `TAG_RESOURCES.xlsx`), indexado |
| `performed_at` | date | fecha en que el técnico declara que se hizo el mantenimiento |
| `type` | text | `preventivo` \| `correctivo` |
| `description` | text | descripción inicial del trabajo — inmutable salvo edición por `oficina` |
| `parts_used` | text | texto libre (repuestos/insumos), nullable |
| `next_scheduled_at` | date | próximo mantenimiento programado, nullable — dato manual en fase 1, no calculado |
| `created_by` | uuid | FK a `auth.users`, se llena solo con el usuario logueado |
| `created_at` | timestamptz | default `now()` — timestamp real del registro en la BD |
| `is_date_anomaly` | boolean, generated always as `(abs(created_at::date - performed_at) > 2) stored` | calculado por Postgres (resta de dos `date` da un entero de días), no duplicado en cada cliente |

### `maintenance_attachments`

Fotos y notas de audio del evento, en una sola tabla (mismo tope, mismas reglas de acceso).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid, PK | |
| `record_id` | uuid | FK a `maintenance_records.id` |
| `kind` | text | `photo` \| `audio` |
| `storage_path` | text | ruta dentro del bucket privado `maintenance-attachments` |
| `created_by` | uuid | FK a `auth.users` |
| `created_at` | timestamptz | default `now()` |

- **Tope de 5 adjuntos por evento**, mezclando fotos y audios (mismo contador). Aplicado solo en la interfaz (sitio y GUI son las únicas dos vías de escritura); no hay trigger de BD que lo fuerce — caso borde aceptado: una carrera de milisegundos entre dos cargas simultáneas al mismo registro podría en teoría superar 5.
- **Fotos:** comprimidas antes de subir — redimensionadas a un ancho máximo (~1600px) y recodificadas a JPEG calidad ~70%. En el sitio, con `<canvas>` (sin librería externa); en `gui.py`, con Pillow.
- **Audio:** grabado con `getUserMedia({audio:true})` + `MediaRecorder` en el sitio (corte automático a 1 minuto, contador visible mientras graba); en `gui.py` se sube un archivo de audio existente (no se asume micrófono disponible en la PC de oficina). Reproducción con `<audio controls>` nativo.
- Bucket privado (no público) — el acceso a los archivos pasa por policies de Storage, coherente con que toda la sección de historial está gated por login.

### `maintenance_comments`

Comentarios adicionales sobre un evento ya cargado (el mecanismo por el cual un técnico "agrega" información sin poder tocar lo ya registrado).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid, PK | |
| `record_id` | uuid | FK a `maintenance_records.id` |
| `author_id` | uuid | FK a `auth.users` |
| `body` | text | |
| `created_at` | timestamptz | default `now()` |

### `maintenance_audit_log`

Auditoría inmutable de toda edición/borrado hecho por `oficina`.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid, PK | |
| `record_id` | uuid | id del registro afectado |
| `action` | text | `update` \| `delete` |
| `old_data` | jsonb | estado anterior |
| `new_data` | jsonb | estado nuevo (null si es `delete`) |
| `changed_by` | uuid | FK a `auth.users` |
| `changed_at` | timestamptz | default `now()` |

Se llena automáticamente vía **trigger** `AFTER UPDATE OR DELETE` en `maintenance_records` (y análogo en `maintenance_attachments`/`maintenance_comments` si `oficina` los edita/borra) — el cliente nunca escribe en esta tabla directamente.

## Roles, permisos y RLS

| Acción | Técnico | Oficina |
|---|---|---|
| SELECT (records, adjuntos, comentarios) | ✅ todos | ✅ todos |
| INSERT record | ✅ | ✅ |
| INSERT adjunto (foto/audio) | ✅ solo en registros propios (`created_by = auth.uid()`), hasta el tope de 5 | ✅ en cualquiera |
| INSERT comentario | ✅ solo en registros propios | ✅ en cualquiera |
| UPDATE / DELETE (record, adjunto o comentario) | ❌ nunca | ✅ (queda en `maintenance_audit_log`) |
| SELECT `maintenance_audit_log` | ❌ | ✅ |
| UPDATE / DELETE `maintenance_audit_log` | ❌ | ❌ (nadie — sin policy, denegado por default; solo lo escribe el trigger) |

Implementación: una función `is_oficina()` (consulta `profiles.role` para `auth.uid()`) usada en las policies de `UPDATE`/`DELETE`. La restricción "técnico solo agrega, nunca modifica" se resuelve estructuralmente: técnico no tiene ningún `UPDATE`/`DELETE` policy sobre `maintenance_records`, y sus "ediciones" son en realidad `INSERT`s en `maintenance_attachments`/`maintenance_comments` — insertar nunca puede borrar ni alterar una fila existente.

## Indicador de anomalía por fecha

`maintenance_records.is_date_anomaly` (columna generada, ver arriba) se muestra como un badge/ícono de alerta (⚠️) junto al evento — tanto en el acordeón del sitio como en la tabla de `gui.py`, visible para ambos roles (es información, no una acción restringida). Se dispara cuando `|created_at − performed_at| > 2 días`, en cualquier dirección (registro tardío o fecha de mantenimiento futura respecto al registro — ambos casos tratados como la misma señal de posible anomalía de procedimiento).

No se agrega un filtro/reporte dedicado de anomalías en fase 1 (no fue pedido), pero al ser una columna calculada, agregar ese filtro después es un simple `WHERE is_date_anomaly`, sin rediseño.

## Flujos

### Técnico (mobile, desde el QR)

1. Escanea QR → llega a la ficha del TAG (como hoy).
2. Acordeón "Historial de Mantenimiento" pide login si no hay sesión (form email/password, pantalla completa en mobile).
3. Logueado: ve lista cronológica descendente de eventos (fecha, tipo, descripción, comentarios, adjuntos con badge de anomalía si aplica) + botón "**+ Registrar mantenimiento**".
4. Formulario de carga: fecha (default hoy), tipo (radio grande, táctil), descripción, repuestos, próximo programado (opcional), hasta 5 adjuntos (fotos vía `capture="environment"` o audio grabado in-browser).
5. En cada evento propio, botón "+ Agregar comentario/adjunto" → formulario reducido (texto y/o adjuntos), respetando el tope acumulado de 5.

Todo el flujo de técnico es **mobile-first**, siguiendo el mismo patrón responsive que ya usa el resto del sitio (topbar+hamburger <900px, touch targets ≥44px, etc.).

### Oficina (`gui.py`)

Pantalla nueva "Mantenimientos": login (mismas cuentas Supabase Auth), selector de TAG, tabla de eventos con acciones crear/editar/borrar, subida de adjuntos desde archivo (no cámara/micrófono, ya que es una app de escritorio), mismo pipeline de compresión (Pillow) antes de subir fotos.

### Lectura

Cualquier usuario logueado ve el historial completo de cualquier TAG. Reutiliza el patrón de lightbox ya existente en el sitio para las fotos.

## Manejo de errores

- **Conectividad (crítico, uso en campo):** el formulario de carga guarda su estado en `localStorage` antes de intentar el submit — si falla por red, no se pierde lo escrito; se muestra error + botón "Reintentar".
- **Adjuntos:** se suben uno por uno, no en un solo request — si algunos fallan, los que subieron bien quedan asociados al registro y solo se reintentan los fallidos.
- **Sesión expirada a mitad de carga:** se detecta el 401, se pide re-login en un modal sin descartar el formulario, y al loguearse continúa el submit pendiente.
- **Supabase caído/inalcanzable:** solo la sección de historial muestra error ("No se pudo cargar el historial, reintentar"); el resto de la ficha sigue funcionando sin depender de Supabase.
- **Validación cliente:** campos obligatorios (fecha, tipo, descripción) antes de habilitar submit; tope de 5 adjuntos deshabilita el control de agregar.
- **403 inesperado (RLS):** mensaje genérico "No tenés permiso para esta acción" — no debería ocurrir en uso normal porque la UI oculta acciones según rol, pero no se asume que el cliente es la única defensa.
- **Carrera del tope de 5 adjuntos:** caso borde aceptado, no resuelto en fase 1 (ver nota en Modelo de datos).

## Testing

El repo no tiene hoy suite de tests automatizados; se mantiene esa convención salvo donde hay un límite de seguridad real que vale la pena fijar en código:

- **RLS (automatizado):** suite con Supabase local (`supabase` CLI + Postgres en Docker) y pytest, con dos usuarios de prueba (`tecnico`, `oficina`) verificando cada celda de la tabla de permisos — incluyendo que nadie pueda `UPDATE`/`DELETE` en `maintenance_audit_log`.
- **Flujos de UI (manual):** checklist en emulador mobile de DevTools (y celular real si hay a mano) — login de ambos roles, carga con cámara y grabación de audio, throttling de red para simular conexión mala en campo, verificar que el draft en `localStorage` sobrevive un fallo de red.
- **Compresión de imágenes (manual):** subir una foto real y confirmar en DevTools que el archivo subido pesa menos que el original, en sitio y en GUI.
- **`gui.py`:** verificación manual, como el resto de la GUI hoy.
