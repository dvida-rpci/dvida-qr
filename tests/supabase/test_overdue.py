"""Atrasados: días de atraso, motivo obligatorio al reprogramar un vencido, cadena de
reprogramaciones y atraso real guardado al registrar (contra la fecha original)."""
import datetime

import pytest
from postgrest.exceptions import APIError

from tests.supabase.test_maintenance_plan import _register, _tag, plan  # noqa: F401

TODAY = datetime.date.today()


def _days(n):
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def _schedule(client, tag, activity, date, replace=False, note=None):
    return client.rpc("schedule_manual", {
        "p_tag": tag, "p_activity": activity, "p_date": date, "p_note": note, "p_replace": replace,
    }).execute().data


def _lub_row(client, tag, activity_id):
    rows = client.table("maintenance_agenda").select("*").eq("tag_id", tag).eq(
        "activity_id", activity_id).execute().data
    assert len(rows) == 1, rows
    return rows[0]


@pytest.fixture
def vencido(service_client, tecnico_client, plan):
    """TAG cuya lubricación venció hace 46 días (hecha hace 100, cada 1300 h a 24 h/día = 54)."""
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, _days(-100), [plan["LUB"]])
    return tag


def test_vencido_reporta_dias_de_atraso(oficina_client, plan, vencido):
    row = _lub_row(oficina_client, vencido, plan["LUB"])
    assert (row["status"], row["due_date"], row["days_overdue"]) == ("vencido", _days(-46), 46)


def test_reprogramar_vencido_exige_motivo(oficina_client, plan, vencido):
    result = _schedule(oficina_client, vencido, plan["LUB"], _days(7))
    assert result["status"] == "conflict"
    assert result["conflicts"][0]["days_overdue"] == 46
    with pytest.raises(APIError, match="motivo"):
        _schedule(oficina_client, vencido, plan["LUB"], _days(7), replace=True, note="  ")


def test_cadena_de_reprogramaciones_conserva_la_fecha_original(oficina_client, plan, vencido):
    _schedule(oficina_client, vencido, plan["LUB"], _days(7), replace=True, note="falta repuesto")
    row = _lub_row(oficina_client, vencido, plan["LUB"])
    assert (row["source"], row["status"], row["reschedule_count"], row["original_due_date"],
            row["note"]) == ("manual", "proximo", 1, _days(-46), "falta repuesto")

    # Segunda vez: no está vencido (fecha nueva), no exige motivo; cuenta 2, original igual.
    _schedule(oficina_client, vencido, plan["LUB"], _days(20), replace=True)
    row = _lub_row(oficina_client, vencido, plan["LUB"])
    assert (row["reschedule_count"], row["original_due_date"], row["due_date"]) == (
        2, _days(-46), _days(20))


def test_registrar_tarde_guarda_la_fecha_original(
    service_client, tecnico_client, oficina_client, plan, vencido
):
    _schedule(oficina_client, vencido, plan["LUB"], _days(7), replace=True, note="falta repuesto")
    record_id = _register(tecnico_client, vencido, TODAY.isoformat(), [plan["LUB"]])
    link = service_client.table("maintenance_record_activities").select("due_date").eq(
        "record_id", record_id).execute().data[0]
    assert link["due_date"] == _days(-46)  # atraso real: 46 días, aunque se reprogramó

    row = _lub_row(oficina_client, vencido, plan["LUB"])
    assert (row["source"], row["due_date"]) == ("automatico", _days(54))  # cuenta desde hoy


def test_registrar_a_tiempo_guarda_su_fecha(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, _days(-10), [plan["LUB"]])  # vence en 44 días
    record_id = _register(tecnico_client, tag, TODAY.isoformat(), [plan["LUB"]])
    link = service_client.table("maintenance_record_activities").select("due_date").eq(
        "record_id", record_id).execute().data[0]
    assert link["due_date"] == _days(44)
