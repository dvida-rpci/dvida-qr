# Histórico de Mantenimientos — Plan 2: Integración en el sitio (frontend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar a la ficha de cada TAG los dos botones "Ver ficha técnica" / "Ver/agregar historial de mantenimiento", y detrás del segundo, todo el flujo cliente-Supabase: login, lectura del historial, carga de nuevos registros (con fotos comprimidas y notas de audio) y comentarios/adjuntos adicionales sobre eventos propios.

**Architecture:** Todo el código nuevo vive en dos archivos estáticos nuevos (`maintenance.css`, `maintenance.js`) que el migrator copia al output sin tocarlos — **no** se embeben como strings de Python dentro de `excel_migrator.py` (que ya tiene 2098 líneas con `STYLES_CSS`/`SCRIPT_JS` embebidos; sumar ahí varios cientos de líneas de JS de auth/cámara/compresión sería imposible de mantener). `excel_migrator.py` solo se toca para: (a) inyectar la config de Supabase y el SDK como `<script>` tags, y (b) envolver el contenido actual de la ficha en un contenedor toggleable y agregar los dos botones. El resto de la lógica (todo lo dinámico) vive en `maintenance.js`, que habla directo con Supabase (mismo patrón BaaS del Plan 1 — ver [spec](../specs/2026-09-20-historico-mantenimientos-design.md)).

**Tech Stack:** JS vainilla (sin build step, consistente con `script.js` existente), Supabase JS SDK v2 vía CDN (`@supabase/supabase-js`), `<canvas>` para compresión de fotos, `MediaRecorder`/`getUserMedia` para audio, `localStorage` para drafts.

**Testing:** el spec de este feature ya define la estrategia de testing (sección "Testing"): solo RLS se automatiza (Plan 1, ya hecho). Todo lo de UI/frontend es **verificación manual en navegador** — este proyecto no tiene ni tiene previsto un framework de test para JS vainilla sin build step, y agregar uno ahora sería una decisión de arquitectura no pedida. Cada task de este plan termina con una verificación manual concreta (qué hacer en el navegador y qué deberías ver) en vez de un `pytest`.

**Prerequisito:** Plan 1 aplicado — como mínimo corriendo en local (`supabase start`, ver Plan 1 Task 1). Vas a necesitar el `anon key` local para el Task 1 de este plan.

---

### Task 1: Config de Supabase en `site_config.json` + inyección en el HTML

**Files:**
- Modify: `excel_migrator.py:188-236` (`load_site_config`)
- Modify: `excel_migrator.py:423-517` (`page_skeleton`)
- Modify: `site_config.json` (raíz del repo)

- [ ] **Step 1: Agregar el bloque `supabase` al schema de `load_site_config()`**

En `excel_migrator.py`, dentro de `load_site_config()`, el dict `cfg` inicial (línea ~209-223) agrega una entrada `"supabase"`:

```python
    cfg = {
        "site_title": SITE_TITLE,
        "banner_title_full": BANNER_TITLE_FULL,
        "banner_title_short": BANNER_TITLE_SHORT,
        "site_url": default_site_url,
        "theme": dict(DEFAULT_THEME),
        "logos": {
            "left": LOGO_LEFT_PATH,
            "left_alt": LOGO_LEFT_ALT,
            "left_href": LOGO_LEFT_HREF,
            "right": LOGO_RIGHT_PATH,
            "right_alt": LOGO_RIGHT_ALT,
            "right_href": LOGO_RIGHT_HREF,
        },
        "supabase": {
            "url": "",
            "anon_key": "",
        },
    }
```

Y en el bloque que mergea `user_cfg` (después de la línea que hace `cfg["logos"].update(user_cfg["logos"])`), agregar:

```python
    if "supabase" in user_cfg and isinstance(user_cfg["supabase"], dict):
        cfg["supabase"].update(user_cfg["supabase"])
```

- [ ] **Step 2: Inyectar la config de Supabase + el SDK en `page_skeleton()`**

En `excel_migrator.py`, `page_skeleton()` recibe hoy `page_title, topbar_title, sidebar_html, content_html, rel_prefix`. Agregar un parámetro nuevo `supabase_config: dict`:

```python
def page_skeleton(
    page_title: str,
    topbar_title: str,
    sidebar_html: str,
    content_html: str,
    rel_prefix: str,
    supabase_config: dict,
) -> str:
```

Dentro del `<head>`, justo debajo de la línea `<link rel="stylesheet" href="{rel_prefix}styles.css">`, agregar:

```python
    <link rel="stylesheet" href="{rel_prefix}styles.css">
    <link rel="stylesheet" href="{rel_prefix}maintenance.css">
    <script>
        window.__SUPABASE_CONFIG__ = {{
            url: {json.dumps(supabase_config.get("url", ""))},
            anonKey: {json.dumps(supabase_config.get("anon_key", ""))}
        }};
    </script>
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
```

Y antes del cierre `</body>`, junto a los otros `<script>` existentes (línea ~513-514), agregar `maintenance.js` **después** de `script.js`:

```python
    <script src="{rel_prefix}search-index.js"></script>
    <script src="{rel_prefix}script.js"></script>
    <script src="{rel_prefix}maintenance.js"></script>
</body>
```

- [ ] **Step 3: Propagar `supabase_config` a los 3 call-sites de `page_skeleton()`**

`page_skeleton()` se llama desde `generate_site()` (home) y desde las funciones que arman `category/index.html` e `item.html` (buscalas con `grep -n "page_skeleton(" excel_migrator.py`). En cada llamada, agregar `supabase_config=config["supabase"]` a los argumentos — `config` ya está disponible en `generate_site()` (parámetro de la función) y se pasa por delante a las funciones que arman cada tipo de página. Si alguna de esas funciones no recibe `config` hoy, agregale un parámetro `config: dict` y pasalo desde donde se la invoca.

- [ ] **Step 4: Cargar la config real de Supabase local en `site_config.json`**

En `site_config.json` (raíz del repo), agregar el bloque `supabase` con los valores impresos por `supabase start` (Plan 1, Task 1, Step 3):

```json
  "supabase": {
    "url": "http://127.0.0.1:54321",
    "anon_key": "PEGAR_ACA_EL_ANON_KEY_QUE_IMPRIMIO_SUPABASE_START"
  }
```

(Cuando el Plan 1 se aplique al proyecto real, estos dos valores se reemplazan por el `Project URL`/`anon public key` reales — es la única línea que cambia entre local y producción.)

- [ ] **Step 5: Crear los dos archivos estáticos vacíos (placeholders reales, no del migrator)**

Create `maintenance.css` (contenido inicial, se completa en el Task 2):
```css
/* Estilos del histórico de mantenimientos — ver Task 2 en adelante */
```

Create `maintenance.js` (contenido inicial, se completa en el Task 3):
```javascript
// Histórico de mantenimientos — ver Task 3 en adelante
```

- [ ] **Step 6: Copiar los archivos nuevos al output y agregarlos al cleanup whitelist**

En `excel_migrator.py`, `generate_site()`:

En el set `KNOWN_FILES` (línea ~1856-1859), agregar `"maintenance.css"` y `"maintenance.js"`:
```python
    KNOWN_FILES = {
        "index.html", "README.md", "styles.css", "script.js", ".nojekyll",
        "migration_metadata.json", "search-index.json", "search-index.js", "urls.txt",
        "maintenance.css", "maintenance.js",
    }
```

Justo debajo de donde se escribe `script.js` (línea ~1876), agregar:
```python
    (output_dir / "maintenance.css").write_text(
        (REPO_ROOT / "maintenance.css").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (output_dir / "maintenance.js").write_text(
        (REPO_ROOT / "maintenance.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
```

(`REPO_ROOT` — si `excel_migrator.py` no tiene ya una constante con ese nombre, usar `Path(__file__).parent` inline o verificar el nombre real de la constante equivalente al inicio del archivo con `grep -n "^REPO_ROOT\|Path(__file__)" excel_migrator.py`.)

- [ ] **Step 7: Verificación manual**

Run:
```bash
python3 excel_migrator.py plantilla_sitio.xlsx docs/
grep -c "maintenance.css\|maintenance.js\|__SUPABASE_CONFIG__" docs/equipos/*.html | head -3
```
Expected: cada HTML de ficha generado contiene las referencias a `maintenance.css`, `maintenance.js` y el bloque `window.__SUPABASE_CONFIG__` con la URL/key que pusiste en `site_config.json`. Abrí uno de esos HTML en el navegador (`python3 -m http.server 8190` desde `docs/`) y confirmá en la consola del navegador (F12) que no hay errores de red al cargar `maintenance.css`/`maintenance.js`/el SDK de Supabase.

- [ ] **Step 8: Commit**

```bash
git add excel_migrator.py site_config.json maintenance.css maintenance.js
git commit -m "feat: inyectar config y SDK de Supabase en el sitio generado"
```

---

### Task 2: Botones "Ver ficha técnica" / "Ver/agregar historial" + estilos base

**Files:**
- Modify: `excel_migrator.py:588-666` (`render_item_page`)
- Modify: `maintenance.css`

- [ ] **Step 1: Envolver el contenido actual de la ficha y agregar los dos botones**

En `excel_migrator.py`, `render_item_page()` construye hoy `parts` con: header, galería (si hay), accordion de propiedades, sección "Documentos y enlaces". Reestructurar así — el header/breadcrumb quedan igual, pero todo lo demás pasa a vivir dentro de `<div id="ficha-view">`, y se agrega el toggle y el contenedor del historial:

```python
def render_item_page(item: Item) -> str:
    parts = [
        f'<header class="page-header"><h1>{h(item.display_title)}</h1>',
        f'<p class="breadcrumb">'
        f'<a href="../index.html">Inicio</a> / '
        f'<a href="index.html">{h(item.category)}</a> / '
        f'<span>{h(item.tag)}</span></p>',
        '</header>',
    ]

    parts.append('<div class="view-toggle" role="tablist">')
    parts.append(
        '<button type="button" class="view-toggle-btn active" id="btn-ver-ficha" '
        'role="tab" aria-selected="true" aria-controls="ficha-view">Ver ficha técnica</button>'
    )
    parts.append(
        '<button type="button" class="view-toggle-btn" id="btn-ver-historial" '
        'role="tab" aria-selected="false" aria-controls="historial-view">'
        'Ver/agregar historial de mantenimiento</button>'
    )
    parts.append('</div>')

    parts.append('<div id="ficha-view" role="tabpanel">')

    # Galería de imágenes (si el TAG tiene)
    if item.images:
        img_urls = [
            f"../assets/images/{item.slug}/{fname}" for fname in item.images
        ]
        data_attr = json.dumps(img_urls).replace('"', '&quot;')
        n = len(item.images)
        label = "Ver imagen" if n == 1 else f"Ver {n} imágenes"
        thumb_src = img_urls[0]
        fallback = "../assets/icons/generic-image.svg"
        parts.append(
            f'<button class="gallery-btn" data-images="{data_attr}" '
            f'data-tag="{h(item.tag)}">'
            f'<img class="gallery-btn-thumb" src="{thumb_src}" alt="" '
            f'loading="lazy" '
            f'onerror="this.onerror=null;this.src=\'{fallback}\'">'
            f'<span class="gallery-btn-label">{label}</span></button>'
        )

    if item.properties:
        parts.append('<div class="accordion">')
        for label, value in item.properties.items():
            parts.append('<div class="acc-item">')
            parts.append(
                f'<button class="acc-header" aria-expanded="false">'
                f'<span class="acc-title">{h(label)}</span>'
                f'<span class="acc-chevron" aria-hidden="true">›</span></button>'
            )
            paragraphs = []
            for line in value.split("\n"):
                line = line.strip()
                if line:
                    paragraphs.append(f'<p>{h(line)}</p>')
            body = "\n".join(paragraphs) if paragraphs else '<p class="empty">—</p>'
            parts.append(f'<div class="acc-body">{body}</div></div>')
        parts.append('</div>')
    else:
        parts.append('<p class="empty">Esta ficha no tiene propiedades cargadas.</p>')

    resource_links = [
        (label, item.resources[col])
        for col, label in TAG_RESOURCES_COLUMNS
        if item.resources.get(col)
    ]
    if item.ficha_tecnica_url or item.curva_url or resource_links:
        parts.append('<section class="external-links">')
        parts.append('<h2>Documentos y enlaces</h2>')
        parts.append('<ul class="link-list">')
        if item.ficha_tecnica_url:
            parts.append(
                f'<li><a class="link-btn" href="{h(item.ficha_tecnica_url)}" '
                f'target="_blank" rel="noopener">Ficha Técnica ↗</a></li>'
            )
        if item.curva_url:
            parts.append(
                f'<li><a class="link-btn" href="{h(item.curva_url)}" '
                f'target="_blank" rel="noopener">Curva ↗</a></li>'
            )
        for label, url in resource_links:
            parts.append(
                f'<li><a class="link-btn" href="{h(url)}" '
                f'target="_blank" rel="noopener">{h(label)} ↗</a></li>'
            )
        parts.append('</ul></section>')

    parts.append('</div>')  # cierre ficha-view

    parts.append(
        f'<div id="historial-view" role="tabpanel" data-tag="{h(item.tag)}" hidden></div>'
    )

    return "\n".join(parts)
```

(`historial-view` queda vacío a propósito — todo su contenido lo arma `maintenance.js` en runtime, empezando en el Task 3.)

- [ ] **Step 2: Estilos del toggle en `maintenance.css`**

Replace the placeholder content of `maintenance.css` with:
```css
.view-toggle {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}

.view-toggle-btn {
    flex: 1;
    min-width: 200px;
    padding: 14px 16px;
    font-size: 0.95rem;
    font-weight: 600;
    border: 2px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text-muted);
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    min-height: 44px;
}

.view-toggle-btn:hover {
    border-color: var(--accent);
    color: var(--text);
}

.view-toggle-btn.active {
    border-color: var(--accent);
    background: var(--accent);
    color: #ffffff;
}

@media (max-width: 480px) {
    .view-toggle-btn {
        min-width: 100%;
    }
}
```

- [ ] **Step 3: JS mínimo para que el toggle funcione (placeholder de `maintenance.js`)**

Replace the placeholder content of `maintenance.js` with:
```javascript
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var btnFicha = document.getElementById('btn-ver-ficha');
        var btnHistorial = document.getElementById('btn-ver-historial');
        var fichaView = document.getElementById('ficha-view');
        var historialView = document.getElementById('historial-view');

        if (!btnFicha || !btnHistorial || !fichaView || !historialView) {
            // Página sin ficha de TAG (home o índice de categoría) — no hay nada que hacer acá.
            return;
        }

        function showFicha() {
            fichaView.hidden = false;
            historialView.hidden = true;
            btnFicha.classList.add('active');
            btnFicha.setAttribute('aria-selected', 'true');
            btnHistorial.classList.remove('active');
            btnHistorial.setAttribute('aria-selected', 'false');
        }

        function showHistorial() {
            fichaView.hidden = true;
            historialView.hidden = false;
            btnHistorial.classList.add('active');
            btnHistorial.setAttribute('aria-selected', 'true');
            btnFicha.classList.remove('active');
            btnFicha.setAttribute('aria-selected', 'false');
        }

        btnFicha.addEventListener('click', showFicha);
        btnHistorial.addEventListener('click', showHistorial);
    });
})();
```

- [ ] **Step 4: Verificación manual**

Run:
```bash
python3 excel_migrator.py plantilla_sitio.xlsx docs/
python3 -m http.server 8190 --directory docs/
```
Abrí `http://localhost:8190/equipos/<algún-tag>.html`. Expected: se ve la ficha técnica como siempre (comportamiento por defecto sin cambios), con los dos botones arriba, del mismo tamaño. Al tocar "Ver/agregar historial de mantenimiento" desaparece la ficha y aparece un área vacía (todavía sin contenido — se llena en el Task 3). Al volver a tocar "Ver ficha técnica" vuelve todo a la normalidad. Probá también con el emulador mobile de DevTools (F12 → toggle device toolbar) — los botones deben apilarse verticalmente en pantallas angostas.

- [ ] **Step 5: Commit**

```bash
git add excel_migrator.py maintenance.css maintenance.js
git commit -m "feat: toggle Ver ficha técnica / Ver historial de mantenimiento"
```

---

### Task 3: Cliente Supabase + login/logout + restauración de sesión

**Files:**
- Modify: `maintenance.js`
- Modify: `maintenance.css`

- [ ] **Step 1: Cliente Supabase + gating por sesión**

Replace the entire contents of `maintenance.js` with (mantiene el toggle del Task 2 y agrega todo lo de auth):
```javascript
(function () {
    'use strict';

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

    function renderError(container, message) {
        container.innerHTML =
            '<div class="maint-error">' + message + ' ' +
            '<button type="button" class="maint-btn maint-btn-secondary" data-action="retry">Reintentar</button>' +
            '</div>';
        var retryBtn = container.querySelector('[data-action="retry"]');
        if (retryBtn) {
            retryBtn.addEventListener('click', function () {
                initHistorialView(container, container.dataset.tag);
            });
        }
    }

    function renderLoginForm(container, tagId) {
        container.innerHTML =
            '<form class="maint-login-form" id="maint-login-form">' +
            '  <h2>Ingresá para ver o cargar el historial</h2>' +
            '  <label class="maint-field">Email' +
            '    <input type="email" name="email" required autocomplete="username">' +
            '  </label>' +
            '  <label class="maint-field">Contraseña' +
            '    <input type="password" name="password" required autocomplete="current-password">' +
            '  </label>' +
            '  <div class="maint-login-error" id="maint-login-error" hidden></div>' +
            '  <button type="submit" class="maint-btn maint-btn-primary">Ingresar</button>' +
            '</form>';

        var form = document.getElementById('maint-login-form');
        var errorBox = document.getElementById('maint-login-error');

        form.addEventListener('submit', function (evt) {
            evt.preventDefault();
            errorBox.hidden = true;
            var email = form.elements.email.value.trim();
            var password = form.elements.password.value;
            var submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Ingresando…';

            getClient().auth.signInWithPassword({ email: email, password: password })
                .then(function (result) {
                    if (result.error) {
                        throw result.error;
                    }
                    initHistorialView(container, tagId);
                })
                .catch(function (err) {
                    errorBox.textContent = 'No se pudo iniciar sesión: ' + err.message;
                    errorBox.hidden = false;
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Ingresar';
                });
        });
    }

    function renderLoggedInShell(container, tagId, session) {
        container.innerHTML =
            '<div class="maint-shell">' +
            '  <div class="maint-session-bar">' +
            '    <span class="maint-session-user"></span>' +
            '    <button type="button" class="maint-btn maint-btn-secondary" id="maint-logout">Cerrar sesión</button>' +
            '  </div>' +
            '  <div id="maint-historial-body">Cargando historial…</div>' +
            '</div>';

        container.querySelector('.maint-session-user').textContent = session.user.email;
        document.getElementById('maint-logout').addEventListener('click', function () {
            getClient().auth.signOut().then(function () {
                initHistorialView(container, tagId);
            });
        });

        return document.getElementById('maint-historial-body');
    }

    function initHistorialView(container, tagId) {
        container.innerHTML = '<p class="maint-loading">Cargando…</p>';
        var client;
        try {
            client = getClient();
        } catch (err) {
            renderError(container, err.message);
            return;
        }

        client.auth.getSession()
            .then(function (result) {
                if (result.error) throw result.error;
                var session = result.data.session;
                if (!session) {
                    renderLoginForm(container, tagId);
                    return;
                }
                var body = renderLoggedInShell(container, tagId, session);
                loadAndRenderRecords(body, tagId);
            })
            .catch(function (err) {
                renderError(container, 'No se pudo conectar con el historial: ' + err.message);
            });
    }

    // Placeholder hasta el Task 4 — se reemplaza por la carga real del historial.
    function loadAndRenderRecords(bodyContainer, tagId) {
        bodyContainer.textContent = 'Sesión iniciada. (Historial: implementado en el Task 4.)';
    }

    document.addEventListener('DOMContentLoaded', function () {
        var btnFicha = document.getElementById('btn-ver-ficha');
        var btnHistorial = document.getElementById('btn-ver-historial');
        var fichaView = document.getElementById('ficha-view');
        var historialView = document.getElementById('historial-view');

        if (!btnFicha || !btnHistorial || !fichaView || !historialView) {
            return;
        }

        var tagId = historialView.dataset.tag;
        var historialLoaded = false;

        function showFicha() {
            fichaView.hidden = false;
            historialView.hidden = true;
            btnFicha.classList.add('active');
            btnFicha.setAttribute('aria-selected', 'true');
            btnHistorial.classList.remove('active');
            btnHistorial.setAttribute('aria-selected', 'false');
        }

        function showHistorial() {
            fichaView.hidden = true;
            historialView.hidden = false;
            btnHistorial.classList.add('active');
            btnHistorial.setAttribute('aria-selected', 'true');
            btnFicha.classList.remove('active');
            btnFicha.setAttribute('aria-selected', 'false');
            if (!historialLoaded) {
                historialLoaded = true;
                initHistorialView(historialView, tagId);
            }
        }

        btnFicha.addEventListener('click', showFicha);
        btnHistorial.addEventListener('click', showHistorial);

        // Exponer para los tasks siguientes (Task 4+ reemplazan loadAndRenderRecords).
        window.__maintenanceInternals = window.__maintenanceInternals || {};
        window.__maintenanceInternals.getClient = getClient;
        window.__maintenanceInternals.initHistorialView = initHistorialView;
    });
})();
```

- [ ] **Step 2: Estilos de login/shell en `maintenance.css`**

Append to `maintenance.css`:
```css
.maint-login-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-width: 360px;
}

.maint-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.85rem;
    color: var(--text-muted);
}

.maint-field input {
    padding: 12px;
    font-size: 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    min-height: 44px;
}

.maint-btn {
    padding: 12px 20px;
    font-size: 0.95rem;
    font-weight: 600;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    min-height: 44px;
}

.maint-btn-primary {
    background: var(--accent);
    color: #ffffff;
}

.maint-btn-secondary {
    background: var(--bg-alt);
    color: var(--text);
    border: 1px solid var(--border);
}

.maint-login-error,
.maint-error {
    color: #b42318;
    font-size: 0.85rem;
}

.maint-session-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 8px;
}

.maint-session-user {
    font-size: 0.85rem;
    color: var(--text-muted);
}

.maint-loading {
    color: var(--text-muted);
}
```

- [ ] **Step 3: Verificación manual**

Prerequisito: en Supabase local (Plan 1) ya deberían existir los usuarios de test `tecnico@test.local` / `oficina@test.local` (contraseña `Test1234!`) creados por la suite de pytest. Si corriste `supabase db reset` después de esos tests, recreálos a mano una vez desde `http://127.0.0.1:54323` (Supabase Studio local) → Authentication → Add user, + una fila en la tabla `profiles`.

Run: `python3 excel_migrator.py plantilla_sitio.xlsx docs/` y `python3 -m http.server 8190 --directory docs/`.

Abrí una ficha, tocá "Ver/agregar historial de mantenimiento". Expected: aparece el formulario de login. Con credenciales inválidas, muestra el error debajo del form sin recargar la página. Con `tecnico@test.local` / `Test1234!`, entra y muestra "Sesión iniciada..." + el email arriba + botón "Cerrar sesión". Recargá la página (F5) y volvé a tocar "Ver/agregar historial" — **no debería pedir login de nuevo** (la sesión persiste, Supabase guarda el token en `localStorage` por defecto). Tocá "Cerrar sesión" y confirmá que vuelve a pedir login.

- [ ] **Step 4: Commit**

```bash
git add maintenance.js maintenance.css
git commit -m "feat: login/logout con Supabase Auth en la sección de historial"
```

---

### Task 4: Lectura del historial (records + comentarios + adjuntos + badge de anomalía)

**Files:**
- Modify: `maintenance.js`
- Modify: `maintenance.css`

- [ ] **Step 1: Reemplazar el placeholder `loadAndRenderRecords` por la carga real**

En `maintenance.js`, reemplazar la función `loadAndRenderRecords` (el placeholder del Task 3) por:
```javascript
    function formatDate(isoDate) {
        var parts = isoDate.split('-');
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    // El bucket es privado: no se puede usar getPublicUrl() para servir el archivo
    // directo. renderAttachment() pide una signed URL de corta duración en su lugar.
    function renderAttachment(client, attachment) {
        var wrapper = document.createElement('div');
        wrapper.className = 'maint-attachment';
        wrapper.textContent = 'Cargando adjunto…';

        client.storage.from('maintenance-attachments')
            .createSignedUrl(attachment.storage_path, 3600)
            .then(function (result) {
                if (result.error) throw result.error;
                var url = result.data.signedUrl;
                if (attachment.kind === 'photo') {
                    wrapper.innerHTML = '<img class="maint-attachment-thumb" src="' + url + '" alt="Foto del mantenimiento" loading="lazy">';
                } else {
                    wrapper.innerHTML = '<audio controls src="' + url + '"></audio>';
                }
            })
            .catch(function () {
                wrapper.textContent = 'No se pudo cargar el adjunto.';
            });

        return wrapper;
    }

    function renderRecord(client, record) {
        var el = document.createElement('article');
        el.className = 'maint-record';

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
            '<header class="maint-record-head">' +
            '  <span class="maint-record-date">' + formatDate(record.performed_at) + '</span>' +
            '  <span class="maint-record-type">' + (record.type === 'preventivo' ? 'Preventivo' : 'Correctivo') + '</span>' +
            badge +
            '</header>' +
            '<p class="maint-record-description">' + escapeHtml(record.description) + '</p>' +
            partsHtml + nextHtml +
            '<div class="maint-record-comments"></div>' +
            '<div class="maint-record-attachments"></div>' +
            '<div class="maint-record-add"></div>';

        var commentsBox = el.querySelector('.maint-record-comments');
        (record.maintenance_comments || [])
            .slice()
            .sort(function (a, b) { return a.created_at.localeCompare(b.created_at); })
            .forEach(function (comment) {
                var p = document.createElement('p');
                p.className = 'maint-comment';
                p.textContent = comment.body;
                commentsBox.appendChild(p);
            });

        var attachmentsBox = el.querySelector('.maint-record-attachments');
        (record.maintenance_attachments || []).forEach(function (attachment) {
            attachmentsBox.appendChild(renderAttachment(client, attachment));
        });

        return el;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function loadAndRenderRecords(bodyContainer, tagId) {
        bodyContainer.innerHTML = '<p class="maint-loading">Cargando historial…</p>';
        var client = getClient();

        client
            .from('maintenance_records')
            .select('*, maintenance_comments(*), maintenance_attachments(*)')
            .eq('tag_id', tagId)
            .order('performed_at', { ascending: false })
            .then(function (result) {
                if (result.error) throw result.error;
                renderHistorialBody(bodyContainer, tagId, client, result.data);
            })
            .catch(function (err) {
                renderError(bodyContainer, 'No se pudo cargar el historial: ' + err.message);
            });
    }

    function renderHistorialBody(bodyContainer, tagId, client, records) {
        bodyContainer.innerHTML = '';

        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'maint-btn maint-btn-primary maint-add-record-btn';
        addBtn.textContent = '+ Registrar mantenimiento';
        bodyContainer.appendChild(addBtn);

        var formSlot = document.createElement('div');
        formSlot.className = 'maint-form-slot';
        bodyContainer.appendChild(formSlot);

        addBtn.addEventListener('click', function () {
            // Implementado en el Task 5 (renderNewRecordForm).
            if (window.__maintenanceInternals.renderNewRecordForm) {
                window.__maintenanceInternals.renderNewRecordForm(formSlot, tagId, function () {
                    loadAndRenderRecords(bodyContainer, tagId);
                });
            }
        });

        if (records.length === 0) {
            var empty = document.createElement('p');
            empty.className = 'maint-empty';
            empty.textContent = 'Todavía no hay mantenimientos registrados para este equipo.';
            bodyContainer.appendChild(empty);
            return;
        }

        var list = document.createElement('div');
        list.className = 'maint-list';
        records.forEach(function (record) {
            list.appendChild(renderRecord(client, record));
        });
        bodyContainer.appendChild(list);
    }
```

- [ ] **Step 2: Exponer `escapeHtml`/`loadAndRenderRecords` para reutilizar en el Task 5**

Dentro del bloque `document.addEventListener('DOMContentLoaded', ...)`, en la sección donde ya se setea `window.__maintenanceInternals`, agregar:
```javascript
        window.__maintenanceInternals.loadAndRenderRecords = loadAndRenderRecords;
        window.__maintenanceInternals.escapeHtml = escapeHtml;
```

- [ ] **Step 3: Estilos de la lista de historial**

Append to `maintenance.css`:
```css
.maint-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 16px;
}

.maint-record {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    background: var(--bg);
}

.maint-record-head {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 6px;
}

.maint-record-date {
    font-weight: 700;
}

.maint-record-type {
    font-size: 0.8rem;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--bg-alt);
    color: var(--text-muted);
}

.maint-badge-anomaly {
    font-size: 0.8rem;
    color: #b42318;
    font-weight: 600;
}

.maint-record-description {
    margin: 6px 0;
}

.maint-record-parts,
.maint-record-next {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin: 2px 0;
}

.maint-comment {
    font-size: 0.9rem;
    padding: 6px 10px;
    background: var(--bg-alt);
    border-radius: 8px;
    margin: 4px 0;
}

.maint-record-attachments {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
}

.maint-attachment-thumb {
    width: 72px;
    height: 72px;
    object-fit: cover;
    border-radius: 8px;
    cursor: pointer;
}

.maint-add-record-btn {
    margin-bottom: 8px;
}

.maint-empty {
    color: var(--text-muted);
}
```

- [ ] **Step 4: Verificación manual**

Con la suite de Supabase local corriendo, insertar a mano (desde Supabase Studio → Table Editor, o vía SQL) un `maintenance_records` de prueba para un TAG real del sitio, con un comentario y un adjunto (subí cualquier imagen chica al bucket `maintenance-attachments` desde Studio y copiá el path). Regenerá el sitio, abrí la ficha de ese TAG, logueate, y confirmá: el evento aparece con fecha/tipo/descripción, el comentario debajo, la foto como thumbnail clickeable (se abre la imagen real vía signed URL). Insertá un registro con `performed_at` 10 días atrás y confirmá que aparece el badge ⚠️.

- [ ] **Step 5: Commit**

```bash
git add maintenance.js maintenance.css
git commit -m "feat: lectura del historial (records, comentarios, adjuntos, badge de anomalía)"
```

---

### Task 5: Formulario de carga — nuevo registro (texto + fotos comprimidas + audio)

**Files:**
- Modify: `maintenance.js`
- Modify: `maintenance.css`

- [ ] **Step 1: Helpers de compresión de fotos y grabación de audio**

Append to `maintenance.js` (antes del `document.addEventListener('DOMContentLoaded', ...)` final):
```javascript
    var MAX_ATTACHMENTS = 5;
    var MAX_AUDIO_SECONDS = 60;
    var DRAFT_KEY_PREFIX = 'maint-draft-';

    function compressImage(file) {
        return new Promise(function (resolve, reject) {
            var img = new Image();
            var reader = new FileReader();
            reader.onerror = reject;
            reader.onload = function () {
                img.onerror = reject;
                img.onload = function () {
                    var maxWidth = 1600;
                    var scale = Math.min(1, maxWidth / img.width);
                    var canvas = document.createElement('canvas');
                    canvas.width = Math.round(img.width * scale);
                    canvas.height = Math.round(img.height * scale);
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    canvas.toBlob(
                        function (blob) {
                            if (!blob) { reject(new Error('No se pudo comprimir la imagen')); return; }
                            resolve(blob);
                        },
                        'image/jpeg',
                        0.7
                    );
                };
                img.src = reader.result;
            };
            reader.readAsDataURL(file);
        });
    }

    function createAudioRecorder(onStop) {
        var recorder = null;
        var chunks = [];
        var timerId = null;
        var secondsElapsed = 0;

        function start(onTick) {
            return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
                chunks = [];
                secondsElapsed = 0;
                recorder = new MediaRecorder(stream);
                recorder.ondataavailable = function (e) {
                    if (e.data && e.data.size > 0) chunks.push(e.data);
                };
                recorder.onstop = function () {
                    stream.getTracks().forEach(function (track) { track.stop(); });
                    clearInterval(timerId);
                    var blob = new Blob(chunks, { type: 'audio/webm' });
                    onStop(blob);
                };
                recorder.start();
                timerId = setInterval(function () {
                    secondsElapsed += 1;
                    if (onTick) onTick(secondsElapsed);
                    if (secondsElapsed >= MAX_AUDIO_SECONDS) {
                        stop();
                    }
                }, 1000);
            });
        }

        function stop() {
            if (recorder && recorder.state !== 'inactive') {
                recorder.stop();
            }
        }

        return { start: start, stop: stop };
    }

    function saveDraft(tagId, fields) {
        try {
            localStorage.setItem(DRAFT_KEY_PREFIX + tagId, JSON.stringify(fields));
        } catch (e) { /* localStorage lleno o deshabilitado: el draft es best-effort, no bloquea */ }
    }

    function loadDraft(tagId) {
        try {
            var raw = localStorage.getItem(DRAFT_KEY_PREFIX + tagId);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function clearDraft(tagId) {
        try {
            localStorage.removeItem(DRAFT_KEY_PREFIX + tagId);
        } catch (e) { /* no-op */ }
    }
```

**Nota sobre el draft:** solo persiste los campos de texto (fecha, tipo, descripción, repuestos, próximo programado) — los archivos adjuntos (fotos/audio) quedan en memoria (`pendingAttachments`, Step 2) y **no sobreviven un F5**. Esto cubre el caso principal del spec ("no perder lo escrito" ante un fallo de red durante el submit, sin recargar la página); un recargado accidental de página sí obliga a re-adjuntar fotos/audio — es una limitación aceptada, no vale la pena un IndexedDB solo para eso.

- [ ] **Step 2: El formulario en sí (`renderNewRecordForm`)**

Append to `maintenance.js` (después de los helpers del Step 1):
```javascript
    function uploadPendingAttachment(client, tagId, recordId, pending) {
        var ext = pending.kind === 'photo' ? 'jpg' : 'webm';
        var path = tagId + '/' + recordId + '/' + Date.now() + '-' + Math.random().toString(36).slice(2) + '.' + ext;

        return client.storage.from('maintenance-attachments').upload(path, pending.blob).then(function (result) {
            if (result.error) throw result.error;
            return client.from('maintenance_attachments').insert({
                record_id: recordId,
                kind: pending.kind,
                storage_path: path,
            });
        }).then(function (result) {
            if (result.error) throw result.error;
        });
    }

    function uploadAllAttachments(client, tagId, recordId, pendingList, statusEl) {
        var results = pendingList.map(function () { return null; });

        function uploadOne(index) {
            if (index >= pendingList.length) return Promise.resolve();
            statusEl.textContent = 'Subiendo adjunto ' + (index + 1) + ' de ' + pendingList.length + '…';
            return uploadPendingAttachment(client, tagId, recordId, pendingList[index])
                .then(function () {
                    results[index] = 'ok';
                    return uploadOne(index + 1);
                })
                .catch(function (err) {
                    results[index] = 'error: ' + err.message;
                    return uploadOne(index + 1);
                });
        }

        return uploadOne(0).then(function () { return results; });
    }

    function renderNewRecordForm(container, tagId, onDone) {
        var draft = loadDraft(tagId) || {};
        var pendingAttachments = []; // [{kind: 'photo'|'audio', blob: Blob}]

        container.innerHTML =
            '<form class="maint-form" id="maint-new-record-form">' +
            '  <label class="maint-field">Fecha del mantenimiento' +
            '    <input type="date" name="performed_at" required>' +
            '  </label>' +
            '  <fieldset class="maint-field">' +
            '    <legend>Tipo</legend>' +
            '    <label class="maint-radio"><input type="radio" name="type" value="preventivo" required> Preventivo</label>' +
            '    <label class="maint-radio"><input type="radio" name="type" value="correctivo"> Correctivo</label>' +
            '  </fieldset>' +
            '  <label class="maint-field">Descripción' +
            '    <textarea name="description" required rows="3"></textarea>' +
            '  </label>' +
            '  <label class="maint-field">Repuestos / insumos (opcional)' +
            '    <textarea name="parts_used" rows="2"></textarea>' +
            '  </label>' +
            '  <label class="maint-field">Próximo mantenimiento programado (opcional)' +
            '    <input type="date" name="next_scheduled_at">' +
            '  </label>' +
            '  <div class="maint-attachments-editor">' +
            '    <div class="maint-attachments-preview" id="maint-attachments-preview"></div>' +
            '    <div class="maint-attachments-actions">' +
            '      <label class="maint-btn maint-btn-secondary maint-file-btn">' +
            '        📷 Agregar foto' +
            '        <input type="file" accept="image/*" capture="environment" id="maint-photo-input" hidden>' +
            '      </label>' +
            '      <button type="button" class="maint-btn maint-btn-secondary" id="maint-audio-btn">🎙️ Grabar audio</button>' +
            '    </div>' +
            '  </div>' +
            '  <div class="maint-form-error" id="maint-form-error" hidden></div>' +
            '  <div class="maint-form-status" id="maint-form-status"></div>' +
            '  <div class="maint-form-buttons">' +
            '    <button type="submit" class="maint-btn maint-btn-primary">Guardar</button>' +
            '    <button type="button" class="maint-btn maint-btn-secondary" id="maint-cancel-btn">Cancelar</button>' +
            '  </div>' +
            '</form>';

        var form = document.getElementById('maint-new-record-form');
        form.elements.performed_at.value = draft.performed_at || new Date().toISOString().slice(0, 10);
        if (draft.type) form.elements.type.value = draft.type;
        form.elements.description.value = draft.description || '';
        form.elements.parts_used.value = draft.parts_used || '';
        form.elements.next_scheduled_at.value = draft.next_scheduled_at || '';

        function currentFields() {
            return {
                performed_at: form.elements.performed_at.value,
                type: form.elements.type.value,
                description: form.elements.description.value,
                parts_used: form.elements.parts_used.value,
                next_scheduled_at: form.elements.next_scheduled_at.value,
            };
        }

        Array.prototype.forEach.call(form.elements, function (el) {
            if (el.name) el.addEventListener('input', function () { saveDraft(tagId, currentFields()); });
        });

        var preview = document.getElementById('maint-attachments-preview');
        var photoInput = document.getElementById('maint-photo-input');
        var audioBtn = document.getElementById('maint-audio-btn');
        var errorBox = document.getElementById('maint-form-error');
        var statusBox = document.getElementById('maint-form-status');

        function attachmentsFull() {
            return pendingAttachments.length >= MAX_ATTACHMENTS;
        }

        function renderPreview() {
            preview.innerHTML = '';
            pendingAttachments.forEach(function (item, idx) {
                var chip = document.createElement('span');
                chip.className = 'maint-attachment-chip';
                chip.textContent = (item.kind === 'photo' ? '📷 foto' : '🎙️ audio') + ' ';
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.textContent = '✕';
                removeBtn.addEventListener('click', function () {
                    pendingAttachments.splice(idx, 1);
                    renderPreview();
                });
                chip.appendChild(removeBtn);
                preview.appendChild(chip);
            });
            photoInput.disabled = attachmentsFull();
            audioBtn.disabled = attachmentsFull();
        }

        photoInput.addEventListener('change', function () {
            var file = photoInput.files[0];
            photoInput.value = '';
            if (!file || attachmentsFull()) return;
            compressImage(file).then(function (blob) {
                pendingAttachments.push({ kind: 'photo', blob: blob });
                renderPreview();
            }).catch(function (err) {
                errorBox.textContent = 'No se pudo procesar la foto: ' + err.message;
                errorBox.hidden = false;
            });
        });

        var recorder = null;
        var recording = false;
        audioBtn.addEventListener('click', function () {
            if (attachmentsFull()) return;
            if (recording) return;
            recording = true;
            audioBtn.textContent = '⏺ Grabando… (0s)';
            recorder = createAudioRecorder(function (blob) {
                pendingAttachments.push({ kind: 'audio', blob: blob });
                renderPreview();
                recording = false;
                audioBtn.textContent = '🎙️ Grabar audio';
            });
            recorder.start(function (seconds) {
                audioBtn.textContent = '⏺ Grabando… (' + seconds + 's) — tocar para detener';
            }).catch(function (err) {
                recording = false;
                audioBtn.textContent = '🎙️ Grabar audio';
                errorBox.textContent = 'No se pudo acceder al micrófono: ' + err.message;
                errorBox.hidden = false;
            });
            audioBtn.onclick = function () {
                if (recording && recorder) {
                    recorder.stop();
                }
            };
        });

        document.getElementById('maint-cancel-btn').addEventListener('click', function () {
            container.innerHTML = '';
        });

        renderPreview();

        form.addEventListener('submit', function (evt) {
            evt.preventDefault();
            errorBox.hidden = true;

            if (!form.elements.type.value) {
                errorBox.textContent = 'Elegí el tipo de mantenimiento.';
                errorBox.hidden = false;
                return;
            }

            var fields = currentFields();
            saveDraft(tagId, fields);

            var submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            statusBox.textContent = 'Guardando registro…';

            var client = getClient();
            var payload = {
                tag_id: tagId,
                performed_at: fields.performed_at,
                type: fields.type,
                description: fields.description,
                parts_used: fields.parts_used || null,
                next_scheduled_at: fields.next_scheduled_at || null,
            };

            client.from('maintenance_records').insert(payload).select().then(function (result) {
                if (result.error) throw result.error;
                var recordId = result.data[0].id;
                return uploadAllAttachments(client, tagId, recordId, pendingAttachments, statusBox);
            }).then(function (uploadResults) {
                var failed = (uploadResults || []).filter(function (r) { return r !== 'ok'; });
                clearDraft(tagId);
                if (failed.length > 0) {
                    statusBox.textContent = 'Registro guardado, pero ' + failed.length + ' adjunto(s) no se pudieron subir. Podés agregarlos después desde "Agregar comentario/adjunto".';
                } else {
                    statusBox.textContent = 'Registro guardado.';
                }
                submitBtn.disabled = false;
                setTimeout(function () { onDone(); }, 800);
            }).catch(function (err) {
                submitBtn.disabled = false;
                statusBox.textContent = '';
                errorBox.textContent = 'No se pudo guardar (los datos siguen en el formulario): ' + err.message;
                errorBox.hidden = false;
            });
        });
    }
```

- [ ] **Step 3: Exponer `renderNewRecordForm`**

Dentro de `document.addEventListener('DOMContentLoaded', ...)`, junto a los otros `window.__maintenanceInternals.*`, agregar:
```javascript
        window.__maintenanceInternals.renderNewRecordForm = renderNewRecordForm;
```

- [ ] **Step 4: Estilos del formulario**

Append to `maintenance.css`:
```css
.maint-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    margin-top: 12px;
    background: var(--bg);
}

.maint-form textarea {
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font: inherit;
    resize: vertical;
}

.maint-radio {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-right: 16px;
    font-size: 0.95rem;
}

.maint-attachments-editor {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.maint-attachments-preview {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.maint-attachment-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    background: var(--bg-alt);
    border-radius: 999px;
    font-size: 0.85rem;
}

.maint-attachment-chip button {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 0.9rem;
}

.maint-attachments-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.maint-file-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
}

.maint-form-buttons {
    display: flex;
    gap: 8px;
}

.maint-form-status {
    font-size: 0.85rem;
    color: var(--text-muted);
    min-height: 1.2em;
}
```

- [ ] **Step 5: Verificación manual**

Con el emulador mobile de DevTools (o un celular real en la misma red que el `http.server`), logueate como `tecnico@test.local`, tocá "+ Registrar mantenimiento", completá el formulario, agregá una foto (con la cámara si estás en celular real) y grabá una nota de audio corta. Confirmá: el contador de segundos se actualiza mientras grabás, se corta solo a los 60s si no la parás antes, el botón de agregar foto/audio se deshabilita al llegar a 5 adjuntos, y al guardar aparece el nuevo registro en la lista con la foto y el audio reproducibles. Con DevTools → Network → Offline activado antes de tocar "Guardar", confirmá que el error se muestra y **el formulario sigue completo** (no se resetea).

- [ ] **Step 6: Commit**

```bash
git add maintenance.js maintenance.css
git commit -m "feat: formulario de carga de mantenimiento (fotos comprimidas + audio)"
```

---

### Task 6: Agregar comentario/adjunto a un evento propio ya cargado

**Files:**
- Modify: `maintenance.js`
- Modify: `maintenance.css`

- [ ] **Step 1: Botón "+ Agregar comentario/adjunto" por evento propio**

En `maintenance.js`, dentro de `renderRecord(client, record)` (Task 4), el `el.innerHTML` ya incluye `'<div class="maint-record-add"></div>'` como contenedor vacío — no hace falta tocar esa parte. Agregar el siguiente bloque **después** del `.forEach` que llena `attachmentsBox`, y **antes** del `return el;` final de la función:
```javascript
        var addBox = el.querySelector('.maint-record-add');
        client.auth.getSession().then(function (result) {
            var session = result.data.session;
            if (session && session.user.id === record.created_by) {
                var addLink = document.createElement('button');
                addLink.type = 'button';
                addLink.className = 'maint-btn maint-btn-secondary maint-add-comment-btn';
                addLink.textContent = '+ Agregar comentario/adjunto';
                addLink.addEventListener('click', function () {
                    renderAddCommentForm(client, record, addBox, addLink);
                });
                addBox.appendChild(addLink);
            }
        });
```

- [ ] **Step 2: El mini-formulario de comentario/adjunto**

Append to `maintenance.js` (después de `renderNewRecordForm`, antes del `document.addEventListener` final):
```javascript
    function renderAddCommentForm(client, record, container, triggerBtn) {
        triggerBtn.hidden = true;
        var pendingAttachments = [];
        var currentCount = (record.maintenance_attachments || []).length;

        var formEl = document.createElement('form');
        formEl.className = 'maint-form maint-comment-form';
        formEl.innerHTML =
            '<label class="maint-field">Comentario' +
            '  <textarea name="body" rows="2"></textarea>' +
            '</label>' +
            '<div class="maint-attachments-preview"></div>' +
            '<div class="maint-attachments-actions">' +
            '  <label class="maint-btn maint-btn-secondary maint-file-btn">📷 Agregar foto' +
            '    <input type="file" accept="image/*" capture="environment" hidden>' +
            '  </label>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" data-action="audio">🎙️ Grabar audio</button>' +
            '</div>' +
            '<div class="maint-form-error" hidden></div>' +
            '<div class="maint-form-status"></div>' +
            '<div class="maint-form-buttons">' +
            '  <button type="submit" class="maint-btn maint-btn-primary">Agregar</button>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" data-action="cancel">Cancelar</button>' +
            '</div>';
        container.appendChild(formEl);

        var preview = formEl.querySelector('.maint-attachments-preview');
        var photoInput = formEl.querySelector('input[type="file"]');
        var audioBtn = formEl.querySelector('[data-action="audio"]');
        var errorBox = formEl.querySelector('.maint-form-error');
        var statusBox = formEl.querySelector('.maint-form-status');

        function remainingSlots() {
            return MAX_ATTACHMENTS - currentCount - pendingAttachments.length;
        }

        function renderPreview() {
            preview.innerHTML = '';
            pendingAttachments.forEach(function (item, idx) {
                var chip = document.createElement('span');
                chip.className = 'maint-attachment-chip';
                chip.textContent = (item.kind === 'photo' ? '📷 foto' : '🎙️ audio') + ' ';
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.textContent = '✕';
                removeBtn.addEventListener('click', function () {
                    pendingAttachments.splice(idx, 1);
                    renderPreview();
                });
                chip.appendChild(removeBtn);
                preview.appendChild(chip);
            });
            var full = remainingSlots() <= 0;
            photoInput.disabled = full;
            audioBtn.disabled = full;
        }

        photoInput.addEventListener('change', function () {
            var file = photoInput.files[0];
            photoInput.value = '';
            if (!file || remainingSlots() <= 0) return;
            compressImage(file).then(function (blob) {
                pendingAttachments.push({ kind: 'photo', blob: blob });
                renderPreview();
            });
        });

        var recorder = null;
        var recording = false;
        audioBtn.addEventListener('click', function () {
            if (remainingSlots() <= 0 || recording) return;
            recording = true;
            audioBtn.textContent = '⏺ Grabando… (0s)';
            recorder = createAudioRecorder(function (blob) {
                pendingAttachments.push({ kind: 'audio', blob: blob });
                renderPreview();
                recording = false;
                audioBtn.textContent = '🎙️ Grabar audio';
            });
            recorder.start(function (seconds) {
                audioBtn.textContent = '⏺ Grabando… (' + seconds + 's) — tocar para detener';
            });
            audioBtn.onclick = function () {
                if (recording && recorder) recorder.stop();
            };
        });

        formEl.querySelector('[data-action="cancel"]').addEventListener('click', function () {
            formEl.remove();
            triggerBtn.hidden = false;
        });

        formEl.addEventListener('submit', function (evt) {
            evt.preventDefault();
            var body = formEl.elements.body.value.trim();
            if (!body && pendingAttachments.length === 0) {
                errorBox.textContent = 'Agregá un comentario o al menos un adjunto.';
                errorBox.hidden = false;
                return;
            }
            errorBox.hidden = true;
            var submitBtn = formEl.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            statusBox.textContent = 'Guardando…';

            var chain = Promise.resolve();
            if (body) {
                chain = client.from('maintenance_comments').insert({ record_id: record.id, body: body }).then(function (result) {
                    if (result.error) throw result.error;
                });
            }
            chain.then(function () {
                return uploadAllAttachments(client, record.tag_id, record.id, pendingAttachments, statusBox);
            }).then(function () {
                statusBox.textContent = 'Guardado.';
                setTimeout(function () {
                    var recordEl = formEl.closest('.maint-record');
                    var bodyContainer = recordEl ? recordEl.closest('#maint-historial-body') : null;
                    if (bodyContainer) {
                        loadAndRenderRecords(bodyContainer, record.tag_id);
                    }
                }, 500);
            }).catch(function (err) {
                submitBtn.disabled = false;
                statusBox.textContent = '';
                errorBox.textContent = 'No se pudo guardar: ' + err.message;
                errorBox.hidden = false;
            });
        });
    }
```

- [ ] **Step 3: Estilos**

Append to `maintenance.css`:
```css
.maint-add-comment-btn {
    margin-top: 8px;
}

.maint-comment-form {
    margin-top: 10px;
}
```

- [ ] **Step 4: Verificación manual**

Logueado como `tecnico@test.local`, en un evento creado por ese mismo usuario, confirmá que aparece "+ Agregar comentario/adjunto". Agregá un comentario de texto solo → aparece debajo del original sin tocarlo. Agregá una foto sin texto → aparece como adjunto nuevo. Deslogueate y entrá como `oficina@test.local`: en ese mismo evento (que no le pertenece) el botón de agregar **no debería aparecer** para oficina tampoco (el spec no le pidió esa función a oficina vía sitio — oficina edita/borra desde `gui.py`, Plan 3). Confirmá también que en eventos ajenos al técnico logueado, el botón no aparece.

- [ ] **Step 5: Commit**

```bash
git add maintenance.js maintenance.css
git commit -m "feat: agregar comentario/adjunto a un evento propio"
```

---

### Task 7: Sesión expirada a mitad de carga + verificación de aislamiento de errores

**Files:**
- Modify: `maintenance.js`

- [ ] **Step 1: Detectar 401 en el submit del formulario nuevo y pedir re-login sin perder los datos**

En `maintenance.js`, dentro de `renderNewRecordForm`, en el `.catch(function (err) { ... })` del listener de `submit` (Task 5), reemplazar el cuerpo del catch por:
```javascript
            }).catch(function (err) {
                submitBtn.disabled = false;
                statusBox.textContent = '';
                if (err.status === 401 || (err.message && err.message.toLowerCase().indexOf('jwt') !== -1)) {
                    showReloginModal(function () {
                        form.dispatchEvent(new Event('submit', { cancelable: true }));
                    });
                    return;
                }
                errorBox.textContent = 'No se pudo guardar (los datos siguen en el formulario): ' + err.message;
                errorBox.hidden = false;
            });
```

- [ ] **Step 2: Modal de re-login**

Append to `maintenance.js` (junto a los otros helpers, antes de `renderNewRecordForm` o después — cualquier lugar a nivel de módulo dentro del IIFE):
```javascript
    function showReloginModal(onSuccess) {
        var overlay = document.createElement('div');
        overlay.className = 'maint-modal-overlay';
        overlay.innerHTML =
            '<div class="maint-modal">' +
            '  <h3>Tu sesión expiró</h3>' +
            '  <p>Iniciá sesión de nuevo — lo que ya escribiste no se pierde.</p>' +
            '  <form id="maint-relogin-form">' +
            '    <label class="maint-field">Email<input type="email" name="email" required></label>' +
            '    <label class="maint-field">Contraseña<input type="password" name="password" required></label>' +
            '    <div class="maint-login-error" hidden></div>' +
            '    <button type="submit" class="maint-btn maint-btn-primary">Ingresar</button>' +
            '  </form>' +
            '</div>';
        document.body.appendChild(overlay);

        var form = overlay.querySelector('#maint-relogin-form');
        var errorBox = overlay.querySelector('.maint-login-error');
        form.addEventListener('submit', function (evt) {
            evt.preventDefault();
            errorBox.hidden = true;
            getClient().auth.signInWithPassword({
                email: form.elements.email.value.trim(),
                password: form.elements.password.value,
            }).then(function (result) {
                if (result.error) throw result.error;
                overlay.remove();
                onSuccess();
            }).catch(function (err) {
                errorBox.textContent = err.message;
                errorBox.hidden = false;
            });
        });
    }
```

- [ ] **Step 3: Estilos del modal**

Append to `maintenance.css`:
```css
.maint-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 16px;
}

.maint-modal {
    background: var(--bg);
    border-radius: 12px;
    padding: 20px;
    max-width: 360px;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.maint-modal form {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
```

- [ ] **Step 4: Verificación manual — sesión expirada**

En Supabase Studio local, bajá el `JWT expiry` del proyecto a un valor bajo (o simplemente esperá a que expire un access token de corta duración en un entorno de test), completá el formulario de carga, dejalo pasar hasta que expire, y tocá "Guardar". Expected: aparece el modal de re-login (no se pierde lo escrito), y al loguearte de nuevo el submit se reintenta solo.

- [ ] **Step 5: Verificación manual — aislamiento de errores (Supabase caído)**

Con DevTools → Network → bloqueá manualmente las requests a tu `SUPABASE_URL` (o apagá `supabase stop` temporalmente), recargá la ficha y tocá "Ver/agregar historial de mantenimiento". Expected: la sección de historial muestra "No se pudo conectar con el historial: ..." con botón "Reintentar" — **el resto de la ficha (specs, documentos, imágenes) sigue funcionando normal**, incluida la navegación por el sidebar.

- [ ] **Step 6: Commit**

```bash
git add maintenance.js maintenance.css
git commit -m "feat: modal de re-login ante sesión expirada durante el submit"
```

---

### Task 8: Checklist final de verificación mobile + documentación

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Checklist manual completo (mobile-first)**

Con DevTools → device toolbar en un perfil de celular (ej. iPhone SE o Galaxy S8, los más angostos disponibles) y, si hay uno a mano, un celular real en la misma red Wi-Fi que la PC (`python3 -m http.server 8190 --bind 0.0.0.0 --directory docs/`, y abrir `http://<ip-de-la-pc>:8190/...` desde el celular):

- [ ] Los dos botones del toggle se ven completos y apilados verticalmente en pantallas angostas (<480px).
- [ ] El formulario de login es usable con el teclado del celular (los `<label>` asocian bien con los inputs, el teclado no tapa el botón de submit).
- [ ] Tocar "📷 Agregar foto" abre la cámara nativa directo (gracias a `capture="environment"`), no un selector de archivos genérico.
- [ ] Grabar audio pide permiso de micrófono la primera vez, el contador de segundos se ve mientras graba, corta solo a los 60s.
- [ ] Con Network throttling en "Slow 3G", cargar el historial muestra el estado de carga y no se cuelga sin feedback.
- [ ] Todos los botones tienen un área táctil cómoda (no hace falta hacer zoom para tocarlos).

- [ ] **Step 2: Documentar en `CLAUDE.md`**

Agregar en la tabla "Estado de archivos":
```markdown
| [maintenance.js](maintenance.js), [maintenance.css](maintenance.css) | ✅ Histórico de mantenimientos (Plan 2) — cliente Supabase, login, lectura/carga de historial, fotos+audio |
```

Y agregar una sección nueva (después de "## Configuración (`site_config.json`)"):
```markdown
## Histórico de mantenimientos (Supabase)

Ver [docs/superpowers/specs/2026-09-20-historico-mantenimientos-design.md](docs/superpowers/specs/2026-09-20-historico-mantenimientos-design.md) para el diseño completo. Resumen operativo:

- Todo el código vive en `maintenance.js`/`maintenance.css` (no en `excel_migrator.py` — ese archivo solo inyecta la config y los `<link>/<script>` tags).
- La config de conexión (`url`/`anon_key`) vive en `site_config.json` → bloque `supabase`. La `anon_key` es pública a propósito (protegida por RLS), pero la `service_role key` **nunca** va acá ni al repo.
- Schema, RLS, triggers de auditoría y Storage: ver `supabase/migrations/` (Plan 1 del feature).
- Para desarrollar/probar local: `supabase start` (requiere Docker) y usar la URL/key que imprime, no las de producción.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: documentar integración de Supabase en el sitio"
```
