import datetime

import pytest
from postgrest.exceptions import APIError


def _record_payload(tag_id: str, performed_at: str, **overrides):
    payload = {
        "tag_id": tag_id,
        "performed_at": performed_at,
        "type": "preventivo",
        "description": "Cambio de filtro",
    }
    payload.update(overrides)
    return payload


def test_tecnico_can_insert_record(tecnico_client, tecnico_id, random_tag_id):
    today = datetime.date.today().isoformat()
    response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    assert len(response.data) == 1
    assert response.data[0]["created_by"] == tecnico_id
    assert response.data[0]["is_date_anomaly"] is False


def test_insert_with_spoofed_created_by_is_rejected(tecnico_client, oficina_id, random_tag_id):
    today = datetime.date.today().isoformat()
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_records").insert(
            _record_payload(random_tag_id, today, created_by=oficina_id)
        ).execute()


def test_is_date_anomaly_true_when_performed_at_is_far_in_the_past(
    tecnico_client, random_tag_id
):
    old_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, old_date))
        .execute()
    )
    assert response.data[0]["is_date_anomaly"] is True


def test_any_authenticated_user_can_select_all_records(oficina_client, tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    tecnico_client.table("maintenance_records").insert(
        _record_payload(random_tag_id, today)
    ).execute()

    response = oficina_client.table("maintenance_records").select("*").eq("tag_id", random_tag_id).execute()
    assert len(response.data) == 1


def test_tecnico_cannot_update_record(tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    update_response = (
        tecnico_client.table("maintenance_records")
        .update({"description": "intento de edición"})
        .eq("id", record_id)
        .execute()
    )
    assert update_response.data == []


def test_tecnico_cannot_delete_record(tecnico_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    delete_response = (
        tecnico_client.table("maintenance_records").delete().eq("id", record_id).execute()
    )
    assert delete_response.data == []


def test_oficina_can_update_record(tecnico_client, oficina_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    update_response = (
        oficina_client.table("maintenance_records")
        .update({"description": "corregido por oficina"})
        .eq("id", record_id)
        .execute()
    )
    assert update_response.data[0]["description"] == "corregido por oficina"


def test_oficina_can_delete_record(tecnico_client, oficina_client, random_tag_id):
    today = datetime.date.today().isoformat()
    insert_response = (
        tecnico_client.table("maintenance_records")
        .insert(_record_payload(random_tag_id, today))
        .execute()
    )
    record_id = insert_response.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_records").delete().eq("id", record_id).execute()
    )
    assert len(delete_response.data) == 1
