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
})();
