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


class _MappingFakeAsyncClient(_FakeAsyncClient):
    async def get(self, url, headers=None):
        return _FakeResponse({
            'document_id': 'test-edit-doc',
            'original_text': 'Иванов Иван Иванович и Иванова Ивана Ивановича',
            'anonymized_text': 'ФИО1 и ФИО2',
            'mappings': [
                {'id': 'm1', 'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
                {'id': 'm2', 'placeholder': 'ФИО2', 'original_value': 'Иванова Ивана Ивановича', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
            ],
        })

    async def patch(self, url, headers=None, json=None):
        return _FakeResponse({
            'document_id': 'test-edit-doc',
            'anonymized_text': 'ФИО1 и ФИО2',
            'mappings': [
                {'id': 'm1', 'placeholder': 'ФИО1', 'original_value': json.get('original_value', 'Иванов И.И.'), 'entity_type': 'PERSON_FULL_NAME', 'source': 'manual'},
                {'id': 'm2', 'placeholder': 'ФИО2', 'original_value': 'Иванова Ивана Ивановича', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
            ],
        })

    async def delete(self, url, headers=None):
        return _FakeResponse({
            'document_id': 'test-edit-doc',
            'anonymized_text': 'ФИО1 и ФИО2',
            'mappings': [
                {'id': 'm1', 'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_type': 'PERSON_FULL_NAME', 'source': 'manual'},
            ],
        })

    async def post(self, url, headers=None, json=None):
        if url.endswith('/mappings/merge'):
            return _FakeResponse({
                'document_id': 'test-edit-doc',
                'anonymized_text': 'ФИО1 и ФИО2',
                'mappings': [
                    {'id': 'm1', 'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_type': 'PERSON_FULL_NAME', 'source': 'manual'},
                    {'id': 'm2', 'placeholder': 'ФИО1', 'original_value': 'Иванова Ивана Ивановича', 'entity_type': 'PERSON_FULL_NAME', 'source': 'manual'},
                ],
            })
        if url.endswith('/reanonymize'):
            return _FakeResponse({'document_id': 'test-edit-doc', 'anonymized_text': 'ФИО1 и ФИО1', 'mappings': json['mappings']})
        return await super().post(url, headers=headers, json=json)


def test_update_delete_merge_mappings_and_audit(monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', _MappingFakeAsyncClient)
    client = TestClient(app)
    doc = {
        'id': 'test-edit-doc',
        'case_id': main.seed_case['id'],
        'title': 'Редактирование таблицы',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'original_text': 'Иванов Иван Иванович и Иванова Ивана Ивановича',
        'anonymized_text': 'ФИО1 и ФИО2',
        'mappings': [],
    }
    main.docs.append(doc)
    try:
        fetched = client.get(f'/api/cases/documents/{doc["id"]}/anonymization', headers=auth_header())
        patched = client.patch(
            f'/api/cases/documents/{doc["id"]}/mappings/m1',
            headers=auth_header(),
            json={'original_value': 'Иванов И.И.'},
        )
        merged = client.post(
            f'/api/cases/documents/{doc["id"]}/mappings/merge',
            headers=auth_header(),
            json={'target_mapping_id': 'm1', 'source_mapping_ids': ['m2']},
        )
        reanon = client.post(
            f'/api/cases/documents/{doc["id"]}/reanonymize',
            headers=auth_header(),
            json={'mappings': merged.json()['mappings']},
        )
        deleted = client.delete(f'/api/cases/documents/{doc["id"]}/mappings/m2', headers=auth_header())

        assert fetched.status_code == 200
        assert fetched.json()['case_id'] == main.seed_case['id']
        assert patched.status_code == 200
        assert patched.json()['mappings'][0]['original_value'] == 'Иванов И.И.'
        assert merged.status_code == 200
        assert {m['placeholder'] for m in merged.json()['mappings']} == {'ФИО1'}
        assert reanon.status_code == 200
        assert reanon.json()['anonymized_text'] == 'ФИО1 и ФИО1'
        assert deleted.status_code == 200
        assert all(m['id'] != 'm2' for m in deleted.json()['mappings'])
        assert any(a['action'] == 'UPDATE_MAPPING' and a['details'].get('mapping_id') == 'm1' for a in main.audit_log)
        assert any(a['action'] == 'MERGE_MAPPINGS' and a['details'].get('target_mapping_id') == 'm1' for a in main.audit_log)
        assert any(a['action'] == 'DELETE_MAPPING' and a['details'].get('mapping_id') == 'm2' for a in main.audit_log)
    finally:
        main.docs.remove(doc)


def test_entity_types_dictionary():
    client = TestClient(app)
    response = client.get('/api/cases/dictionaries/entity-types')

    assert response.status_code == 200
    assert {'value': 'PERSON_FULL_NAME', 'label': 'ФИО'} in response.json()


def test_save_anonymization_persists_content_and_pending_fields():
    client = TestClient(app)
    doc = {
        'id': 'test-save-content',
        'case_id': main.seed_case['id'],
        'title': 'Сохранение контента',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'original_text': 'Текст',
        'anonymized_text': 'Текст',
        'mappings': [],
    }
    main.docs.append(doc)
    try:
        payload = {
            'anonymized_text': 'ФИО1',
            'anonymized_content': {'type': 'doc', 'content': []},
            'mappings': [{'placeholder': 'ФИО1', 'original_value': 'Иванов', 'entity_type': 'PERSON_FULL_NAME'}],
            'pending_review': [{'entity_key': 'PERSON::Иванов'}],
            'pending_markers': [{'entity_key': 'PERSON::Иванов', 'start': 0, 'end': 6}],
        }
        saved = client.post(f'/api/cases/documents/{doc["id"]}/save-anonymization', headers=auth_header(), json=payload)
        fetched = client.get(f'/api/cases/documents/{doc["id"]}/anonymization', headers=auth_header())
        assert saved.status_code == 200
        assert saved.json()['anonymized_content'] == payload['anonymized_content']
        assert saved.json()['pending_review'] == payload['pending_review']
        assert fetched.status_code == 200
        assert fetched.json()['anonymized_content'] == payload['anonymized_content']
    finally:
        main.docs.remove(doc)


def test_publish_blocked_by_pending_or_review_entities():
    client = TestClient(app)
    case = {
        **main.seed_case,
        'id': 'test-publish-block-case',
        'case_number': 'publish-block',
        'status': 'DRAFT',
        'staff_user_ids': [JUDGE_ID],
        'judge_user_ids': [JUDGE_ID],
    }
    doc = {
        'id': 'test-publish-block-doc',
        'case_id': case['id'],
        'title': 'Блок публикации',
        'act_type': 'RULING',
        'status': 'ANONYMIZED',
        'document_date': '2026-05-10',
        'anonymized_text': 'Готово',
        'pending_review': [],
        'review_entities': [{'entity_class': 'EMAIL', 'requires_review': True}],
    }
    main.cases.append(case)
    main.case_staff[case['id']] = {JUDGE_ID}
    main.docs.append(doc)
    try:
        response = client.post(f'/api/cases/documents/{doc["id"]}/publish', headers=auth_header())
        assert response.status_code == 409
        error = response.json()['error']
        assert error['code'] == 'PENDING_REDACTION_REVIEW'
        assert error['details']['pending_count'] == 0
        assert error['details']['review_count'] == 1
    finally:
        main.docs.remove(doc)
        main.cases.remove(case)
        main.case_staff.pop(case['id'], None)


class _FailingProcessAsyncClient(_FakeAsyncClient):
    async def post(self, url, headers=None, json=None):
        if url.endswith('/process'):
            return _FakeResponse({
                'error': {
                    'code': 'CROSS_TEXT_NODE_MENTION_UNSUPPORTED',
                    'message': 'Упоминание пересекает несколько text-node TipTap и не может быть безопасно заменено автоматически',
                    'details': {'mention_id': 'm1'},
                }
            }, status_code=409)
        return await super().post(url, headers=headers, json=json)


def test_upload_does_not_report_anonymized_when_cross_node_redaction_is_unsupported(monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', _FailingProcessAsyncClient)
    client = TestClient(app)

    response = client.post(
        f'/api/cases/{main.seed_case["id"]}/documents',
        headers=auth_header(),
        json={
            'title': 'Сложный rich документ',
            'act_type': 'RULING',
            'text': 'Иванов Иван Иванович',
            'content_format': 'TIPTAP_JSON',
            'content': {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Иванов'}, {'type': 'text', 'text': ' Иван Иванович'}]}]},
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload['error']['code'] == 'CROSS_TEXT_NODE_MENTION_UNSUPPORTED'
    failed_docs = [d for d in main.docs if d['title'] == 'Сложный rich документ']
    assert failed_docs
    assert failed_docs[-1]['status'] == 'ANONYMIZATION_FAILED'
    assert failed_docs[-1].get('public_anonymized_document_id') is None
    main.docs[:] = [d for d in main.docs if d['title'] != 'Сложный rich документ']
