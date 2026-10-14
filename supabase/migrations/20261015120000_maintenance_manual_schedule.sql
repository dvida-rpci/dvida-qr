-- Programación manual con advertencia de duplicados + agenda unificada
-- (diseño 2026-10-14-plan-mantenimiento-design.md, "Programación manual").

create table public.maintenance_manual_schedule (
  id uuid primary key default gen_random_uuid(),
  tag_id text not null,
  activity_id uuid references public.maintenance_activities(id) on delete restrict,
  scheduled_for date not null,
  note text,
  status text not null default 'pendiente'
    check (status in ('pendiente', 'reemplazado', 'cancelado')),
  replaced_by uuid references public.maintenance_manual_schedule(id),
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now()
);

create index maintenance_manual_schedule_tag_idx
  on public.maintenance_manual_schedule (tag_id) where status = 'pendiente';

alter table public.maintenance_manual_schedule enable row level security;

create policy "maintenance_manual_schedule_select_public" on public.maintenance_manual_schedule
  for select to anon, authenticated using (true);
create policy "maintenance_manual_schedule_insert_oficina" on public.maintenance_manual_schedule
  for insert to authenticated with check (public.is_oficina());
create policy "maintenance_manual_schedule_update_oficina" on public.maintenance_manual_schedule
  for update to authenticated using (public.is_oficina()) with check (public.is_oficina());

-- ── Agenda: automático (sábana) + manual + "próximo" de registros libres ──

create or replace function public.maintenance_agenda_at(p_today date)
returns table (
  tag_id text,
  activity_id uuid,
  activity_name text,
  due_date date,
  status text,
  source text,
  manual_id uuid,
  note text
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
           'automatico'::text as source, null::uuid as manual_id, null::text as note
    from public.maintenance_schedule_at(p_today) s
    where not exists (
      select 1 from manual m where m.tag_id = s.tag_id and m.activity_id = s.activity_id
    )
    union all
    select m.tag_id, m.activity_id, coalesce(a.name, 'Libre'), m.scheduled_for, null,
           'manual', m.id, m.note
    from manual m
    left join public.maintenance_activities a on a.id = m.activity_id
    union all
    select lr.tag_id, null, 'Libre', lr.next_scheduled_at, null, 'registro', null, null
    from latest_record lr
    where lr.next_scheduled_at is not null
      and not lr.has_activities
      and not exists (
        select 1 from manual m
        where m.tag_id = lr.tag_id and m.activity_id is null and m.created_at > lr.created_at
      )
  )
  select r.tag_id, r.activity_id, r.activity_name, r.due_date,
         coalesce(r.status, case
           when r.due_date < p_today then 'vencido'
           when r.due_date <= p_today + 14 then 'proximo'
           else 'al_dia'
         end),
         r.source, r.manual_id, r.note
  from rows r;
$$;

grant execute on function public.maintenance_agenda_at(date) to anon, authenticated;

create view public.maintenance_agenda
with (security_invoker = true) as
  select * from public.maintenance_agenda_at((now() at time zone 'America/Bogota')::date);

revoke all on public.maintenance_agenda from anon, authenticated;
grant select on public.maintenance_agenda to anon, authenticated;

-- ── Programar a mano: avisa si ya hay algo programado para ese TAG ───────
-- Mismo TAG + misma actividad (o libre + libre) = conflicto: no guarda salvo p_replace.
-- Lo programado para otras actividades se devuelve en "others" como aviso.

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

  insert into public.maintenance_manual_schedule (tag_id, activity_id, scheduled_for, note)
  values (p_tag, p_activity, p_date, nullif(p_note, ''))
  returning id into v_id;

  update public.maintenance_manual_schedule
  set status = 'reemplazado', replaced_by = v_id
  where tag_id = p_tag and activity_id is not distinct from p_activity
    and status = 'pendiente' and id <> v_id;

  return jsonb_build_object('status', 'ok', 'id', v_id, 'others', v_others);
end;
$$;

revoke execute on function public.schedule_manual(text, uuid, date, text, boolean) from public, anon;
grant execute on function public.schedule_manual(text, uuid, date, text, boolean) to authenticated;
