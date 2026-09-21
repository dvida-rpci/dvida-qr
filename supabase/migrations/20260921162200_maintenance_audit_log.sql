create table public.maintenance_audit_log (
  id uuid primary key default gen_random_uuid(),
  record_id uuid not null,
  action text not null check (action in ('update', 'delete')),
  old_data jsonb,
  new_data jsonb,
  changed_by uuid not null references auth.users(id),
  changed_at timestamptz not null default now()
);

create index maintenance_audit_log_record_id_idx on public.maintenance_audit_log (record_id);

alter table public.maintenance_audit_log enable row level security;

create policy "maintenance_audit_log_select_oficina"
  on public.maintenance_audit_log for select
  to authenticated
  using (public.is_oficina());

-- Sin políticas de insert/update/delete para ningún rol: por default, RLS deniega
-- lo que no tiene policy. Solo el trigger (SECURITY DEFINER, dueño de la tabla,
-- por lo tanto exento de RLS) puede escribir acá.

create or replace function public.log_maintenance_audit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'UPDATE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.id, 'update', to_jsonb(old), to_jsonb(new), auth.uid());
    return new;
  elsif tg_op = 'DELETE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.id, 'delete', to_jsonb(old), null, auth.uid());
    return old;
  end if;
  return null;
end;
$$;

create trigger maintenance_records_audit
  after update or delete on public.maintenance_records
  for each row execute function public.log_maintenance_audit();

create or replace function public.log_maintenance_child_audit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'UPDATE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.record_id, 'update', to_jsonb(old), to_jsonb(new), auth.uid());
    return new;
  elsif tg_op = 'DELETE' then
    insert into public.maintenance_audit_log (record_id, action, old_data, new_data, changed_by)
    values (old.record_id, 'delete', to_jsonb(old), null, auth.uid());
    return old;
  end if;
  return null;
end;
$$;

create trigger maintenance_attachments_audit
  after update or delete on public.maintenance_attachments
  for each row execute function public.log_maintenance_child_audit();

create trigger maintenance_comments_audit
  after update or delete on public.maintenance_comments
  for each row execute function public.log_maintenance_child_audit();
