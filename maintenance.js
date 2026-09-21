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

    function formatDate(isoDate) {
        var parts = isoDate.split('-');
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
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
                wrapper.textContent = '';
                if (attachment.kind === 'photo') {
                    var link = document.createElement('a');
                    link.href = url;
                    link.target = '_blank';
                    link.rel = 'noopener';
                    var img = document.createElement('img');
                    img.className = 'maint-attachment-thumb';
                    img.alt = 'Foto del mantenimiento';
                    img.loading = 'lazy';
                    img.src = url;
                    link.appendChild(img);
                    wrapper.appendChild(link);
                } else {
                    var audio = document.createElement('audio');
                    audio.controls = true;
                    audio.src = url;
                    wrapper.appendChild(audio);
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
            // Se implementa en el Task 5 (renderNewRecordForm).
            if (typeof renderNewRecordForm === 'function') {
                renderNewRecordForm(formSlot, tagId, function () {
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
