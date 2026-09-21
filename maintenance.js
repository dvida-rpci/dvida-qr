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

    function renderNewRecordForm(container, tagId, onDone) {
        var draft = loadDraft(tagId) || {};

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
            '  <div class="maint-attachments-editor" id="maint-attachments-editor"></div>' +
            '  <div class="maint-form-error" id="maint-form-error" hidden></div>' +
            '  <div class="maint-form-status" id="maint-form-status"></div>' +
            '  <div class="maint-form-buttons">' +
            '    <button type="submit" class="maint-btn maint-btn-primary">Guardar</button>' +
            '    <button type="button" class="maint-btn maint-btn-secondary" id="maint-cancel-btn">Cancelar</button>' +
            '  </div>' +
            '</form>';

        var form = document.getElementById('maint-new-record-form');
        form.elements.performed_at.value = draft.performed_at || todayLocalISO();
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
                next_scheduled_at: form.elements.next_scheduled_at.value
            };
        }

        Array.prototype.forEach.call(form.elements, function (el) {
            if (el.name) el.addEventListener('input', function () { saveDraft(tagId, currentFields()); });
        });

        var editor = createAttachmentsEditor(document.getElementById('maint-attachments-editor'), 0);
        var errorBox = document.getElementById('maint-form-error');
        var statusBox = document.getElementById('maint-form-status');

        document.getElementById('maint-cancel-btn').addEventListener('click', function () {
            container.innerHTML = '';
        });

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
                next_scheduled_at: fields.next_scheduled_at || null
            };

            client.from('maintenance_records').insert(payload).select().then(function (result) {
                if (result.error) throw result.error;
                var recordId = result.data[0].id;
                // Desde acá el registro ya existe: un fallo posterior NO debe permitir re-enviar (duplicaría).
                clearDraft(tagId);
                return uploadAllAttachments(client, tagId, recordId, editor.getPending(), statusBox);
            }).then(function (uploadResults) {
                var failed = uploadResults.filter(function (r) { return r !== 'ok'; });
                if (failed.length > 0) {
                    statusBox.textContent = 'Registro guardado, pero ' + failed.length + ' adjunto(s) no se pudieron subir. Podés agregarlos después desde "Agregar comentario/adjunto".';
                } else {
                    statusBox.textContent = 'Registro guardado.';
                }
                // El botón queda deshabilitado a propósito: el formulario se reemplaza al recargar la lista.
                setTimeout(onDone, failed.length > 0 ? 3500 : 800);
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
