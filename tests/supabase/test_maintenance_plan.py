"""Plan de mantenimiento por sábana: cálculo de la programación, alta atómica y RLS del catálogo.

Las fechas del cálculo se fijan con maintenance_schedule_at(p_today) para que los tests no
dependan del día en que se corren.
"""
import uuid

import pytest
from postgrest.exceptions import APIError
from supabase import Client, create_client

from tests.supabase.conftest import SUPABASE_ANON_KEY, SUPABASE_URL


@pytest.fixture
def anon_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _new_class(service_client, hours_per_day=24):
    code = f"TEST-{uuid.uuid4().hex[:8]}"
    return (
        service_client.table("equipment_classes")
        .insert({"code": code, "name": f"Clase {code}", "hours_per_day": hours_per_day})
        .execute()
        .data[0]["id"]
    )


@pytest.fixture
def plan(service_client):
    """Clase de prueba (24 h/día) con LUB (1300 h / 12 sem) y SOLOH (2000 h, sin semanas)."""
    class_id = _new_class(service_client)
    activities = (
        service_client.table("maintenance_activities")
        .insert([
            {"class_id": class_id, "code": "LUB", "name": "Lubricación",
             "interval_hours": 1300, "interval_weeks": 12},
            {"class_id": class_id, "code": "SOLOH", "name": "Solo horas", "interval_hours": 2000},
        ])
        .execute()
        .data
    )
    return {"class_id": class_id, **{a["code"]: a["id"] for a in activities}}


def _tag(service_client, plan, regime="normal", group_key=None):
    tag_id = f"TEST-{uuid.uuid4().hex[:8]}"
    service_client.table("equipment_tags").insert(
        {"tag_id": tag_id, "class_id": plan["class_id"], "regime": regime, "group_key": group_key}
    ).execute()
    return tag_id


def _register(client, tag_id, performed_at, activity_ids=(), hmi_hours=None, type_="preventivo"):
    record = {"tag_id": tag_id, "performed_at": performed_at, "type": type_, "description": "prueba"}
    if hmi_hours is not None:
        record["hmi_hours"] = hmi_hours
    return client.rpc(
        "create_maintenance_record", {"p_record": record, "p_activity_ids": list(activity_ids)}
    ).execute().data


def _schedule(client, today, tag_id, code):
    rows = (
        client.rpc("maintenance_schedule_at", {"p_today": today})
        .eq("tag_id", tag_id)
        .eq("activity_code", code)
        .execute()
        .data
    )
    assert len(rows) == 1, rows
    return rows[0]


# ── Cálculo ──────────────────────────────────────────────────────────────

def test_ejemplo_dvida_sin_lecturas(service_client, tecnico_client, plan):
    solo = _tag(service_client, plan)
    group = f"TEST-G-{uuid.uuid4().hex[:6]}"
    alterna_a = _tag(service_client, plan, "alterna", group)
    _tag(service_client, plan, "alterna", group)
    _register(tecnico_client, solo, "2026-10-14", [plan["LUB"]])
    _register(tecnico_client, alterna_a, "2026-10-14", [plan["LUB"]])

    row = _schedule(tecnico_client, "2026-10-14", solo, "LUB")
    assert (row["due_date"], row["rate_hours_per_day"], row["rate_source"], row["status"]) == (
        "2026-12-07", 24, "estimado", "al_dia")

    row = _schedule(tecnico_client, "2026-10-14", alterna_a, "LUB")
    assert (row["due_date"], row["rate_hours_per_day"]) == ("2027-01-06", 12)


def test_ritmo_real_con_dos_lecturas(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, "2026-09-01", hmi_hours=10000, type_="correctivo")
    _register(tecnico_client, tag, "2026-10-01", [plan["LUB"]], hmi_hours=10600)

    row = _schedule(tecnico_client, "2026-10-14", tag, "LUB")
    assert (row["rate_hours_per_day"], row["rate_source"], row["due_hours"], row["due_date"]) == (
        20, "real", 11900, "2026-12-05")


def test_lectura_posterior_recalcula_desde_la_ultima(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, "2026-09-01", hmi_hours=10000, type_="correctivo")
    _register(tecnico_client, tag, "2026-10-01", [plan["LUB"]], hmi_hours=10600)
    _register(tecnico_client, tag, "2026-11-01", hmi_hours=11400, type_="correctivo")

    row = _schedule(tecnico_client, "2026-11-02", tag, "LUB")
    # 1400 h en 61 días = 22,95 h/día; faltan 500 h → 21 días después del 1 nov.
    assert (row["rate_hours_per_day"], row["due_date"]) == (22.95, "2026-11-22")


def test_reset_del_contador_vuelve_al_estimado(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, "2026-09-01", hmi_hours=10000, type_="correctivo")
    _register(tecnico_client, tag, "2026-10-01", [plan["LUB"]], hmi_hours=10600)
    _register(tecnico_client, tag, "2026-11-05", hmi_hours=50, type_="correctivo")

    row = _schedule(tecnico_client, "2026-11-06", tag, "LUB")
    assert (row["rate_source"], row["rate_hours_per_day"], row["due_date"]) == (
        "estimado", 24, "2026-11-24")


def test_reserva_con_frecuencia_solo_en_horas_queda_sin_fecha(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan, "reserva")
    _register(tecnico_client, tag, "2026-10-14", [plan["SOLOH"]])

    row = _schedule(tecnico_client, "2026-10-14", tag, "SOLOH")
    assert (row["status"], row["due_date"]) == ("sin_fecha", None)
    assert _schedule(tecnico_client, "2026-10-14", tag, "LUB")["status"] == "sin_registro"


@pytest.mark.parametrize("today, status", [
    ("2026-07-01", "al_dia"),
    ("2026-07-15", "proximo"),
    ("2026-08-01", "vencido"),
])
def test_estados(service_client, tecnico_client, plan, today, status):
    tag = _tag(service_client, plan)
    _register(tecnico_client, tag, "2026-06-01", [plan["LUB"]])  # vence el 2026-07-25
    row = _schedule(tecnico_client, today, tag, "LUB")
    assert (row["due_date"], row["status"]) == ("2026-07-25", status)


def test_actividad_inactiva_no_se_programa(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    service_client.table("maintenance_activities").update({"active": False}).eq(
        "id", plan["SOLOH"]).execute()
    rows = tecnico_client.rpc("maintenance_schedule_at", {"p_today": "2026-10-14"}).eq(
        "tag_id", tag).execute().data
    assert [r["activity_code"] for r in rows] == ["LUB"]


def test_la_vista_es_publica(service_client, anon_client, plan):
    tag = _tag(service_client, plan)
    rows = anon_client.table("maintenance_schedule").select("*").eq("tag_id", tag).execute().data
    assert sorted(r["activity_code"] for r in rows) == ["LUB", "SOLOH"]


# ── Alta atómica ─────────────────────────────────────────────────────────

def test_actividad_de_otra_clase_no_deja_registro(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    other_activity = (
        service_client.table("maintenance_activities")
        .insert({"class_id": _new_class(service_client), "code": "X", "name": "Otra",
                 "interval_weeks": 4})
        .execute()
        .data[0]["id"]
    )
    with pytest.raises(APIError, match="no corresponde a la clase"):
        _register(tecnico_client, tag, "2026-10-14", [plan["LUB"], other_activity])
    assert service_client.table("maintenance_records").select("id").eq(
        "tag_id", tag).execute().data == []


def test_registro_guarda_horas_y_actividades(service_client, tecnico_client, plan):
    tag = _tag(service_client, plan)
    record_id = _register(tecnico_client, tag, "2026-10-14", [plan["LUB"], plan["SOLOH"]],
                          hmi_hours=12480)
    record = service_client.table("maintenance_records").select("hmi_hours").eq(
        "id", record_id).execute().data[0]
    assert record["hmi_hours"] == 12480
    links = service_client.table("maintenance_record_activities").select("activity_id").eq(
        "record_id", record_id).execute().data
    assert {l["activity_id"] for l in links} == {plan["LUB"], plan["SOLOH"]}


def test_anon_no_puede_registrar(service_client, anon_client, plan):
    tag = _tag(service_client, plan)
    with pytest.raises(APIError):
        _register(anon_client, tag, "2026-10-14", [plan["LUB"]])


# ── RLS del catálogo ─────────────────────────────────────────────────────

def test_anon_lee_el_catalogo_pero_no_lo_escribe(service_client, anon_client, plan):
    tag = _tag(service_client, plan)
    assert anon_client.table("equipment_classes").select("id").eq(
        "id", plan["class_id"]).execute().data
    assert len(anon_client.table("maintenance_activities").select("id").eq(
        "class_id", plan["class_id"]).execute().data) == 2
    assert anon_client.table("equipment_tags").select("tag_id").eq("tag_id", tag).execute().data
    with pytest.raises(APIError):
        anon_client.table("equipment_classes").insert(
            {"code": f"TEST-{uuid.uuid4().hex[:8]}", "name": "x", "hours_per_day": 8}).execute()


def test_tecnico_no_edita_el_catalogo(service_client, tecnico_client, plan):
    with pytest.raises(APIError):
        tecnico_client.table("equipment_classes").insert(
            {"code": f"TEST-{uuid.uuid4().hex[:8]}", "name": "x", "hours_per_day": 8}).execute()
    updated = tecnico_client.table("maintenance_activities").update({"interval_hours": 1}).eq(
        "id", plan["LUB"]).execute().data
    assert updated == []
    assert service_client.table("maintenance_activities").select("interval_hours").eq(
        "id", plan["LUB"]).execute().data[0]["interval_hours"] == 1300


def test_oficina_edita_frecuencias_y_queda_el_autor(oficina_client, oficina_id, plan):
    updated = oficina_client.table("maintenance_activities").update({"interval_hours": 1500}).eq(
        "id", plan["LUB"]).execute().data
    assert (updated[0]["interval_hours"], updated[0]["updated_by"]) == (1500, oficina_id)


def test_tecnico_no_agrega_actividades_a_registro_ajeno(
    service_client, tecnico_client, oficina_client, plan
):
    tag = _tag(service_client, plan)
    record_id = _register(oficina_client, tag, "2026-10-14")
    with pytest.raises(APIError):
        tecnico_client.table("maintenance_record_activities").insert(
            {"record_id": record_id, "activity_id": plan["LUB"]}).execute()


def test_solo_oficina_quita_actividades(service_client, tecnico_client, oficina_client, plan):
    tag = _tag(service_client, plan)
    record_id = _register(tecnico_client, tag, "2026-10-14", [plan["LUB"]])
    assert tecnico_client.table("maintenance_record_activities").delete().eq(
        "record_id", record_id).execute().data == []
    assert len(oficina_client.table("maintenance_record_activities").delete().eq(
        "record_id", record_id).execute().data) == 1
