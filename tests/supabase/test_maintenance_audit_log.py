import datetime


def _insert_record(client, tag_id: str) -> str:
    today = datetime.date.today().isoformat()
    response = (
        client.table("maintenance_records")
        .insert(
            {
                "tag_id": tag_id,
                "performed_at": today,
                "type": "preventivo",
                "description": "original",
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def test_oficina_update_creates_audit_entry(tecnico_client, oficina_client, oficina_id, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    assert len(audit.data) == 1
    entry = audit.data[0]
    assert entry["action"] == "update"
    assert entry["changed_by"] == oficina_id
    assert entry["old_data"]["description"] == "original"
    assert entry["new_data"]["description"] == "corregido"


def test_oficina_delete_creates_audit_entry(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").delete().eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    assert len(audit.data) == 1
    entry = audit.data[0]
    assert entry["action"] == "delete"
    assert entry["new_data"] is None
    assert entry["old_data"]["description"] == "original"


def test_tecnico_cannot_select_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    response = tecnico_client.table("maintenance_audit_log").select("*").eq("record_id", record_id).execute()
    assert response.data == []


def test_oficina_cannot_update_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    audit_id = audit.data[0]["id"]

    tamper_response = (
        oficina_client.table("maintenance_audit_log")
        .update({"action": "update", "old_data": {}})
        .eq("id", audit_id)
        .execute()
    )
    assert tamper_response.data == []


def test_oficina_cannot_delete_audit_log(tecnico_client, oficina_client, random_tag_id):
    record_id = _insert_record(tecnico_client, random_tag_id)
    oficina_client.table("maintenance_records").update(
        {"description": "corregido"}
    ).eq("id", record_id).execute()

    audit = (
        oficina_client.table("maintenance_audit_log")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    )
    audit_id = audit.data[0]["id"]

    delete_response = (
        oficina_client.table("maintenance_audit_log").delete().eq("id", audit_id).execute()
    )
    assert delete_response.data == []
