"""Programación manual: advertencia de duplicados, sobrescritura y agenda unificada.

Usa la fecha real (la vista y schedule_manual trabajan con "hoy" en hora de Colombia).
"""
import datetime

import pytest
from postgrest.exceptions import APIError

from tests.supabase.test_maintenance_plan import _new_class, _register, _tag, plan  # noqa: F401

TODAY = datetime.date.today()
IN_20 = (TODAY + datetime.timedelta(days=20)).isoformat()
IN_30 = (TODAY + datetime.timedelta(days=30)).isoformat()


def _schedule(client, tag, activity, date, replace=False, note=None):
    return client.rpc("schedule_manual", {
        "p_tag": tag, "p_activity": activity, "p_date": date, "p_note": note, "p_replace": replace,
    }).execute().data


def _agenda(client, tag):
    return client.table("maintenance_agenda").select("*").eq("tag_id", tag).execute().data


def test_conflicto_con_automatico_no_guarda_y_con_replace_lo_reemplaza(
    service_client, tecnico_client, oficina_client, plan
):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, TODAY.isoformat(), [plan["LUB"]])

    result = _schedule(oficina_client, tag, plan["LUB"], IN_20)
    assert result["status"] == "conflict"
    assert [c["source"] for c in result["conflicts"]] == ["automatico"]
    assert service_client.table("maintenance_manual_schedule").select("id").eq(
        "tag_id", tag).execute().data == []

    assert _schedule(oficina_client, tag, plan["LUB"], IN_20, replace=True)["status"] == "ok"
    lub = [r for r in _agenda(oficina_client, tag) if r["activity_id"] == plan["LUB"]]
    assert [(r["source"], r["due_date"]) for r in lub] == [("manual", IN_20)]


def test_reemplazar_un_manual_lo_marca_reemplazado(service_client, oficina_client, plan):
    tag = _tag(service_client, plan)
    first = _schedule(oficina_client, tag, None, IN_20, note="primero")
    assert _schedule(oficina_client, tag, None, IN_30)["status"] == "conflict"
    second = _schedule(oficina_client, tag, None, IN_30, replace=True)

    old = service_client.table("maintenance_manual_schedule").select("status, replaced_by").eq(
        "id", first["id"]).execute().data[0]
    assert old == {"status": "reemplazado", "replaced_by": second["id"]}
    libres = [r for r in _agenda(oficina_client, tag) if r["activity_id"] is None]
    assert [(r["source"], r["due_date"]) for r in libres] == [("manual", IN_30)]


def test_otra_actividad_no_bloquea_pero_avisa(service_client, tecnico_client, oficina_client, plan):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, TODAY.isoformat(), [plan["LUB"]])
    result = _schedule(oficina_client, tag, plan["SOLOH"], IN_20)
    assert result["status"] == "ok"
    assert [o["activity_id"] for o in result["others"]] == [plan["LUB"]]


def test_registrar_la_actividad_cumple_el_manual(service_client, tecnico_client, oficina_client, plan):
    tag = _tag(service_client, plan)
    _schedule(oficina_client, tag, plan["LUB"], IN_20)
    _register(tecnico_client, tag, TODAY.isoformat(), [plan["LUB"]])
    lub = [r for r in _agenda(oficina_client, tag) if r["activity_id"] == plan["LUB"]]
    assert [r["source"] for r in lub] == ["automatico"]


def test_proximo_de_registro_libre_aparece_y_genera_conflicto(
    service_client, tecnico_client, oficina_client, plan
):
    tag = _tag(service_client, plan)
    tecnico_client.table("maintenance_records").insert({
        "tag_id": tag, "performed_at": TODAY.isoformat(), "type": "correctivo",
        "description": "libre", "next_scheduled_at": IN_30,
    }).execute()
    libres = [r for r in _agenda(oficina_client, tag) if r["activity_id"] is None]
    assert [(r["source"], r["due_date"]) for r in libres] == [("registro", IN_30)]

    result = _schedule(oficina_client, tag, None, IN_20)
    assert [c["source"] for c in result["conflicts"]] == ["registro"]
    _schedule(oficina_client, tag, None, IN_20, replace=True)
    libres = [r for r in _agenda(oficina_client, tag) if r["activity_id"] is None]
    assert [r["source"] for r in libres] == ["manual"]


def test_solo_oficina_programa(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    with pytest.raises(APIError):
        _schedule(tecnico_client, tag, None, IN_20)


def test_actividad_de_otra_clase_se_rechaza(service_client, oficina_client, plan):
    tag = _tag(service_client, plan)
    other = service_client.table("maintenance_activities").insert({
        "class_id": _new_class(service_client), "code": "X", "name": "Otra", "interval_weeks": 4,
    }).execute().data[0]["id"]
    with pytest.raises(APIError, match="no corresponde"):
        _schedule(oficina_client, tag, other, IN_20)
