insert into storage.buckets (id, name, public)
values ('maintenance-attachments', 'maintenance-attachments', false)
on conflict (id) do nothing;

create policy "maintenance_attachments_storage_select"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'maintenance-attachments');

create policy "maintenance_attachments_storage_insert"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'maintenance-attachments');

create policy "maintenance_attachments_storage_delete_oficina"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'maintenance-attachments' and public.is_oficina());
