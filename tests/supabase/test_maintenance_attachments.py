import datetime

import pytest
from postgrest.exceptions import APIError


def _insert_record(client, tag_id: str) -> str:
    today = datetime.date.today().isoformat()
    response = (
        client.table("maintenance_records")
        .insert(
            {
                "tag_id": tag_id,
                "performed_at": today,
                "type": "preventivo",
                "description": "Registro base para adjuntos",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_tecnico_can_insert_attachment_on_own_record(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_insert_attachment_on_others_record(
    tecnico_client, oficina_client, random_tag_id
):
    record_id = _insert_record(oficina_client, random_tag_id)
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_attachments").insert(
            {"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"}
        ).execute()


def test_oficina_can_insert_attachment_on_any_record(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        oficina_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "audio", "storage_path": f"{random_tag_id}/{record_id}/1.webm"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_delete_attachment(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    attachment_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_attachments").delete().eq("id", attachment_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_delete_attachment(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_attachments")
        .insert({"record_id": record_id, "kind": "photo", "storage_path": f"{random_tag_id}/{record_id}/1.jpg"})
        .execute()
    )
    attachment_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_attachments").delete().eq("id", attachment_id).execute()
    )
    assert len(delete_response.data) == 1
