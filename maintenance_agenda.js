// Lógica pura de la agenda de mantenimientos (vista maintenance_agenda), compartida por
// la ficha (maintenance.js) y mantenimientos.html (maintenance_feed.js).
// Sin DOM: se prueba con node --test. Espejo de filter_agenda/agenda_summary de
// maintenance_plan.py (diseño 2026-10-14-plan-mantenimiento-design.md, "Atrasados").
(function (root) {
    'use strict';

    var CRITICAL_DAYS = 30;
    var FILTERS = [
        { value: 'semana', label: 'Esta semana' },
        { value: 'atrasados', label: 'Atrasados' },
        { value: 'sin_historial', label: 'Sin historial' },
        { value: 'proxima', label: 'Próxima semana' },
        { value: '4semanas', label: 'Próximas 4 semanas' },
        { value: 'todo', label: 'Todo' }
    ];
    var SOURCE_LABEL = { automatico: 'según sábana', manual: 'manual', registro: 'próximo de un registro' };
    var DAY = 86400000;

    function toUtc(iso) {
        var p = String(iso).split('-');
        return Date.UTC(+p[0], +p[1] - 1, +p[2]);
    }

    function fromUtc(ms) {
        return new Date(ms).toISOString().slice(0, 10);
    }

    function addDays(iso, n) {
        return fromUtc(toUtc(iso) + n * DAY);
    }

    function daysBetween(fromIso, toIso) {
        return Math.round((toUtc(toIso) - toUtc(fromIso)) / DAY);
    }

    // "Hoy" en Colombia, igual que la base (now() at time zone 'America/Bogota').
    function todayIso(now) {
        return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota' }).format(now || new Date());
    }

    function formatDate(iso) {
        if (!iso) return '—';
        var p = String(iso).split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    }

    function weekBounds(today, offsetWeeks) {
        var weekday = (new Date(toUtc(today)).getUTCDay() + 6) % 7;  // lunes = 0
        var monday = addDays(today, -weekday + 7 * (offsetWeeks || 0));
        return [monday, addDays(monday, 6)];
    }

    function filterAgenda(rows, mode, today) {
        function inRange(r, start, end) {
            return !!r.due_date && r.due_date >= start && r.due_date <= end;
        }
        var overdue = rows.filter(function (r) { return r.status === 'vencido'; });
        var noHistory = rows.filter(function (r) { return r.status === 'sin_registro'; });
        var upcoming = rows.filter(function (r) { return r.status !== 'vencido' && r.status !== 'sin_registro'; });
        var selected, w;
        if (mode === 'atrasados') {
            selected = overdue;
        } else if (mode === 'sin_historial') {
            selected = noHistory;
        } else if (mode === 'semana') {
            w = weekBounds(today, 0);
            selected = overdue.concat(upcoming.filter(function (r) { return inRange(r, w[0], w[1]); }));
        } else if (mode === 'proxima') {
            w = weekBounds(today, 1);
            selected = upcoming.filter(function (r) { return inRange(r, w[0], w[1]); });
        } else if (mode === '4semanas') {
            selected = overdue.concat(upcoming.filter(function (r) { return inRange(r, today, addDays(today, 27)); }));
        } else {
            selected = rows.slice();
        }
        var rank = { vencido: 0, sin_registro: 2 };
        return selected.slice().sort(function (a, b) {
            var ra = rank[a.status] === undefined ? 1 : rank[a.status];
            var rb = rank[b.status] === undefined ? 1 : rank[b.status];
            if (ra !== rb) return ra - rb;
            var da = a.due_date || '9999-12-31';
            var db = b.due_date || '9999-12-31';
            if (da !== db) return da < db ? -1 : 1;
            return a.tag_id < b.tag_id ? -1 : a.tag_id > b.tag_id ? 1 : 0;
        });
    }

    function summary(rows) {
        var overdue = rows.filter(function (r) { return r.status === 'vencido'; });
        return {
            vencidos: overdue.length,
            criticos: overdue.filter(function (r) { return (r.days_overdue || 0) >= CRITICAL_DAYS; }).length,
            sinHistorial: rows.filter(function (r) { return r.status === 'sin_registro'; }).length
        };
    }

    // {text, level}: level = 'critico' | 'vencido' | 'proximo' | 'al_dia' | 'sin_registro' | 'sin_fecha'
    function statusInfo(row) {
        if (row.status === 'vencido') {
            var d = row.days_overdue || 0;
            var text = 'Vencido hace ' + d + (d === 1 ? ' día' : ' días');
            if (d >= CRITICAL_DAYS) return { text: '‼️ ' + text + ' · crítico', level: 'critico' };
            return { text: '🔴 ' + text, level: 'vencido' };
        }
        if (row.status === 'sin_registro') {
            return { text: '⚪ Nunca registrado — registralo para arrancar el conteo', level: 'sin_registro' };
        }
        if (row.status === 'proximo') return { text: '🟠 ' + formatDate(row.due_date), level: 'proximo' };
        if (row.status === 'sin_fecha') return { text: '— Sin fecha', level: 'sin_fecha' };
        return { text: '🟢 ' + formatDate(row.due_date), level: 'al_dia' };
    }

    function rescheduleText(row) {
        if (!row.reschedule_count) return '';
        var parts = ['Reprogramado ×' + row.reschedule_count];
        if (row.original_due_date) parts.push('fecha original ' + formatDate(row.original_due_date));
        if (row.note) parts.push('motivo: ' + row.note);
        return parts.join(' · ');
    }

    // Atraso de un mantenimiento ya hecho contra la fecha que tenía programada.
    function delayText(dueIso, performedIso) {
        if (!dueIso || !performedIso) return '';
        var d = daysBetween(dueIso, performedIso);
        if (d <= 0) return 'A tiempo';
        return 'Hecho con ' + d + (d === 1 ? ' día' : ' días') + ' de atraso';
    }

    // Agrupa por TAG conservando el orden de llegada (el primero de cada TAG manda).
    function groupByTag(rows) {
        var groups = [];
        var byTag = {};
        rows.forEach(function (r) {
            if (!byTag[r.tag_id]) {
                byTag[r.tag_id] = { tag: r.tag_id, rows: [] };
                groups.push(byTag[r.tag_id]);
            }
            byTag[r.tag_id].rows.push(r);
        });
        return groups;
    }

    var api = {
        CRITICAL_DAYS: CRITICAL_DAYS,
        FILTERS: FILTERS,
        SOURCE_LABEL: SOURCE_LABEL,
        addDays: addDays,
        daysBetween: daysBetween,
        todayIso: todayIso,
        formatDate: formatDate,
        weekBounds: weekBounds,
        filterAgenda: filterAgenda,
        summary: summary,
        statusInfo: statusInfo,
        rescheduleText: rescheduleText,
        delayText: delayText,
        groupByTag: groupByTag
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    } else {
        root.MaintAgenda = api;
    }
})(typeof window !== 'undefined' ? window : this);
