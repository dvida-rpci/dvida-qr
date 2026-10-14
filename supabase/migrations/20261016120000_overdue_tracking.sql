-- Atrasados: trazabilidad de reprogramaciones y atraso real al registrar
-- (diseño 2026-10-14-plan-mantenimiento-design.md, "Atrasados").

alter table public.maintenance_manual_schedule
  add column previous_due_date date,
  add column original_due_date date,
  add column reschedule_count integer not null default 0;

-- Fecha que tenía programada la actividad al registrarse (la original si fue reprogramada).
alter table public.maintenance_record_activities
  add column due_date date;

-- ── Agenda con datos de atraso ───────────────────────────────────────────
-- Cambia el tipo de retorno: hay que recrear vista y función.

drop view public.maintenance_agenda;
drop function public.maintenance_agenda_at(date);

create function public.maintenance_agenda_at(p_today date)
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
    select distinct on (r.tag_id) r.tag_id, r.next_scheduled_at, r.created_at,
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
    select m.tag_id, m.activity_id, coalesce(a.name, 'Libre'), m.scheduled_for, null,
           'manual', m.id, m.note, m.original_due_date, m.reschedule_count
    from manual m
    left join public.maintenance_activities a on a.id = m.activity_id
    union all
    select lr.tag_id, null, 'Libre', lr.next_scheduled_at, null, 'registro', null, null, null, 0
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

grant execute on function public.maintenance_agenda_at(date) to anon, authenticated;

create view public.maintenance_agenda
with (security_invoker = true) as
  select * from public.maintenance_agenda_at((now() at time zone 'America/Bogota')::date);

revoke all on public.maintenance_agenda from anon, authenticated;
grant select on public.maintenance_agenda to anon, authenticated;

-- ── Reprogramar: motivo obligatorio si lo reemplazado está vencido ───────

create or replace function public.schedule_manual(
  p_tag text,
  p_activity uuid,
  p_date date,
  p_note text default null,
  p_replace boolean default false
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_today date := (now() at time zone 'America/Bogota')::date;
  v_conflicts jsonb;
  v_others jsonb;
  v_first jsonb;
  v_id uuid;
begin
  if not public.is_oficina() then
    raise exception 'Solo oficina puede programar mantenimientos' using errcode = '42501';
  end if;
  if p_activity is not null and not exists (
    select 1 from public.equipment_tags t
    join public.maintenance_activities a on a.class_id = t.class_id
    where t.tag_id = p_tag and a.id = p_activity and a.active
  ) then
    raise exception 'La actividad no corresponde a la clase del TAG % o está inactiva', p_tag
      using errcode = 'P0001';
  end if;

  select coalesce(jsonb_agg(to_jsonb(a) order by a.due_date), '[]'::jsonb) into v_conflicts
  from public.maintenance_agenda_at(v_today) a
  where a.tag_id = p_tag and a.due_date is not null
    and a.activity_id is not distinct from p_activity;

  select coalesce(jsonb_agg(to_jsonb(a) order by a.due_date), '[]'::jsonb) into v_others
  from public.maintenance_agenda_at(v_today) a
  where a.tag_id = p_tag and a.due_date is not null
    and a.activity_id is distinct from p_activity;

  if jsonb_array_length(v_conflicts) > 0 and not p_replace then
    return jsonb_build_object('status', 'conflict', 'conflicts', v_conflicts, 'others', v_others);
  end if;

  v_first := v_conflicts -> 0;
  if v_first is not null and v_first->>'status' = 'vencido' and coalesce(btrim(p_note), '') = '' then
    raise exception 'Indicá el motivo: lo que se reprograma está vencido' using errcode = 'P0001';
  end if;

  insert into public.maintenance_manual_schedule
    (tag_id, activity_id, scheduled_for, note,
     previous_due_date, original_due_date, reschedule_count)
  values (
    p_tag, p_activity, p_date, nullif(btrim(p_note), ''),
    (v_first->>'due_date')::date,
    coalesce((v_first->>'original_due_date')::date, (v_first->>'due_date')::date),
    case when v_first is null then 0
         else coalesce((v_first->>'reschedule_count')::int, 0) + 1 end
  )
  returning id into v_id;

  update public.maintenance_manual_schedule
  set status = 'reemplazado', replaced_by = v_id
  where tag_id = p_tag and activity_id is not distinct from p_activity
    and status = 'pendiente' and id <> v_id;

  return jsonb_build_object('status', 'ok', 'id', v_id, 'others', v_others);
end;
$$;

-- ── Alta: guarda la fecha que tenía programada cada actividad ────────────

create or replace function public.create_maintenance_record(
  p_record jsonb,
  p_activity_ids uuid[] default '{}'
)
returns uuid
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_id uuid;
  v_due jsonb;
begin
  -- Antes de insertar: después el registro nuevo ya movería la programación.
  select coalesce(jsonb_object_agg(a.activity_id, coalesce(a.original_due_date, a.due_date)),
                  '{}'::jsonb)
  into v_due
  from public.maintenance_agenda_at((now() at time zone 'America/Bogota')::date) a
  where a.tag_id = p_record->>'tag_id'
    and a.activity_id = any(coalesce(p_activity_ids, '{}'));

  insert into public.maintenance_records
    (tag_id, performed_at, type, description, parts_used, next_scheduled_at, hmi_hours)
  values (
    p_record->>'tag_id',
    (p_record->>'performed_at')::date,
    p_record->>'type',
    p_record->>'description',
    nullif(p_record->>'parts_used', ''),
    nullif(p_record->>'next_scheduled_at', '')::date,
    nullif(p_record->>'hmi_hours', '')::numeric
  )
  returning id into v_id;

  insert into public.maintenance_record_activities (record_id, activity_id, due_date)
  select v_id, a, (v_due->>a::text)::date
  from unnest(coalesce(p_activity_ids, '{}')) as a;

  return v_id;
end;
$$;
