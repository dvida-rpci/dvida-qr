-- Lectura pública del histórico de mantenimientos (2026-09-21).
-- Decisión de producto: el histórico completo (incluidos autor y adjuntos) es
-- visible sin sesión. La ESCRITURA sigue exigiendo sesión y perfil (policies
-- insert/update/delete sin cambios). Reemplaza las policies select_member del
-- endurecimiento previo por una sola de lectura para anon y authenticated, para
-- que un usuario logueado sin perfil no vea MENOS que un visitante anónimo.

drop policy "maintenance_records_select_member" on public.maintenance_records;
create policy "maintenance_records_select_public"
  on public.maintenance_records for select
  to anon, authenticated
  using (true);

drop policy "maintenance_attachments_select_member" on public.maintenance_attachments;
create policy "maintenance_attachments_select_public"
  on public.maintenance_attachments for select
  to anon, authenticated
  using (true);

drop policy "maintenance_comments_select_member" on public.maintenance_comments;
create policy "maintenance_comments_select_public"
  on public.maintenance_comments for select
  to anon, authenticated
  using (true);

-- El bucket sigue siendo privado: anon necesita select en storage.objects para
-- poder pedir URLs firmadas y descargar.
drop policy "maintenance_attachments_storage_select" on storage.objects;
create policy "maintenance_attachments_storage_select_public"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'maintenance-attachments');

-- Nombre del autor sin exponer profiles (correo, rol). La vista corre con los
-- permisos de su dueño (security_invoker = false) para saltar profiles_select_own.
create view public.author_names as
  select user_id, full_name from public.profiles;

alter view public.author_names set (security_invoker = false);

-- CRÍTICO: Supabase concede ALL sobre objetos nuevos de public a anon y
-- authenticated. Una vista simple es auto-actualizable, así que sin este revoke
-- cualquiera podría insertar/editar/borrar perfiles a través de la vista.
revoke all on public.author_names from anon, authenticated;
grant select on public.author_names to anon, authenticated;
