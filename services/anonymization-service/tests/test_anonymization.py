from fastapi.testclient import TestClient
from app.main import app


def test_internal_access_denied_without_token():
    client = TestClient(app)
    r = client.get('/internal/anonymization/jobs/unknown')
    assert r.status_code == 403


def test_placeholder_mapping_same_value_same_placeholder():
    from app.main import make_placeholder
    assert make_placeholder('PERSON_FULL_NAME', 1) == 'ФИО1'
    assert make_placeholder('EMAIL', 2) == 'EMAIL2'
