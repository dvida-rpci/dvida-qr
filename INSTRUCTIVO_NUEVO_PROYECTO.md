# Instructivo: crear un proyecto nuevo (TAGs nuevos + Supabase nuevo)

Sirve cuando un cliente nuevo necesita **su propio sitio de fichas técnicas** con **su propio histórico de mantenimientos** en **otra cuenta de Supabase**. Tiempo estimado: 45–60 min la primera vez, unos 30 min después.

**Regla de oro: un proyecto = un repo de GitHub + un proyecto de Supabase.** No reutilices el repo ni la base del proyecto anterior: GitHub Pages sirve `docs/` de *ese* repo, los QR (`urls.txt`) se arman con el remote de git, y los mantenimientos se guardan por TAG en texto, así que dos proyectos con el mismo TAG (`100-P-01A`) se mezclarían en una misma base.

## Qué necesitas antes de empezar

- El Excel de fichas técnicas del cliente (una hoja por TAG, ver "Formato del Excel").
- Logo del cliente (PNG) y, si quieres que sea clickeable, su URL.
- Una cuenta de GitHub donde vivirá el repo, y una cuenta de Supabase (la del cliente o la tuya).
- Herramientas ya instaladas: Python 3.12 + `openpyxl` + `nicegui`, `git`, `gh` (opcional) y el CLI `supabase` (guía en `New_Laptop.txt`).

---

## Parte 1 — Repo nuevo a partir de este

```bash
git clone https://github.com/dvida-rpci/dvida-qr.git qr-<cliente>
cd qr-<cliente>
rm -rf .git && git init -b master          # historial limpio; el proyecto anterior no viaja
```

Crea un repo **vacío** en GitHub (cuenta del cliente o tuya), sin README, y conéctalo:

```bash
git remote add origin https://github.com/<cuenta>/<repo>.git
```

### Limpiar todo lo del proyecto anterior

Estos archivos son datos del cliente anterior. Si los dejas, terminan publicados (o se usan por error):

```bash
rm -f  *.xlsx                              # fichas viejas, plantilla_sitio.xlsx, TAG_RESOURCES.xlsx, fichas_source.xlsx
rm -rf docs/equipos docs/instrumentos docs/tanques
rm -rf docs/assets/images/*                # fotos de los TAGs anteriores
rm -f  docs/CNAME                          # dominio propio del proyecto anterior (si lo dejas, Pages intenta servir ese dominio)
rm -f  docs/urls.txt docs/search-index.* docs/migration_metadata.json
```

Reemplaza los logos en `docs/assets/logos/`: `LogoRPCI.png` (izquierdo) y `LogoCliente.png` (derecho). También puedes subir el del cliente desde la GUI (paso 3.2).

> `docs/superpowers/` contiene los specs y planes del desarrollo. Puedes dejarlo (documenta el sistema) o borrarlo; al estar dentro de `docs/`, Pages lo publica.

---

## Parte 2 — Proyecto de Supabase nuevo

### 2.1 Crear el proyecto

1. Entra a https://supabase.com con la cuenta destino → **New project**. Elige nombre, región (la más cercana a los usuarios) y **guarda la contraseña de la base de datos**: la pide el CLI.
2. Espera a que quede `ACTIVE_HEALTHY` (1–2 min).
3. Anota, de **Project Settings → API**: `Project URL` y la clave **anon / publishable**. Del panel, el **Project ref** (parte inicial de la URL, `https://<ref>.supabase.co`).

> ⚠️ La `service_role` / `secret` key **nunca** va al repo ni al `site_config.json`. Solo la `anon` (pública a propósito, protegida por RLS).

### 2.2 Aplicar el esquema (tablas, RLS, bucket)

El CLI guarda **una sesión a la vez**. Para no pisar la de tu cuenta habitual, usa el token de la cuenta nueva solo en estos comandos (token en Supabase → *Account → Access Tokens*):

```bash
export SUPABASE_ACCESS_TOKEN=<token-de-la-cuenta-nueva>     # solo para esta terminal
supabase link --project-ref <ref> --password '<password-de-la-base>'
supabase db push --dry-run                                  # muestra qué se va a aplicar
supabase db push                                            # aplica TODAS las migraciones de supabase/migrations/ en orden
```

Las migraciones crean `profiles`, `maintenance_records`, `maintenance_attachments`, `maintenance_comments`, `maintenance_audit_log`, el bucket privado `maintenance-attachments` (con límites de tamaño/tipo) y todas las políticas RLS. No hay que crear nada a mano.

**Verifica** (debe decir `tablas: 5`, `usuarios: 0`, `perfiles: 0`):

```bash
supabase db query --project-ref <ref> --linked "select (select count(*) from information_schema.tables where table_schema='public' and table_name in ('profiles','maintenance_records','maintenance_attachments','maintenance_comments','maintenance_audit_log')) as tablas, (select count(*) from auth.users) as usuarios, (select count(*) from public.profiles) as perfiles"
```

### 2.3 Cerrar el auto-registro

En el dashboard: **Authentication → Sign In / Providers → Email** y desactiva **"Allow new users to sign up"** (el nombre exacto del interruptor puede variar según la versión del panel). Sin esto, cualquiera con la `anon_key` (que es pública en el sitio) puede crearse una cuenta. Esas cuentas no tienen perfil y por eso no pueden escribir, pero es mejor no tenerlas.

### 2.4 Crear los usuarios y sus perfiles

Sin auto-registro, las cuentas las creas tú. Por cada persona, dos pasos:

1. **Authentication → Users → Add user → Create new user**: correo y contraseña, y marca **Auto Confirm User**. Copia el **UID** que aparece.
2. **SQL Editor** (o `supabase db query --linked "<sql>"`), con ese UID:

```sql
insert into public.profiles (user_id, full_name, role)
values ('<uid-del-usuario>', 'Nombre Apellido', 'tecnico');   -- o 'oficina'
```

Sin la fila de `profiles` el usuario inicia sesión pero **no puede registrar nada**.

| Rol | Puede |
| --- | --- |
| `tecnico` | Desde la ficha del sitio: registrar mantenimientos y agregar comentarios/adjuntos a los **suyos**. No edita ni borra. |
| `oficina` | Editar y borrar registros desde `gui.py` → **🧰 Mantenimientos**. |

Crea al menos una cuenta de cada rol y guarda las contraseñas en un gestor de contraseñas (nunca en el repo).

---

## Parte 3 — Configurar el sitio y cargar los TAGs

### 3.1 `site_config.json`

Edita el archivo en la raíz. La GUI cambia solo título, color, logo y enlace del logo; **estos campos se editan a mano**:

```json
{
  "site_title": "QR <Cliente>",
  "banner_title_full": "Documentación Técnica — <Proyecto>",
  "banner_title_short": "<Proyecto>",
  "site_url": "https://<cuenta>.github.io/<repo>/",
  "logos": {
    "left": "assets/logos/LogoRPCI.png", "left_alt": "RPCI", "left_href": "https://rpci.com.co",
    "right": "assets/logos/LogoCliente.png", "right_alt": "<Cliente>",
    "right_href": "https://<sitio-del-cliente>"
  },
  "supabase": {
    "url": "https://<ref>.supabase.co",
    "anon_key": "<anon key del proyecto NUEVO>"
  }
}
```

- Los valores por defecto de los títulos del banner son los del proyecto anterior ("PTAR STARnD"); si no los cambias aquí, el sitio nuevo los muestra.
- `site_url` gobierna el banner y el README. Los QR (`urls.txt`) **no** lo usan: salen del remote de git.
- Usa la `anon_key` del proyecto **nuevo**. Mezclarla con la URL vieja es el error más común: el login falla con "Invalid API key".

### 3.2 Cargar las fichas y generar el sitio

Puedes usar la GUI o la línea de comandos.

**Con la GUI** (recomendado la primera vez): `./launch_gui.sh` → http://localhost:8080. Sube el xlsx de fichas, el logo y el `TAG_RESOURCES.xlsx` si ya lo tienes, ajusta título y color, y pulsa **Generar sitio**. Como no hay plantilla, se ejecuta la conversión con tu xlsx.

**Con la línea de comandos:**

```bash
python3 convert_fichas_to_template.py "<fichas-del-cliente>.xlsx"   # crea plantilla_sitio.xlsx y extrae imágenes a docs/assets/images/<TAG>/
python3 generate_tag_resources_template.py                          # crea TAG_RESOURCES.xlsx con una fila por TAG
# edita TAG_RESOURCES.xlsx: en cada celda Specifications/Handbook_Manual/Maintenance usa Ctrl+K para pegar el enlace
python3 excel_migrator.py plantilla_sitio.xlsx docs/
```

Mira el log: debe mostrar el número de TAGs esperado y su distribución por categoría.

### Formato del Excel de fichas

- **Una hoja por TAG.** El nombre de la hoja debe cumplir `^\d{3}-[A-Z]+-` (por ejemplo `100-P-01A`). Las demás hojas se ignoran.
- Hojas con varios TAGs se expanden: `100-P-01 A_B` → `100-P-01A` y `100-P-01B`.
- La categoría sale del tipo del TAG: `TK|R|F|SD` → TANQUES, `P|MX|M|C|PS` → EQUIPOS, `AIT|FIT|SV|LT` → INSTRUMENTOS. **Un tipo nuevo (por ejemplo `HX`) no cae en ninguna categoría**: hay que agregarlo en el mapeo de `convert_fichas_to_template.py`.
- Layout `ETIQUETA | VALOR` por fila; el campo `SERVICIO` da el nombre que se ve en el título y en el buscador.
- Los logos del encabezado del Excel se filtran solos (filas 1–3 y ≤5 filas de alto). Las fotos de equipos se conservan.

---

## Parte 4 — Probar en local antes de publicar

1. En la GUI pulsa **Ver sitio** (http://localhost:8190) o ejecuta `cd docs && python3 -m http.server 8190`.
2. Revisa: cantidad de TAGs, títulos, imágenes, botones de documentos, buscador, colores y logos.
3. Abre una ficha → **Ver/agregar historial de mantenimiento** → inicia sesión con el usuario `tecnico` del proyecto nuevo → registra un mantenimiento de prueba con una foto. Si entra y guarda, la conexión con el Supabase nuevo está bien.
4. Abre **🧰 Mantenimientos** en la GUI con el usuario `oficina` y confirma que ves ese registro y puedes borrarlo (bórralo, es de prueba).

---

## Parte 5 — Publicar

1. `git add . && git commit -m "Proyecto inicial <cliente>"` y `git push -u origin master`.
2. En GitHub: **Settings → Pages → Source: Deploy from a branch → `master` / carpeta `/docs`**. Ese ajuste no se hereda: hay que hacerlo en cada repo.
3. Espera 1–2 min (`gh api repos/<cuenta>/<repo>/pages/builds/latest --jq .status` debe decir `built`).
4. Abre `https://<cuenta>.github.io/<repo>/` y repite la prueba de login/historial.
5. **Dominio propio (opcional):** crea `docs/CNAME` con el dominio, apunta el DNS y actívalo en Settings → Pages.
6. **QR:** `docs/urls.txt` ya trae la URL final de cada TAG (`CATEGORIA,URL`), derivada del remote de git. Genera los QR **después** de confirmar que el remote es el repo definitivo.

---

## Checklist final

- [ ] `site_config.json` con URL y `anon_key` del proyecto **nuevo** y títulos del cliente
- [ ] `supabase db push` aplicado y verificación `tablas: 5`
- [ ] Auto-registro desactivado en Supabase
- [ ] Al menos un usuario `tecnico` y uno `oficina`, cada uno con su fila en `profiles`
- [ ] Sin archivos del cliente anterior (`*.xlsx`, `docs/assets/images/*`, `docs/CNAME`)
- [ ] Sitio publicado, Pages sirviendo `/docs`, y prueba de historial hecha en producción
- [ ] QR generados desde `urls.txt` del repo definitivo

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
| --- | --- | --- |
| El sitio muestra TAGs del cliente anterior | Quedó `plantilla_sitio.xlsx` o un xlsx viejo en la raíz | Borrar los `*.xlsx`, re-correr `convert_fichas_to_template.py` |
| Login: "Invalid API key" / no conecta | `url` y `anon_key` de proyectos distintos, o falta regenerar el sitio | Corregir `site_config.json` y volver a generar (la config se inyecta al generar) |
| Login funciona pero no deja registrar | El usuario no tiene fila en `profiles` | Insertarla (Parte 2.4) |
| "relation ... does not exist" | No se aplicaron las migraciones | `supabase db push` (Parte 2.2) |
| Pages sirve una página en blanco/404 | Pages apunta a la raíz o quedó un `CNAME` viejo | Pages → `/docs`; borrar `docs/CNAME` |
| El banner dice "PTAR STARnD" | Títulos por defecto sin cambiar | Editar `banner_title_*` en `site_config.json` |
| Un TAG no aparece | El nombre de hoja no cumple `^\d{3}-[A-Z]+-` o el tipo no tiene categoría | Renombrar la hoja o agregar el tipo al mapeo |
| Hay fotos que no corresponden | Fotos de TAGs anteriores en `docs/assets/images/` | Vaciar esa carpeta y re-extraer con `--images-only` |

## Cuando el proyecto ya está en marcha

- **Actualizar fichas:** GUI con el switch **🔄 Forzar regeneración** y el xlsx nuevo, o `./update_site_from_excel.sh --from-fichas --push`.
- **Agregar TAGs nuevos al Excel:** no afecta a los mantenimientos ya cargados. El historial vive en Supabase y regenerar el sitio solo reescribe archivos HTML. El TAG nuevo arranca sin historial ("Todavía no hay mantenimientos registrados") y basta con que alguien cargue el primero; no hay que darlo de alta en la base.
- **⚠️ Renombrar o borrar un TAG del Excel:** ahí sí hay riesgo. El mantenimiento se empareja con la ficha por el **texto exacto** del TAG, así que al corregir `100-P-01A` por `100-P-1A` la ficha nueva aparece vacía y los registros viejos quedan huérfanos: siguen en la base y se ven en la pestaña **Todos** de últimos mantenimientos, pero sin enlace a ninguna ficha y fuera de las pestañas por categoría. Si hay que renombrar, actualizá también la base:

  ```sql
  update public.maintenance_records set tag_id = '<TAG nuevo>' where tag_id = '<TAG viejo>';
  ```

  Queda registrado en `maintenance_audit_log`. Hacelo con backup: no está probado en producción.
- **Nuevas migraciones del sistema** (cuando se agreguen en `supabase/migrations/`): se aplican en cada proyecto con `supabase link` + `supabase db push`; los proyectos ya creados solo reciben las nuevas.
- **Cuentas nuevas:** repite la Parte 2.4.
- **Copia de seguridad:** el histórico vive solo en Supabase; activa los backups del proyecto (o exporta periódicamente desde el dashboard).
