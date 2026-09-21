# Vista pública de últimos mantenimientos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Página pública `mantenimientos.html` con los últimos mantenimientos (10 + "Mostrar más"), tabs por categoría, buscador por TAG/elemento y popup de fotos/audio, más historial de ficha legible sin login.

**Architecture:** Migración que abre la *lectura* (no la escritura) del histórico al rol `anon` y expone `author_names(user_id, full_name)`. `excel_migrator.py` genera `mantenimientos.html` con un índice TAG→categoría/servicio incrustado; `maintenance_feed.js` (lógica pura testeable con node + capa DOM) consulta Supabase con `tag_id in (...)`. `maintenance.js` deja de exigir sesión para leer.

**Tech Stack:** Supabase (Postgres RLS, Storage), supabase-js v2 (CDN), JS vainilla (ES5-style como `maintenance.js`), Python 3.12 + pytest, `node --test` para la lógica pura.

**Spec:** [docs/superpowers/specs/2026-09-21-ultimos-mantenimientos-design.md](../specs/2026-09-21-ultimos-mantenimientos-design.md)

## Convenciones del repo (obligatorias)

- Idioma español en textos de UI, comentarios, commits y docs.
- Commits terminan con la línea `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- `node` no está en el PATH: usar `/home/administrador/.codegpt/bin/node` (v22).
- Tests de RLS: `python3 -m pytest tests/supabase -v` (requiere el stack local `supabase start`, ya corriendo; `.env.test` existe).
- Las migraciones locales se aplican con `supabase db query --local -f <archivo>` (el historial local de migraciones no está sincronizado; **no** usar `supabase migration up` ni `db reset`).
- **Nunca** aplicar nada a producción (`qgxvukllzuaiyhzegaef`) sin confirmación explícita del usuario (Task 7).
- No commitear `.claude/`, `.mcp.json`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `GUIA_GUI_QR_DEPLOY.txt` (sin seguimiento a propósito).

## Desviaciones deliberadas respecto al spec (se corrigen en Task 1)

1. **Política de lectura única `to anon, authenticated`** en vez de conservar `select_member` + agregar una de `anon`. Con dos políticas, un usuario logueado *sin perfil* vería menos que un visitante anónimo. Las políticas `select_member` se reemplazan.
2. **URLs firmadas en lote** (`createSignedUrls`) al renderizar cada página de resultados, no al abrir el popup. Una sola llamada por página y el popup no espera red.

## Estructura de archivos

| Archivo | Responsabilidad |
| --- | --- |
| `supabase/migrations/20260921210000_public_read.sql` (nuevo) | Lectura pública + vista `author_names` |
| `tests/supabase/test_public_read.py` (nuevo) | RLS: anon lee, anon no escribe, vista segura |
| `tests/supabase/test_hardening.py` (modif.) | El *outsider* ahora puede leer, sigue sin poder escribir |
| `maintenance_feed.js` (nuevo) | Lógica pura (exportable a node) + UI de la página |
| `maintenance_feed.css` (nuevo) | Estilos de la página y del popup |
| `tests/js/feed_logic.test.js` (nuevo) | Tests de la lógica pura con `node --test` |
| `excel_migrator.py` (modif.) | Genera `mantenimientos.html`, enlace en menú e inicio, copia assets, whitelist |
| `tests/test_generator_feed.py` (nuevo) | Genera el sitio en un tmp y verifica salida |
| `maintenance.css` (modif.) | Estilos del enlace del menú y del botón del inicio (cargan en todas las páginas) |
| `maintenance.js` (modif.) | Historial de ficha legible sin login |
| `CLAUDE.md` (modif.) | Documentación |

---

### Task 1: Lectura pública en la base de datos (TDD) + corrección del spec

**Files:**
- Create: `tests/supabase/test_public_read.py`
- Create: `supabase/migrations/20260921210000_public_read.sql`
- Modify: `tests/supabase/test_hardening.py`
- Modify: `docs/superpowers/specs/2026-09-21-ultimos-mantenimientos-design.md`

- [ ] **Step 1: Escribir los tests de RLS anónimo (fallarán)**

Crear `tests/supabase/test_public_read.py`:

```python
"""Lectura pública del histórico (2026-09-21): el rol anon lee, nunca escribe."""
import datetime

import pytest
from postgrest.exceptions import APIError
from storage3.utils import StorageException
from supabase import Client, create_client

from tests.supabase.conftest import SUPABASE_ANON_KEY, SUPABASE_URL

BUCKET = "maintenance-attachments"
CONTENT = b"contenido-de-prueba"


@pytest.fixture
def anon_client() -> Client:
    """Cliente sin sesión: lo que ve cualquier visitante del sitio."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _record(tag_id: str, **overrides):
    payload = {
        "tag_id": tag_id,
        "performed_at": datetime.date.today().isoformat(),
        "type": "preventivo",
        "description": "Cambio de filtro",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def seeded(tecnico_client, random_tag_id):
    record_id = (
        tecnico_client.table("maintenance_records")
        .insert(_record(random_tag_id))
        .execute()
        .data[0]["id"]
    )
    tecnico_client.table("maintenance_comments").insert(
        {"record_id": record_id, "body": "comentario"}
    ).execute()
    path = f"{random_tag_id}/{record_id}/foto.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, CONTENT, {"content-type": "image/jpeg"})
    tecnico_client.table("maintenance_attachments").insert(
        {"record_id": record_id, "kind": "photo", "storage_path": path}
    ).execute()
    return {"tag_id": random_tag_id, "record_id": record_id, "path": path}


def _rows(query):
    """Filas visibles; si el rol ni siquiera tiene permiso sobre la tabla, cuenta como vacío."""
    try:
        return query.execute().data
    except APIError:
        return []


# ── Lectura ──────────────────────────────────────────────────────────────


def test_anon_reads_records(anon_client, seeded):
    rows = anon_client.table("maintenance_records").select("*").eq("id", seeded["record_id"]).execute().data
    assert len(rows) == 1
    assert rows[0]["description"] == "Cambio de filtro"


def test_anon_reads_attachments_and_comments(anon_client, seeded):
    atts = anon_client.table("maintenance_attachments").select("*").eq("record_id", seeded["record_id"]).execute().data
    comments = anon_client.table("maintenance_comments").select("*").eq("record_id", seeded["record_id"]).execute().data
    assert len(atts) == 1
    assert len(comments) == 1


def test_anon_can_sign_and_download_attachment(anon_client, seeded):
    signed = anon_client.storage.from_(BUCKET).create_signed_urls([seeded["path"]], 60)
    assert signed[0].get("signedURL") or signed[0].get("signedUrl")
    assert anon_client.storage.from_(BUCKET).download(seeded["path"]) == CONTENT


def test_author_names_exposes_only_id_and_name(anon_client, tecnico_id):
    rows = anon_client.table("author_names").select("*").eq("user_id", tecnico_id).execute().data
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"user_id", "full_name"}
    assert rows[0]["full_name"] == "Test tecnico"


# ── Escritura: sigue exigiendo sesión ────────────────────────────────────


def test_anon_cannot_insert_record(anon_client, random_tag_id):
    with pytest.raises(APIError):
        anon_client.table("maintenance_records").insert(_record(random_tag_id)).execute()


def test_anon_cannot_update_or_delete_record(anon_client, service_client, seeded):
    anon_client.table("maintenance_records").update({"description": "hackeado"}).eq(
        "id", seeded["record_id"]
    ).execute()
    anon_client.table("maintenance_records").delete().eq("id", seeded["record_id"]).execute()

    row = service_client.table("maintenance_records").select("*").eq("id", seeded["record_id"]).execute().data
    assert len(row) == 1
    assert row[0]["description"] == "Cambio de filtro"


def test_anon_cannot_insert_comment_or_attachment(anon_client, seeded):
    with pytest.raises(APIError):
        anon_client.table("maintenance_comments").insert(
            {"record_id": seeded["record_id"], "body": "spam"}
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("maintenance_attachments").insert(
            {"record_id": seeded["record_id"], "kind": "photo", "storage_path": "x/y.jpg"}
        ).execute()


def test_anon_cannot_upload_or_delete_storage(anon_client, seeded, random_tag_id):
    with pytest.raises(StorageException):
        anon_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/anon.jpg", CONTENT, {"content-type": "image/jpeg"}
        )
    anon_client.storage.from_(BUCKET).remove([seeded["path"]])
    assert anon_client.storage.from_(BUCKET).download(seeded["path"]) == CONTENT


# ── Lo que sigue privado ─────────────────────────────────────────────────


def test_anon_cannot_read_audit_log_or_profiles(anon_client, seeded):
    assert _rows(anon_client.table("maintenance_audit_log").select("*")) == []
    assert _rows(anon_client.table("profiles").select("*")) == []


def test_anon_cannot_write_through_author_names(anon_client, service_client, tecnico_id):
    with pytest.raises(APIError):
        anon_client.table("author_names").insert(
            {"user_id": tecnico_id, "full_name": "hackeado"}
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("author_names").update({"full_name": "hackeado"}).eq(
            "user_id", tecnico_id
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("author_names").delete().eq("user_id", tecnico_id).execute()

    profile = service_client.table("profiles").select("full_name").eq("user_id", tecnico_id).execute().data
    assert profile[0]["full_name"] == "Test tecnico"
```

- [ ] **Step 2: Ejecutar y comprobar que fallan**

Run: `python3 -m pytest tests/supabase/test_public_read.py -v 2>&1 | tail -25`
Expected: FAIL en `test_anon_reads_*`, `test_anon_can_sign_and_download_attachment` y `test_author_names_exposes_only_id_and_name` (filas vacías / relación `author_names` inexistente). Los tests de "no escribe" pueden pasar ya (correcto: es la línea base).

- [ ] **Step 3: Escribir la migración**

Crear `supabase/migrations/20260921210000_public_read.sql`:

```sql
-- Lectura pública del histórico de mantenimientos (2026-09-21).
-- Decisión de producto: el histórico completo (incluidos autor y adjuntos) es
-- visible sin sesión. La ESCRITURA sigue exigiendo sesión y perfil (policies
-- insert/update/delete sin cambios). Reemplaza las policies select_member del
-- endurecimiento previo por una sola de lectura para anon y authenticated, para
-- que un usuario logueado sin perfil no vea MENOS que un visitante anónimo.

drop policy "maintenance_records_select_member" on public.maintenance_records;
create policy "maintenance_records_select_public"
  on public.maintenance_records for select
  to anon, authenticated
  using (true);

drop policy "maintenance_attachments_select_member" on public.maintenance_attachments;
create policy "maintenance_attachments_select_public"
  on public.maintenance_attachments for select
  to anon, authenticated
  using (true);

drop policy "maintenance_comments_select_member" on public.maintenance_comments;
create policy "maintenance_comments_select_public"
  on public.maintenance_comments for select
  to anon, authenticated
  using (true);

-- El bucket sigue siendo privado: anon necesita select en storage.objects para
-- poder pedir URLs firmadas y descargar.
drop policy "maintenance_attachments_storage_select" on storage.objects;
create policy "maintenance_attachments_storage_select_public"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'maintenance-attachments');

-- Nombre del autor sin exponer profiles (correo, rol). La vista corre con los
-- permisos de su dueño (security_invoker = false) para saltar profiles_select_own.
create view public.author_names as
  select user_id, full_name from public.profiles;

alter view public.author_names set (security_invoker = false);

-- CRÍTICO: Supabase concede ALL sobre objetos nuevos de public a anon y
-- authenticated. Una vista simple es auto-actualizable, así que sin este revoke
-- cualquiera podría insertar/editar/borrar perfiles a través de la vista.
revoke all on public.author_names from anon, authenticated;
grant select on public.author_names to anon, authenticated;
```

- [ ] **Step 4: Aplicar en el stack local y ejecutar los tests nuevos**

Run: `supabase db query --local -f supabase/migrations/20260921210000_public_read.sql 2>&1 | tail -5`
Expected: sin errores (JSON con `rows: []`).

Run: `python3 -m pytest tests/supabase/test_public_read.py -v 2>&1 | tail -20`
Expected: 10 passed.

- [ ] **Step 5: Actualizar `test_hardening.py`**

Estos tests afirmaban que un usuario logueado sin perfil no lee nada; ahora todo es de lectura pública, pero sigue sin poder escribir.

Edit 1 — docstring. Reemplazar:

```
2. Un usuario autenticado sin fila en profiles (p. ej. alguien que se auto-registra
   con el anon key público) no ve ni escribe nada.
```
por:
```
2. Un usuario autenticado sin fila en profiles (p. ej. alguien que se auto-registra
   con el anon key público) puede LEER (el histórico es público desde 2026-09-21)
   pero no escribe nada.
```

Edit 2 — reemplazar `# ── 2. Usuario sin profile no accede a nada` por `# ── 2. Usuario sin profile: lee (todo es público) pero no escribe`, y reemplazar la función `test_outsider_cannot_select_records` completa por:

```python
def test_outsider_can_read_records(tecnico_client, outsider_client, random_tag_id):
    tecnico_client.table("maintenance_records").insert(_record(random_tag_id)).execute()

    response = (
        outsider_client.table("maintenance_records").select("*").eq("tag_id", random_tag_id).execute()
    )
    assert len(response.data) == 1
```

Edit 3 — renombrar `test_outsider_cannot_select_attachments_or_comments` a `test_outsider_can_read_attachments_and_comments` y reemplazar sus dos asserts finales:

```python
    assert comments.data == []
    assert attachments.data == []
```
por:
```python
    assert len(comments.data) == 1
    assert len(attachments.data) == 1
```

Edit 4 — reemplazar la función `test_outsider_cannot_upload_or_read_storage` completa por:

```python
def test_outsider_can_download_but_not_upload_storage(tecnico_client, outsider_client, random_tag_id):
    path = f"{random_tag_id}/test/outsider.jpg"
    tecnico_client.storage.from_(BUCKET).upload(
        path, b"contenido-de-prueba", {"content-type": "image/jpeg"}
    )

    assert outsider_client.storage.from_(BUCKET).download(path) == b"contenido-de-prueba"
    with pytest.raises(StorageException):
        outsider_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/test/outsider-up.jpg",
            b"contenido-de-prueba",
            {"content-type": "image/jpeg"},
        )
```

`test_outsider_cannot_insert_record` no cambia.

- [ ] **Step 6: Suite completa de RLS**

Run: `python3 -m pytest tests/supabase -q 2>&1 | tail -4`
Expected: `50 passed` (40 previos + 10 nuevos; el conteo de hardening no cambia). Si algún test previo falla por asumir lectura restringida, ajustarlo con el mismo criterio (leer sí, escribir no) y reportarlo.

- [ ] **Step 7: Corregir el spec**

En `docs/superpowers/specs/2026-09-21-ultimos-mantenimientos-design.md`:

Reemplazar el punto 3 de "Base de datos":
```
3. Las políticas `select_member` existentes para `authenticated` se conservan (un usuario logueado sigue leyendo; no se rompe nada). Al haber una política `anon` no hace falta cambiarlas.
```
por:
```
3. Las políticas `select_member` se **reemplazan** por una única política `select` `to anon, authenticated`; conservarlas haría que un usuario logueado sin perfil viera menos que un visitante anónimo.
4. `revoke all` sobre `author_names` a `anon`/`authenticated` y `grant select` solo: Supabase concede ALL por defecto y una vista simple es auto-actualizable (sin el revoke, anon podría escribir en `profiles`).
```
Y en "Popup de multimedia", reemplazar la viñeta `Las URLs se piden con \`createSignedUrl\` (1 h) al abrir el popup.` por `Las URLs firmadas (1 h) se piden en lote con \`createSignedUrls\` al renderizar cada página de resultados; el popup no hace peticiones.`

- [ ] **Step 8: Commit**

```bash
git add supabase/migrations/20260921210000_public_read.sql tests/supabase/test_public_read.py tests/supabase/test_hardening.py docs/superpowers/specs/2026-09-21-ultimos-mantenimientos-design.md
git commit -m "feat: lectura pública del histórico de mantenimientos (RLS anon + vista author_names)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Lógica pura del feed (TDD con node)

**Files:**
- Create: `tests/js/feed_logic.test.js`
- Create: `maintenance_feed.js`

- [ ] **Step 1: Escribir los tests (fallarán: el módulo no existe)**

Crear `tests/js/feed_logic.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const feed = require('../../maintenance_feed.js');

const INDEX = [
    { tag: '100-P-01A', categoria: 'EQUIPOS', servicio: 'Bomba de alimentación', filename: '100-P-01A.html' },
    { tag: '100-TK-01', categoria: 'TANQUES', servicio: 'Tanque de aireación', filename: '100-TK-01.html' },
    { tag: '600-SV-01', categoria: 'INSTRUMENTOS', servicio: 'Válvula solenoide', filename: '600-SV-01.html' },
    { tag: '200-P-01B', categoria: 'EQUIPOS', servicio: '', filename: '200-P-01B.html' },
];

test('normalize quita tildes, pasa a minúsculas y recorta', () => {
    assert.equal(feed.normalize('  Válvula SOLENOIDE '), 'valvula solenoide');
    assert.equal(feed.normalize(null), '');
});

test('escapeHtml escapa los 5 caracteres peligrosos', () => {
    assert.equal(feed.escapeHtml('<a href="x">&\'</a>'), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;');
});

test('formatDate pasa ISO a dd/mm/aaaa', () => {
    assert.equal(feed.formatDate('2026-09-21'), '21/09/2026');
});

test('filterTags sin filtros devuelve todo', () => {
    assert.equal(feed.filterTags(INDEX, 'TODOS', '').length, 4);
});

test('filterTags por categoría', () => {
    const tags = feed.filterTags(INDEX, 'EQUIPOS', '').map((e) => e.tag);
    assert.deepEqual(tags, ['100-P-01A', '200-P-01B']);
});

test('filterTags por TAG parcial sin distinguir mayúsculas', () => {
    const tags = feed.filterTags(INDEX, 'TODOS', '100-p').map((e) => e.tag);
    assert.deepEqual(tags, ['100-P-01A']);
});

test('filterTags por servicio sin distinguir tildes', () => {
    const tags = feed.filterTags(INDEX, 'TODOS', 'valvula').map((e) => e.tag);
    assert.deepEqual(tags, ['600-SV-01']);
});

test('filterTags combina categoría y texto (intersección)', () => {
    assert.deepEqual(feed.filterTags(INDEX, 'TANQUES', 'bomba'), []);
    assert.equal(feed.filterTags(INDEX, 'EQUIPOS', 'bomba').length, 1);
});

test('hasFilter', () => {
    assert.equal(feed.hasFilter('TODOS', ''), false);
    assert.equal(feed.hasFilter('TODOS', '   '), false);
    assert.equal(feed.hasFilter('EQUIPOS', ''), true);
    assert.equal(feed.hasFilter('TODOS', 'bomba'), true);
});

test('splitPage recorta a size y detecta si hay más', () => {
    const rows = Array.from({ length: 11 }, (_, i) => ({ id: i }));
    const page = feed.splitPage(rows, 10);
    assert.equal(page.rows.length, 10);
    assert.equal(page.hasMore, true);
    assert.equal(feed.splitPage(rows.slice(0, 10), 10).hasMore, false);
});

test('mergeRecords agrupa adjuntos y resuelve autor (con fallback)', () => {
    const records = [
        { id: 'r1', created_by: 'u1' },
        { id: 'r2', created_by: 'u-desconocido' },
    ];
    const attachments = [
        { id: 'a1', record_id: 'r1', kind: 'photo' },
        { id: 'a2', record_id: 'r1', kind: 'audio' },
    ];
    const authors = [{ user_id: 'u1', full_name: 'Ana' }];
    const merged = feed.mergeRecords(records, attachments, authors);
    assert.equal(merged[0].attachments.length, 2);
    assert.equal(merged[0].author_name, 'Ana');
    assert.equal(merged[1].attachments.length, 0);
    assert.equal(merged[1].author_name, 'Usuario desconocido');
});

test('stepIndex avanza y retrocede con vuelta circular', () => {
    assert.equal(feed.stepIndex(0, -1, 3), 2);
    assert.equal(feed.stepIndex(2, 1, 3), 0);
    assert.equal(feed.stepIndex(1, 1, 3), 2);
});

test('fichaHref arma la ruta relativa a la raíz', () => {
    assert.equal(feed.fichaHref(INDEX[0]), 'equipos/100-P-01A.html');
    assert.equal(feed.fichaHref(INDEX[2]), 'instrumentos/600-SV-01.html');
});

test('indexByTag indexa por TAG', () => {
    assert.equal(feed.indexByTag(INDEX)['100-TK-01'].categoria, 'TANQUES');
});
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `/home/administrador/.codegpt/bin/node --test tests/js/ 2>&1 | tail -8`
Expected: FAIL — `Cannot find module '../../maintenance_feed.js'`.

- [ ] **Step 3: Implementar la lógica pura**

Crear `maintenance_feed.js`:

```js
(function () {
    'use strict';

    var PAGE_SIZE = 10;

    // ── Lógica pura (sin DOM: se prueba con node --test) ─────────────────

    function normalize(str) {
        return String(str == null ? '' : str)
            .normalize('NFD').replace(/[̀-ͯ]/g, '')
            .toLowerCase().trim();
    }

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function formatDate(isoDate) {
        var parts = String(isoDate).split('-');
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    // index: [{tag, categoria, servicio, filename}]. category: 'TODOS' | nombre de categoría.
    function filterTags(index, category, query) {
        var q = normalize(query);
        return index.filter(function (entry) {
            if (category && category !== 'TODOS' && entry.categoria !== category) return false;
            if (!q) return true;
            return normalize(entry.tag).indexOf(q) !== -1 ||
                normalize(entry.servicio).indexOf(q) !== -1;
        });
    }

    function hasFilter(category, query) {
        return (!!category && category !== 'TODOS') || normalize(query) !== '';
    }

    // Se piden size + 1 filas: la fila extra indica que hay otra página.
    function splitPage(rows, size) {
        return { rows: rows.slice(0, size), hasMore: rows.length > size };
    }

    function mergeRecords(records, attachments, authors) {
        var attsByRecord = {};
        attachments.forEach(function (att) {
            (attsByRecord[att.record_id] = attsByRecord[att.record_id] || []).push(att);
        });
        var names = {};
        authors.forEach(function (a) { names[a.user_id] = a.full_name; });
        return records.map(function (record) {
            return Object.assign({}, record, {
                attachments: attsByRecord[record.id] || [],
                author_name: names[record.created_by] || 'Usuario desconocido'
            });
        });
    }

    function stepIndex(current, delta, length) {
        return (((current + delta) % length) + length) % length;
    }

    function fichaHref(entry) {
        return entry.categoria.toLowerCase() + '/' + entry.filename;
    }

    function indexByTag(index) {
        var map = {};
        index.forEach(function (entry) { map[entry.tag] = entry; });
        return map;
    }

    var api = {
        PAGE_SIZE: PAGE_SIZE,
        normalize: normalize,
        escapeHtml: escapeHtml,
        formatDate: formatDate,
        filterTags: filterTags,
        hasFilter: hasFilter,
        splitPage: splitPage,
        mergeRecords: mergeRecords,
        stepIndex: stepIndex,
        fichaHref: fichaHref,
        indexByTag: indexByTag
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (typeof document === 'undefined') {
        return;
    }

    // ── UI (DOM) — se agrega en la Task 3 ──
})();
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `/home/administrador/.codegpt/bin/node --test tests/js/ 2>&1 | tail -12`
Expected: `# pass 14`, `# fail 0`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_feed.js tests/js/feed_logic.test.js
git commit -m "feat: lógica pura del feed de mantenimientos (filtro, paginación, merge) con tests node" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: UI del feed (consulta, tarjetas, popup) y estilos

**Files:**
- Modify: `maintenance_feed.js` (reemplazar la línea `// ── UI (DOM) — se agrega en la Task 3 ──`)
- Create: `maintenance_feed.css`

- [ ] **Step 1: Agregar la capa DOM**

En `maintenance_feed.js`, reemplazar exactamente la línea `    // ── UI (DOM) — se agrega en la Task 3 ──` por:

```js
    // ── Cliente Supabase ─────────────────────────────────────────────────

    var BUCKET = 'maintenance-attachments';
    var SIGNED_URL_SECONDS = 3600;
    var sbClient = null;

    function getClient() {
        if (sbClient) return sbClient;
        var cfg = window.__SUPABASE_CONFIG__ || {};
        if (!cfg.url || !cfg.anonKey) {
            throw new Error('Falta configurar Supabase en site_config.json (bloque "supabase").');
        }
        sbClient = window.supabase.createClient(cfg.url, cfg.anonKey);
        return sbClient;
    }

    function unique(list) {
        return list.filter(function (v, i) { return list.indexOf(v) === i; });
    }

    function checked(result) {
        if (result.error) throw result.error;
        return result.data;
    }

    // Una llamada por página de resultados: firma todas las rutas de golpe.
    function signAttachments(client, attachments) {
        if (!attachments.length) return Promise.resolve(attachments);
        var paths = attachments.map(function (a) { return a.storage_path; });
        return client.storage.from(BUCKET).createSignedUrls(paths, SIGNED_URL_SECONDS)
            .then(function (result) {
                var rows = checked(result);
                var byPath = {};
                rows.forEach(function (row) { byPath[row.path] = row.signedUrl; });
                return attachments.map(function (a) {
                    return Object.assign({}, a, { url: byPath[a.storage_path] || null });
                });
            });
    }

    // tags: array de TAGs o null (sin filtro). Devuelve {records, hasMore}.
    function fetchPage(client, tags, offset) {
        var query = client.from('maintenance_records').select('*')
            .order('performed_at', { ascending: false })
            .order('created_at', { ascending: false });
        if (tags) query = query.in('tag_id', tags);

        // range es inclusivo: offset..offset+PAGE_SIZE devuelve PAGE_SIZE + 1 filas.
        return query.range(offset, offset + PAGE_SIZE).then(function (result) {
            var page = splitPage(checked(result), PAGE_SIZE);
            if (!page.rows.length) return { records: [], hasMore: false };

            var recordIds = page.rows.map(function (r) { return r.id; });
            var userIds = unique(page.rows.map(function (r) { return r.created_by; }));
            return Promise.all([
                client.from('maintenance_attachments').select('*').in('record_id', recordIds),
                client.from('author_names').select('user_id, full_name').in('user_id', userIds)
            ]).then(function (results) {
                return signAttachments(client, checked(results[0])).then(function (atts) {
                    return {
                        records: mergeRecords(page.rows, atts, checked(results[1])),
                        hasMore: page.hasMore
                    };
                });
            });
        });
    }

    // ── Popup de multimedia ──────────────────────────────────────────────

    function createViewer() {
        var overlay = document.createElement('div');
        overlay.className = 'feed-viewer';
        overlay.hidden = true;
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Multimedia del mantenimiento');
        overlay.innerHTML =
            '<div class="feed-viewer-backdrop"></div>' +
            '<button type="button" class="feed-viewer-close" aria-label="Cerrar">✕</button>' +
            '<button type="button" class="feed-viewer-prev" aria-label="Anterior">‹</button>' +
            '<button type="button" class="feed-viewer-next" aria-label="Siguiente">›</button>' +
            '<div class="feed-viewer-stage"></div>' +
            '<div class="feed-viewer-counter" aria-live="polite"></div>';
        document.body.appendChild(overlay);

        var stage = overlay.querySelector('.feed-viewer-stage');
        var counter = overlay.querySelector('.feed-viewer-counter');
        var closeBtn = overlay.querySelector('.feed-viewer-close');
        var items = [];
        var current = 0;
        var opener = null;
        var touchStartX = null;

        function show(i) {
            current = i;
            stage.innerHTML = '';
            var item = items[i];
            if (item.kind === 'photo') {
                var img = document.createElement('img');
                img.alt = 'Foto del mantenimiento';
                img.src = item.url;
                stage.appendChild(img);
            } else {
                var audio = document.createElement('audio');
                audio.controls = true;
                audio.src = item.url;
                stage.appendChild(audio);
            }
            counter.textContent = (i + 1) + ' / ' + items.length;
            overlay.classList.toggle('single', items.length === 1);
        }

        function step(delta) {
            if (items.length > 1) show(stepIndex(current, delta, items.length));
        }

        function onKey(evt) {
            if (evt.key === 'Escape') close();
            else if (evt.key === 'ArrowLeft') step(-1);
            else if (evt.key === 'ArrowRight') step(1);
        }

        function open(list, startIndex, openerEl) {
            items = list;
            opener = openerEl || null;
            show(startIndex);
            overlay.hidden = false;
            document.body.style.overflow = 'hidden';
            document.addEventListener('keydown', onKey);
            closeBtn.focus();
        }

        function close() {
            overlay.hidden = true;
            stage.innerHTML = '';  // detiene el audio en reproducción
            document.body.style.overflow = '';
            document.removeEventListener('keydown', onKey);
            if (opener) opener.focus();
        }

        closeBtn.addEventListener('click', close);
        overlay.querySelector('.feed-viewer-backdrop').addEventListener('click', close);
        overlay.querySelector('.feed-viewer-prev').addEventListener('click', function () { step(-1); });
        overlay.querySelector('.feed-viewer-next').addEventListener('click', function () { step(1); });
        overlay.addEventListener('touchstart', function (evt) {
            touchStartX = evt.changedTouches[0].clientX;
        }, { passive: true });
        overlay.addEventListener('touchend', function (evt) {
            if (touchStartX === null) return;
            var dx = evt.changedTouches[0].clientX - touchStartX;
            touchStartX = null;
            if (Math.abs(dx) >= 50) step(dx < 0 ? 1 : -1);
        }, { passive: true });

        return { open: open };
    }

    // ── Tarjeta de un mantenimiento ──────────────────────────────────────

    function renderCard(record, entry, openViewer) {
        var el = document.createElement('article');
        el.className = 'maint-record feed-card';

        var tagHtml = entry
            ? '<a class="feed-card-tag" href="' + escapeHtml(fichaHref(entry)) + '">' + escapeHtml(record.tag_id) + '</a>'
            : '<span class="feed-card-tag">' + escapeHtml(record.tag_id) + '</span>';
        var servicioHtml = entry && entry.servicio
            ? '<span class="feed-card-servicio">' + escapeHtml(entry.servicio) + '</span>'
            : '';
        var badge = record.is_date_anomaly
            ? '<span class="maint-badge-anomaly" title="La fecha de carga difiere más de 2 días de la fecha declarada del mantenimiento">⚠️ revisar fecha</span>'
            : '';
        var partsHtml = record.parts_used
            ? '<p class="maint-record-parts"><strong>Repuestos:</strong> ' + escapeHtml(record.parts_used) + '</p>'
            : '';
        var nextHtml = record.next_scheduled_at
            ? '<p class="maint-record-next"><strong>Próximo programado:</strong> ' + formatDate(record.next_scheduled_at) + '</p>'
            : '';

        el.innerHTML =
            '<header class="feed-card-head">' + tagHtml + servicioHtml + '</header>' +
            '<div class="feed-card-meta">' +
            '  <span class="maint-record-date">' + formatDate(record.performed_at) + '</span>' +
            '  <span class="maint-record-type">' + (record.type === 'preventivo' ? 'Preventivo' : 'Correctivo') + '</span>' +
            badge +
            '</div>' +
            '<p class="maint-record-description">' + escapeHtml(record.description) + '</p>' +
            partsHtml + nextHtml +
            '<p class="feed-card-author">Registrado por ' + escapeHtml(record.author_name) + '</p>' +
            '<div class="feed-card-media"></div>';

        var media = el.querySelector('.feed-card-media');
        var playable = record.attachments.filter(function (a) { return !!a.url; });
        record.attachments.forEach(function (att) {
            if (!att.url) {
                var missing = document.createElement('span');
                missing.className = 'feed-thumb-missing';
                missing.textContent = 'Adjunto no disponible';
                media.appendChild(missing);
                return;
            }
            var btn = document.createElement('button');
            btn.type = 'button';
            if (att.kind === 'photo') {
                btn.className = 'feed-thumb';
                btn.setAttribute('aria-label', 'Ver foto');
                var img = document.createElement('img');
                img.alt = 'Foto del mantenimiento';
                img.loading = 'lazy';
                img.src = att.url;
                btn.appendChild(img);
            } else {
                btn.className = 'feed-thumb feed-thumb-audio';
                btn.setAttribute('aria-label', 'Escuchar audio');
                btn.textContent = '🎧';
            }
            btn.addEventListener('click', function () {
                openViewer(playable, playable.indexOf(att), btn);
            });
            media.appendChild(btn);
        });

        return el;
    }

    // ── Controlador de la página ─────────────────────────────────────────

    function init() {
        var listEl = document.getElementById('feed-list');
        if (!listEl) return;  // otra página del sitio

        var moreBtn = document.getElementById('feed-more');
        var searchInput = document.getElementById('feed-search');
        var clearBtn = document.getElementById('feed-search-clear');
        var tabs = Array.prototype.slice.call(document.querySelectorAll('.feed-tab'));
        var index = window.__TAG_INDEX__ || [];
        var byTag = indexByTag(index);
        var state = { category: 'TODOS', query: '', offset: 0, token: 0 };
        var debounceTimer = null;
        var client;
        var viewer;

        try {
            client = getClient();
            viewer = createViewer();
        } catch (err) {
            listEl.innerHTML = '<div class="maint-error"></div>';
            listEl.firstChild.textContent = err.message;
            return;
        }

        function showEmpty() {
            listEl.innerHTML = '';
            moreBtn.hidden = true;
            var p = document.createElement('p');
            p.className = 'maint-empty';
            var q = state.query.trim();
            if (q) {
                p.textContent = 'No hay mantenimientos para «' + q + '».';
            } else if (state.category !== 'TODOS') {
                p.textContent = 'Todavía no hay mantenimientos registrados en ' + state.category + '.';
            } else {
                p.textContent = 'Todavía no hay mantenimientos registrados.';
            }
            listEl.appendChild(p);
        }

        function showError(message) {
            if (state.offset === 0) listEl.innerHTML = '';
            var box = document.createElement('div');
            box.className = 'maint-error';
            box.textContent = message + ' ';
            var retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'maint-btn maint-btn-secondary';
            retry.textContent = 'Reintentar';
            retry.addEventListener('click', function () {
                box.remove();
                load(false);
            });
            box.appendChild(retry);
            listEl.appendChild(box);
            moreBtn.disabled = false;
        }

        function load(reset) {
            if (reset) {
                state.offset = 0;
                state.token += 1;
                listEl.innerHTML = '';
                moreBtn.hidden = true;
            }
            var token = state.token;
            var filtered = hasFilter(state.category, state.query);
            var candidates = filterTags(index, state.category, state.query);
            if (filtered && candidates.length === 0) {
                showEmpty();
                return;
            }
            var tags = filtered ? candidates.map(function (e) { return e.tag; }) : null;

            moreBtn.disabled = true;
            if (state.offset === 0) {
                listEl.innerHTML = '<p class="maint-loading">Cargando…</p>';
            }
            fetchPage(client, tags, state.offset)
                .then(function (page) {
                    if (token !== state.token) return;  // respuesta de una búsqueda anterior
                    var first = state.offset === 0;
                    if (first) listEl.innerHTML = '';
                    if (first && page.records.length === 0) {
                        showEmpty();
                        return;
                    }
                    page.records.forEach(function (record) {
                        listEl.appendChild(renderCard(record, byTag[record.tag_id], viewer.open));
                    });
                    state.offset += PAGE_SIZE;
                    moreBtn.hidden = !page.hasMore;
                    moreBtn.disabled = false;
                })
                .catch(function (err) {
                    if (token !== state.token) return;
                    showError('No se pudieron cargar los mantenimientos: ' + err.message);
                });
        }

        function selectTab(tab) {
            tabs.forEach(function (t) {
                var on = t === tab;
                t.classList.toggle('active', on);
                t.setAttribute('aria-selected', on ? 'true' : 'false');
                t.tabIndex = on ? 0 : -1;
            });
            state.category = tab.dataset.cat;
            load(true);
        }

        tabs.forEach(function (tab, i) {
            tab.addEventListener('click', function () { selectTab(tab); });
            tab.addEventListener('keydown', function (evt) {
                var delta = evt.key === 'ArrowRight' ? 1 : evt.key === 'ArrowLeft' ? -1 : 0;
                if (!delta) return;
                evt.preventDefault();
                var next = tabs[stepIndex(i, delta, tabs.length)];
                next.focus();
                selectTab(next);
            });
        });

        function applyQuery() {
            state.query = searchInput.value;
            load(true);
        }

        searchInput.addEventListener('input', function () {
            clearBtn.hidden = searchInput.value === '';
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(applyQuery, 300);
        });
        searchInput.addEventListener('keydown', function (evt) {
            if (evt.key === 'Enter') {
                clearTimeout(debounceTimer);
                applyQuery();
            }
        });
        clearBtn.addEventListener('click', function () {
            clearTimeout(debounceTimer);
            searchInput.value = '';
            clearBtn.hidden = true;
            applyQuery();
            searchInput.focus();
        });
        moreBtn.addEventListener('click', function () { load(false); });

        load(true);
    }

    document.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 2: Los tests de lógica siguen pasando (la capa DOM no se carga en node)**

Run: `/home/administrador/.codegpt/bin/node --test tests/js/ 2>&1 | tail -6 && /home/administrador/.codegpt/bin/node --check maintenance_feed.js && echo SINTAXIS_OK`
Expected: `# pass 14`, `# fail 0` y `SINTAXIS_OK`.

- [ ] **Step 3: Crear los estilos**

Crear `maintenance_feed.css` (usa las variables del tema del sitio: `--bg`, `--border`, `--text`, `--text-muted`, `--accent`):

```css
.feed-controls {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 16px;
}

.feed-search {
    position: relative;
}

.feed-search input {
    width: 100%;
    min-height: 44px;
    padding: 10px 44px 10px 14px;
    font-size: 1rem;
    font-family: inherit;
    border: 2px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text);
    box-sizing: border-box;
}

.feed-search input:focus {
    outline: 2px solid var(--accent);
    border-color: var(--accent);
}

.feed-search-clear {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 44px;
    border: 0;
    background: none;
    color: var(--text-muted);
    font-size: 1.1rem;
    cursor: pointer;
}

.feed-search-clear[hidden] {
    display: none;
}

.feed-tabs {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.feed-tab {
    flex: 1;
    min-width: 90px;
    min-height: 44px;
    padding: 10px 12px;
    font-size: 0.9rem;
    font-weight: 600;
    font-family: inherit;
    border: 2px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text-muted);
    cursor: pointer;
}

.feed-tab:hover {
    border-color: var(--accent);
    color: var(--accent);
}

.feed-tab.active {
    border-color: var(--accent);
    background: var(--accent);
    color: #fff;
}

.feed-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.feed-card-head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 4px 10px;
    margin-bottom: 6px;
}

.feed-card-tag {
    font-weight: 700;
    font-size: 1.05rem;
    color: var(--accent);
    text-decoration: none;
}

a.feed-card-tag:hover {
    text-decoration: underline;
}

.feed-card-servicio {
    color: var(--text-muted);
    font-size: 0.9rem;
}

.feed-card-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 6px;
}

.feed-card-author {
    margin: 8px 0 0;
    color: var(--text-muted);
    font-size: 0.85rem;
}

.feed-card-media {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
}

.feed-card-media:empty {
    display: none;
}

.feed-thumb {
    width: 72px;
    height: 72px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    cursor: pointer;
    overflow: hidden;
}

.feed-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.feed-thumb-audio {
    font-size: 1.8rem;
}

.feed-thumb:focus-visible {
    outline: 2px solid var(--accent);
}

.feed-thumb-missing {
    color: var(--text-muted);
    font-size: 0.85rem;
}

.feed-more {
    display: flex;
    justify-content: center;
    margin-top: 16px;
}

.feed-more .maint-btn[hidden] {
    display: none;
}

/* Popup de multimedia */
.feed-viewer {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.feed-viewer[hidden] {
    display: none;
}

.feed-viewer-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
}

.feed-viewer-stage {
    position: relative;
    max-width: 92vw;
    max-height: 82vh;
    display: flex;
    align-items: center;
    justify-content: center;
}

.feed-viewer-stage img {
    max-width: 92vw;
    max-height: 82vh;
    object-fit: contain;
    border-radius: 6px;
}

.feed-viewer-stage audio {
    width: min(420px, 88vw);
}

.feed-viewer-close,
.feed-viewer-prev,
.feed-viewer-next {
    position: absolute;
    width: 48px;
    height: 48px;
    border: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.18);
    color: #fff;
    font-size: 1.6rem;
    line-height: 1;
    cursor: pointer;
}

.feed-viewer-close:hover,
.feed-viewer-prev:hover,
.feed-viewer-next:hover {
    background: rgba(255, 255, 255, 0.32);
}

.feed-viewer-close {
    top: 14px;
    right: 14px;
}

.feed-viewer-prev {
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
}

.feed-viewer-next {
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
}

.feed-viewer.single .feed-viewer-prev,
.feed-viewer.single .feed-viewer-next,
.feed-viewer.single .feed-viewer-counter {
    display: none;
}

.feed-viewer-counter {
    position: absolute;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    color: #fff;
    font-size: 0.9rem;
}

@media (max-width: 480px) {
    .feed-tab {
        min-width: 0;
        flex-basis: calc(50% - 8px);
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add maintenance_feed.js maintenance_feed.css
git commit -m "feat: UI del feed de mantenimientos (consulta paginada, tarjetas, popup de fotos/audio)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: El generador produce `mantenimientos.html` (TDD)

**Files:**
- Create: `tests/test_generator_feed.py`
- Modify: `excel_migrator.py`
- Modify: `maintenance.css`

- [ ] **Step 1: Escribir el test del generador (fallará)**

Crear `tests/test_generator_feed.py`:

```python
"""Genera el sitio en un directorio temporal y verifica la página de mantenimientos."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site")
    # Evita que ensure_images() re-extraiga imágenes hacia docs/ durante el test.
    keep = out / "assets" / "images" / "x"
    keep.mkdir(parents=True)
    (keep / "keep.txt").write_text("x", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "excel_migrator.py", "plantilla_sitio.xlsx", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out


def test_feed_page_has_controls_and_tabs_in_order(site):
    html = (site / "mantenimientos.html").read_text(encoding="utf-8")
    assert 'id="feed-list"' in html
    assert 'id="feed-search"' in html
    assert 'id="feed-more"' in html
    assert 'src="maintenance_feed.js"' in html
    assert 'href="maintenance_feed.css"' in html
    cats = re.findall(r'class="feed-tab[^"]*" role="tab" data-cat="(\w+)"', html)
    assert cats == ["TODOS", "EQUIPOS", "TANQUES", "INSTRUMENTOS"]


def test_feed_page_embeds_tag_index(site):
    html = (site / "mantenimientos.html").read_text(encoding="utf-8")
    match = re.search(r"window\.__TAG_INDEX__ = (\[.*?\]);\s*</script>", html, re.S)
    assert match, "falta window.__TAG_INDEX__"
    index = json.loads(match.group(1).replace("<\\/", "</"))
    assert len(index) == 42
    assert set(index[0]) == {"tag", "categoria", "servicio", "filename"}
    assert {e["categoria"] for e in index} <= {"EQUIPOS", "TANQUES", "INSTRUMENTOS"}


def test_static_assets_are_copied(site):
    assert (site / "maintenance_feed.js").is_file()
    assert (site / "maintenance_feed.css").is_file()


def test_sidebar_link_on_every_page_level(site):
    assert 'href="mantenimientos.html"' in (site / "index.html").read_text(encoding="utf-8")
    assert 'href="../mantenimientos.html"' in (site / "equipos" / "100-P-01A.html").read_text(encoding="utf-8")
    assert 'href="../mantenimientos.html"' in (site / "equipos" / "index.html").read_text(encoding="utf-8")


def test_home_has_feed_button(site):
    home = (site / "index.html").read_text(encoding="utf-8")
    assert 'class="home-feed-cta" href="mantenimientos.html"' in home


def test_feed_link_is_active_only_on_feed_page(site):
    assert "nav-link-feed active" in (site / "mantenimientos.html").read_text(encoding="utf-8")
    assert "nav-link-feed active" not in (site / "index.html").read_text(encoding="utf-8")
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python3 -m pytest tests/test_generator_feed.py -v 2>&1 | tail -15`
Expected: FAIL — `FileNotFoundError` de `mantenimientos.html` (la fixture genera bien; falta la página).

- [ ] **Step 3: Constante del orden de tabs**

En `excel_migrator.py`, debajo de la línea `CATEGORY_ORDER = ["EQUIPOS", "INSTRUMENTOS", "TANQUES"]` (línea ~120) agregar:

```python
# Orden de los tabs de la página de mantenimientos (distinto al del menú lateral)
FEED_TAB_ORDER = ["EQUIPOS", "TANQUES", "INSTRUMENTOS"]
```

- [ ] **Step 4: Enlace en el menú lateral**

En `build_nav` (línea ~405) reemplazar la firma y la línea de apertura:

```python
def build_nav(grouped: dict[str, list[Item]], rel_prefix: str, active_tag: Optional[str] = None) -> str:
    """Construye el <nav> del sidebar con paths relativos según ubicación."""
    out = ['<nav class="nav"><ul class="nav-list">']
```
por:
```python
def build_nav(
    grouped: dict[str, list[Item]],
    rel_prefix: str,
    active_tag: Optional[str] = None,
    feed_active: bool = False,
) -> str:
    """Construye el <nav> del sidebar con paths relativos según ubicación."""
    out = ['<nav class="nav"><ul class="nav-list">']
    # Fuera de .nav-group a propósito: script.js recorre los .nav-group esperando un .nav-cat
    feed_cls = "nav-link-feed active" if feed_active else "nav-link-feed"
    out.append(
        f'<li class="nav-feed"><a class="{feed_cls}" '
        f'href="{rel_prefix}mantenimientos.html">🛠 Últimos mantenimientos</a></li>'
    )
```

- [ ] **Step 5: Extender `page_skeleton`**

En la firma de `page_skeleton` (línea ~429) reemplazar:
```python
    rel_prefix: str,
    supabase_config: dict,
) -> str:
    """Skeleton HTML completo (head + banner + sidebar + content)."""
```
por:
```python
    rel_prefix: str,
    supabase_config: dict,
    extra_head: str = "",
    extra_scripts: str = "",
) -> str:
    """Skeleton HTML completo (head + banner + sidebar + content)."""
```
Reemplazar la línea `    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>\n</head>` por:
```python
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
    {extra_head}
</head>
```
y la línea `    <script src="{rel_prefix}maintenance.js"></script>\n</body>` por:
```python
    <script src="{rel_prefix}maintenance.js"></script>
    {extra_scripts}
</body>
```

- [ ] **Step 6: Botón en el inicio y `render_maintenance_page`**

En `render_home`, reemplazar:
```python
        f'<p class="subtitle">{h(SITE_SUBTITLE)}</p></header>',
        '<div class="accordion">',
```
por:
```python
        f'<p class="subtitle">{h(SITE_SUBTITLE)}</p></header>',
        '<a class="home-feed-cta" href="mantenimientos.html">🛠 Ver últimos mantenimientos →</a>',
        '<div class="accordion">',
```

Justo antes de `def render_home(` agregar:

```python
def render_maintenance_page(items: list[Item]) -> str:
    """Página pública de últimos mantenimientos (la arma maintenance_feed.js en runtime)."""
    tag_index = [
        {
            "tag": i.tag,
            "categoria": i.category,
            "servicio": (i.properties.get("SERVICIO") or "").strip(),
            "filename": i.filename,
        }
        for i in sorted(items, key=lambda i: i.tag)
    ]
    # "</" dentro de un <script> cerraría la etiqueta antes de tiempo
    index_json = json.dumps(tag_index, ensure_ascii=False).replace("</", "<\\/")

    tabs = [
        '<button type="button" class="feed-tab active" role="tab" data-cat="TODOS" '
        'aria-selected="true" tabindex="0">Todos</button>'
    ]
    for cat in FEED_TAB_ORDER:
        tabs.append(
            f'<button type="button" class="feed-tab" role="tab" data-cat="{h(cat)}" '
            f'aria-selected="false" tabindex="-1">{h(cat)}</button>'
        )

    return "\n".join([
        '<header class="page-header"><h1>Últimos mantenimientos</h1>',
        '<p class="subtitle">Los mantenimientos más recientes de todos los equipos</p></header>',
        '<div class="feed-controls">',
        '<div class="feed-search">',
        '<input type="search" id="feed-search" placeholder="Buscar por TAG o elemento…" '
        'autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Buscar mantenimientos por TAG o elemento">',
        '<button type="button" class="feed-search-clear" id="feed-search-clear" hidden aria-label="Limpiar búsqueda">✕</button>',
        '</div>',
        '<div class="feed-tabs" role="tablist" aria-label="Categoría">',
        *tabs,
        '</div>',
        '</div>',
        '<div class="feed-list" id="feed-list" aria-live="polite"></div>',
        '<div class="feed-more"><button type="button" class="maint-btn maint-btn-secondary" id="feed-more" hidden>Mostrar más</button></div>',
        f'<script>window.__TAG_INDEX__ = {index_json};</script>',
    ])


```

- [ ] **Step 7: `main()` — whitelist, copia de assets y generación de la página**

Reemplazar en el `KNOWN_FILES`:
```python
        "maintenance.css", "maintenance.js",
    }
```
por:
```python
        "maintenance.css", "maintenance.js",
        "maintenance_feed.css", "maintenance_feed.js", "mantenimientos.html",
    }
```
Reemplazar `    for static_name in ("maintenance.css", "maintenance.js"):` por:
```python
    for static_name in ("maintenance.css", "maintenance.js", "maintenance_feed.css", "maintenance_feed.js"):
```
Después de `    print("   ✅ index.html")` agregar:

```python

    # Página pública de últimos mantenimientos
    feed_html = page_skeleton(
        page_title="Últimos mantenimientos",
        topbar_title="Últimos mantenimientos",
        sidebar_html=build_nav(grouped, rel_prefix="", feed_active=True),
        content_html=render_maintenance_page(items),
        rel_prefix="",
        supabase_config=config["supabase"],
        extra_head='<link rel="stylesheet" href="maintenance_feed.css">',
        extra_scripts='<script src="maintenance_feed.js"></script>',
    )
    (output_dir / "mantenimientos.html").write_text(feed_html, encoding="utf-8")
    print("   ✅ mantenimientos.html")
```

- [ ] **Step 8: Estilos del enlace del menú y del botón del inicio (cargan en todas las páginas)**

Agregar al final de `maintenance.css`:

```css

/* Acceso a la vista de últimos mantenimientos (menú lateral e inicio) */
.nav-feed {
    margin-bottom: 8px;
}

.nav-link-feed {
    display: block;
    padding: 12px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
    border: 1px solid var(--border);
}

.nav-link-feed:hover,
.nav-link-feed.active {
    background: var(--accent);
    color: #fff;
}

.home-feed-cta {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    margin-bottom: 20px;
    padding: 12px 16px;
    border-radius: 10px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    text-decoration: none;
}

.home-feed-cta:hover {
    background: var(--accent-hover);
}
```

- [ ] **Step 9: Ejecutar tests del generador y los de node**

Run: `python3 -m pytest tests/test_generator_feed.py -v 2>&1 | tail -12`
Expected: 6 passed.

Run: `git status --short | grep -v -E '^\?\? (\.claude|\.dockerignore|\.mcp\.json|Dockerfile|GUIA_GUI|docker-compose)'`
Expected: solo los archivos de esta task (no debe haber cambios en `docs/`; el test genera en un tmp).

- [ ] **Step 10: Commit**

```bash
git add excel_migrator.py maintenance.css tests/test_generator_feed.py
git commit -m "feat: el generador crea mantenimientos.html con enlace en menú e inicio" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Historial de la ficha legible sin login

**Files:**
- Modify: `maintenance.js` (funciones `renderLoginForm`, `renderLoggedInShell`, `initHistorialView`, `renderHistorialBody`)

- [ ] **Step 1: Login opcional (con "Cancelar")**

En `renderLoginForm` reemplazar:
```js
            '  <h2>Ingresá para ver o cargar el historial</h2>' +
```
por:
```js
            '  <h2>Ingresá para cargar mantenimientos</h2>' +
```
Reemplazar:
```js
            '  <button type="submit" class="maint-btn maint-btn-primary">Ingresar</button>' +
            '</form>';
```
por:
```js
            '  <button type="submit" class="maint-btn maint-btn-primary">Ingresar</button>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" id="maint-login-cancel">Cancelar</button>' +
            '</form>';
```
Y después de la línea `        var errorBox = document.getElementById('maint-login-error');` agregar:
```js
        document.getElementById('maint-login-cancel').addEventListener('click', function () {
            initHistorialView(container, tagId);
        });
```

- [ ] **Step 2: Cabecera de sesión con modo solo lectura**

Reemplazar la función `renderLoggedInShell` completa por:

```js
    function renderLoggedInShell(container, tagId, session) {
        container.innerHTML =
            '<div class="maint-shell">' +
            '  <div class="maint-session-bar">' +
            '    <span class="maint-session-user"></span>' +
            '    <button type="button" class="maint-btn maint-btn-secondary" id="maint-logout"></button>' +
            '  </div>' +
            '  <div id="maint-historial-body">Cargando historial…</div>' +
            '</div>';

        var userEl = container.querySelector('.maint-session-user');
        var actionBtn = document.getElementById('maint-logout');
        if (session) {
            userEl.textContent = session.user.email;
            actionBtn.textContent = 'Cerrar sesión';
            actionBtn.addEventListener('click', function () {
                getClient().auth.signOut().then(function () {
                    initHistorialView(container, tagId);
                });
            });
        } else {
            // El historial es público de lectura; el login se pide solo para agregar.
            userEl.textContent = 'Solo lectura';
            actionBtn.textContent = 'Iniciar sesión para agregar';
            actionBtn.addEventListener('click', function () {
                renderLoginForm(container, tagId);
            });
        }

        return document.getElementById('maint-historial-body');
    }
```

- [ ] **Step 3: `initHistorialView` ya no bloquea la lectura**

Reemplazar:
```js
                var session = result.data.session;
                if (!session) {
                    renderLoginForm(container, tagId);
                    return;
                }
                var body = renderLoggedInShell(container, tagId, session);
```
por:
```js
                var session = result.data.session;
                var body = renderLoggedInShell(container, tagId, session);
```

- [ ] **Step 4: El botón de alta solo aparece con sesión**

En `renderHistorialBody`, reemplazar:
```js
        addBtn.textContent = '+ Registrar mantenimiento';
        bodyContainer.appendChild(addBtn);
```
por:
```js
        addBtn.textContent = '+ Registrar mantenimiento';
        addBtn.hidden = true;
        bodyContainer.appendChild(addBtn);
        client.auth.getSession().then(function (result) {
            addBtn.hidden = !(result.data && result.data.session);
        });
```

- [ ] **Step 5: Sintaxis y tests**

Run: `/home/administrador/.codegpt/bin/node --check maintenance.js && echo SINTAXIS_OK && /home/administrador/.codegpt/bin/node --test tests/js/ 2>&1 | grep -E "^# (pass|fail)"`
Expected: `SINTAXIS_OK`, `# pass 14`, `# fail 0`.

(La verificación de comportamiento va en la Task 6, en navegador.)

- [ ] **Step 6: Commit**

```bash
git add maintenance.js
git commit -m "feat: el historial de la ficha se lee sin login; el login se pide solo para agregar" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Verificación en navegador contra Supabase local

Sin cambios de código salvo que se encuentre un bug (en ese caso corregir con el mismo criterio TDD cuando sea lógica pura, y commitear aparte con `fix:`).

**Files (scratch, fuera del repo):** todo en `/tmp/claude-1001/-home-administrador-google-sites-migrator/f070e61f-6ddb-4cc2-88c8-d315f4c37c0e/scratchpad/` (`$S` abajo).

- [ ] **Step 1: Sembrar datos locales**

Crear `$S/seed_feed.py`:

```python
"""Siembra 13 mantenimientos con marca [SEED-FEED] en el Supabase LOCAL."""
import io
import os
import sys

sys.path.insert(0, "/home/administrador/google-sites-migrator")
from dotenv import load_dotenv
from PIL import Image
from supabase import create_client

load_dotenv("/home/administrador/google-sites-migrator/.env.test")
assert "127.0.0.1" in os.environ["SUPABASE_URL"], "solo contra el stack LOCAL"
svc = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

# Asegurar un usuario tecnico con perfil
users = {u.email: u.id for u in svc.auth.admin.list_users()}
tecnico = users.get("tecnico@test.local") or svc.auth.admin.create_user(
    {"email": "tecnico@test.local", "password": "Test1234!", "email_confirm": True}
).user.id
svc.table("profiles").upsert({"user_id": tecnico, "full_name": "Test tecnico", "role": "tecnico"}).execute()

lines = [l.split(",", 1) for l in open("/home/administrador/google-sites-migrator/docs/urls.txt").read().split()]
by_cat = {}
for cat, url in lines:
    by_cat.setdefault(cat, []).append(url.rsplit("/", 1)[1].removesuffix(".html"))
tags = by_cat["EQUIPO"][:8] + by_cat["TANQUE"][:3] + by_cat["INSTRUMENTO"][:2]
print("TAGs:", tags)

def jpeg(color):
    buf = io.BytesIO()
    Image.new("RGB", (320, 200), color).save(buf, "JPEG")
    return buf.getvalue()

for i, tag in enumerate(tags):
    rec = svc.table("maintenance_records").insert({
        "tag_id": tag,
        "performed_at": f"2026-09-{20 - i:02d}",   # 13 fechas distintas, descendentes
        "type": "preventivo" if i % 2 == 0 else "correctivo",
        "description": f"[SEED-FEED] Mantenimiento {i + 1} <b>x</b>",  # el <b> prueba el escapado
        "created_by": tecnico,
    }).execute().data[0]
    if i == 0:  # el más reciente lleva 2 fotos + 1 audio
        for n, color in enumerate(["red", "blue"]):
            path = f"{tag}/{rec['id']}/foto{n}.jpg"
            svc.storage.from_("maintenance-attachments").upload(path, jpeg(color), {"content-type": "image/jpeg"})
            svc.table("maintenance_attachments").insert(
                {"record_id": rec["id"], "kind": "photo", "storage_path": path, "created_by": tecnico}).execute()
        path = f"{tag}/{rec['id']}/nota.webm"
        svc.storage.from_("maintenance-attachments").upload(path, b"audio-falso", {"content-type": "audio/webm"})
        svc.table("maintenance_attachments").insert(
            {"record_id": rec["id"], "kind": "audio", "storage_path": path, "created_by": tecnico}).execute()
print("OK 13 registros sembrados")
```

Run: `python3 $S/seed_feed.py`
Expected: imprime los 13 TAGs y `OK 13 registros sembrados`.

- [ ] **Step 2: Generar el sitio apuntando al Supabase local y servirlo**

```bash
S=/tmp/claude-1001/-home-administrador-google-sites-migrator/f070e61f-6ddb-4cc2-88c8-d315f4c37c0e/scratchpad
mkdir -p $S/site/assets/images/x && echo x > $S/site/assets/images/x/keep.txt
python3 excel_migrator.py plantilla_sitio.xlsx $S/site
ANON=$(supabase status -o json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['ANON_KEY'])")
python3 - "$S/site" "$ANON" <<'EOF'
import re, sys, pathlib
root, anon = pathlib.Path(sys.argv[1]), sys.argv[2]
for f in root.rglob("*.html"):
    t = f.read_text(encoding="utf-8")
    t = re.sub(r'url: "[^"]*"', 'url: "http://127.0.0.1:54321"', t, count=1)
    t = re.sub(r'anonKey: "[^"]*"', f'anonKey: "{anon}"', t, count=1)
    f.write_text(t, encoding="utf-8")
EOF
(python3 -m http.server 8191 --directory $S/site >/dev/null 2>&1 &)
```
Expected: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8191/mantenimientos.html` → `200`.

- [ ] **Step 3: Script de comprobaciones de la página**

Crear `$S/feed_check.mjs`:

```js
export default async (page) => {
  const out = {};
  const count = () => page.locator('.feed-card').count();
  const dates = async () => (await page.locator('.feed-card .maint-record-date').allTextContents())
    .map((d) => d.split('/').reverse().join('-'));

  await page.waitForSelector('.feed-card');
  out.primeraPagina = await count();                                   // esperado 10
  out.mostrarMasVisible = await page.locator('#feed-more').isVisible(); // true
  const d = await dates();
  out.ordenDescendente = d.every((v, i) => i === 0 || d[i - 1] >= v);   // true
  out.escapado = await page.locator('.feed-card b').count();            // 0 (el <b> no se interpreta)
  out.autor = (await page.locator('.feed-card-author').first().textContent()).trim(); // Registrado por Test tecnico

  await page.click('#feed-more');
  await page.waitForFunction(() => document.querySelectorAll('.feed-card').length > 10);
  out.trasMostrarMas = await count();                                  // 13 (los sembrados; puede ser más si hay otros)
  out.mostrarMasOculto = !(await page.locator('#feed-more').isVisible());

  await page.click('.feed-tab[data-cat="TANQUES"]');
  await page.waitForFunction(() => !document.querySelector('.maint-loading'));
  out.tanques = await count();                                          // 3
  await page.click('.feed-tab[data-cat="INSTRUMENTOS"]');
  await page.waitForFunction(() => !document.querySelector('.maint-loading'));
  out.instrumentos = await count();                                     // 2

  await page.click('.feed-tab[data-cat="TODOS"]');
  await page.waitForSelector('.feed-card');
  await page.fill('#feed-search', '100-p-01a');                         // parcial y en minúsculas
  await page.waitForFunction(() => document.querySelectorAll('.feed-card').length === 1);
  out.busquedaTag = await page.locator('.feed-card-tag').first().textContent();
  await page.fill('#feed-search', 'zzzz-no-existe');
  await page.waitForSelector('.maint-empty');
  out.vacio = await page.locator('.maint-empty').textContent();         // No hay mantenimientos para «zzzz-no-existe».
  await page.click('#feed-search-clear');
  await page.waitForSelector('.feed-card');
  out.limpiar = await count();                                          // 10 otra vez

  // Popup: el registro más reciente tiene 2 fotos + 1 audio
  await page.locator('.feed-thumb').first().click();
  out.popupAbierto = await page.locator('.feed-viewer').isVisible();    // true
  out.contador1 = await page.locator('.feed-viewer-counter').textContent(); // 1 / 3
  await page.keyboard.press('ArrowRight');
  out.contador2 = await page.locator('.feed-viewer-counter').textContent(); // 2 / 3
  await page.keyboard.press('ArrowRight');
  out.hayAudio = await page.locator('.feed-viewer-stage audio').count();    // 1
  await page.click('.feed-viewer-next');
  out.vueltaCircular = await page.locator('.feed-viewer-counter').textContent(); // 1 / 3
  await page.click('.feed-viewer-close');
  out.popupCerrado = !(await page.locator('.feed-viewer').isVisible());    // true
  await page.locator('.feed-thumb').first().click();
  await page.keyboard.press('Escape');
  out.escCierra = !(await page.locator('.feed-viewer').isVisible());       // true

  // Ficha: historial sin login
  await page.goto('http://localhost:8191/equipos/100-P-01A.html');
  await page.click('#btn-ver-historial');
  await page.waitForSelector('.maint-record');
  out.fichaRegistros = await page.locator('.maint-record').count();        // >= 1
  out.fichaSinLoginForzado = await page.locator('#maint-login-form').count(); // 0
  out.fichaBotonAlta = await page.locator('.maint-add-record-btn').isVisible(); // false
  out.fichaTextoBoton = (await page.locator('#maint-logout').textContent()).trim(); // Iniciar sesión para agregar
  await page.click('#maint-logout');
  out.fichaLoginAbre = await page.locator('#maint-login-form').count();    // 1
  await page.click('#maint-login-cancel');
  await page.waitForSelector('.maint-record');
  out.fichaVuelve = await page.locator('.maint-record').count();           // >= 1

  // Enlaces de acceso
  await page.goto('http://localhost:8191/index.html');
  out.homeBoton = await page.locator('.home-feed-cta').isVisible();        // true

  // Móvil: la página nueva no debe agregar scroll horizontal
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto('http://localhost:8191/mantenimientos.html');
  await page.waitForSelector('.feed-card');
  out.scrollX390 = await page.evaluate(() => document.documentElement.scrollWidth); // <= 390
  return out;
};
```

- [ ] **Step 4: Ejecutar y validar**

Run:
```bash
node_bin=/home/administrador/.codegpt/bin
PATH=$node_bin:$PATH node ~/.claude/skills/browser-automation/browser.mjs http://localhost:8191/mantenimientos.html --script $S/feed_check.mjs --screenshot $S/feed.png 2>&1 | tail -60
```
Expected: cada valor coincide con el comentario `// esperado` del script, sin errores de consola ni peticiones fallidas (salvo el favicon). Mirar `$S/feed.png` para revisar el aspecto. Si algo no coincide: corregir el código (Task 2/3/5), repetir el paso 2 (regenerar) y este paso.

- [ ] **Step 5: Limpieza local**

```bash
pkill -f "http.server 8191" || true
python3 - <<'EOF'
import os
from dotenv import load_dotenv
from supabase import create_client
load_dotenv("/home/administrador/google-sites-migrator/.env.test")
svc = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
svc.table("maintenance_records").delete().like("description", "[SEED-FEED]%").execute()
print("sembrado local eliminado")
EOF
git status --short | grep -v -E '^\?\? (\.claude|\.dockerignore|\.mcp\.json|Dockerfile|GUIA_GUI|docker-compose)'
```
Expected: `sembrado local eliminado` y árbol de trabajo limpio (los archivos scratch están fuera del repo).

---

### Task 7: Documentación, regeneración de `docs/` y despliegue

**Files:**
- Modify: `CLAUDE.md`
- Modify (generado): `docs/**`

- [ ] **Step 1: Documentar en `CLAUDE.md`**

En la sección "Histórico de mantenimientos (Supabase)", agregar al final de la lista estas viñetas:

```markdown
- **Lectura pública (desde 2026-09-21):** el histórico completo (registros, comentarios, adjuntos, autor) es legible sin sesión con la `anon_key`; la escritura sigue exigiendo login + perfil. Migración `20260921210000_public_read.sql`: una policy `select` `to anon, authenticated` por tabla y por el bucket, y la vista `author_names(user_id, full_name)` (sin correo ni rol; con `revoke all` a anon/authenticated + `grant select`, porque Supabase concede ALL por defecto y la vista sería escribible).
- **Vista de últimos mantenimientos:** `mantenimientos.html` (generada por `excel_migrator.py`, lógica en `maintenance_feed.js/.css`). 10 más recientes por `performed_at desc`, "Mostrar más" de a 10, tabs Todos/EQUIPOS/TANQUES/INSTRUMENTOS y buscador por TAG o SERVICIO. La categoría no está en la base: el generador incrusta `window.__TAG_INDEX__` y el filtro consulta con `tag_id in (...)`. Popup de fotos/audio con ✕, Esc, flechas y swipe. Acceso: primer ítem del menú lateral y botón en el inicio.
- **Historial de la ficha:** se lee sin login; el botón de alta y "+ Comentario/adjunto" solo aparecen con sesión (`Iniciar sesión para agregar`).
- **Tests JS de la lógica pura:** `/home/administrador/.codegpt/bin/node --test tests/js/`. Tests del generador: `python3 -m pytest tests/test_generator_feed.py`.
```

En la tabla "Archivos generados por `excel_migrator.py`" agregar la fila:

```markdown
| `mantenimientos.html`, `maintenance.css/js`, `maintenance_feed.css/js` | Vista pública de últimos mantenimientos y su código (los `.css/.js` se copian tal cual desde la raíz del repo) |
```

Y en "Cleanup whitelist" no hay que tocar el texto (la tabla ya lista los archivos gestionados).

- [ ] **Step 2: Suite completa**

Run:
```bash
python3 -m pytest tests -q 2>&1 | tail -3
/home/administrador/.codegpt/bin/node --test tests/js/ 2>&1 | grep -E "^# (pass|fail)"
```
Expected: pytest `56 passed` (50 RLS + 6 generador), node `# pass 14`, `# fail 0`.

- [ ] **Step 3: Regenerar `docs/` y revisar el diff**

Run: `./update_site_from_excel.sh 2>&1 | tail -8 && git status --short docs | head -20`
Expected: `docs/mantenimientos.html`, `docs/maintenance_feed.js`, `docs/maintenance_feed.css` nuevos; el resto de páginas modificadas solo por el enlace del menú (y `docs/index.html` por el botón). Comprobar: `grep -c "mantenimientos.html" docs/equipos/100-P-01A.html` → `1` o más.

- [ ] **Step 4: Commit (sin push)**

```bash
git add CLAUDE.md docs/
git commit -m "docs: documentar la vista pública de mantenimientos y regenerar el sitio" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: DETENERSE y pedir confirmación al usuario antes de tocar producción**

Mostrar al usuario este resumen y esperar un "sí" explícito:
> "Voy a aplicar `20260921210000_public_read.sql` en Supabase producción (`qgxvukllzuaiyhzegaef`). Efecto: cualquiera con la `anon_key` podrá LEER todo el histórico y descargar adjuntos; la escritura sigue exigiendo login. Después haré push para publicar el sitio. ¿Confirmas?"

**No continuar sin confirmación.**

- [ ] **Step 6: Aplicar la migración en producción (solo tras el "sí")**

Run: `supabase db query --project-ref qgxvukllzuaiyhzegaef --linked -f supabase/migrations/20260921210000_public_read.sql 2>&1 | tail -5`
Expected: sin errores. (`db query` no registra la migración en el historial; es igual que el resto de migraciones del proyecto.)

- [ ] **Step 7: Verificar producción con la anon key (lectura sí, escritura no)**

```bash
URL=$(python3 -c "import json;print(json.load(open('site_config.json'))['supabase']['url'])")
KEY=$(python3 -c "import json;print(json.load(open('site_config.json'))['supabase']['anon_key'])")
echo "lectura registros:"; curl -s -o /dev/null -w "%{http_code}\n" "$URL/rest/v1/maintenance_records?select=id&limit=1" -H "apikey: $KEY"
echo "vista autores:";    curl -s "$URL/rest/v1/author_names?select=*" -H "apikey: $KEY"
echo; echo "escritura registros (debe fallar):"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$URL/rest/v1/maintenance_records" -H "apikey: $KEY" -H "Content-Type: application/json" -d '{"tag_id":"X","performed_at":"2026-01-01","type":"preventivo","description":"x"}'
echo "escritura vista autores (debe fallar):"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$URL/rest/v1/author_names" -H "apikey: $KEY" -H "Content-Type: application/json" -d '{"user_id":"00000000-0000-0000-0000-000000000000","full_name":"x"}'
```
Expected: lectura `200`; vista de autores devuelve solo `user_id` y `full_name` de los 2 usuarios de producción; ambas escrituras `401` o `403` (nunca `201`). Si alguna escritura devuelve `201`: **revertir de inmediato** (`drop policy`/`revoke`) y avisar al usuario.

- [ ] **Step 8: Push y comprobar el build de Pages**

```bash
git push origin master 2>&1 | tail -2
gh api repos/dvida-rpci/dvida-qr/pages/builds/latest --jq '.status'
```
Expected: push OK; el estado pasa de `building` a `built` en 1–2 min (repetir el segundo comando). Luego `curl -s -o /dev/null -w "%{http_code}\n" http://www.rpcidvida.dpdns.org/mantenimientos.html` → `200`, y confirmar con el usuario que ve la lista (con los usuarios de producción `tecnico@dvida.com.co` / `innovacion@rpci.com.co` puede cargar un mantenimiento de prueba).
