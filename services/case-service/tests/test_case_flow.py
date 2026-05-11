from jose import jwt
from fastapi.testclient import TestClient
from app import main
from app.main import ALG, JUDGE_ID, SECRET, app


def auth_header(user_id=JUDGE_ID, roles=None):
    token = jwt.encode({'sub': user_id, 'roles': roles or ['JUDGE']}, SECRET, algorithm=ALG)
    return {'Authorization': f'Bearer {token}'}


def test_public_seed_document_returns_non_empty_anonymized_text():
    client = TestClient(app)
    response = client.get(f'/api/cases/public/documents/{main.seed_doc_id}')

    assert response.status_code == 200
    payload = response.json()
    assert payload['document_id'] == main.seed_doc_id
    assert payload['case_id'] == main.seed_case['id']
    assert payload['anonymized_text'].strip()
    assert payload['metadata']['case_number'] == main.seed_case['case_number']


def test_unpublished_document_is_not_public():
    client = TestClient(app)
    case_id = main.seed_case['id']
    doc = {
        'id': 'test-unpublished-doc',
        'case_id': case_id,
        'title': 'Черновик',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'anonymized_text': 'Текст черновика',
        'public_anonymized_document_id': 'test-unpublished-doc',
    }
    main.docs.append(doc)
    try:
        detail = client.get(f'/api/cases/public/documents/{doc["id"]}')
        listing = client.get('/api/cases/public/documents')

        assert detail.status_code == 404
        assert all(item['document_id'] != doc['id'] for item in listing.json()['items'])
    finally:
        main.docs.remove(doc)


def test_patch_case_status_changes_status_and_keeps_staff_visibility():
    client = TestClient(app)
    response = client.patch(f'/api/cases/{main.seed_case["id"]}/status', headers=auth_header(), json={'status': 'DRAFT'})
    staff = client.get('/api/cases/staff/my', headers=auth_header())
    restore = client.patch(f'/api/cases/{main.seed_case["id"]}/status', headers=auth_header(), json={'status': 'PUBLISHED'})

    assert response.status_code == 200
    assert response.json()['status'] == 'DRAFT'
    assert any(item['id'] == main.seed_case['id'] and item['status'] == 'DRAFT' for item in staff.json()['items'])
    assert restore.status_code == 200


def test_publish_document_sets_document_and_case_published():
    client = TestClient(app)
    case = {
        **main.seed_case,
        'id': 'test-publish-case',
        'case_number': 'publish-1',
        'status': 'DRAFT',
        'staff_user_ids': [JUDGE_ID],
        'judge_user_ids': [JUDGE_ID],
    }
    doc = {
        'id': 'test-publish-doc',
        'case_id': case['id'],
        'title': 'Для публикации',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'anonymized_text': 'Непустой обезличенный текст',
        'public_anonymized_document_id': 'test-publish-doc',
    }
    main.cases.append(case)
    main.case_staff[case['id']] = {JUDGE_ID}
    main.docs.append(doc)
    try:
        response = client.post(f'/api/cases/documents/{doc["id"]}/publish', headers=auth_header())

        assert response.status_code == 200
        assert response.json() == {
            'ok': True,
            'document_id': doc['id'],
            'document_status': 'PUBLISHED',
            'case_id': case['id'],
            'case_status': 'PUBLISHED',
        }
        assert doc['status'] == 'PUBLISHED'
        assert case['status'] == 'PUBLISHED'
    finally:
        main.docs.remove(doc)
        main.cases.remove(case)
        main.case_staff.pop(case['id'], None)


def test_patch_case_updates_only_passed_fields():
    client = TestClient(app)
    response = client.patch(
        f'/api/cases/{main.seed_case["id"]}',
        headers=auth_header(),
        json={'region': 'Новый регион', 'judge_names': 'Судья 1, Судья 2'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['region'] == 'Новый регион'
    assert payload['judge_names'] == ['Судья 1', 'Судья 2']
    assert payload['case_number'] == main.seed_case['case_number']

    client.patch(
        f'/api/cases/{main.seed_case["id"]}',
        headers=auth_header(),
        json={'region': 'Белгородская область', 'judge_names': ['Светашова С.Н.']},
    )


def test_delete_case_document_removes_document_and_audits():
    client = TestClient(app)
    doc = {
        'id': 'test-delete-doc',
        'case_id': main.seed_case['id'],
        'title': 'Удалить',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'anonymized_text': 'text',
        'mappings': [],
    }
    main.docs.append(doc)
    try:
        response = client.delete(f'/api/cases/{main.seed_case["id"]}/documents/{doc["id"]}', headers=auth_header())

        assert response.status_code == 200
        assert response.json() == {'ok': True}
        assert all(d['id'] != doc['id'] for d in main.docs)
        assert any(a['action'] == 'DELETE_DOCUMENT' and a['resource_id'] == doc['id'] for a in main.audit_log)
    finally:
        if doc in main.docs:
            main.docs.remove(doc)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        if url.endswith('/mappings'):
            return _FakeResponse({'document_id': 'test-manual-doc', 'anonymized_text': 'Иванов И.И.', 'mappings': [{'placeholder': 'ФИО1', 'original_value': 'Иванов И.И.', 'entity_type': 'PERSON_FULL_NAME', 'source': 'manual'}]})
        if url.endswith('/reanonymize'):
            return _FakeResponse({'document_id': 'test-manual-doc', 'anonymized_text': 'ФИО1 подписал', 'mappings': json['mappings']})
        if url.endswith('/process'):
            return _FakeResponse({'job_id': 'job-1', 'anonymized_text': 'ФИО1 подал заявление', 'mappings': [{'placeholder': 'ФИО1', 'original_value': 'Иванов И.И.', 'entity_type': 'PERSON_FULL_NAME'}]})
        return _FakeResponse({})


def test_add_mapping_reanonymize_and_save(monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', _FakeAsyncClient)
    client = TestClient(app)
    doc = {
        'id': 'test-manual-doc',
        'case_id': main.seed_case['id'],
        'title': 'Ручная правка',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'original_text': 'Иванов И.И. подписал',
        'anonymized_text': 'Иванов И.И. подписал',
        'mappings': [],
    }
    main.docs.append(doc)
    try:
        mapping = client.post(
            f'/api/cases/documents/{doc["id"]}/mappings',
            headers=auth_header(),
            json={'original_value': 'Иванов И.И.', 'placeholder': 'ФИО1', 'entity_type': 'PERSON_FULL_NAME', 'mode': 'existing'},
        )
        reanon = client.post(
            f'/api/cases/documents/{doc["id"]}/reanonymize',
            headers=auth_header(),
            json={'mappings': mapping.json()['mappings']},
        )
        saved = client.post(
            f'/api/cases/documents/{doc["id"]}/save-anonymization',
            headers=auth_header(),
            json={'anonymized_text': reanon.json()['anonymized_text'], 'mappings': reanon.json()['mappings']},
        )

        assert mapping.status_code == 200
        assert mapping.json()['mappings'][0]['placeholder'] == 'ФИО1'
        assert reanon.status_code == 200
        assert reanon.json()['anonymized_text'] == 'ФИО1 подписал'
        assert saved.status_code == 200
        assert saved.json()['anonymized_text'] == 'ФИО1 подписал'
        assert any(a['action'] == 'ADD_MANUAL_MAPPING' for a in main.audit_log)
        assert any(a['action'] == 'REANONYMIZE_DOCUMENT' for a in main.audit_log)
        assert any(a['action'] == 'SAVE_ANONYMIZATION' for a in main.audit_log)
    finally:
        main.docs.remove(doc)


def test_upload_document_returns_anonymized_text_and_mappings(monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', _FakeAsyncClient)
    client = TestClient(app)

    response = client.post(
        f'/api/cases/{main.seed_case["id"]}/documents',
        headers=auth_header(),
        json={'title': 'Загрузка', 'act_type': 'RULING', 'text': 'Иванов И.И. подал заявление'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ANONYMIZED'
    assert payload['anonymized_text'] == 'ФИО1 подал заявление'
    assert payload['mappings'][0]['original_value'] == 'Иванов И.И.'
    main.docs[:] = [d for d in main.docs if d['id'] != payload['document_id']]
