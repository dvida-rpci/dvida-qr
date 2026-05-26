document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.querySelector('.sidebar');
    var backdrop = document.querySelector('.sidebar-backdrop');
    var toggle = document.querySelector('.menu-toggle');
    var closeBtn = document.querySelector('.sidebar-close');

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('open');
        if (backdrop) backdrop.classList.add('show');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
    }
    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.remove('show');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }

    if (toggle) toggle.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (backdrop) backdrop.addEventListener('click', closeSidebar);

    // Cerrar al navegar (en móvil)
    document.querySelectorAll('.sidebar a').forEach(function (a) {
        a.addEventListener('click', function () {
            if (window.matchMedia('(max-width: 900px)').matches) closeSidebar();
        });
    });

    // Cerrar con tecla Escape
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeSidebar();
    });

    // Toggle de categorías
    document.querySelectorAll('.nav-cat').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var group = btn.closest('.nav-group');
            var open = group.classList.toggle('open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });

    // Abrir automáticamente la categoría con link activo (o todas si no hay activo)
    var active = document.querySelector('.nav-items a.active');
    if (active) {
        var group = active.closest('.nav-group');
        if (group) {
            group.classList.add('open');
            var b = group.querySelector('.nav-cat');
            if (b) b.setAttribute('aria-expanded', 'true');
        }
    } else {
        document.querySelectorAll('.nav-group').forEach(function (g) {
            g.classList.add('open');
            var b = g.querySelector('.nav-cat');
            if (b) b.setAttribute('aria-expanded', 'true');
        });
    }

    // Scroll al ítem activo dentro del sidebar
    if (active) {
        setTimeout(function () {
            active.scrollIntoView({ block: 'center', behavior: 'instant' });
        }, 30);
    }

    // Acordeones de contenido (cards colapsables)
    document.querySelectorAll('.acc-header').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var item = btn.closest('.acc-item');
            if (!item) return;
            var open = item.classList.toggle('open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });

    // ─────────────────────────────────────────────────────────────
    // Búsqueda
    // ─────────────────────────────────────────────────────────────
    var searchToggle = document.querySelector('.search-toggle');
    var searchModal = document.querySelector('.search-modal');
    var searchInput = document.querySelector('.search-input');
    var searchResults = document.querySelector('.search-results');
    var searchClose = document.querySelector('.search-modal-close');
    var searchOverlay = document.querySelector('.search-modal-overlay');
    var rel = document.body.getAttribute('data-rel') || '';

    var searchIndex = null;       // cargado lazy
    var searchLoading = false;
    var activeResultIdx = -1;
    var lastResults = [];

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function highlight(text, query) {
        if (!query) return escapeHtml(text);
        var lower = text.toLowerCase();
        var q = query.toLowerCase();
        var out = '', i = 0, idx;
        while ((idx = lower.indexOf(q, i)) !== -1) {
            out += escapeHtml(text.slice(i, idx));
            out += '<mark>' + escapeHtml(text.slice(idx, idx + q.length)) + '</mark>';
            i = idx + q.length;
        }
        out += escapeHtml(text.slice(i));
        return out;
    }

    function loadIndex() {
        if (searchIndex || searchLoading) return Promise.resolve(searchIndex || []);
        // 1) Embebido como variable global (search-index.js) → funciona en file:// y http://
        if (window.__SEARCH_INDEX__) {
            searchIndex = window.__SEARCH_INDEX__;
            return Promise.resolve(searchIndex);
        }
        // 2) Fallback: fetch del JSON (sólo http://)
        searchLoading = true;
        return fetch(rel + 'search-index.json?_t=' + Date.now())
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (data) { searchIndex = data; return data; })
            .catch(function () { searchIndex = []; return []; })
            .finally(function () { searchLoading = false; });
    }

    function openSearch() {
        if (!searchModal) return;
        searchModal.hidden = false;
        document.body.classList.add('search-open');
        searchToggle && searchToggle.setAttribute('aria-expanded', 'true');
        loadIndex().then(function () {
            // foco al input después del paint para que en móvil aparezca el teclado
            setTimeout(function () { searchInput && searchInput.focus(); }, 20);
            renderResults(searchInput.value);
        });
    }

    function closeSearch() {
        if (!searchModal) return;
        searchModal.hidden = true;
        document.body.classList.remove('search-open');
        searchToggle && searchToggle.setAttribute('aria-expanded', 'false');
        activeResultIdx = -1;
    }

    function renderResults(query) {
        if (!searchResults) return;
        query = (query || '').trim();
        if (!searchIndex) {
            searchResults.innerHTML = '<div class="search-empty">Cargando índice…</div>';
            return;
        }
        if (!query) {
            // Sin query: mostrar todos (hasta 50)
            lastResults = searchIndex.slice(0, 50);
        } else {
            var q = query.toLowerCase();
            // Filtrar por substring en el haystack
            var matches = [];
            for (var i = 0; i < searchIndex.length; i++) {
                if (searchIndex[i].haystack.indexOf(q) !== -1) {
                    matches.push(searchIndex[i]);
                }
            }
            // Ordenar: TAGs que empiezan con la query primero, luego por TAG alfabético
            matches.sort(function (a, b) {
                var aStarts = a.tag.toLowerCase().indexOf(q) === 0 ? 0 : 1;
                var bStarts = b.tag.toLowerCase().indexOf(q) === 0 ? 0 : 1;
                if (aStarts !== bStarts) return aStarts - bStarts;
                return a.tag.localeCompare(b.tag);
            });
            lastResults = matches.slice(0, 50);
        }

        if (lastResults.length === 0) {
            searchResults.innerHTML = '<div class="search-empty">Sin resultados para “' + escapeHtml(query) + '”.</div>';
            activeResultIdx = -1;
            return;
        }

        var html = '';
        for (var j = 0; j < lastResults.length; j++) {
            var r = lastResults[j];
            html += '<a class="search-result" href="' + rel + r.url + '" data-idx="' + j + '">';
            html += '<div class="search-result-head">';
            html += '<span class="search-result-tag">' + highlight(r.tag, query) + '</span>';
            html += '<span class="search-result-cat">' + escapeHtml(r.category) + '</span>';
            html += '</div>';
            if (r.preview) {
                html += '<div class="search-result-preview">' + highlight(r.preview, query) + '</div>';
            }
            html += '</a>';
        }
        searchResults.innerHTML = html;
        activeResultIdx = lastResults.length ? 0 : -1;
        updateActiveResult();
    }

    function updateActiveResult() {
        var nodes = searchResults.querySelectorAll('.search-result');
        nodes.forEach(function (n, i) {
            n.classList.toggle('active', i === activeResultIdx);
        });
        if (activeResultIdx >= 0 && nodes[activeResultIdx]) {
            nodes[activeResultIdx].scrollIntoView({ block: 'nearest' });
        }
    }

    // Debounce del input
    var searchTimer = null;
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                renderResults(searchInput.value);
            }, 80);
        });
        // Flechas + Enter para navegar resultados
        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (lastResults.length === 0) return;
                activeResultIdx = (activeResultIdx + 1) % lastResults.length;
                updateActiveResult();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (lastResults.length === 0) return;
                activeResultIdx = (activeResultIdx - 1 + lastResults.length) % lastResults.length;
                updateActiveResult();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (activeResultIdx >= 0 && lastResults[activeResultIdx]) {
                    window.location.href = rel + lastResults[activeResultIdx].url;
                }
            }
        });
    }

    if (searchToggle) searchToggle.addEventListener('click', openSearch);
    if (searchClose) searchClose.addEventListener('click', closeSearch);
    if (searchOverlay) searchOverlay.addEventListener('click', closeSearch);

    // Esc cierra (sobreescribe el handler genérico de Esc para sidebar si la búsqueda está abierta)
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && searchModal && !searchModal.hidden) {
            e.stopPropagation();
            closeSearch();
        }
    }, true);  // capture phase para correr antes del Esc del sidebar

    // ─────────────────────────────────────────────────────────────
    // Lightbox / galería de imágenes
    // ─────────────────────────────────────────────────────────────
    var lightbox = document.getElementById('lightbox');
    var lbImg = lightbox && lightbox.querySelector('.lightbox-img');
    var lbCaption = lightbox && lightbox.querySelector('.lightbox-caption');
    var lbCounter = lightbox && lightbox.querySelector('.lightbox-counter');
    var lbPrev = lightbox && lightbox.querySelector('.lightbox-prev');
    var lbNext = lightbox && lightbox.querySelector('.lightbox-next');
    var lbClose = lightbox && lightbox.querySelector('.lightbox-close');
    var lbOverlay = lightbox && lightbox.querySelector('.lightbox-overlay');
    var lbImages = [];
    var lbCurrent = 0;
    var lbTag = '';
    var lbTouchStartX = null;

    function lbRender() {
        if (!lbImages.length) return;
        var url = lbImages[lbCurrent];
        lbImg.src = url;
        lbImg.alt = lbTag + ' — imagen ' + (lbCurrent + 1);
        lbCaption.textContent = lbTag + ' — ' + (lbCurrent + 1) + ' / ' + lbImages.length;
        lbCounter.textContent = (lbCurrent + 1) + ' / ' + lbImages.length;
        lightbox.classList.toggle('single', lbImages.length <= 1);
    }
    function lbOpen(images, tag) {
        if (!lightbox || !images || !images.length) return;
        lbImages = images.slice();
        lbCurrent = 0;
        lbTag = tag || '';
        lbRender();
        lightbox.hidden = false;
        document.body.classList.add('lightbox-open');
    }
    function lbCloseFn() {
        if (!lightbox) return;
        lightbox.hidden = true;
        document.body.classList.remove('lightbox-open');
        lbImg.src = '';  // libera memoria
    }
    function lbStep(delta) {
        if (lbImages.length <= 1) return;
        lbCurrent = (lbCurrent + delta + lbImages.length) % lbImages.length;
        lbRender();
    }

    // Conectar los botones "Ver imágenes" de cada página
    document.querySelectorAll('.gallery-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var raw = btn.getAttribute('data-images') || '[]';
            try {
                var imgs = JSON.parse(raw);
                lbOpen(imgs, btn.getAttribute('data-tag') || '');
            } catch (e) { /* ignore */ }
        });
    });

    if (lbPrev) lbPrev.addEventListener('click', function () { lbStep(-1); });
    if (lbNext) lbNext.addEventListener('click', function () { lbStep(1); });
    if (lbClose) lbClose.addEventListener('click', lbCloseFn);
    if (lbOverlay) lbOverlay.addEventListener('click', lbCloseFn);

    // Teclado: ← → para navegar, Esc para cerrar
    document.addEventListener('keydown', function (e) {
        if (!lightbox || lightbox.hidden) return;
        if (e.key === 'ArrowLeft') { e.preventDefault(); lbStep(-1); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); lbStep(1); }
        else if (e.key === 'Escape') { e.stopPropagation(); lbCloseFn(); }
    }, true);

    // Swipe touch en móvil
    if (lightbox) {
        lightbox.addEventListener('touchstart', function (e) {
            lbTouchStartX = e.touches[0].clientX;
        }, { passive: true });
        lightbox.addEventListener('touchend', function (e) {
            if (lbTouchStartX === null) return;
            var dx = e.changedTouches[0].clientX - lbTouchStartX;
            if (Math.abs(dx) > 50) lbStep(dx < 0 ? 1 : -1);
            lbTouchStartX = null;
        }, { passive: true });
    }
});
