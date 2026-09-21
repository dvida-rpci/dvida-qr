-- Endurecimiento tras la revisión de migraciones (2026-09-21).

-- ── 1. created_at no puede venir del cliente ──────────────────────────────
-- is_date_anomaly compara created_at contra performed_at para detectar
-- registros con fecha retroactiva; si el técnico podía enviar created_at, la
-- anomalía se ocultaba. BEFORE INSERT lo fuerza a now() sin importar el payload.

create or replace function public.force_created_at_now()
returns trigger
language plpgsql
as $$
begin
  new.created_at := now();
  return new;
end;
$$;

create trigger maintenance_records_force_created_at
  before insert on public.maintenance_records
  for each row execute function public.force_created_at_now();

-- ── 2. Solo usuarios con fila en profiles ─────────────────────────────────
-- Con signup abierto y el anon key en el sitio público, cualquiera puede
-- obtener el rol `authenticated`. Las policies exigen ahora ser miembro.
-- No es SECURITY DEFINER: profiles_select_own ya permite ver la propia fila.

create or replace function public.is_member()
returns boolean
language sql
stable
as $$
  select exists (
    select 1 from public.profiles where user_id = auth.uid()
  );
$$;

-- maintenance_records
drop policy "maintenance_records_select_authenticated" on public.maintenance_records;
create policy "maintenance_records_select_member"
  on public.maintenance_records for select
  to authenticated
  using (public.is_member());

drop policy "maintenance_records_insert_own" on public.maintenance_records;
create policy "maintenance_records_insert_own"
  on public.maintenance_records for insert
  to authenticated
  with check (created_by = auth.uid() and public.is_member());

-- maintenance_attachments
drop policy "maintenance_attachments_select_authenticated" on public.maintenance_attachments;
create policy "maintenance_attachments_select_member"
  on public.maintenance_attachments for select
  to authenticated
  using (public.is_member());

drop policy "maintenance_attachments_insert_own_record_or_oficina" on public.maintenance_attachments;
create policy "maintenance_attachments_insert_own_record_or_oficina"
  on public.maintenance_attachments for insert
  to authenticated
  with check (
    created_by = auth.uid()
    and public.is_member()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

-- maintenance_comments
drop policy "maintenance_comments_select_authenticated" on public.maintenance_comments;
create policy "maintenance_comments_select_member"
  on public.maintenance_comments for select
  to authenticated
  using (public.is_member());

drop policy "maintenance_comments_insert_own_record_or_oficina" on public.maintenance_comments;
create policy "maintenance_comments_insert_own_record_or_oficina"
  on public.maintenance_comments for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and public.is_member()
    and (
      public.is_oficina()
      or exists (
        select 1 from public.maintenance_records r
        where r.id = record_id and r.created_by = auth.uid()
      )
    )
  );

-- Storage
drop policy "maintenance_attachments_storage_select" on storage.objects;
create policy "maintenance_attachments_storage_select"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'maintenance-attachments' and public.is_member());

drop policy "maintenance_attachments_storage_insert" on storage.objects;
create policy "maintenance_attachments_storage_insert"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'maintenance-attachments' and public.is_member());

-- ── 3. Límites del bucket ─────────────────────────────────────────────────
-- 10 MiB por archivo; solo fotos y audio (los formatos que graban los
-- navegadores móviles: webm/ogg en Chrome y Firefox, mp4/m4a en Safari).

update storage.buckets
set file_size_limit = 10485760,
    allowed_mime_types = array[
      'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif',
      'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'audio/x-m4a'
    ]
where id = 'maintenance-attachments';
