-- La agenda deja de mostrar "Libre": dice qué hay que hacer
-- (diseño 2026-10-14-plan-mantenimiento-design.md, "Fuera del plan").
--   * "próximo" de un registro sin actividades → "Off-plan · <descripción del registro>"
--   * programación manual sin actividad → "Off-plan · <nota>", o solo "Off-plan"
-- "Off-plan" = fuera de la sábana (nombre corto elegido por el usuario).
-- Mismo tipo de retorno: basta con reemplazar la función (la vista no cambia).

create or replace function public.maintenance_agenda_at(p_today date)
returns table (
  tag_id text,
  activity_id uuid,
  activity_name text,
  due_date date,
  status text,
  source text,
  manual_id uuid,
  note text,
  original_due_date date,
  reschedule_count integer,
  days_overdue integer
)
language sql
stable
security invoker
set search_path = public
as $$
  with manual as (
    -- Pendientes no cumplidos: se cumplen con un registro del TAG (con esa actividad,
    -- si la tiene) cargado después de programarlo.
    select m.*
    from public.maintenance_manual_schedule m
    where m.status = 'pendiente'
      and not exists (
        select 1 from public.maintenance_records r
        where r.tag_id = m.tag_id
          and r.created_at > m.created_at
          and r.performed_at <= p_today
          and (
            m.activity_id is null
            or exists (
              select 1 from public.maintenance_record_activities ra
              where ra.record_id = r.id and ra.activity_id = m.activity_id
            )
          )
      )
  ),
  latest_record as (
    select distinct on (r.tag_id) r.tag_id, r.next_scheduled_at, r.created_at, r.description,
           exists (select 1 from public.maintenance_record_activities ra
                   where ra.record_id = r.id) as has_activities
    from public.maintenance_records r
    where r.performed_at <= p_today
    order by r.tag_id, r.performed_at desc, r.created_at desc
  ),
  rows as (
    select s.tag_id, s.activity_id, s.activity_name, s.due_date, s.status,
           'automatico'::text as source, null::uuid as manual_id, null::text as note,
           null::date as original_due_date, 0 as reschedule_count
    from public.maintenance_schedule_at(p_today) s
    where not exists (
      select 1 from manual m where m.tag_id = s.tag_id and m.activity_id = s.activity_id
    )
    union all
    select m.tag_id, m.activity_id,
           coalesce(a.name, 'Off-plan' || coalesce(' · ' || nullif(btrim(m.note), ''), '')),
           m.scheduled_for, null,
           'manual', m.id, m.note, m.original_due_date, m.reschedule_count
    from manual m
    left join public.maintenance_activities a on a.id = m.activity_id
    union all
    select lr.tag_id, null,
           'Off-plan · ' || left(lr.description, 60)
             || case when length(lr.description) > 60 then '…' else '' end,
           lr.next_scheduled_at, null, 'registro', null, null, null, 0
    from latest_record lr
    where lr.next_scheduled_at is not null
      and not lr.has_activities
      and not exists (
        select 1 from manual m
        where m.tag_id = lr.tag_id and m.activity_id is null and m.created_at > lr.created_at
      )
  ),
  with_status as (
    select r.*,
           coalesce(r.status, case
             when r.due_date < p_today then 'vencido'
             when r.due_date <= p_today + 14 then 'proximo'
             else 'al_dia'
           end) as final_status
    from rows r
  )
  select w.tag_id, w.activity_id, w.activity_name, w.due_date, w.final_status, w.source,
         w.manual_id, w.note, w.original_due_date, w.reschedule_count,
         case when w.final_status = 'vencido' then p_today - w.due_date end
  from with_status w;
$$;

