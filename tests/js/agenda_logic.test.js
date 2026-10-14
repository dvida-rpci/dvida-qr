const test = require('node:test');
const assert = require('node:assert/strict');
const A = require('../../maintenance_agenda.js');

test('weekBounds: lunes a domingo', () => {
    assert.deepEqual(A.weekBounds('2026-10-14', 0), ['2026-10-12', '2026-10-18']);
    assert.deepEqual(A.weekBounds('2026-10-18', 0), ['2026-10-12', '2026-10-18']);
    assert.deepEqual(A.weekBounds('2026-10-14', 1), ['2026-10-19', '2026-10-25']);
});

test('todayIso usa la hora de Colombia', () => {
    // 2026-10-15 03:00 UTC = 2026-10-14 22:00 en Bogotá
    assert.equal(A.todayIso(new Date(Date.UTC(2026, 9, 15, 3, 0))), '2026-10-14');
});

const AGENDA = [
    { tag_id: 'B', due_date: '2026-10-16', status: 'proximo' },
    { tag_id: 'A', due_date: '2026-10-20', status: 'proximo' },
    { tag_id: 'C', due_date: null, status: 'sin_registro' },
    { tag_id: 'D', due_date: '2026-10-01', status: 'vencido', days_overdue: 13 },
    { tag_id: 'E', due_date: '2026-12-07', status: 'al_dia' },
];

for (const [mode, tags] of [
    ['semana', ['D', 'B']],
    ['atrasados', ['D']],
    ['sin_historial', ['C']],
    ['proxima', ['A']],
    ['4semanas', ['D', 'B', 'A']],
    ['todo', ['D', 'B', 'A', 'E', 'C']],
]) {
    test(`filterAgenda ${mode} (mismo resultado que maintenance_plan.filter_agenda)`, () => {
        assert.deepEqual(A.filterAgenda(AGENDA, mode, '2026-10-14').map(r => r.tag_id), tags);
    });
}

test('summary separa críticos y sin historial', () => {
    assert.deepEqual(A.summary([
        { status: 'vencido', days_overdue: 45 },
        { status: 'vencido', days_overdue: 3 },
        { status: 'sin_registro' },
        { status: 'proximo' },
    ]), { vencidos: 2, criticos: 1, sinHistorial: 1 });
});

test('statusInfo', () => {
    assert.deepEqual(A.statusInfo({ status: 'vencido', days_overdue: 1 }), { text: '🔴 Vencido hace 1 día', level: 'vencido' });
    assert.deepEqual(A.statusInfo({ status: 'vencido', days_overdue: 30 }),
        { text: '‼️ Vencido hace 30 días · crítico', level: 'critico' });
    assert.equal(A.statusInfo({ status: 'sin_registro' }).level, 'sin_registro');
    assert.equal(A.statusInfo({ status: 'proximo', due_date: '2026-10-16' }).text, '🟠 16/10/2026');
});

test('rescheduleText', () => {
    assert.equal(A.rescheduleText({ reschedule_count: 0 }), '');
    assert.equal(
        A.rescheduleText({ reschedule_count: 2, original_due_date: '2026-12-07', note: 'falta repuesto' }),
        'Reprogramado ×2 · fecha original 07/12/2026 · motivo: falta repuesto');
});

test('delayText mide contra la fecha programada', () => {
    assert.equal(A.delayText('2026-12-07', '2026-12-19'), 'Hecho con 12 días de atraso');
    assert.equal(A.delayText('2026-12-07', '2026-12-08'), 'Hecho con 1 día de atraso');
    assert.equal(A.delayText('2026-12-07', '2026-12-07'), 'A tiempo');
    assert.equal(A.delayText(null, '2026-12-07'), '');
});

test('groupByTag conserva el orden', () => {
    const groups = A.groupByTag([
        { tag_id: 'X', activity_name: '1' }, { tag_id: 'Y', activity_name: '2' }, { tag_id: 'X', activity_name: '3' },
    ]);
    assert.deepEqual(groups.map(g => [g.tag, g.rows.map(r => r.activity_name)]), [['X', ['1', '3']], ['Y', ['2']]]);
});
