# Plan de mantenimiento por sábana — Fase 2 (GUI)

> Ejecutado en línea el 2026-10-14. Diseño: [2026-10-14-plan-mantenimiento-design.md](../specs/2026-10-14-plan-mantenimiento-design.md).

**Objetivo:** programación manual con advertencia de duplicados, agenda unificada y la ventana "📋 Plan de mantenimiento" en `gui.py`; registro con actividades y horas HMI en 🧰 Mantenimientos.

**Stack:** PostgreSQL/Supabase (RLS, plpgsql), Python 3.12 + NiceGUI 3 (Quasar) + supabase-py, pytest, navegador headless (patchright).

---

### Task 1: Migración de programación manual — ✅

- Archivos: `supabase/migrations/20261015120000_maintenance_manual_schedule.sql`, `tests/supabase/test_manual_schedule.py`.
- [x] Tests primero (fallaban: objetos inexistentes); migración aplicada en local con `psql`.
- [x] Bug encontrado por los tests: un manual se daba por cumplido con un registro del mismo día cargado *antes* de programarlo. Regla corregida: cumple un registro con `created_at` posterior. Spec actualizado.
- [x] 7 passed.

### Task 2: Filtros de agenda (lógica pura) — ✅

- Archivos: `maintenance_plan.py` (`week_bounds`, `filter_agenda`, `AGENDA_FILTERS`), `tests/test_maintenance_plan_lib.py`.
- [x] 16 passed (10 de fase 1 + 6 nuevos).

### Task 3: 🧰 Mantenimientos — ✅

- Archivo: `gui_maintenance.py`.
- [x] Login extraído a `render_login_card` (compartido con `gui_plan.py`).
- [x] Alta vía `create_maintenance_record` con horas HMI y casillas de actividades; "Próximo programado" se oculta si hay actividades y avisa antes de sobrescribir lo programado (`confirm_overwrite`).
- [x] Edición de oficina: horas HMI y actividades. Tarjeta muestra actividades y horas.

### Task 4: Ventana "📋 Plan de mantenimiento" — ✅

- Archivos: `gui_plan.py`, `gui.py` (botón).
- [x] Pestañas Agenda / Sábana / Equipos; cada una se recarga al entrar (bug encontrado en el navegador: Equipos no veía las clases recién importadas).

### Task 5: Verificación en navegador — ✅

- [x] Contra Supabase local: importar sábana base, auto-asignar (propone las 7 centrífugas con pares), programar manual (sin conflicto guarda; repetido muestra la advertencia y deja el anterior `reemplazado`), registrar lubricación en 200-P-01A → próxima 2027-01-06.
- [x] Celular 360/390 px: principal, Mantenimientos (historial y registrar), Plan (3 pestañas y programar manual) sin desborde; pestañas sin flechas. Arreglos: filas → tarjetas de dos líneas, toggle → select, `truncate w-full` en servicios largos, pestañas cortas.

### Task 6: Regresión y documentación — ✅

- [x] `python3 -m pytest tests/supabase tests/test_maintenance_plan_lib.py tests/test_generator_feed.py` → 97 passed; `node --test tests/js/*.test.js` → 14 passed.
- [x] `CLAUDE.md` y spec actualizados.

### Pendiente

- Aplicar `20261014120000_maintenance_plan.sql` y `20261015120000_maintenance_manual_schedule.sql` en producción (`qgxvukllzuaiyhzegaef`) con `psql`: **requiere confirmación explícita**.
