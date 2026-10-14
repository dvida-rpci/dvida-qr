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
            '  <h2>Ingresá para cargar mantenimientos</h2>' +
            '  <label class="maint-field">Email' +
            '    <input type="email" name="email" required autocomplete="username">' +
            '  </label>' +
            '  <label class="maint-field">Contraseña' +
            '    <input type="password" name="password" required autocomplete="current-password">' +
            '  </label>' +
            '  <div class="maint-login-error" id="maint-login-error" hidden></div>' +
            '  <button type="submit" class="maint-btn maint-btn-primary">Ingresar</button>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" id="maint-login-cancel">Cancelar</button>' +
            '</form>';

        var form = document.getElementById('maint-login-form');
        var errorBox = document.getElementById('maint-login-error');
        document.getElementById('maint-login-cancel').addEventListener('click', function () {
            initHistorialView(container, tagId);
        });

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

    // ── Plan de mantenimiento: agenda, rol, actividades y advertencias ──────
    // Lógica pura en maintenance_agenda.js (window.MaintAgenda).

    var Agenda = window.MaintAgenda;
    // Actividad pedida con ?hecho= en la URL ('' = mantenimiento libre); null = nada pendiente.
    var pendingDone = typeof window !== 'undefined' && window.location
        ? new URLSearchParams(window.location.search).get('hecho')
        : null;

    function fetchAgenda(client, tagId) {
        return client.from('maintenance_agenda').select('*').eq('tag_id', tagId).then(function (result) {
            if (result.error) throw result.error;
            return result.data;
        });
    }

    // Rol del usuario con sesión ('oficina' | 'tecnico'), o null sin sesión/perfil.
    function fetchRole(client) {
        return client.auth.getSession().then(function (result) {
            var session = result.data && result.data.session;
            if (!session) return null;
            return client.from('profiles').select('role').eq('user_id', session.user.id).then(function (r) {
                return r.data && r.data[0] ? r.data[0].role : null;
            });
        });
    }

    function fetchTagActivities(client, tagId) {
        return client.from('equipment_tags').select('class_id').eq('tag_id', tagId).then(function (r) {
            if (r.error) throw r.error;
            var classId = r.data[0] && r.data[0].class_id;
            if (!classId) return [];
            return client.from('maintenance_activities')
                .select('id, name, interval_hours, interval_weeks')
                .eq('class_id', classId).eq('active', true).order('name')
                .then(function (a) {
                    if (a.error) throw a.error;
                    return a.data;
                });
        });
    }

    function openModal(innerHtml) {
        var overlay = document.createElement('div');
        overlay.className = 'maint-modal-overlay';
        overlay.innerHTML = '<div class="maint-modal" role="dialog" aria-modal="true">' + innerHtml + '</div>';
        document.body.appendChild(overlay);
        return overlay;
    }

    function conflictLine(tagId, c) {
        var when = '<strong>' + Agenda.formatDate(c.due_date) + '</strong>';
        var src = Agenda.SOURCE_LABEL[c.source] || c.source;
        if (c.status === 'vencido' && c.days_overdue != null) {
            return '⚠️ <strong>' + escapeHtml(tagId) + ' — ' + escapeHtml(c.activity_name) + '</strong> estaba programado para el ' +
                when + ' y está <strong>vencido hace ' + c.days_overdue + ' días</strong> (' + escapeHtml(src) + ').';
        }
        return '⚠️ <strong>' + escapeHtml(tagId) + ' — ' + escapeHtml(c.activity_name) + '</strong> ya está programado para el ' +
            when + ' (' + escapeHtml(src) + ').';
    }

    // Advertencia del spec. Resuelve con el motivo (string, '' si es opcional y vacío)
    // o null si se cancela. Si algo está vencido y askReason, el motivo es obligatorio.
    function confirmOverwrite(tagId, conflicts, newDate, askReason) {
        var overdue = conflicts.some(function (c) { return c.status === 'vencido'; });
        var verb = overdue ? 'Reprogramar' : 'Sobrescribir';
        return new Promise(function (resolve) {
            var overlay = openModal(
                conflicts.map(function (c) { return '<p>' + conflictLine(tagId, c) + '</p>'; }).join('') +
                '<p>¿' + verb + ' para el <strong>' + Agenda.formatDate(newDate) + '</strong>?</p>' +
                (askReason ? '<label class="maint-field">Motivo' + (overdue ? ' (obligatorio: está vencido)' : ' (opcional)') +
                    '<input type="text" name="reason"></label>' : '') +
                '<div class="maint-form-error" hidden></div>' +
                '<div class="maint-form-buttons">' +
                '  <button type="button" class="maint-btn maint-btn-warning" data-action="ok">' + verb + '</button>' +
                '  <button type="button" class="maint-btn maint-btn-secondary" data-action="cancel">Cancelar</button>' +
                '</div>');
            var input = overlay.querySelector('input[name="reason"]');
            var errorBox = overlay.querySelector('.maint-form-error');
            function close(value) {
                document.removeEventListener('keydown', onKey);
                overlay.remove();
                resolve(value);
            }
            function onKey(evt) { if (evt.key === 'Escape') close(null); }
            document.addEventListener('keydown', onKey);
            overlay.querySelector('[data-action="cancel"]').addEventListener('click', function () { close(null); });
            overlay.querySelector('[data-action="ok"]').addEventListener('click', function () {
                var reason = input ? input.value.trim() : '';
                if (input && overdue && !reason) {
                    errorBox.textContent = 'Escribí el motivo de la reprogramación.';
                    errorBox.hidden = false;
                    return;
                }
                close(reason);
            });
            (input || overlay.querySelector('[data-action="ok"]')).focus();
        });
    }

    // Reprogramar (solo oficina; RLS/servidor lo hacen cumplir).
    function openRescheduleModal(client, row, onDone) {
        var overlay = openModal(
            '<h3>Reprogramar — ' + escapeHtml(row.activity_name) + '</h3>' +
            '<label class="maint-field">Nueva fecha<input type="date" name="date" required></label>' +
            '<div class="maint-form-error" hidden></div>' +
            '<div class="maint-form-buttons">' +
            '  <button type="button" class="maint-btn maint-btn-primary" data-action="ok">Continuar</button>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" data-action="cancel">Cancelar</button>' +
            '</div>');
        var dateInput = overlay.querySelector('input[name="date"]');
        var errorBox = overlay.querySelector('.maint-form-error');
        dateInput.value = Agenda.addDays(Agenda.todayIso(), 7);
        overlay.querySelector('[data-action="cancel"]').addEventListener('click', function () { overlay.remove(); });
        overlay.querySelector('[data-action="ok"]').addEventListener('click', function () {
            if (!dateInput.value) return;
            var params = { p_tag: row.tag_id, p_activity: row.activity_id, p_date: dateInput.value, p_note: null, p_replace: false };
            overlay.remove();
            client.rpc('schedule_manual', params).then(function (result) {
                if (result.error) throw result.error;
                if (result.data.status !== 'conflict') return result;
                return confirmOverwrite(row.tag_id, result.data.conflicts, params.p_date, true).then(function (reason) {
                    if (reason === null) return null;
                    params.p_replace = true;
                    params.p_note = reason || null;
                    return client.rpc('schedule_manual', params).then(function (r2) {
                        if (r2.error) throw r2.error;
                        return r2;
                    });
                });
            }).then(function (done) {
                if (done) onDone();
            }).catch(function (err) {
                window.alert('No se pudo reprogramar: ' + err.message);
            });
        });
    }

    // Bloque "Próximos mantenimientos" de la ficha (lectura pública).
    function renderUpcoming(container, client, tagId, openForm) {
        container.innerHTML = '<p class="maint-loading">Cargando programación…</p>';
        Promise.all([fetchAgenda(client, tagId), fetchRole(client)]).then(function (res) {
            var rows = Agenda.filterAgenda(res[0], 'todo', Agenda.todayIso());
            var isOficina = res[1] === 'oficina';
            var canRegister = !!res[1] && typeof openForm === 'function';
            container.innerHTML = '';
            if (rows.length === 0) return;
            var h = document.createElement('h3');
            h.className = 'maint-upcoming-title';
            h.textContent = 'Próximos mantenimientos';
            container.appendChild(h);
            rows.forEach(function (row) {
                var info = Agenda.statusInfo(row);
                var item = document.createElement('div');
                item.className = 'maint-upcoming-item maint-level-' + info.level;
                var extra = Agenda.rescheduleText(row);
                item.innerHTML =
                    '<div class="maint-upcoming-main">' +
                    '  <span class="maint-upcoming-activity">' + escapeHtml(row.activity_name) + '</span>' +
                    '  <span class="maint-upcoming-status">' + escapeHtml(info.text) + '</span>' +
                    '</div>' +
                    (extra ? '<div class="maint-upcoming-extra">' + escapeHtml(extra) + '</div>' : '');
                if (canRegister) {
                    var done = document.createElement('button');
                    done.type = 'button';
                    done.className = 'maint-btn maint-btn-primary maint-btn-small maint-btn-done';
                    done.textContent = '✔ Hecho';
                    done.addEventListener('click', function () { openForm(row.activity_id); });
                    item.querySelector('.maint-upcoming-main').appendChild(done);
                }
                if (isOficina && row.status !== 'sin_fecha') {
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'maint-btn maint-btn-secondary maint-btn-small';
                    btn.textContent = row.status === 'sin_registro' ? 'Programar' : 'Reprogramar';
                    btn.addEventListener('click', function () {
                        openRescheduleModal(client, row, function () { renderUpcoming(container, client, tagId, openForm); });
                    });
                    item.querySelector('.maint-upcoming-main').appendChild(btn);
                }
                container.appendChild(item);
            });
        }).catch(function (err) {
            container.innerHTML = '';
            var box = document.createElement('div');
            box.className = 'maint-error';
            box.textContent = 'No se pudo cargar la programación: ' + err.message + ' ';
            var retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'maint-btn maint-btn-secondary';
            retry.textContent = 'Reintentar';
            retry.addEventListener('click', function () { renderUpcoming(container, client, tagId, openForm); });
            box.appendChild(retry);
            container.appendChild(box);
        });
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

    function renderRecord(client, record, onChange) {
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

        var activitiesHtml = (record.maintenance_record_activities || [])
            .filter(function (link) { return link.maintenance_activities; })
            .map(function (link) {
                var delay = Agenda.delayText(link.due_date, record.performed_at);
                var late = delay && delay !== 'A tiempo';
                return '<li class="maint-done-activity">✅ ' + escapeHtml(link.maintenance_activities.name) +
                    (delay ? ' <span class="maint-delay' + (late ? ' maint-delay-late' : '') + '">' + delay + '</span>' : '') +
                    '</li>';
            }).join('');
        var hmiHtml = record.hmi_hours != null
            ? '<p class="maint-record-hmi"><strong>Horas HMI:</strong> ' + Number(record.hmi_hours).toLocaleString('es-CO') + ' h</p>'
            : '';

        el.innerHTML =
            '<header class="maint-record-head">' +
            '  <span class="maint-record-date">' + formatDate(record.performed_at) + '</span>' +
            '  <span class="maint-record-type">' + (record.type === 'preventivo' ? 'Preventivo' : 'Correctivo') + '</span>' +
            badge +
            '</header>' +
            (activitiesHtml ? '<ul class="maint-done-activities">' + activitiesHtml + '</ul>' : '') +
            '<p class="maint-record-description">' + escapeHtml(record.description) + '</p>' +
            hmiHtml + partsHtml + nextHtml +
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

        // Solo el autor del evento puede sumarle comentarios/adjuntos desde el sitio
        // (oficina edita/borra desde gui.py, Plan 3).
        var addBox = el.querySelector('.maint-record-add');
        client.auth.getSession().then(function (result) {
            var session = result.data.session;
            if (session && session.user.id === record.created_by) {
                var addLink = document.createElement('button');
                addLink.type = 'button';
                addLink.className = 'maint-btn maint-btn-secondary maint-add-comment-btn';
                addLink.textContent = '+ Agregar comentario/adjunto';
                addLink.addEventListener('click', function () {
                    renderAddCommentForm(client, record, addBox, addLink, onChange);
                });
                addBox.appendChild(addLink);
            }
        });

        return el;
    }

    function loadAndRenderRecords(bodyContainer, tagId) {
        bodyContainer.innerHTML = '<p class="maint-loading">Cargando historial…</p>';
        var client = getClient();

        client
            .from('maintenance_records')
            .select('*, maintenance_comments(*), maintenance_attachments(*), ' +
                'maintenance_record_activities(due_date, maintenance_activities(name))')
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
        addBtn.hidden = true;
        bodyContainer.appendChild(addBtn);
        client.auth.getSession().then(function (result) {
            addBtn.hidden = !(result.data && result.data.session);
        });

        var formSlot = document.createElement('div');
        formSlot.className = 'maint-form-slot';
        bodyContainer.appendChild(formSlot);

        var upcoming = document.createElement('section');
        upcoming.className = 'maint-upcoming';
        bodyContainer.appendChild(upcoming);
        renderUpcoming(upcoming, client, tagId, openForm);

        // Llegó desde "✔ Hecho" en Programados (?hecho=<actividad>): abrir el formulario
        // apenas haya sesión (si no la hay, queda pendiente hasta que inicie sesión).
        if (pendingDone !== null) {
            client.auth.getSession().then(function (result) {
                if (!(result.data && result.data.session) || pendingDone === null) return;
                var activityId = pendingDone;
                pendingDone = null;
                openForm(activityId);
            });
        }

        // Abre el formulario; con activityId esa actividad llega ya marcada (botón ✔ Hecho).
        function openForm(activityId) {
            renderNewRecordForm(formSlot, tagId, function () {
                loadAndRenderRecords(bodyContainer, tagId);
            }, activityId === undefined ? null : { activity_ids: activityId ? [activityId] : [] });
            formSlot.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        addBtn.addEventListener('click', function () { openForm(); });

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
            list.appendChild(renderRecord(client, record, function () {
                loadAndRenderRecords(bodyContainer, tagId);
            }));
        });
        bodyContainer.appendChild(list);
    }

    // ── Carga de mantenimientos (Task 5) ─────────────────────────────────

    var MAX_ATTACHMENTS = 5;
    var MAX_AUDIO_SECONDS = 60;
    var DRAFT_KEY_PREFIX = 'maint-draft-';
    // Tipos que acepta el bucket (ver migración de endurecimiento); el resto se rechaza en el servidor.
    var AUDIO_EXT = { 'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/wav': 'wav' };

    // "audio/webm;codecs=opus" -> "audio/webm" (el bucket compara el tipo sin parámetros)
    function baseMime(mime) {
        return (mime || '').split(';')[0].trim();
    }

    function todayLocalISO() {
        // toISOString() da la fecha UTC: en Colombia (UTC-5) después de las 19:00 ya sería "mañana".
        var d = new Date();
        var mm = String(d.getMonth() + 1).padStart(2, '0');
        var dd = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + mm + '-' + dd;
    }

    function compressImage(file) {
        return new Promise(function (resolve, reject) {
            var img = new Image();
            var reader = new FileReader();
            reader.onerror = reject;
            reader.onload = function () {
                img.onerror = function () { reject(new Error('formato de imagen no soportado')); };
                img.onload = function () {
                    var maxWidth = 1600;
                    var scale = Math.min(1, maxWidth / img.width);
                    var canvas = document.createElement('canvas');
                    canvas.width = Math.round(img.width * scale);
                    canvas.height = Math.round(img.height * scale);
                    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                    canvas.toBlob(function (blob) {
                        if (!blob) { reject(new Error('No se pudo comprimir la imagen')); return; }
                        resolve(blob);
                    }, 'image/jpeg', 0.7);
                };
                img.src = reader.result;
            };
            reader.readAsDataURL(file);
        });
    }

    function pickAudioMime() {
        if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return '';
        var candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
        for (var i = 0; i < candidates.length; i++) {
            if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
        }
        return '';
    }

    function createAudioRecorder(onStop) {
        var recorder = null;
        var chunks = [];
        var timerId = null;

        function stop() {
            if (recorder && recorder.state !== 'inactive') recorder.stop();
        }

        function start(onTick) {
            // Promise.resolve().then: si mediaDevices no existe (http fuera de localhost) el error
            // sale como rechazo y no como excepción síncrona.
            return Promise.resolve().then(function () {
                return navigator.mediaDevices.getUserMedia({ audio: true });
            }).then(function (stream) {
                chunks = [];
                var mime = pickAudioMime();
                recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
                recorder.ondataavailable = function (e) {
                    if (e.data && e.data.size > 0) chunks.push(e.data);
                };
                recorder.onstop = function () {
                    stream.getTracks().forEach(function (track) { track.stop(); });
                    clearInterval(timerId);
                    // Se usa el tipo real que grabó el navegador (Safari/iOS graba mp4, no webm).
                    var type = baseMime(recorder.mimeType) || 'audio/webm';
                    onStop(new Blob(chunks, { type: type }));
                };
                recorder.start();
                var seconds = 0;
                timerId = setInterval(function () {
                    seconds += 1;
                    if (onTick) onTick(seconds);
                    if (seconds >= MAX_AUDIO_SECONDS) stop();
                }, 1000);
            });
        }

        return { start: start, stop: stop };
    }

    // Editor de adjuntos reutilizable (fotos + audio). `reserved` = adjuntos que el registro ya tiene.
    function createAttachmentsEditor(root, reserved) {
        var pending = []; // [{kind: 'photo'|'audio', blob: Blob}]
        var recorder = null;
        var recording = false;
        var starting = false;

        root.innerHTML =
            '<div class="maint-attachments-preview"></div>' +
            '<div class="maint-attachments-actions">' +
            '  <label class="maint-btn maint-btn-secondary maint-file-btn">📷 Agregar foto' +
            '    <input type="file" accept="image/*" capture="environment" hidden>' +
            '  </label>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" data-action="audio">🎙️ Grabar audio</button>' +
            '</div>' +
            '<div class="maint-form-error" hidden></div>';

        var preview = root.querySelector('.maint-attachments-preview');
        var photoInput = root.querySelector('input[type="file"]');
        var photoLabel = root.querySelector('.maint-file-btn');
        var audioBtn = root.querySelector('[data-action="audio"]');
        var errorBox = root.querySelector('.maint-form-error');

        function showError(msg) {
            errorBox.textContent = msg;
            errorBox.hidden = false;
        }

        function full() {
            return (reserved || 0) + pending.length >= MAX_ATTACHMENTS;
        }

        function renderPreview() {
            preview.innerHTML = '';
            pending.forEach(function (item, idx) {
                var chip = document.createElement('span');
                chip.className = 'maint-attachment-chip';
                chip.textContent = (item.kind === 'photo' ? '📷 foto' : '🎙️ audio') + ' ';
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.setAttribute('aria-label', 'Quitar adjunto');
                removeBtn.textContent = '✕';
                removeBtn.addEventListener('click', function () {
                    pending.splice(idx, 1);
                    renderPreview();
                });
                chip.appendChild(removeBtn);
                preview.appendChild(chip);
            });
            photoInput.disabled = full();
            photoLabel.classList.toggle('is-disabled', full());
            if (!recording) audioBtn.disabled = full();
        }

        photoInput.addEventListener('change', function () {
            var file = photoInput.files[0];
            photoInput.value = '';
            errorBox.hidden = true;
            if (!file || full()) return;
            compressImage(file).then(function (blob) {
                pending.push({ kind: 'photo', blob: blob });
                renderPreview();
            }).catch(function (err) {
                showError('No se pudo procesar la foto: ' + err.message);
            });
        });

        // Un único handler: el primer toque inicia la grabación, el siguiente la detiene.
        audioBtn.addEventListener('click', function () {
            if (recording) { recorder.stop(); return; }
            if (starting || full()) return;
            errorBox.hidden = true;
            starting = true;
            recorder = createAudioRecorder(function (blob) {
                pending.push({ kind: 'audio', blob: blob });
                recording = false;
                audioBtn.textContent = '🎙️ Grabar audio';
                renderPreview();
            });
            recorder.start(function (seconds) {
                audioBtn.textContent = '⏺ Grabando… (' + seconds + 's) — tocar para detener';
            }).then(function () {
                starting = false;
                recording = true;
                audioBtn.textContent = '⏺ Grabando… (0s) — tocar para detener';
            }).catch(function (err) {
                starting = false;
                recording = false;
                audioBtn.textContent = '🎙️ Grabar audio';
                showError('No se pudo acceder al micrófono: ' + err.message);
            });
        });

        renderPreview();

        return {
            getPending: function () { return pending; },
            isRecording: function () { return recording || starting; },
            showError: showError
        };
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

    function uploadPendingAttachment(client, tagId, recordId, pending) {
        var mime = baseMime(pending.blob.type) || (pending.kind === 'photo' ? 'image/jpeg' : 'audio/webm');
        var ext = pending.kind === 'photo' ? 'jpg' : (AUDIO_EXT[mime] || 'webm');
        var path = tagId + '/' + recordId + '/' + Date.now() + '-' + Math.random().toString(36).slice(2) + '.' + ext;
        var storage = client.storage.from('maintenance-attachments');

        return storage.upload(path, pending.blob, { contentType: mime }).then(function (result) {
            if (result.error) throw result.error;
            return client.from('maintenance_attachments').insert({
                record_id: recordId,
                kind: pending.kind,
                storage_path: path
            });
        }).then(function (result) {
            if (result.error) {
                // El archivo subió pero su fila no: se borra (best-effort) para no dejar huérfanos.
                // Si el rol no puede borrar (técnico), queda; es inofensivo y no aparece en el historial.
                storage.remove([path]);
                throw result.error;
            }
        });
    }

    function uploadAllAttachments(client, tagId, recordId, pendingList, statusEl) {
        var results = [];

        function uploadOne(index) {
            if (index >= pendingList.length) return Promise.resolve();
            statusEl.textContent = 'Subiendo adjunto ' + (index + 1) + ' de ' + pendingList.length + '…';
            return uploadPendingAttachment(client, tagId, recordId, pendingList[index])
                .then(function () { results[index] = 'ok'; })
                .catch(function (err) { results[index] = 'error: ' + err.message; })
                .then(function () { return uploadOne(index + 1); });
        }

        return uploadOne(0).then(function () { return results; });
    }

    function isAuthExpired(err) {
        return !!err && (err.status === 401 || err.code === 'PGRST301' ||
            (err.message && err.message.toLowerCase().indexOf('jwt') !== -1));
    }

    function showReloginModal(onSuccess) {
        var overlay = document.createElement('div');
        overlay.className = 'maint-modal-overlay';
        overlay.innerHTML =
            '<div class="maint-modal" role="dialog" aria-modal="true">' +
            '  <h3>Tu sesión expiró</h3>' +
            '  <p>Iniciá sesión de nuevo — lo que ya escribiste no se pierde.</p>' +
            '  <form id="maint-relogin-form">' +
            '    <label class="maint-field">Email<input type="email" name="email" required autocomplete="username"></label>' +
            '    <label class="maint-field">Contraseña<input type="password" name="password" required autocomplete="current-password"></label>' +
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
                password: form.elements.password.value
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

    function renderNewRecordForm(container, tagId, onDone, preset) {
        var draft = loadDraft(tagId) || {};
        if (preset) {
            draft.activity_ids = preset.activity_ids;
            if (preset.activity_ids.length) draft.type = 'preventivo';
        }

        container.innerHTML =
            '<form class="maint-form" id="maint-new-record-form">' +
            '  <label class="maint-field">Fecha del mantenimiento' +
            '    <input type="date" name="performed_at" required>' +
            '  </label>' +
            '  <label class="maint-field">Horas HMI (opcional)' +
            '    <input type="number" name="hmi_hours" min="0" step="1" inputmode="numeric" placeholder="Lo que marca el HMI">' +
            '  </label>' +
            '  <fieldset class="maint-field">' +
            '    <legend>Tipo</legend>' +
            '    <label class="maint-radio"><input type="radio" name="type" value="preventivo" required> Preventivo</label>' +
            '    <label class="maint-radio"><input type="radio" name="type" value="correctivo"> Correctivo</label>' +
            '  </fieldset>' +
            '  <fieldset class="maint-field maint-activities" id="maint-activities" hidden>' +
            '    <legend>Actividades de la sábana</legend>' +
            '  </fieldset>' +
            '  <label class="maint-field">Descripción' +
            '    <textarea name="description" required rows="3"></textarea>' +
            '  </label>' +
            '  <label class="maint-field">Repuestos / insumos (opcional)' +
            '    <textarea name="parts_used" rows="2"></textarea>' +
            '  </label>' +
            '  <label class="maint-field" id="maint-next-field">Próximo mantenimiento programado (opcional)' +
            '    <input type="date" name="next_scheduled_at">' +
            '  </label>' +
            '  <div class="maint-attachments-editor" id="maint-attachments-editor"></div>' +
            '  <div class="maint-form-error" id="maint-form-error" hidden></div>' +
            '  <div class="maint-form-status" id="maint-form-status"></div>' +
            '  <div class="maint-form-buttons">' +
            '    <button type="submit" class="maint-btn maint-btn-primary">Guardar</button>' +
            '    <button type="button" class="maint-btn maint-btn-secondary" id="maint-cancel-btn">Cancelar</button>' +
            '  </div>' +
            '</form>';

        var form = document.getElementById('maint-new-record-form');
        var activitiesBox = document.getElementById('maint-activities');
        var nextField = document.getElementById('maint-next-field');
        form.elements.performed_at.value = draft.performed_at || todayLocalISO();
        if (draft.type) form.elements.type.value = draft.type;
        form.elements.hmi_hours.value = draft.hmi_hours || '';
        form.elements.description.value = draft.description || '';
        form.elements.parts_used.value = draft.parts_used || '';
        form.elements.next_scheduled_at.value = draft.next_scheduled_at || '';

        function selectedActivities() {
            return Array.prototype.map.call(
                activitiesBox.querySelectorAll('input[type="checkbox"]:checked'),
                function (box) { return box.value; });
        }

        function currentFields() {
            return {
                performed_at: form.elements.performed_at.value,
                type: form.elements.type.value,
                hmi_hours: form.elements.hmi_hours.value,
                description: form.elements.description.value,
                parts_used: form.elements.parts_used.value,
                next_scheduled_at: form.elements.next_scheduled_at.value,
                activity_ids: selectedActivities()
            };
        }

        // Con actividades de la sábana el próximo lo calcula el sistema.
        function syncNextField() {
            nextField.hidden = selectedActivities().length > 0;
        }

        form.addEventListener('input', function () { saveDraft(tagId, currentFields()); });
        form.addEventListener('change', function () { syncNextField(); saveDraft(tagId, currentFields()); });

        fetchTagActivities(getClient(), tagId).then(function (activities) {
            if (!activities.length) return;
            var restore = draft.activity_ids || [];
            activities.forEach(function (a) {
                var freq = [a.interval_hours ? a.interval_hours + ' h' : '', a.interval_weeks ? a.interval_weeks + ' sem' : '']
                    .filter(Boolean).join(' / ');
                var label = document.createElement('label');
                label.className = 'maint-check';
                label.innerHTML = '<input type="checkbox" value="' + escapeHtml(a.id) + '"> ' +
                    '<span>' + escapeHtml(a.name) + ' <small>(cada ' + escapeHtml(freq) + ')</small></span>';
                label.querySelector('input').checked = restore.indexOf(a.id) !== -1;
                activitiesBox.appendChild(label);
            });
            activitiesBox.hidden = false;
            syncNextField();
        }).catch(function () { /* sin sábana: el formulario funciona como antes */ });

        var editor = createAttachmentsEditor(document.getElementById('maint-attachments-editor'), 0);
        var errorBox = document.getElementById('maint-form-error');
        var statusBox = document.getElementById('maint-form-status');

        document.getElementById('maint-cancel-btn').addEventListener('click', function () {
            container.innerHTML = '';
        });

        // Antes de fijar un "próximo" libre: ¿ya hay algo programado para este equipo?
        function confirmNextDate(client, fields) {
            if (!fields.next_scheduled_at || fields.activity_ids.length) return Promise.resolve(true);
            return fetchAgenda(client, tagId).then(function (rows) {
                var conflicts = rows.filter(function (r) { return r.activity_id === null && r.due_date; });
                if (!conflicts.length) return true;
                return confirmOverwrite(tagId, conflicts, fields.next_scheduled_at, false)
                    .then(function (r) { return r !== null; });
            });
        }

        function nextDatesMessage(client, activityIds) {
            if (!activityIds.length) return Promise.resolve('');
            return fetchAgenda(client, tagId).then(function (rows) {
                return rows.filter(function (r) { return activityIds.indexOf(r.activity_id) !== -1 && r.due_date; })
                    .map(function (r) { return 'Próxima ' + r.activity_name + ': ' + Agenda.formatDate(r.due_date); })
                    .join(' · ');
            }).catch(function () { return ''; });
        }

        form.addEventListener('submit', function (evt) {
            evt.preventDefault();
            errorBox.hidden = true;

            if (!form.elements.type.value) {
                errorBox.textContent = 'Elegí el tipo de mantenimiento.';
                errorBox.hidden = false;
                return;
            }
            if (editor.isRecording()) {
                errorBox.textContent = 'Detené la grabación de audio antes de guardar.';
                errorBox.hidden = false;
                return;
            }

            var fields = currentFields();
            saveDraft(tagId, fields);
            var client = getClient();
            var submitBtn = form.querySelector('button[type="submit"]');

            confirmNextDate(client, fields).then(function (ok) {
                if (!ok) return;
                submitBtn.disabled = true;
                statusBox.textContent = 'Guardando registro…';
                var payload = {
                    tag_id: tagId,
                    performed_at: fields.performed_at,
                    type: fields.type,
                    description: fields.description,
                    parts_used: fields.parts_used || null,
                    next_scheduled_at: fields.activity_ids.length ? null : (fields.next_scheduled_at || null),
                    hmi_hours: fields.hmi_hours === '' ? null : Number(fields.hmi_hours)
                };
                var recordId;
                return client.rpc('create_maintenance_record', { p_record: payload, p_activity_ids: fields.activity_ids })
                    .then(function (result) {
                        if (result.error) throw result.error;
                        recordId = result.data;
                        // Desde acá el registro ya existe: un fallo posterior NO debe permitir re-enviar (duplicaría).
                        clearDraft(tagId);
                        return uploadAllAttachments(client, tagId, recordId, editor.getPending(), statusBox);
                    })
                    .then(function (uploadResults) {
                        var failed = uploadResults.filter(function (r) { return r !== 'ok'; });
                        return nextDatesMessage(client, fields.activity_ids).then(function (nextMsg) {
                            var msg = failed.length > 0
                                ? 'Registro guardado, pero ' + failed.length + ' adjunto(s) no se pudieron subir. Podés agregarlos después desde "Agregar comentario/adjunto".'
                                : 'Registro guardado.';
                            statusBox.textContent = msg + (nextMsg ? ' ' + nextMsg : '');
                            // El botón queda deshabilitado a propósito: el formulario se reemplaza al recargar la lista.
                            setTimeout(onDone, failed.length > 0 || nextMsg ? 3500 : 800);
                        });
                    });
            }).catch(function (err) {
                submitBtn.disabled = false;
                statusBox.textContent = '';
                if (isAuthExpired(err)) {
                    showReloginModal(function () {
                        form.dispatchEvent(new Event('submit', { cancelable: true }));
                    });
                    return;
                }
                errorBox.textContent = 'No se pudo guardar (los datos siguen en el formulario): ' + err.message;
                errorBox.hidden = false;
            });
        });
    }

    function renderAddCommentForm(client, record, container, triggerBtn, onDone) {
        triggerBtn.hidden = true;

        var formEl = document.createElement('form');
        formEl.className = 'maint-form maint-comment-form';
        formEl.innerHTML =
            '<label class="maint-field">Comentario' +
            '  <textarea name="body" rows="2"></textarea>' +
            '</label>' +
            '<div class="maint-attachments-editor"></div>' +
            '<div class="maint-form-error" hidden></div>' +
            '<div class="maint-form-status"></div>' +
            '<div class="maint-form-buttons">' +
            '  <button type="submit" class="maint-btn maint-btn-primary">Agregar</button>' +
            '  <button type="button" class="maint-btn maint-btn-secondary" data-action="cancel">Cancelar</button>' +
            '</div>';
        container.appendChild(formEl);

        var editor = createAttachmentsEditor(
            formEl.querySelector('.maint-attachments-editor'),
            (record.maintenance_attachments || []).length
        );
        var errorBox = formEl.querySelector('.maint-form-error');
        var statusBox = formEl.querySelector('.maint-form-status');
        var commentSaved = false; // evita duplicar el comentario si solo falla la subida de adjuntos

        formEl.querySelector('[data-action="cancel"]').addEventListener('click', function () {
            formEl.remove();
            triggerBtn.hidden = false;
        });

        formEl.addEventListener('submit', function (evt) {
            evt.preventDefault();
            var body = formEl.elements.body.value.trim();
            var pending = editor.getPending();
            errorBox.hidden = true;

            if (editor.isRecording()) {
                errorBox.textContent = 'Detené la grabación de audio antes de guardar.';
                errorBox.hidden = false;
                return;
            }
            if (!body && pending.length === 0) {
                errorBox.textContent = 'Agregá un comentario o al menos un adjunto.';
                errorBox.hidden = false;
                return;
            }

            var submitBtn = formEl.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            statusBox.textContent = 'Guardando…';

            var chain = Promise.resolve();
            if (body && !commentSaved) {
                chain = client.from('maintenance_comments').insert({ record_id: record.id, body: body }).then(function (result) {
                    if (result.error) throw result.error;
                    commentSaved = true;
                });
            }
            chain.then(function () {
                return uploadAllAttachments(client, record.tag_id, record.id, pending, statusBox);
            }).then(function (uploadResults) {
                var failed = uploadResults.filter(function (r) { return r !== 'ok'; });
                // El botón queda deshabilitado a propósito: reintentar re-subiría los adjuntos que sí subieron.
                if (failed.length > 0) {
                    statusBox.textContent = 'Guardado, pero ' + failed.length + ' adjunto(s) no se pudieron subir. Podés agregarlos de nuevo.';
                } else {
                    statusBox.textContent = 'Guardado.';
                }
                setTimeout(onDone, failed.length > 0 ? 3500 : 500);
            }).catch(function (err) {
                submitBtn.disabled = false;
                statusBox.textContent = '';
                if (isAuthExpired(err)) {
                    showReloginModal(function () {
                        formEl.dispatchEvent(new Event('submit', { cancelable: true }));
                    });
                    return;
                }
                errorBox.textContent = 'No se pudo guardar: ' + err.message;
                errorBox.hidden = false;
            });
        });
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

        // Aviso al escanear el QR: si este equipo tiene mantenimientos vencidos se ve
        // arriba sin abrir el historial (diseño, "Si olvidan el aplicativo").
        try {
            fetchAgenda(getClient(), tagId).then(function (rows) {
                var n = Agenda.summary(rows).vencidos;
                if (!n) return;
                var alertBtn = document.createElement('button');
                alertBtn.type = 'button';
                alertBtn.className = 'maint-overdue-alert';
                alertBtn.textContent = '🔴 ' + n + (n === 1 ? ' mantenimiento vencido' : ' mantenimientos vencidos') +
                    ' en este equipo — ver';
                alertBtn.addEventListener('click', function () { showHistorial(); });
                var toggle = btnFicha.parentNode;
                toggle.parentNode.insertBefore(alertBtn, toggle);
            }).catch(function () { /* sin red: la ficha sigue funcionando */ });
        } catch (e) { /* Supabase sin configurar */ }

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
        if (pendingDone !== null) showHistorial();
    });

    // Inicio del sitio: franja de vencidos de toda la planta (diseño, "Si olvidan el aplicativo").
    document.addEventListener('DOMContentLoaded', function () {
        var homeAlert = document.getElementById('home-overdue');
        if (!homeAlert) return;
        try {
            getClient().from('maintenance_agenda').select('tag_id, status, days_overdue').eq('status', 'vencido')
                .then(function (result) {
                    if (result.error) return;
                    // Solo equipos del sitio (los TAGs renombrados/borrados no inflan el aviso).
                    var known = {};
                    (window.__SEARCH_INDEX__ || []).forEach(function (e) { known[e.tag] = true; });
                    var rows = window.__SEARCH_INDEX__
                        ? result.data.filter(function (r) { return known[r.tag_id]; })
                        : result.data;
                    var sum = Agenda.summary(rows);
                    if (!sum.vencidos) return;
                    homeAlert.textContent = '🔴 ' + sum.vencidos +
                        (sum.vencidos === 1 ? ' mantenimiento vencido' : ' mantenimientos vencidos') +
                        (sum.criticos ? ' (' + sum.criticos + (sum.criticos === 1 ? ' crítico)' : ' críticos)') : '') + ' → ver';
                    homeAlert.hidden = false;
                });
        } catch (e) { /* Supabase sin configurar: no hay franja */ }
    });
})();
