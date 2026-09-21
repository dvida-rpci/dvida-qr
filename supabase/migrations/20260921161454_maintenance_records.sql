create table public.maintenance_records (
  id uuid primary key default gen_random_uuid(),
  tag_id text not null,
  performed_at date not null,
  type text not null check (type in ('preventivo', 'correctivo')),
  description text not null,
  parts_used text,
  next_scheduled_at date,
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now(),
  -- Zona fija: created_at::date depende del TimeZone de la sesión y no es inmutable
  is_date_anomaly boolean generated always as (
    abs((created_at at time zone 'America/Bogota')::date - performed_at) > 2
  ) stored
);

create index maintenance_records_tag_id_idx on public.maintenance_records (tag_id);

alter table public.maintenance_records enable row level security;

create policy "maintenance_records_select_authenticated"
  on public.maintenance_records for select
  to authenticated
  using (true);

create policy "maintenance_records_insert_own"
  on public.maintenance_records for insert
  to authenticated
  with check (created_by = auth.uid());

create policy "maintenance_records_update_oficina"
  on public.maintenance_records for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_records_delete_oficina"
  on public.maintenance_records for delete
  to authenticated
  using (public.is_oficina());
