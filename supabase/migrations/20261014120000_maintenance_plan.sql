-- Plan de mantenimiento por sábana (diseño 2026-10-14-plan-mantenimiento-design.md).
-- Migración genérica: NO contiene datos de ninguna planta. Las clases y actividades
-- se cargan desde sabana_base.xlsx con la ventana "Plan de mantenimiento" de gui.py.

-- ── 1. Tablas ─────────────────────────────────────────────────────────────

create table public.equipment_classes (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  hours_per_day numeric not null check (hours_per_day > 0 and hours_per_day <= 24),
  updated_by uuid default auth.uid() references auth.users(id),
  updated_at timestamptz not null default now()
);

create table public.maintenance_activities (
  id uuid primary key default gen_random_uuid(),
  class_id uuid not null references public.equipment_classes(id) on delete restrict,
  code text not null,
  name text not null,
  interval_hours numeric check (interval_hours > 0),
  interval_weeks integer check (interval_weeks > 0),
  active boolean not null default true,
  updated_by uuid default auth.uid() references auth.users(id),
  updated_at timestamptz not null default now(),
  unique (class_id, code),
  check (interval_hours is not null or interval_weeks is not null)
);

create table public.equipment_tags (
  tag_id text primary key,
  class_id uuid references public.equipment_classes(id) on delete restrict,
  group_key text,
  regime text not null default 'normal'
    check (regime in ('normal', 'alterna', 'principal', 'reserva')),
  updated_by uuid default auth.uid() references auth.users(id),
  updated_at timestamptz not null default now()
);

create index equipment_tags_group_key_idx on public.equipment_tags (group_key);

create table public.maintenance_record_activities (
  record_id uuid not null references public.maintenance_records(id) on delete cascade,
  activity_id uuid not null references public.maintenance_activities(id) on delete restrict,
  primary key (record_id, activity_id)
);

create index maintenance_record_activities_activity_idx
  on public.maintenance_record_activities (activity_id);

alter table public.maintenance_records
  add column hmi_hours numeric check (hmi_hours >= 0);

-- ── 2. updated_at / updated_by automáticos en el catálogo ────────────────

create or replace function public.touch_updated()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end;
$$;

create trigger equipment_classes_touch before update on public.equipment_classes
  for each row execute function public.touch_updated();
create trigger maintenance_activities_touch before update on public.maintenance_activities
  for each row execute function public.touch_updated();
create trigger equipment_tags_touch before update on public.equipment_tags
  for each row execute function public.touch_updated();

-- ── 3. Una actividad solo se registra en un TAG de su clase, y activa ────

create or replace function public.check_record_activity()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_tag text;
  v_tag_class uuid;
  v_act public.maintenance_activities%rowtype;
begin
  select tag_id into v_tag from public.maintenance_records where id = new.record_id;
  select class_id into v_tag_class from public.equipment_tags where tag_id = v_tag;
  select * into v_act from public.maintenance_activities where id = new.activity_id;

  if v_act.id is null or not v_act.active then
    raise exception 'La actividad no existe o está inactiva' using errcode = 'P0001';
  end if;
  if v_tag_class is distinct from v_act.class_id then
    raise exception 'La actividad "%" no corresponde a la clase del TAG %', v_act.name, v_tag
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create trigger maintenance_record_activities_check
  before insert on public.maintenance_record_activities
  for each row execute function public.check_record_activity();

-- ── 4. RLS ────────────────────────────────────────────────────────────────

alter table public.equipment_classes enable row level security;
alter table public.maintenance_activities enable row level security;
alter table public.equipment_tags enable row level security;
alter table public.maintenance_record_activities enable row level security;

-- Lectura pública, como el resto del histórico (migración 20260921210000).
create policy "equipment_classes_select_public" on public.equipment_classes
  for select to anon, authenticated using (true);
create policy "maintenance_activities_select_public" on public.maintenance_activities
  for select to anon, authenticated using (true);
create policy "equipment_tags_select_public" on public.equipment_tags
  for select to anon, authenticated using (true);
create policy "maintenance_record_activities_select_public" on public.maintenance_record_activities
  for select to anon, authenticated using (true);

-- El catálogo (sábana + asignación de equipos) solo lo edita oficina.
create policy "equipment_classes_insert_oficina" on public.equipment_classes
  for insert to authenticated with check (public.is_oficina());
create policy "equipment_classes_update_oficina" on public.equipment_classes
  for update to authenticated using (public.is_oficina()) with check (public.is_oficina());
create policy "equipment_classes_delete_oficina" on public.equipment_classes
  for delete to authenticated using (public.is_oficina());

create policy "maintenance_activities_insert_oficina" on public.maintenance_activities
  for insert to authenticated with check (public.is_oficina());
create policy "maintenance_activities_update_oficina" on public.maintenance_activities
  for update to authenticated using (public.is_oficina()) with check (public.is_oficina());
create policy "maintenance_activities_delete_oficina" on public.maintenance_activities
  for delete to authenticated using (public.is_oficina());

create policy "equipment_tags_insert_oficina" on public.equipment_tags
  for insert to authenticated with check (public.is_oficina());
create policy "equipment_tags_update_oficina" on public.equipment_tags
  for update to authenticated using (public.is_oficina()) with check (public.is_oficina());
create policy "equipment_tags_delete_oficina" on public.equipment_tags
  for delete to authenticated using (public.is_oficina());

-- Actividades de un registro: las agrega su autor (o oficina); solo oficina las quita.
create policy "maintenance_record_activities_insert_own" on public.maintenance_record_activities
  for insert to authenticated
  with check (
    public.is_member()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );
create policy "maintenance_record_activities_delete_oficina" on public.maintenance_record_activities
  for delete to authenticated using (public.is_oficina());

-- ── 5. Alta atómica: registro + actividades en una sola transacción ──────

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
begin
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

  insert into public.maintenance_record_activities (record_id, activity_id)
  select v_id, a from unnest(coalesce(p_activity_ids, '{}')) as a;

  return v_id;
end;
$$;

revoke execute on function public.create_maintenance_record(jsonb, uuid[]) from public, anon;
grant execute on function public.create_maintenance_record(jsonb, uuid[]) to authenticated;

-- ── 6. Cálculo de la programación (fuente única: sitio y GUI solo leen) ──

create or replace function public.maintenance_schedule_at(p_today date)
returns table (
  tag_id text,
  class_id uuid,
  class_name text,
  activity_id uuid,
  activity_code text,
  activity_name text,
  interval_hours numeric,
  interval_weeks integer,
  regime text,
  last_done_at date,
  last_record_id uuid,
  last_hmi_hours numeric,
  rate_hours_per_day numeric,
  rate_source text,
  due_hours numeric,
  due_date date,
  status text
)
language sql
stable
security invoker
set search_path = public
as $$
  with tags as (
    select t.tag_id, t.class_id, t.regime, t.group_key, c.name as class_name, c.hours_per_day
    from public.equipment_tags t
    join public.equipment_classes c on c.id = t.class_id
  ),
  readings as (
    select r.tag_id, r.performed_at, r.hmi_hours,
           row_number() over (
             partition by r.tag_id order by r.performed_at desc, r.created_at desc
           ) as rn
    from public.maintenance_records r
    where r.hmi_hours is not null
      and r.performed_at <= p_today
      and r.tag_id in (select tag_id from tags)
  ),
  latest as (select tag_id, performed_at, hmi_hours from readings where rn = 1),
  prev as (select tag_id, hmi_hours from readings where rn = 2),
  -- Lectura más antigua dentro de los 180 días previos a la última, separada al menos 7 días.
  earliest as (
    select distinct on (rd.tag_id) rd.tag_id, rd.performed_at, rd.hmi_hours
    from readings rd
    join latest l on l.tag_id = rd.tag_id
    where rd.performed_at >= l.performed_at - 180
      and rd.performed_at <= l.performed_at - 7
    order by rd.tag_id, rd.performed_at asc
  ),
  rate as (
    select
      t.tag_id,
      -- Sin ritmo real si el contador bajó (reset o cambio de PLC).
      case
        when e.tag_id is not null
             and l.hmi_hours >= e.hmi_hours
             and (p.hmi_hours is null or l.hmi_hours >= p.hmi_hours)
        then least((l.hmi_hours - e.hmi_hours) / (l.performed_at - e.performed_at), 24)
      end as real_rate,
      case t.regime
        when 'reserva' then 0
        when 'alterna' then t.hours_per_day / greatest(1, (
          select count(*) from public.equipment_tags g
          where g.group_key = t.group_key and g.regime = 'alterna'
        ))
        else t.hours_per_day
      end as est_rate,
      l.performed_at as latest_at,
      l.hmi_hours as latest_hours
    from tags t
    left join latest l on l.tag_id = t.tag_id
    left join prev p on p.tag_id = t.tag_id
    left join earliest e on e.tag_id = t.tag_id
  ),
  last_done as (
    select distinct on (r.tag_id, ra.activity_id)
           r.tag_id, ra.activity_id, r.id as record_id, r.performed_at, r.hmi_hours
    from public.maintenance_records r
    join public.maintenance_record_activities ra on ra.record_id = r.id
    where r.performed_at <= p_today
    order by r.tag_id, ra.activity_id, r.performed_at desc, r.created_at desc
  ),
  base as (
    select
      t.tag_id, t.class_id, t.class_name, t.regime,
      a.id as activity_id, a.code as activity_code, a.name as activity_name,
      a.interval_hours, a.interval_weeks,
      ld.performed_at as last_done_at, ld.record_id as last_record_id,
      ld.hmi_hours as last_hmi_hours,
      coalesce(rt.real_rate, rt.est_rate) as rate,
      case when rt.real_rate is not null then 'real' else 'estimado' end as rate_source,
      rt.latest_at, rt.latest_hours
    from tags t
    join public.maintenance_activities a on a.class_id = t.class_id and a.active
    join rate rt on rt.tag_id = t.tag_id
    left join last_done ld on ld.tag_id = t.tag_id and ld.activity_id = a.id
  ),
  dates as (
    select
      b.*,
      case when b.last_hmi_hours is not null and b.interval_hours is not null
           then b.last_hmi_hours + b.interval_hours end as due_hours,
      -- Días truncados hacia abajo: mejor temprano que tarde.
      case
        when b.last_done_at is null or b.interval_hours is null or b.rate <= 0 then null
        when b.last_hmi_hours is not null and b.latest_hours >= b.last_hmi_hours
          then b.latest_at
               + floor((b.last_hmi_hours + b.interval_hours - b.latest_hours) / b.rate)::int
        else b.last_done_at + floor(b.interval_hours / b.rate)::int
      end as by_hours,
      case when b.last_done_at is not null and b.interval_weeks is not null
           then b.last_done_at + 7 * b.interval_weeks end as by_weeks
    from base b
  )
  select
    d.tag_id, d.class_id, d.class_name, d.activity_id, d.activity_code, d.activity_name,
    d.interval_hours, d.interval_weeks, d.regime,
    d.last_done_at, d.last_record_id, d.last_hmi_hours,
    round(d.rate, 2) as rate_hours_per_day, d.rate_source, d.due_hours,
    least(d.by_hours, d.by_weeks) as due_date,
    case
      when d.last_done_at is null then 'sin_registro'
      when least(d.by_hours, d.by_weeks) is null then 'sin_fecha'
      when least(d.by_hours, d.by_weeks) < p_today then 'vencido'
      when least(d.by_hours, d.by_weeks) <= p_today + 14 then 'proximo'
      else 'al_dia'
    end as status
  from dates d;
$$;

grant execute on function public.maintenance_schedule_at(date) to anon, authenticated;

create view public.maintenance_schedule
with (security_invoker = true) as
  select * from public.maintenance_schedule_at((now() at time zone 'America/Bogota')::date);

-- Supabase concede ALL por defecto sobre objetos nuevos de public: solo lectura.
revoke all on public.maintenance_schedule from anon, authenticated;
grant select on public.maintenance_schedule to anon, authenticated;
