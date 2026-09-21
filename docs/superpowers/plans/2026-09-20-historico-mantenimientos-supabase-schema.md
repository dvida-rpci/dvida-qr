# Histórico de Mantenimientos — Plan 1: Schema, RLS y Storage en Supabase

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear en Supabase el schema completo (tablas, columna calculada, función `is_oficina()`, políticas RLS, triggers de auditoría y bucket de Storage) que sustenta el histórico de mantenimientos, con una suite de tests automatizados que prueba cada regla de permisos definida en el spec.

**Architecture:** Todo vive en Supabase (Postgres + Auth + Storage), sin backend propio. El control de acceso se resuelve 100% con Row Level Security — no hay lógica de autorización en ningún cliente. Este plan NO toca `excel_migrator.py`, `gui.py` ni ningún archivo del sitio — es puramente la base de datos. Los planes 2 (sitio) y 3 (`gui.py`) consumen este schema una vez aplicado.

**Tech Stack:** Supabase CLI (dev local con Docker), Postgres/SQL (migraciones versionadas en `supabase/migrations/`), Python + `pytest` + `supabase-py` (suite de tests contra la instancia local).

**Referencia:** [docs/superpowers/specs/2026-09-20-historico-mantenimientos-design.md](../specs/2026-09-20-historico-mantenimientos-design.md) — secciones "Modelo de datos", "Roles, permisos y RLS", "Indicador de anomalía por fecha".

---

## Antes de empezar

Ya verificado en este entorno:
- Docker está instalado y corriendo (`docker ps` funciona).
- Python 3.12.3 disponible.
- El proyecto instala paquetes con `pip3 install --break-system-packages ...` (sin venv), según convención ya usada en `CLAUDE.md` — este plan sigue la misma convención.

No verificado todavía (Task 1 lo cubre): la Supabase CLI no está instalada (`which supabase` no devuelve nada).

---

### Task 1: Entorno local de Supabase

**Files:**
- Create: `supabase/config.toml` (generado por `supabase init`)
- Create: `requirements-dev.txt`
- Modify: `requirements.txt`
- Create: `.env.test.example`
- Modify: `.gitignore`
- Create: `tests/supabase/__init__.py` (vacío, para que pytest trate el directorio como paquete)

- [ ] **Step 1: Instalar la Supabase CLI**

Seguí la documentación oficial de instalación para Linux en `https://supabase.com/docs/guides/cli/getting-started` (la CLI se distribuye como binario/paquete, no vía `pip`). Una vez instalada:

Run: `supabase --version`
Expected: imprime un número de versión (ej. `1.x.x` o `2.x.x`) sin error.

- [ ] **Step 2: Inicializar el proyecto Supabase en el repo**

Run (desde la raíz del repo):
```bash
supabase init
```
Expected: crea `supabase/config.toml` y `supabase/.gitignore`. Confirmá con `ls supabase/`.

- [ ] **Step 3: Levantar el stack local (requiere Docker corriendo)**

Run:
```bash
supabase start
```
Expected: descarga las imágenes la primera vez (puede tardar varios minutos) y al final imprime una tabla con `API URL`, `DB URL`, `anon key`, `service_role key`. **Anotá esos tres valores**, los necesitás en el paso siguiente. Si el puerto 54321/54322/54323 estuviera ocupado, `supabase start` lo va a reportar — este repo ya tiene un contenedor Postgres corriendo en el puerto `5433` (`localbd-ptar`, de otro propósito) que **no** choca con los puertos default de Supabase.

- [ ] **Step 4: Crear `.env.test.example` (versionado) y `.env.test` (real, ignorado por git)**

Create `.env.test.example`:
```
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=reemplazar-con-el-anon-key-que-imprimio-supabase-start
SUPABASE_SERVICE_ROLE_KEY=reemplazar-con-el-service-role-key-que-imprimio-supabase-start
```

Create `.env.test` (mismo contenido pero con los valores reales que imprimió `supabase start` en el Step 3 — este archivo NO se commitea).

- [ ] **Step 5: Ignorar `.env.test` en git**

El `.gitignore` ya ignora `.env` genérico pero no el patrón `.env.test`. Agregar la línea:

En `.gitignore`, después de la línea `.env`:
```
.env.test
```

- [ ] **Step 6: Agregar dependencias de testing**

Create `requirements-dev.txt`:
```
pytest
python-dotenv
```

Modify `requirements.txt` (agregar `supabase` — también la va a usar `gui.py` en el Plan 3):
```
nicegui
openpyxl
python-multipart
supabase
```

Run:
```bash
pip3 install --break-system-packages -r requirements.txt -r requirements-dev.txt
```
Expected: instala sin errores (`supabase`, `pytest`, `python-dotenv` entre los nuevos paquetes).

- [ ] **Step 7: Crear el paquete de tests**

Create `tests/supabase/__init__.py` (archivo vacío).

- [ ] **Step 8: Commit**

```bash
git add supabase/config.toml requirements.txt requirements-dev.txt .env.test.example .gitignore tests/supabase/__init__.py
git commit -m "chore: inicializar Supabase local + dependencias de testing"
```

(`supabase/.gitignore`, generado por `supabase init`, ya excluye los volúmenes de datos locales — revisalo con `cat supabase/.gitignore` antes del commit para confirmar que no se está por trackear nada pesado.)

---

### Task 2: `profiles` + `is_oficina()` + RLS

**Files:**
- Create: `supabase/migrations/<timestamp>_profiles_and_roles.sql` (el nombre exacto lo genera el comando del Step 1 — usá `ls supabase/migrations/` para verlo)
- Create: `tests/supabase/conftest.py`
- Create: `tests/supabase/test_profiles.py`

- [ ] **Step 1: Generar el archivo de migración**

Run:
```bash
supabase migration new profiles_and_roles
```
Expected: imprime la ruta creada, algo como `supabase/migrations/20260920120000_profiles_and_roles.sql`. Usá esa ruta exacta en el Step 3.

- [ ] **Step 2: Escribir `conftest.py` (fixtures compartidas por toda la suite)**

Create `tests/supabase/conftest.py`:
```python
import os
import uuid

import pytest
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(".env.test")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

TEST_PASSWORD = "Test1234!"
TECNICO_EMAIL = "tecnico@test.local"
OFICINA_EMAIL = "oficina@test.local"


@pytest.fixture(scope="session")
def service_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _recreate_test_user(service_client: Client, email: str, role: str) -> str:
    existing = service_client.auth.admin.list_users()
    for user in existing:
        if user.email == email:
            service_client.auth.admin.delete_user(user.id)

    result = service_client.auth.admin.create_user(
        {"email": email, "password": TEST_PASSWORD, "email_confirm": True}
    )
    user_id = result.user.id
    service_client.table("profiles").insert(
        {"user_id": user_id, "full_name": f"Test {role}", "role": role}
    ).execute()
    return user_id


@pytest.fixture(scope="session")
def seed_test_users(service_client: Client) -> dict[str, str]:
    tecnico_id = _recreate_test_user(service_client, TECNICO_EMAIL, "tecnico")
    oficina_id = _recreate_test_user(service_client, OFICINA_EMAIL, "oficina")
    return {"tecnico": tecnico_id, "oficina": oficina_id}


def _signed_in_client(email: str) -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.auth.sign_in_with_password({"email": email, "password": TEST_PASSWORD})
    return client


@pytest.fixture
def tecnico_client(seed_test_users) -> Client:
    return _signed_in_client(TECNICO_EMAIL)


@pytest.fixture
def oficina_client(seed_test_users) -> Client:
    return _signed_in_client(OFICINA_EMAIL)


@pytest.fixture
def tecnico_id(seed_test_users) -> str:
    return seed_test_users["tecnico"]


@pytest.fixture
def oficina_id(seed_test_users) -> str:
    return seed_test_users["oficina"]


@pytest.fixture
def random_tag_id() -> str:
    return f"TEST-{uuid.uuid4().hex[:8]}"
```

- [ ] **Step 3: Escribir el test (falla porque `profiles` todavía no existe)**

Create `tests/supabase/test_profiles.py`:
```python
def test_tecnico_can_select_own_profile(tecnico_client, tecnico_id):
    response = tecnico_client.table("profiles").select("*").eq("user_id", tecnico_id).execute()
    assert len(response.data) == 1
    assert response.data[0]["role"] == "tecnico"


def test_tecnico_cannot_select_other_profile(tecnico_client, oficina_id):
    response = tecnico_client.table("profiles").select("*").eq("user_id", oficina_id).execute()
    assert response.data == []


def test_is_oficina_true_for_oficina_role(oficina_client):
    response = oficina_client.rpc("is_oficina").execute()
    assert response.data is True


def test_is_oficina_false_for_tecnico_role(tecnico_client):
    response = tecnico_client.rpc("is_oficina").execute()
    assert response.data is False
```

- [ ] **Step 4: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_profiles.py -v`
Expected: FAIL — error tipo `relation "public.profiles" does not exist` (la tabla no existe todavía) o `Could not find the function public.is_oficina`.

- [ ] **Step 5: Escribir la migración**

Write into the file created in Step 1 (`supabase/migrations/<timestamp>_profiles_and_roles.sql`):
```sql
create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  role text not null check (role in ('tecnico', 'oficina')),
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using (user_id = auth.uid());

create or replace function public.is_oficina()
returns boolean
language sql
stable
as $$
  select exists (
    select 1 from public.profiles
    where user_id = auth.uid() and role = 'oficina'
  );
$$;
```

- [ ] **Step 6: Aplicar la migración**

Run: `supabase db reset`
Expected: reconstruye la base local aplicando todas las migraciones existentes, termina sin error.

- [ ] **Step 7: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_profiles.py -v`
Expected: 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add supabase/migrations tests/supabase
git commit -m "feat: tabla profiles + is_oficina() + RLS"
```

---

### Task 3: `maintenance_records` + columna calculada `is_date_anomaly` + RLS

**Files:**
- Create: `supabase/migrations/<timestamp>_maintenance_records.sql`
- Create: `tests/supabase/test_maintenance_records.py`

- [ ] **Step 1: Generar el archivo de migración**

Run: `supabase migration new maintenance_records`
Expected: imprime la ruta creada (usarla en el Step 3).

- [ ] **Step 2: Escribir el test (falla porque la tabla no existe)**

Create `tests/supabase/test_maintenance_records.py`:
```python
import datetime

import pytest
from postgrest.exceptions import APIError


def _record_payload(tag_id: str, performed_at: str, **overrides):
    payload = {
        "tag_id": tag_id,
        "performed_at": performed_at,
        "type": "preventivo",
        "description": "Cambio de filtro",
    }
    payload.update(overrides)
    return payload


def test_tecnico_can_insert_record(tecnico_client, tecnico_id, random_tag_id):
    today = datetime.date.today().isoformat()
    response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    assert len(response.data) == 1
    assert response.data[0]["created_by"] == tecnico_id
    assert response.data[0]["is_date_anomaly"] is False


def test_insert_with_spoofed_created_by_is_rejected(tecnico_client, oficina_id, random_tag_id):
    today = datetime.date.today().isoformat()
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_records").insert(
            _record_payload(random_tag_id, today, created_by=oficina_id)
        ).execute()


def test_is_date_anomaly_true_when_performed_at_is_far_in_the_past(
    tecnico_client, random_tag_id
):
    old_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, old_date))
        .execute()
    )
    assert response.data[0]["is_date_anomaly"] is True


def test_any_authenticated_user_can_select_all_records(oficina_client, tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    tecnico_client.table("maintenance_records").insert(
        _record_payload(random_tag_id, today)
    ).execute()

    response = oficina_client.table("maintenance_records").select("*").eq("tag_id", random_tag_id).execute()
    assert len(response.data) == 1


def test_tecnico_cannot_update_record(tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    update_response = (
        tecnico_client.table("maintenance_records")
        .update({"description": "intento de edición"})
        .eq("id", record_id)
        .execute()
    )
    assert update_response.data == []


def test_tecnico_cannot_delete_record(tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_records").delete().eq("id", record_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_update_record(tecnico_client, oficina_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    update_response = (
        oficina_client.table("maintenance_records")
        .update({"description": "corregido por oficina"})
        .eq("id", record_id)
        .execute()
    )
    assert update_response.data[0]["description"] == "corregido por oficina"


def test_oficina_can_delete_record(tecnico_client, oficina_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_records").delete().eq("id", record_id).execute()
    )
    assert len(delete_response.data) == 1
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_maintenance_records.py -v`
Expected: FAIL — `relation "public.maintenance_records" does not exist`.

- [ ] **Step 4: Escribir la migración**

Write into `supabase/migrations/<timestamp>_maintenance_records.sql`:
```sql
create table public.maintenance_records (
  id uuid primary key default gen_random_uuid(),
  tag_id text not null,
  performed_at date not null,
  type text not null check (type in ('preventivo', 'correctivo')),
  description text not null,
  parts_used text,
  next_scheduled_at date,
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now(),
  is_date_anomaly boolean generated always as (
    abs(created_at::date - performed_at) > 2
  ) stored
);

create index maintenance_records_tag_id_idx on public.maintenance_records (tag_id);

alter table public.maintenance_records enable row level security;

create policy "maintenance_records_select_authenticated"
  on public.maintenance_records for select
  to authenticated
  using (true);

create policy "maintenance_records_insert_own"
  on public.maintenance_records for insert
  to authenticated
  with check (created_by = auth.uid());

create policy "maintenance_records_update_oficina"
  on public.maintenance_records for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_records_delete_oficina"
  on public.maintenance_records for delete
  to authenticated
  using (public.is_oficina());
```

Nota sobre `test_is_date_anomaly_true_when_performed_at_is_far_in_the_past`: `created_at` se genera como `now()` en el momento del insert, y `performed_at` se manda 10 días atrás — la diferencia (10 > 2) da `is_date_anomaly = true`. Es una prueba determinística porque no depende de mockear la hora.

- [ ] **Step 5: Aplicar la migración**

Run: `supabase db reset`
Expected: aplica las dos migraciones (Task 2 + esta) sin error.

- [ ] **Step 6: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_maintenance_records.py -v`
Expected: 8 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations tests/supabase/test_maintenance_records.py
git commit -m "feat: tabla maintenance_records con is_date_anomaly + RLS"
```

---

### Task 4: `maintenance_attachments` + RLS (técnico solo en registros propios)

**Files:**
- Create: `supabase/migrations/<timestamp>_maintenance_attachments.sql`
- Create: `tests/supabase/test_maintenance_attachments.py`

- [ ] **Step 1: Generar el archivo de migración**

Run: `supabase migration new maintenance_attachments`

- [ ] **Step 2: Escribir el test**

Create `tests/supabase/test_maintenance_attachments.py`:
```python
import datetime

import pytest
from postgrest.exceptions import APIError


def _insert_record(client, tag_id: str) -> str:
    today = datetime.date.today().isoformat()
    response = (
        client.table("maintenance_records")
        .insert(
            {
                "tag_id": tag_id,
                "performed_at": today,
                "type": "preventivo",
                "description": "Registro base para adjuntos",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_tecnico_can_insert_attachment_on_own_record(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_insert_attachment_on_others_record(
    tecnico_client, oficina_client, random_tag_id
):
    record_id = _insert_record(oficina_client, random_tag_id)
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_attachments").insert(
            {"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"}
        ).execute()


def test_oficina_can_insert_attachment_on_any_record(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        oficina_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "audio", "storage_path": f"{random_tag_id}/{record_id}/1.webm"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_delete_attachment(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    attachment_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_attachments").delete().eq("id", attachment_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_delete_attachment(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    attachment_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_attachments").delete().eq("id", attachment_id).execute()
    )
    assert len(delete_response.data) == 1
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_maintenance_attachments.py -v`
Expected: FAIL — `relation "public.maintenance_attachments" does not exist`.

- [ ] **Step 4: Escribir la migración**

Write into `supabase/migrations/<timestamp>_maintenance_attachments.sql`:
```sql
create table public.maintenance_attachments (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null references public.maintenance_records(id) on delete cascade,
  kind text not null check (kind in ('photo', 'audio')),
  storage_path text not null,
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now()
);

create index maintenance_attachments_record_id_idx on public.maintenance_attachments (record_id);

alter table public.maintenance_attachments enable row level security;

create policy "maintenance_attachments_select_authenticated"
  on public.maintenance_attachments for select
  to authenticated
  using (true);

create policy "maintenance_attachments_insert_own_record_or_oficina"
  on public.maintenance_attachments for insert
  to authenticated
  with check (
    created_by = auth.uid()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

create policy "maintenance_attachments_update_oficina"
  on public.maintenance_attachments for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_attachments_delete_oficina"
  on public.maintenance_attachments for delete
  to authenticated
  using (public.is_oficina());
```

- [ ] **Step 5: Aplicar la migración**

Run: `supabase db reset`

- [ ] **Step 6: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_maintenance_attachments.py -v`
Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations tests/supabase/test_maintenance_attachments.py
git commit -m "feat: tabla maintenance_attachments + RLS (técnico solo en registros propios)"
```

---

### Task 5: `maintenance_comments` + RLS (mismo patrón que adjuntos)

**Files:**
- Create: `supabase/migrations/<timestamp>_maintenance_comments.sql`
- Create: `tests/supabase/test_maintenance_comments.py`

- [ ] **Step 1: Generar el archivo de migración**

Run: `supabase migration new maintenance_comments`

- [ ] **Step 2: Escribir el test**

Create `tests/supabase/test_maintenance_comments.py`:
```python
import datetime

import pytest
from postgrest.exceptions import APIError


def _insert_record(client, tag_id: str) -> str:
    today = datetime.date.today().isoformat()
    response = (
        client.table("maintenance_records")
        .insert(
            {
                "tag_id": tag_id,
                "performed_at": today,
                "type": "correctivo",
                "description": "Registro base para comentarios",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_tecnico_can_comment_on_own_record(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "Se reemplazó el rodamiento"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_comment_on_others_record(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(oficina_client, random_tag_id)
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_comments").insert(
            {"record_id": record_id, "body": "intento ajeno"}
        ).execute()


def test_tecnico_cannot_delete_comment(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "comentario original"})
        .execute()
    )
    comment_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_comments").delete().eq("id", comment_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_delete_comment(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "comentario a borrar"})
        .execute()
    )
    comment_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_comments").delete().eq("id", comment_id).execute()
    )
    assert len(delete_response.data) == 1
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_maintenance_comments.py -v`
Expected: FAIL — `relation "public.maintenance_comments" does not exist`.

- [ ] **Step 4: Escribir la migración**

Write into `supabase/migrations/<timestamp>_maintenance_comments.sql`:
```sql
create table public.maintenance_comments (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null references public.maintenance_records(id) on delete cascade,
  author_id uuid not null default auth.uid() references auth.users(id),
  body text not null,
  created_at timestamptz not null default now()
);

create index maintenance_comments_record_id_idx on public.maintenance_comments (record_id);

alter table public.maintenance_comments enable row level security;

create policy "maintenance_comments_select_authenticated"
  on public.maintenance_comments for select
  to authenticated
  using (true);

create policy "maintenance_comments_insert_own_record_or_oficina"
  on public.maintenance_comments for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

create policy "maintenance_comments_update_oficina"
  on public.maintenance_comments for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_comments_delete_oficina"
  on public.maintenance_comments for delete
  to authenticated
  using (public.is_oficina());
```

- [ ] **Step 5: Aplicar la migración**

Run: `supabase db reset`

- [ ] **Step 6: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_maintenance_comments.py -v`
Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations tests/supabase/test_maintenance_comments.py
git commit -m "feat: tabla maintenance_comments + RLS (técnico solo en registros propios)"
```

---

### Task 6: `maintenance_audit_log` + triggers de auditoría inmutable

**Files:**
- Create: `supabase/migrations/<timestamp>_maintenance_audit_log.sql`
- Create: `tests/supabase/test_maintenance_audit_log.py`

- [ ] **Step 1: Generar el archivo de migración**

Run: `supabase migration new maintenance_audit_log`

- [ ] **Step 2: Escribir el test**

Create `tests/supabase/test_maintenance_audit_log.py`:
```python
import datetime


def _insert_record(client, tag_id: str) -> str:
    today = datetime.date.today().isoformat()
    response = (
        client.table("maintenance_records")
        .insert(
            {
                "tag_id": tag_id,
                "performed_at": today,
                "type": "preventivo",
                "description": "original",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_oficina_update_creates_audit_entry(tecnico_client, oficina_client, oficina_id, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    assert len(audit.data) == 1
    entry = audit.data[0]
    assert entry["action"] == "update"
    assert entry["changed_by"] == oficina_id
    assert entry["old_data"]["description"] == "original"
    assert entry["new_data"]["description"] == "corregido"


def test_oficina_delete_creates_audit_entry(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").delete().eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    assert len(audit.data) == 1
    entry = audit.data[0]
    assert entry["action"] == "delete"
    assert entry["new_data"] is None
    assert entry["old_data"]["description"] == "original"


def test_tecnico_cannot_select_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    response = tecnico_client.table("maintenance_audit_log").select("*").eq("record_id", record_id).execute()
    assert response.data == []


def test_oficina_cannot_update_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    audit_id = audit.data[0]["id"]

    tamper_response = (
        oficina_client.table("maintenance_audit_log")
        .update({"action": "update", "old_data": {}})
        .eq("id", audit_id)
        .execute()
    )
    assert tamper_response.data == []


def test_oficina_cannot_delete_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    audit_id = audit.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_audit_log").delete().eq("id", audit_id).execute()
    )
    assert delete_response.data == []
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_maintenance_audit_log.py -v`
Expected: FAIL — `relation "public.maintenance_audit_log" does not exist`.

- [ ] **Step 4: Escribir la migración**

Write into `supabase/migrations/<timestamp>_maintenance_audit_log.sql`:
```sql
create table public.maintenance_audit_log (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null,
  action text not null check (action in ('update', 'delete')),
  old_data jsonb,
  new_data jsonb,
  changed_by uuid not null references auth.users(id),
  changed_at timestamptz not null default now()
);

create index maintenance_audit_log_record_id_idx on public.maintenance_audit_log (record_id);

alter table public.maintenance_audit_log enable row level security;

create policy "maintenance_audit_log_select_oficina"
  on public.maintenance_audit_log for select
  to authenticated
  using (public.is_oficina());

-- Sin políticas de insert/update/delete para ningún rol: por default, RLS deniega
-- lo que no tiene policy. Solo el trigger (SECURITY DEFINER, dueño de la tabla,
-- por lo tanto exento de RLS) puede escribir acá.

create or replace function public.log_maintenance_audit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'UPDATE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.id, 'update', to_jsonb(old), to_jsonb(new), auth.uid());
    return new;
  elsif tg_op = 'DELETE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.id, 'delete', to_jsonb(old), null, auth.uid());
    return old;
  end if;
  return null;
end;
$$;

create trigger maintenance_records_audit
  after update or delete on public.maintenance_records
  for each row execute function public.log_maintenance_audit();

create or replace function public.log_maintenance_child_audit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'UPDATE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.record_id, 'update', to_jsonb(old), to_jsonb(new), auth.uid());
    return new;
  elsif tg_op = 'DELETE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.record_id, 'delete', to_jsonb(old), null, auth.uid());
    return old;
  end if;
  return null;
end;
$$;

create trigger maintenance_attachments_audit
  after update or delete on public.maintenance_attachments
  for each row execute function public.log_maintenance_child_audit();

create trigger maintenance_comments_audit
  after update or delete on public.maintenance_comments
  for each row execute function public.log_maintenance_child_audit();
```

- [ ] **Step 5: Aplicar la migración**

Run: `supabase db reset`

- [ ] **Step 6: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_maintenance_audit_log.py -v`
Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations tests/supabase/test_maintenance_audit_log.py
git commit -m "feat: maintenance_audit_log + triggers de auditoría inmutable"
```

---

### Task 7: Storage bucket `maintenance-attachments` + policies

**Files:**
- Create: `supabase/migrations/<timestamp>_maintenance_storage.sql`
- Create: `tests/supabase/test_maintenance_storage.py`

**Nota de alcance:** la policy de INSERT en Storage permite a cualquier usuario autenticado subir un archivo a este bucket (no valida "es dueño del `record_id`" contra la tabla, porque implicaría parsear el path del objeto). El control real de propiedad ya está aplicado en la tabla `maintenance_attachments` (Task 4) — el cliente siempre sube primero el archivo y después inserta la fila de metadata, y la UI solo muestra archivos que tienen una fila asociada. El único gap aceptado es que un técnico podría en teoría subir un archivo "huérfano" sin fila de metadata — no expone nada (la lectura sigue exigiendo estar logueado) y como mucho desperdicia espacio. El borrado sí queda restringido a `oficina` a nivel de Storage, para que la regla "técnico nunca borra" no se pueda esquivar borrando el archivo directamente aunque no pueda borrar la fila.

- [ ] **Step 1: Generar el archivo de migración**

Run: `supabase migration new maintenance_storage`

- [ ] **Step 2: Escribir el test**

Create `tests/supabase/test_maintenance_storage.py`:
```python
import pytest
from storage3.utils import StorageException

BUCKET = "maintenance-attachments"


def test_tecnico_can_upload_and_read(tecnico_client, random_tag_id):
    path = f"{random_tag_id}/test/1.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    downloaded = tecnico_client.storage.from_(BUCKET).download(path)
    assert downloaded == b"contenido-de-prueba"


def test_tecnico_cannot_delete(tecnico_client, random_tag_id):
    path = f"{random_tag_id}/test/2.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    with pytest.raises(StorageException):
        tecnico_client.storage.from_(BUCKET).remove([path])


def test_oficina_can_delete(tecnico_client, oficina_client, random_tag_id):
    path = f"{random_tag_id}/test/3.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    result = oficina_client.storage.from_(BUCKET).remove([path])
    assert result is not None
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/supabase/test_maintenance_storage.py -v`
Expected: FAIL — el bucket `maintenance-attachments` no existe (error tipo `Bucket not found`).

- [ ] **Step 4: Escribir la migración**

Write into `supabase/migrations/<timestamp>_maintenance_storage.sql`:
```sql
insert into storage.buckets (id, name, public)
values ('maintenance-attachments', 'maintenance-attachments', false)
on conflict (id) do nothing;

create policy "maintenance_attachments_storage_select"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'maintenance-attachments');

create policy "maintenance_attachments_storage_insert"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'maintenance-attachments');

create policy "maintenance_attachments_storage_delete_oficina"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'maintenance-attachments' and public.is_oficina());
```

- [ ] **Step 5: Aplicar la migración**

Run: `supabase db reset`

- [ ] **Step 6: Correr los tests y confirmar que pasan**

Run: `pytest tests/supabase/test_maintenance_storage.py -v`
Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations tests/supabase/test_maintenance_storage.py
git commit -m "feat: bucket maintenance-attachments + storage policies"
```

---

### Task 8: Correr la suite completa, documentar y preparar el proyecto Supabase real

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Correr toda la suite junta**

Run: `pytest tests/supabase -v`
Expected: todos los tests de los Tasks 2-7 PASS (28 tests en total).

- [ ] **Step 2: Documentar el nuevo componente en `CLAUDE.md`**

Agregar en la tabla "Estado de archivos" de `CLAUDE.md`:
```markdown
| [supabase/migrations/](supabase/migrations/) | ✅ Schema + RLS + triggers + Storage del histórico de mantenimientos (Plan 1) |
| [tests/supabase/](tests/supabase/) | ✅ Suite pytest de RLS — requiere `supabase start` (Docker) corriendo localmente |
```

- [ ] **Step 3: Commit de la documentación**

```bash
git add CLAUDE.md
git commit -m "docs: documentar schema de Supabase para histórico de mantenimientos"
```

- [ ] **Step 4 (manual, fuera del repo): crear el proyecto Supabase real y aplicar las migraciones**

Esto lo hacés vos, no es un paso de código:
1. Crear el proyecto en `https://supabase.com/dashboard`.
2. `supabase link --project-ref <tu-project-ref>` desde este repo.
3. `supabase db push` para aplicar todas las migraciones al proyecto real.
4. Crear las cuentas reales de técnico(s) y oficina desde el dashboard (Authentication → Users) + su fila correspondiente en `profiles` (Table Editor).
5. Agregar el dominio `https://www.rpcidvida.dpdns.org` (y `http://localhost:8190` para pruebas locales del sitio) en Authentication → URL Configuration.
6. Guardar el `Project URL` y el `anon public key` reales — los va a pedir el Plan 2 (integración en el sitio) para escribirlos en `site_config.json`.

Este plan (Plan 1) termina acá. El Plan 2 (sitio) y el Plan 3 (`gui.py`) asumen que este schema ya está aplicado, sea en local (`supabase start`) para seguir desarrollando, o en el proyecto real para producción.
