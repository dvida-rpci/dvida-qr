# Vista pública de últimos mantenimientos — diseño

Fecha: 2026-09-21

## Propósito

Agregar al sitio una página con los **últimos mantenimientos realizados**, filtrable por categoría (EQUIPOS / TANQUES / INSTRUMENTOS), con buscador por TAG o nombre del elemento, visible **sin iniciar sesión**. Complementa el historial por ficha del diseño [2026-09-20-historico-mantenimientos-design.md](2026-09-20-historico-mantenimientos-design.md).

Decisiones ya tomadas con el usuario:

- Todo el dato de mantenimiento es público de lectura: descripción, repuestos, próximo mantenimiento, **autor (nombre)** y **fotos/audio**.
- El historial dentro de cada ficha también pasa a ser de lectura sin login; el login se pide solo para agregar (registro, comentario o adjunto).
- La vista vive en una **página nueva** (`mantenimientos.html`), enlazada desde el menú lateral y el inicio, no dentro del home.

**Fuera de alcance:** búsqueda por texto dentro de la descripción o por autor; edición/borrado desde esta vista (sigue en `gui.py`); notificaciones o predicción de mantenimientos (fase 2 del diseño original).

## Impacto en seguridad (revertir una decisión previa)

La migración `20260921180723` restringió la lectura de registros, adjuntos, comentarios y del bucket a usuarios con fila en `profiles` (`is_member()`). Este diseño **revierte esa restricción solo para lectura**: cualquier persona con la `anon_key` (pública en el sitio) podrá leer todo el histórico y descargar sus adjuntos.

Se mantiene sin cambios:

- Escritura (`insert`/`update`/`delete`) exige sesión, y `insert` exige además perfil (`is_member()`).
- `maintenance_audit_log` y `profiles` siguen sin lectura pública.
- El correo y el rol de los usuarios **no** se exponen; solo `full_name` del autor.

Efecto secundario a tener presente: los adjuntos son públicos por URL firmada solicitada con la `anon_key`; borrar un registro desde `gui.py` no elimina el archivo del bucket (ya documentado), por lo que esos archivos seguirían accesibles a quien conserve la ruta.

## Base de datos (migración nueva)

Archivo nuevo en `supabase/migrations/` (timestamp posterior a `20260921180723`):

1. Políticas `select` para el rol `anon` (`using (true)`) en:
   - `public.maintenance_records`
   - `public.maintenance_attachments`
   - `public.maintenance_comments`
   - `storage.objects` con `bucket_id = 'maintenance-attachments'` (necesario para `createSignedUrl` con `anon`).
2. Vista `public.author_names (user_id, full_name)` sobre `public.profiles`, con `security_invoker = false` (corre con los permisos del dueño para saltar `profiles_select_own`), y `grant select` a `anon` y `authenticated`. Solo esas dos columnas.
3. Las políticas `select_member` se **reemplazan** por una única política `select` `to anon, authenticated`; conservarlas haría que un usuario logueado sin perfil viera menos que un visitante anónimo.
4. `revoke all` sobre `author_names` a `anon`/`authenticated` y `grant select` solo: Supabase concede ALL por defecto y una vista simple es auto-actualizable (sin el revoke, anon podría escribir en `profiles`).

La consulta del cliente une registros con `author_names` (por `created_by = user_id`) en un segundo `select` y combina en el navegador, para no depender de relaciones entre tabla y vista en PostgREST.

## Página `mantenimientos.html`

Generada por `excel_migrator.py` (nueva función `render_maintenance_page`), con la misma cabecera/banner/menú que el resto. Carga `maintenance_feed.css` y `maintenance_feed.js`, más el cliente de Supabase y la config que ya se inyecta en las fichas.

### Datos incrustados

El generador incrusta en la página un JSON `window.__TAG_INDEX__`: lista de `{tag, categoria, servicio, filename}` para todos los TAGs (misma fuente que el buscador del sitio). La categoría no existe en la base de datos; solo vive en el Excel.

### Controles

- **Buscador** (`<input type="search">`) encima de los tabs. Busca por TAG o por `servicio`, sin distinguir mayúsculas ni tildes, por coincidencia parcial. Espera 300 ms tras dejar de escribir. Botón ✕ para limpiar.
- **Tabs**: `Todos` (por defecto), `EQUIPOS`, `TANQUES`, `INSTRUMENTOS`. Semántica `role="tablist"`, navegables con teclado.
- Tabs y buscador se **combinan** (intersección).

### Consulta

1. En el navegador se filtra `__TAG_INDEX__` por categoría del tab y por texto del buscador → lista de TAGs candidatos.
2. Si la lista queda vacía: mensaje "No hay mantenimientos para «texto»" sin consultar.
3. Si no: `maintenance_records` con `.in('tag_id', candidatos)` (omitido en `Todos` sin texto), orden `performed_at desc, created_at desc`, `.range(offset, offset+9)`. Se pide 11 filas para saber si hay más y mostrar "Mostrar más" sin una consulta extra de conteo.
4. Adjuntos de esos registros (`maintenance_attachments` con `record_id in (...)`) y nombres de autor (`author_names` con `user_id in (...)`).
5. "Mostrar más" pide las siguientes 10 (offset += 10) y las agrega al final. Cambiar de tab o de texto reinicia la lista.

### Tarjeta de registro

TAG (enlace a su ficha, `../<categoria>/<filename>`), fecha (`performed_at`), tipo (preventivo/correctivo), descripción, repuestos, próximo mantenimiento, autor (`full_name`), marca ⚠️ si `is_date_anomaly`, y miniaturas de adjuntos. Todo texto se escapa (`escapeHtml`) antes de insertarse.

## Popup de multimedia

Modal propio de la vista (no reutiliza el `#lightbox` de las fichas porque este es solo de imágenes):

- Botón **✕**, tecla **Esc** y clic en el fondo cierran.
- Flechas **‹ ›**, teclas ← → y swipe táctil (≥50 px) navegan entre los adjuntos **del mismo registro**. Con un solo adjunto las flechas se ocultan (clase `.single`, igual que el lightbox actual).
- Foto → `<img>`; audio → `<audio controls>`. Las URLs firmadas (1 h) se piden en lote con `createSignedUrls` al renderizar cada página de resultados; el popup no hace peticiones.
- Bloquea el scroll del fondo mientras está abierto y devuelve el foco al elemento que lo abrió.

## Historial dentro de la ficha (cambio en `maintenance.js`)

`initHistorialView` deja de exigir sesión para **leer**: carga y muestra el historial directamente. El formulario de alta y "+ Comentario/adjunto" se muestran solo con sesión; sin sesión aparece un botón "Iniciar sesión para agregar" que abre el formulario de login existente. El modal de re-login por sesión expirada se mantiene.

## Archivos

| Archivo | Cambio |
| --- | --- |
| `supabase/migrations/<ts>_public_read.sql` | Nuevo: políticas `anon` + vista `author_names` |
| `maintenance_feed.js`, `maintenance_feed.css` | Nuevos: buscador, tabs, paginación, tarjetas, popup |
| `excel_migrator.py` | `render_maintenance_page`, enlace en menú e inicio, copia de los dos archivos nuevos, whitelist de limpieza (`mantenimientos.html`) |
| `maintenance.js` | Lectura sin login en la ficha; login solo para escribir |
| `tests/supabase/` | Ver Pruebas |
| `CLAUDE.md` | Documentar la vista pública, la lectura anónima y el cambio de política |

`maintenance_feed.js` crea su propio cliente Supabase (unas pocas líneas) en vez de acoplarse al cierre interno de `maintenance.js`.

## Errores

- Supabase no responde o devuelve error: la lista muestra el error con botón "Reintentar"; el resto del sitio no se afecta.
- Sin resultados: mensaje vacío explícito.
- Un adjunto cuya URL firmada falla: el popup muestra "No se pudo cargar el archivo" y permite seguir navegando.

## Pruebas

**RLS (pytest, requiere `supabase start`):**

- `anon` puede `select` en registros, adjuntos, comentarios y `author_names`; puede crear una URL firmada y descargar un objeto del bucket.
- `anon` **no** puede `insert`/`update`/`delete` en ninguna de esas tablas ni subir/borrar en el bucket.
- `anon` no lee `maintenance_audit_log` ni `profiles`; `author_names` no expone otras columnas (correo, rol).
- Ajustar `test_hardening.py` y los tests existentes que asumían lectura solo para `authenticated`/miembros: las afirmaciones de "no ve nada" del *outsider* pasan a valer solo para escritura.

**UI (navegador headless contra Supabase local, con la skill browser-automation):**

- Sin sesión: la página lista los 10 más recientes ordenados; "Mostrar más" carga otros 10 y desaparece al agotarse.
- Cada tab filtra por categoría; el buscador filtra por TAG y por servicio; tab + búsqueda se combinan.
- El popup abre foto y audio, navega con flechas/teclado y cierra con ✕/Esc.
- La ficha muestra el historial sin sesión y pide login solo al intentar agregar.
- Vista a 360 px y 390 px sin scroll horizontal introducido por esta página.

## Despliegue

1. Regenerar el sitio con `./update_site_from_excel.sh` (incluye `mantenimientos.html`).
2. Aplicar la migración en Supabase remoto (`qgxvukllzuaiyhzegaef`). **Modifica accesos de producción: se hace solo con confirmación explícita del usuario.**
3. Commit y push de `docs/` y de `supabase/migrations/`.
