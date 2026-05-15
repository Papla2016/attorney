from app.main import apply_anonymization, make_placeholder


def test_internal_access_denied_without_token():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get('/internal/anonymization/jobs/unknown')
    assert r.status_code == 403


def test_placeholder_mapping_same_value_same_placeholder():
    assert make_placeholder('PERSON_FULL_NAME', 1) == 'ФИО1'
    assert make_placeholder('EMAIL', 2) == 'EMAIL2'


def test_person_and_passport_anonymization_reuses_placeholders():
    text = 'Иванов Иван Иванович предъявил паспорт 1234 567890. Иванов Иван Иванович подписал протокол.'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 0, 'end': 20},
        {'type': 'PASSPORT', 'text': 'паспорт 1234 567890', 'start': 31, 'end': 50},
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 52, 'end': 72},
    ]

    anonymized, mappings = apply_anonymization(text, entities)

    assert anonymized == 'ФИО1 предъявил ПАСПОРТ1. ФИО1 подписал протокол.'
    assert [m['placeholder'] for m in mappings] == ['ФИО1', 'ПАСПОРТ1', 'ФИО1']


def test_manual_mapping_replaces_text_on_reanonymize():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    main.restored_docs['manual-doc'] = {
        'document_id': 'manual-doc',
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Иванов И.И. подписал документ. Иванов И.И. пришел.',
        'anonymized_text': 'Иванов И.И. подписал документ. Иванов И.И. пришел.',
        'mappings': [],
    }

    add = client.post(
        '/internal/anonymization/documents/manual-doc/mappings',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'original_value': 'Иванов И.И.', 'entity_type': 'PERSON_FULL_NAME', 'mode': 'new'},
    )
    reanon = client.post(
        '/internal/anonymization/documents/manual-doc/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': add.json()['mappings']},
    )

    assert add.status_code == 200
    assert add.json()['mappings'][0]['placeholder'] == 'ФИО1'
    assert reanon.status_code == 200
    assert reanon.json()['anonymized_text'] == 'ФИО1 подписал документ. ФИО1 пришел.'


def test_existing_placeholder_is_reused_for_new_value():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    main.restored_docs['existing-doc'] = {
        'document_id': 'existing-doc',
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Иванов Иван Иванович и Иванова Ивану Ивановичу',
        'anonymized_text': 'ФИО1 и Иванова Ивану Ивановичу',
        'mappings': [{'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_type': 'PERSON_FULL_NAME', 'source': 'ner'}],
    }

    add = client.post(
        '/internal/anonymization/documents/existing-doc/mappings',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'original_value': 'Иванова Ивану Ивановичу', 'placeholder': 'ФИО1', 'entity_type': 'PERSON_FULL_NAME', 'mode': 'existing'},
    )
    reanon = client.post(
        '/internal/anonymization/documents/existing-doc/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': add.json()['mappings']},
    )

    assert add.status_code == 200
    assert any(m['original_value'] == 'Иванова Ивану Ивановичу' and m['placeholder'] == 'ФИО1' for m in add.json()['mappings'])
    assert reanon.json()['anonymized_text'] == 'ФИО1 и ФИО1'


def test_duplicate_values_keep_single_placeholder():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    main.restored_docs['duplicate-doc'] = {
        'document_id': 'duplicate-doc',
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Петров П.П. Петров П.П.',
        'anonymized_text': 'Петров П.П. Петров П.П.',
        'mappings': [],
    }
    payload = {'original_value': 'Петров П.П.', 'entity_type': 'PERSON_FULL_NAME', 'mode': 'new'}

    first = client.post('/internal/anonymization/documents/duplicate-doc/mappings', headers={'X-Internal-Service-Token': main.INTERNAL}, json=payload)
    second = client.post('/internal/anonymization/documents/duplicate-doc/mappings', headers={'X-Internal-Service-Token': main.INTERNAL}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len([m for m in second.json()['mappings'] if m['original_value'] == 'Петров П.П.']) == 1


def test_patch_delete_merge_and_reanonymize_mappings():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'edit-merge-doc'
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Иванов Иван Иванович, Иванова Ивана Ивановича и Иванову Ивану Ивановичу',
        'anonymized_text': 'ФИО1, ФИО2 и ФИО3',
        'mappings': [
            {'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
            {'placeholder': 'ФИО2', 'original_value': 'Иванова Ивана Ивановича', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
            {'placeholder': 'ФИО3', 'original_value': 'Иванову Ивану Ивановичу', 'entity_type': 'PERSON_FULL_NAME', 'source': 'natasha'},
        ],
    }

    fetched = client.get(f'/internal/anonymization/documents/{doc_id}', headers={'X-Internal-Service-Token': main.INTERNAL})
    assert fetched.status_code == 200
    mappings = fetched.json()['mappings']
    assert all(m.get('id') and m.get('created_at') and m.get('updated_at') for m in mappings)

    target_id = mappings[0]['id']
    source_id = mappings[1]['id']
    third_id = mappings[2]['id']
    patched = client.patch(
        f'/internal/anonymization/documents/{doc_id}/mappings/{source_id}',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'original_value': 'Иванова Ивана Ивановича'},
    )
    assert patched.status_code == 200
    assert next(m for m in patched.json()['mappings'] if m['id'] == source_id)['source'] == 'manual'

    merged = client.post(
        f'/internal/anonymization/documents/{doc_id}/mappings/merge',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'target_mapping_id': target_id, 'source_mapping_ids': [source_id, third_id]},
    )
    assert merged.status_code == 200
    assert {m['placeholder'] for m in merged.json()['mappings']} == {'ФИО1'}

    reanon = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': merged.json()['mappings']},
    )
    assert reanon.status_code == 200
    assert reanon.json()['anonymized_text'] == 'ФИО1, ФИО1 и ФИО1'

    deleted = client.delete(
        f'/internal/anonymization/documents/{doc_id}/mappings/{third_id}',
        headers={'X-Internal-Service-Token': main.INTERNAL},
    )
    assert deleted.status_code == 200
    assert all(m['id'] != third_id for m in deleted.json()['mappings'])
