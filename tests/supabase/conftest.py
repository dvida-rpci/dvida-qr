import os
import uuid

import pytest
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(".env.test")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

TEST_PASSWORD = "Test1234!"
TECNICO_EMAIL = "tecnico@test.local"
OFICINA_EMAIL = "oficina@test.local"


@pytest.fixture(scope="session")
def service_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _recreate_test_user(service_client: Client, email: str, role: str) -> str:
    existing = service_client.auth.admin.list_users()
    for user in existing:
        if user.email == email:
            service_client.auth.admin.delete_user(user.id)

    result = service_client.auth.admin.create_user(
        {"email": email, "password": TEST_PASSWORD, "email_confirm": True}
    )
    user_id = result.user.id
    service_client.table("profiles").insert(
        {"user_id": user_id, "full_name": f"Test {role}", "role": role}
    ).execute()
    return user_id


@pytest.fixture(scope="session")
def seed_test_users(service_client: Client) -> dict[str, str]:
    tecnico_id = _recreate_test_user(service_client, TECNICO_EMAIL, "tecnico")
    oficina_id = _recreate_test_user(service_client, OFICINA_EMAIL, "oficina")
    return {"tecnico": tecnico_id, "oficina": oficina_id}


def _signed_in_client(email: str) -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.auth.sign_in_with_password({"email": email, "password": TEST_PASSWORD})
    return client


@pytest.fixture
def tecnico_client(seed_test_users) -> Client:
    return _signed_in_client(TECNICO_EMAIL)


@pytest.fixture
def oficina_client(seed_test_users) -> Client:
    return _signed_in_client(OFICINA_EMAIL)


@pytest.fixture
def tecnico_id(seed_test_users) -> str:
    return seed_test_users["tecnico"]


@pytest.fixture
def oficina_id(seed_test_users) -> str:
    return seed_test_users["oficina"]


@pytest.fixture
def random_tag_id() -> str:
    return f"TEST-{uuid.uuid4().hex[:8]}"
