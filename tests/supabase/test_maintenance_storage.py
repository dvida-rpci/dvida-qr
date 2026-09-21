import pytest
from storage3.utils import StorageException

BUCKET = "maintenance-attachments"


def test_tecnico_can_upload_and_read(tecnico_client, random_tag_id):
    path = f"{random_tag_id}/test/1.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    downloaded = tecnico_client.storage.from_(BUCKET).download(path)
    assert downloaded == b"contenido-de-prueba"


def test_tecnico_cannot_delete(tecnico_client, random_tag_id):
    path = f"{random_tag_id}/test/2.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    # Storage no lanza error cuando RLS deniega el borrado: responde OK con
    # lista vacía y no borra nada. Se verifica el efecto, no una excepción.
    removed = tecnico_client.storage.from_(BUCKET).remove([path])
    assert removed == []
    assert tecnico_client.storage.from_(BUCKET).download(path) == b"contenido-de-prueba"


def test_oficina_can_delete(tecnico_client, oficina_client, random_tag_id):
    path = f"{random_tag_id}/test/3.jpg"
    tecnico_client.storage.from_(BUCKET).upload(path, b"contenido-de-prueba")

    removed = oficina_client.storage.from_(BUCKET).remove([path])
    assert len(removed) == 1

    with pytest.raises(StorageException):
        oficina_client.storage.from_(BUCKET).download(path)
