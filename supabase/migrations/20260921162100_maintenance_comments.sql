create table public.maintenance_comments (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null references public.maintenance_records(id) on delete cascade,
  author_id uuid not null default auth.uid() references auth.users(id),
  body text not null,
  created_at timestamptz not null default now()
);

create index maintenance_comments_record_id_idx on public.maintenance_comments (record_id);

alter table public.maintenance_comments enable row level security;

create policy "maintenance_comments_select_authenticated"
  on public.maintenance_comments for select
  to authenticated
  using (true);

create policy "maintenance_comments_insert_own_record_or_oficina"
  on public.maintenance_comments for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

create policy "maintenance_comments_update_oficina"
  on public.maintenance_comments for update
  to authenticated
  using (public.is_oficina())
  with check (public.is_oficina());

create policy "maintenance_comments_delete_oficina"
  on public.maintenance_comments for delete
  to authenticated
  using (public.is_oficina());
