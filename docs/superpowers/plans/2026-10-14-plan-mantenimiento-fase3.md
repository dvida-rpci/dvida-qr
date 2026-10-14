# Plan de mantenimiento por sábana — Fase 3 (sitio + atrasados)

> Ejecutado en línea el 2026-10-14. Diseño: [2026-10-14-plan-mantenimiento-design.md](../specs/2026-10-14-plan-mantenimiento-design.md) ("Atrasados", "Si la cola crece", "Si olvidan el aplicativo", "Celular primero").

### Task 1: Migración de atrasados — ✅
- `supabase/migrations/20261016120000_overdue_tracking.sql`, `tests/supabase/test_overdue.py` (5). Tests primero; 80/80 Supabase en verde.

### Task 2: Lógica de agenda — ✅
- Python: `filter_agenda` separa "Sin historial", `agenda_summary`, `spread_dates`, `CRITICAL_DAYS` (19 tests).
- JS: `maintenance_agenda.js` + `tests/js/agenda_logic.test.js` (mismos casos que Python; 27 JS en total).

### Task 3: GUI — ✅
- Agenda: resumen con críticos, "Vencido hace N días", reprogramación con fecha original y motivo, selección + "Programar seleccionados" con "Repartir en N semanas"; motivo obligatorio si hay vencidos. Filtrada a TAGs de la plantilla.

### Task 4: Sitio — ✅
- Ficha: aviso de vencidos al escanear, "Próximos mantenimientos", reprogramar (oficina), formulario con horas HMI + actividades + advertencia del "próximo", tarjetas con "Hecho con N días de atraso".
- `mantenimientos.html`: Realizados | Programados con filtro, resumen, tarjeta por equipo, 20 por página, contador en la pestaña. Inicio: franja de vencidos.
- Banner: logos ceden ancho a ≤480 px (resuelve el desborde preexistente de ~30 px a 360 px).

### Task 5: Verificación — ✅
- Navegador headless contra Supabase local, **360 y 390 px**: franja → Programados/Atrasados → ficha con aviso → Próximos → login técnico → registrar con actividad → "Próxima …: fecha" y "Hecho con 46 días de atraso". Overflow 0 en todas. GUI: lote de 2 vencidos repartidos en 2 semanas con motivo, overflow 0.
- Bugs encontrados y corregidos: `hidden` anulado por `display` de `.maint-field`; contadores que incluían TAGs fuera del sitio; plurales.
- Regresión: 105 pytest + 27 node.

### Pendiente
- Aplicar las 3 migraciones del plan en producción (`qgxvukllzuaiyhzegaef`) — requiere confirmación.
- Regenerar `docs/` y push para publicar el sitio (sin las migraciones en producción, el sitio mostraría errores en Próximos/Programados).
- Fase 4: resumen semanal automático (canal por definir).
