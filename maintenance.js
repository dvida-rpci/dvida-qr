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
            '<div class="maint-error"></div>';
        var box = container.querySelector('.maint-error');
        box.textContent = message + ' ';
        var retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'maint-btn maint-btn-secondary';
        retryBtn.textContent = 'Reintentar';
        retryBtn.addEventListener('click', function () {
            initHistorialView(container.closest('#historial-view') || container, container.closest('#historial-view').dataset.tag);
        });
        box.appendChild(retryBtn);
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
            // Página sin ficha de TAG (home o índice de categoría) — no hay nada que hacer acá.
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
    });
})();
