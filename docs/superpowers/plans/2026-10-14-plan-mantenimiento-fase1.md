# Plan de mantenimiento por sábana — Fase 1 (base)

> Ejecutado en línea el 2026-10-14. Diseño: [2026-10-14-plan-mantenimiento-design.md](../specs/2026-10-14-plan-mantenimiento-design.md).

**Objetivo:** dejar en Supabase y en Python todo lo necesario para calcular la programación, sin interfaz todavía (las fases 2 y 3 la construyen encima).

**Arquitectura:** migración genérica (sin datos de planta) con el catálogo, el alta atómica y el cálculo como función SQL de fuente única; lógica pura en `maintenance_plan.py` para la biblioteca Excel; script de montaje para plantas nuevas.

**Stack:** PostgreSQL/Supabase (RLS, plpgsql), Python 3.12 + openpyxl + supabase-py, pytest.

---

### Task 1: Biblioteca y lógica pura — ✅

- Archivos: `maintenance_plan.py`, `tests/test_maintenance_plan_lib.py`, `sabana_base.xlsx` (commit previo).
- [x] Tests escritos primero (fallaban por import), luego el módulo.
- [x] `python3 -m pytest tests/test_maintenance_plan_lib.py` → 10 passed.

### Task 2: Migración, alta atómica y cálculo — ✅

- Archivos: `supabase/migrations/20261014120000_maintenance_plan.sql`, `tests/supabase/test_maintenance_plan.py`.
- [x] SQL validado primero en una transacción con rollback (ejemplo DVida, ritmo real, reset, validación de clase).
- [x] Tests escritos primero (fallaban: tablas inexistentes).
- [x] Migración aplicada al stack local: `psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -v ON_ERROR_STOP=1 -1 -f supabase/migrations/20261014120000_maintenance_plan.sql`.
- [x] `python3 -m pytest tests/supabase/test_maintenance_plan.py` → 18 passed.
- [x] Regresión: `python3 -m pytest tests/supabase tests/test_maintenance_plan_lib.py tests/test_generator_feed.py` → 84 passed; `node --test tests/js/*.test.js` → 14 passed.

### Task 3: Montaje de plantas nuevas — ✅

- Archivo: `setup_supabase_planta.sh`.
- [x] `bash -n` ok; sin argumentos muestra uso (exit 1); ref de confirmación distinto cancela.
- [ ] Prueba real contra un proyecto Supabase vacío: pendiente hasta la próxima planta.

### Task 4: Documentación — ✅

- [x] `CLAUDE.md`: sección "Plan de mantenimiento por sábana" + estado de archivos.

### Pendiente fuera de esta fase

- Aplicar la migración en producción (`qgxvukllzuaiyhzegaef`) con `psql`: **requiere confirmación explícita del usuario** (se planificó para la fase 3, puede adelantarse).
- Validar las frecuencias de `sabana_base.xlsx` con el manual del fabricante.
