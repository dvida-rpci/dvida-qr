def test_tecnico_can_select_own_profile(tecnico_client, tecnico_id):
    response = tecnico_client.table("profiles").select("*").eq("user_id", tecnico_id).execute()
    assert len(response.data) == 1
    assert response.data[0]["role"] == "tecnico"


def test_tecnico_cannot_select_other_profile(tecnico_client, oficina_id):
    response = tecnico_client.table("profiles").select("*").eq("user_id", oficina_id).execute()
    assert response.data == []


def test_is_oficina_true_for_oficina_role(oficina_client):
    response = oficina_client.rpc("is_oficina").execute()
    assert response.data is True


def test_is_oficina_false_for_tecnico_role(tecnico_client):
    response = tecnico_client.rpc("is_oficina").execute()
    assert response.data is False
