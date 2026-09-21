"""Endurecimiento detectado en la revisión de migraciones (2026-09-21).

1. created_at no puede ser falseado por el cliente (rompía is_date_anomaly).
2. Un usuario autenticado sin fila en profiles (p. ej. alguien que se auto-registra
   con el anon key público) puede LEER (el histórico es público desde 2026-09-21)
   pero no escribe nada.
3. El bucket limita tamaño y tipo MIME.
"""
import datetime

import pytest
from postgrest.exceptions import APIError
from storage3.utils import StorageException
from supabase import Client

from tests.supabase.conftest import TEST_PASSWORD, _signed_in_client

BUCKET = "maintenance-attachments"
OUTSIDER_EMAIL = "outsider@test.local"


@pytest.fixture(scope="session")
def outsider_id(service_client: Client) -> str:
    """Usuario autenticado válido pero SIN fila en profiles."""
    user_id = next(
        (u.id for u in service_client.auth.admin.list_users() if u.email == OUTSIDER_EMAIL),
        None,
    )
    if user_id is None:
        result = service_client.auth.admin.create_user(
            {"email": OUTSIDER_EMAIL, "password": TEST_PASSWORD, "email_confirm": True}
        )
        user_id = result.user.id
    service_client.table("profiles").delete().eq("user_id", user_id).execute()
    return user_id


@pytest.fixture
def outsider_client(outsider_id) -> Client:
    return _signed_in_client(OUTSIDER_EMAIL)


def _record(tag_id: str, **overrides):
    payload = {
        "tag_id": tag_id,
        "performed_at": datetime.date.today().isoformat(),
        "type": "preventivo",
        "description": "Cambio de filtro",
    }
    payload.update(overrides)
    return payload


# ── 1. created_at forzado a now() ────────────────────────────────────────


def test_created_at_sent_by_client_is_ignored(tecnico_client, random_tag_id):
    sixty_days_ago = datetime.date.today() - datetime.timedelta(days=60)
    response = (
        tecnico_client.table("maintenance_records")
        .insert(
            _record(
                random_tag_id,
                performed_at=sixty_days_ago.isoformat(),
                created_at=f"{sixty_days_ago.isoformat()}T12:00:00+00:00",
            )
        )
        .execute()
    )
    row = response.data[0]
    assert row["created_at"][:10] != sixty_days_ago.isoformat()
    assert row["is_date_anomaly"] is True


# ── 2. Usuario sin profile: lee (todo es público) pero no escribe ──────────────────────────────


def test_outsider_can_read_records(tecnico_client, outsider_client, random_tag_id):
    tecnico_client.table("maintenance_records").insert(_record(random_tag_id)).execute()

    response = (
        outsider_client.table("maintenance_records").select("*").eq("tag_id", random_tag_id).execute()
    )
    assert len(response.data) == 1


def test_outsider_cannot_insert_record(outsider_client, random_tag_id):
    with pytest.raises(APIError):
        outsider_client.table("maintenance_records").insert(_record(random_tag_id)).execute()


def test_outsider_can_read_attachments_and_comments(
    tecnico_client, outsider_client, random_tag_id
):
    record_id = (
        tecnico_client.table("maintenance_records")
        .insert(_record(random_tag_id))
        .execute()
        .data[0]["id"]
    )
    tecnico_client.table("maintenance_comments").insert(
        {"record_id": record_id, "body": "comentario"}
    ).execute()
    tecnico_client.table("maintenance_attachments").insert(
        {"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/x.jpg"}
    ).execute()

    comments = outsider_client.table("maintenance_comments").select("*").eq("record_id", record_id).execute()
    attachments = outsider_client.table("maintenance_attachments").select("*").eq("record_id", record_id).execute()
    assert len(comments.data) == 1
    assert len(attachments.data) == 1


def test_outsider_can_download_but_not_upload_storage(tecnico_client, outsider_client, random_tag_id):
    path = f"{random_tag_id}/test/outsider.jpg"
    tecnico_client.storage.from_(BUCKET).upload(
        path, b"contenido-de-prueba", {"content-type": "image/jpeg"}
    )

    assert outsider_client.storage.from_(BUCKET).download(path) == b"contenido-de-prueba"
    with pytest.raises(StorageException):
        outsider_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/test/outsider-up.jpg",
            b"contenido-de-prueba",
            {"content-type": "image/jpeg"},
        )


# ── 3. Límites del bucket ────────────────────────────────────────────────


def test_bucket_rejects_disallowed_mime_type(tecnico_client, random_tag_id):
    with pytest.raises(StorageException):
        tecnico_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/test/script.html",
            b"<script>alert(1)</script>",
            {"content-type": "text/html"},
        )


def test_bucket_rejects_oversized_file(tecnico_client, random_tag_id):
    too_big = b"0" * (11 * 1024 * 1024)
    with pytest.raises(StorageException):
        tecnico_client.storage.from_(BUCKET).upload(
            f"{random_tag_id}/test/big.jpg", too_big, {"content-type": "image/jpeg"}
        )


@pytest.mark.parametrize(
    "name,mime",
    [("foto.jpg", "image/jpeg"), ("foto.png", "image/png"), ("nota.webm", "audio/webm"), ("nota.m4a", "audio/mp4")],
)
def test_bucket_accepts_photos_and_audio(tecnico_client, random_tag_id, name, mime):
    tecnico_client.storage.from_(BUCKET).upload(
        f"{random_tag_id}/test/{name}", b"contenido-de-prueba", {"content-type": mime}
    )
