from fastapi.testclient import TestClient
from app.main import SEED_IDS, app

c = TestClient(app)


def login(username='admin', password='admin123'):
    response = c.post('/api/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def test_register_login():
    r = c.post('/api/auth/register', json={'username': 'u1', 'email': 'u1@e.com', 'password': 'p1'})
    assert r.status_code == 200
    l = c.post('/api/auth/login', json={'username': 'u1', 'password': 'p1'})
    assert l.status_code == 200 and 'access_token' in l.json()
    assert l.json()['user']['role'] == 'REGISTERED_USER'
    assert l.json()['user']['roles'] == ['REGISTERED_USER']


def test_set_single_role_contract_changes_role():
    response = c.post(
        f"/api/auth/users/{SEED_IDS['staff']}/roles",
        headers=login(),
        json={'role': 'JUDGE'},
    )

    assert response.status_code == 200
    assert response.json()['role'] == 'JUDGE'
    assert response.json()['roles'] == ['JUDGE']


def test_set_multiple_roles_is_rejected():
    response = c.post(
        f"/api/auth/users/{SEED_IDS['staff']}/roles",
        headers=login(),
        json={'roles': ['JUDGE', 'ADMIN']},
    )

    assert response.status_code == 400
    assert response.json()['error']['code'] == 'ONLY_ONE_ROLE_ALLOWED'


def test_me_returns_role_and_compatible_roles():
    response = c.get('/api/auth/me', headers=login('judge', 'judge123'))

    assert response.status_code == 200
    assert response.json()['role'] == 'JUDGE'
    assert response.json()['roles'] == ['JUDGE']
