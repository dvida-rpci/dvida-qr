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
