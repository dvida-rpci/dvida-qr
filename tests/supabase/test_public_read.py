"""Lectura pública del histórico (2026-09-21): el rol anon lee, nunca escribe."""
import datetime

import pytest
from postgrest.exceptions import APIError
from storage3.utils import StorageException
from supabase import Client, create_client

from tests.supabase.conftest import SUPABASE_ANON_KEY, SUPABASE_URL

BUCKET = "maintenance-attachments"
CONTENT = b"contenido-de-prueba"


@pytest.fixture
def anon_client() -> Client:
    """Cliente sin sesión: lo que ve cualquier visitante del sitio."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _record(tag_id: str, **overrides):
    payload = {
        "tag_id": tag_id,
        "performed_at": datetime.date.today().isoformat(),
        "type": "preventivo",
        "description": "Cambio de filtro",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def seeded(tecnico_client, random_tag_id):
    record_id = (
        tecnico_client.table("maintenance_records")
        .insert(_record(random_tag_id))
        .execute()
        .data[0]["id"]
    )
    tecnico_client.table("maintenance_comments").insert(
        {"record_id": record_id, "body": "comentario"}
    ).execute()
    path = f"{random_tag_id}/{record_id}/foto.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, CONTENT, {"content-type": "image/jpeg"})
    tecnico_client.table("maintenance_attachments").insert(
        {"record_id": record_id, "kind": "photo", "storage_path": path}
    ).execute()
    return {"tag_id": random_tag_id, "record_id": record_id, "path": path}


def _rows(query):
    """Filas visibles; si el rol ni siquiera tiene permiso sobre la tabla, cuenta como vacío."""
    try:
        return query.execute().data
    except APIError:
        return []


# ── Lectura ──────────────────────────────────────────────────────────────


def test_anon_reads_records(anon_client, seeded):
    rows = anon_client.table("maintenance_records").select("*").eq("id", seeded["record_id"]).execute().data
    assert len(rows) == 1
    assert rows[0]["description"] == "Cambio de filtro"


def test_anon_reads_attachments_and_comments(anon_client, seeded):
    atts = anon_client.table("maintenance_attachments").select("*").eq("record_id", seeded["record_id"]).execute().data
    comments = anon_client.table("maintenance_comments").select("*").eq("record_id", seeded["record_id"]).execute().data
    assert len(atts) == 1
    assert len(comments) == 1


def test_anon_can_sign_and_download_attachment(anon_client, seeded):
    signed = anon_client.storage.from_(BUCKET).create_signed_urls([seeded["path"]], 60)
    assert signed[0].get("signedURL") or signed[0].get("signedUrl")
    assert anon_client.storage.from_(BUCKET).download(seeded["path"]) == CONTENT


def test_author_names_exposes_only_id_and_name(anon_client, tecnico_id):
    rows = anon_client.table("author_names").select("*").eq("user_id", tecnico_id).execute().data
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"user_id", "full_name"}
    assert rows[0]["full_name"] == "Test tecnico"


# ── Escritura: sigue exigiendo sesión ────────────────────────────────────


def test_anon_cannot_insert_record(anon_client, random_tag_id):
    with pytest.raises(APIError):
        anon_client.table("maintenance_records").insert(_record(random_tag_id)).execute()


def test_anon_cannot_update_or_delete_record(anon_client, service_client, seeded):
    anon_client.table("maintenance_records").update({"description": "hackeado"}).eq(
        "id", seeded["record_id"]
    ).execute()
    anon_client.table("maintenance_records").delete().eq("id", seeded["record_id"]).execute()

    row = service_client.table("maintenance_records").select("*").eq("id", seeded["record_id"]).execute().data
    assert len(row) == 1
    assert row[0]["description"] == "Cambio de filtro"


def test_anon_cannot_insert_comment_or_attachment(anon_client, seeded):
    with pytest.raises(APIError):
        anon_client.table("maintenance_comments").insert(
            {"record_id": seeded["record_id"], "body": "spam"}
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("maintenance_attachments").insert(
            {"record_id": seeded["record_id"], "kind": "photo", "storage_path": "x/y.jpg"}
        ).execute()


def test_anon_cannot_upload_or_delete_storage(anon_client, seeded, random_tag_id):
    with pytest.raises(StorageException):
        anon_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/anon.jpg", CONTENT, {"content-type": "image/jpeg"}
        )
    anon_client.storage.from_(BUCKET).remove([seeded["path"]])
    assert anon_client.storage.from_(BUCKET).download(seeded["path"]) == CONTENT


# ── Lo que sigue privado ─────────────────────────────────────────────────


def test_anon_cannot_read_audit_log_or_profiles(anon_client, seeded):
    assert _rows(anon_client.table("maintenance_audit_log").select("*")) == []
    assert _rows(anon_client.table("profiles").select("*")) == []


def test_anon_cannot_write_through_author_names(anon_client, service_client, tecnico_id):
    with pytest.raises(APIError):
        anon_client.table("author_names").insert(
            {"user_id": tecnico_id, "full_name": "hackeado"}
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("author_names").update({"full_name": "hackeado"}).eq(
            "user_id", tecnico_id
        ).execute()
    with pytest.raises(APIError):
        anon_client.table("author_names").delete().eq("user_id", tecnico_id).execute()

    profile = service_client.table("profiles").select("full_name").eq("user_id", tecnico_id).execute().data
    assert profile[0]["full_name"] == "Test tecnico"
