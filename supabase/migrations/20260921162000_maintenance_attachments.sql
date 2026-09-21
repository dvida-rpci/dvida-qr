create table public.maintenance_attachments (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null references public.maintenance_records(id) on delete cascade,
  kind text not null check (kind in ('photo', 'audio')),
  storage_path text not null,
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now()
);

create index maintenance_attachments_record_id_idx on public.maintenance_attachments (record_id);

alter table public.maintenance_attachments enable row level security;

create policy "maintenance_attachments_select_authenticated"
  on public.maintenance_attachments for select
  to authenticated
  using (true);

create policy "maintenance_attachments_insert_own_record_or_oficina"
  on public.maintenance_attachments for insert
  to authenticated
  with check (
    created_by = auth.uid()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

create policy "maintenance_attachments_update_oficina"
  on public.maintenance_attachments for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_attachments_delete_oficina"
  on public.maintenance_attachments for delete
  to authenticated
  using (public.is_oficina());
