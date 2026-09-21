'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const feed = require('../../maintenance_feed.js');

const INDEX = [
    { tag: '100-P-01A', categoria: 'EQUIPOS', servicio: 'Bomba de alimentación', filename: '100-P-01A.html' },
    { tag: '100-TK-01', categoria: 'TANQUES', servicio: 'Tanque de aireación', filename: '100-TK-01.html' },
    { tag: '600-SV-01', categoria: 'INSTRUMENTOS', servicio: 'Válvula solenoide', filename: '600-SV-01.html' },
    { tag: '200-P-01B', categoria: 'EQUIPOS', servicio: '', filename: '200-P-01B.html' },
];

test('normalize quita tildes, pasa a minúsculas y recorta', () => {
    assert.equal(feed.normalize('  Válvula SOLENOIDE '), 'valvula solenoide');
    assert.equal(feed.normalize(null), '');
});

test('escapeHtml escapa los 5 caracteres peligrosos', () => {
    assert.equal(feed.escapeHtml('<a href="x">&\'</a>'), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;');
});

test('formatDate pasa ISO a dd/mm/aaaa', () => {
    assert.equal(feed.formatDate('2026-09-21'), '21/09/2026');
});

test('filterTags sin filtros devuelve todo', () => {
    assert.equal(feed.filterTags(INDEX, 'TODOS', '').length, 4);
});

test('filterTags por categoría', () => {
    const tags = feed.filterTags(INDEX, 'EQUIPOS', '').map((e) => e.tag);
    assert.deepEqual(tags, ['100-P-01A', '200-P-01B']);
});

test('filterTags por TAG parcial sin distinguir mayúsculas', () => {
    const tags = feed.filterTags(INDEX, 'TODOS', '100-p').map((e) => e.tag);
    assert.deepEqual(tags, ['100-P-01A']);
});

test('filterTags por servicio sin distinguir tildes', () => {
    const tags = feed.filterTags(INDEX, 'TODOS', 'valvula').map((e) => e.tag);
    assert.deepEqual(tags, ['600-SV-01']);
});

test('filterTags combina categoría y texto (intersección)', () => {
    assert.deepEqual(feed.filterTags(INDEX, 'TANQUES', 'bomba'), []);
    assert.equal(feed.filterTags(INDEX, 'EQUIPOS', 'bomba').length, 1);
});

test('hasFilter', () => {
    assert.equal(feed.hasFilter('TODOS', ''), false);
    assert.equal(feed.hasFilter('TODOS', '   '), false);
    assert.equal(feed.hasFilter('EQUIPOS', ''), true);
    assert.equal(feed.hasFilter('TODOS', 'bomba'), true);
});

test('splitPage recorta a size y detecta si hay más', () => {
    const rows = Array.from({ length: 11 }, (_, i) => ({ id: i }));
    const page = feed.splitPage(rows, 10);
    assert.equal(page.rows.length, 10);
    assert.equal(page.hasMore, true);
    assert.equal(feed.splitPage(rows.slice(0, 10), 10).hasMore, false);
});

test('mergeRecords agrupa adjuntos y resuelve autor (con fallback)', () => {
    const records = [
        { id: 'r1', created_by: 'u1' },
        { id: 'r2', created_by: 'u-desconocido' },
    ];
    const attachments = [
        { id: 'a1', record_id: 'r1', kind: 'photo' },
        { id: 'a2', record_id: 'r1', kind: 'audio' },
    ];
    const authors = [{ user_id: 'u1', full_name: 'Ana' }];
    const merged = feed.mergeRecords(records, attachments, authors);
    assert.equal(merged[0].attachments.length, 2);
    assert.equal(merged[0].author_name, 'Ana');
    assert.equal(merged[1].attachments.length, 0);
    assert.equal(merged[1].author_name, 'Usuario desconocido');
});

test('stepIndex avanza y retrocede con vuelta circular', () => {
    assert.equal(feed.stepIndex(0, -1, 3), 2);
    assert.equal(feed.stepIndex(2, 1, 3), 0);
    assert.equal(feed.stepIndex(1, 1, 3), 2);
});

test('fichaHref arma la ruta relativa a la raíz', () => {
    assert.equal(feed.fichaHref(INDEX[0]), 'equipos/100-P-01A.html');
    assert.equal(feed.fichaHref(INDEX[2]), 'instrumentos/600-SV-01.html');
});

test('indexByTag indexa por TAG', () => {
    assert.equal(feed.indexByTag(INDEX)['100-TK-01'].categoria, 'TANQUES');
});
