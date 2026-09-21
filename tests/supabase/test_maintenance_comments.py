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
                "type": "correctivo",
                "description": "Registro base para comentarios",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_tecnico_can_comment_on_own_record(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "Se reemplazó el rodamiento"})
        .execute()
    )
    assert len(response.data) == 1


def test_tecnico_cannot_comment_on_others_record(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(oficina_client, random_tag_id)
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_comments").insert(
            {"record_id": record_id, "body": "intento ajeno"}
        ).execute()


def test_tecnico_cannot_delete_comment(tecnico_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "comentario original"})
        .execute()
    )
    comment_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_comments").delete().eq("id", comment_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_delete_comment(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    insert_response = (
        tecnico_client.table("maintenance_comments")
        .insert({"record_id": record_id, "body": "comentario a borrar"})
        .execute()
    )
    comment_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_comments").delete().eq("id", comment_id).execute()
    )
    assert len(delete_response.data) == 1
