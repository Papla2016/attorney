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
