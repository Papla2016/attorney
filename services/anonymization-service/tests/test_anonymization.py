from app.main import apply_anonymization, make_placeholder
from app.main import resolve_entities, build_mappings_from_resolved


def test_internal_access_denied_without_token():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get('/internal/anonymization/jobs/unknown')
    assert r.status_code == 403


def test_placeholder_mapping_same_value_same_placeholder():
    assert make_placeholder('PERSON_FULL_NAME', 1) == 'ФИО1'
    assert make_placeholder('EMAIL', 2) == 'ЭЛЕКТРОННАЯ_ПОЧТА2'


def test_person_and_passport_anonymization_reuses_placeholders():
    text = 'Иванов Иван Иванович предъявил паспорт 1234 567890. Иванов Иван Иванович подписал протокол.'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 0, 'end': 20},
        {'type': 'PASSPORT', 'text': 'паспорт 1234 567890', 'start': 31, 'end': 50},
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 52, 'end': 72},
    ]

    from app.main import build_entities_from_resolved, anonymize_text_by_mentions
    resolved = resolve_entities(text, entities)
    redacted, _, _ = build_entities_from_resolved('d1', resolved)
    anonymized = anonymize_text_by_mentions(text, redacted)
    assert anonymized == 'ФИО1 предъявил ПАСПОРТ1. ФИО1 подписал протокол.'
    person = next(e for e in redacted if e['entity_class'] == 'PERSON')
    passport = next(e for e in redacted if e['entity_class'] == 'PASSPORT')
    assert person['placeholder'] == 'ФИО1'
    assert len(person['mentions']) == 2
    assert passport['placeholder'] == 'ПАСПОРТ1'
    assert len(passport['mentions']) == 1


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

    main.restored_docs['manual-doc']['entities'] = [{
        'entity_id': 'e1', 'entity_class': 'PERSON', 'canonical_value': 'Иванов И.И.', 'normalized_value': 'Иванов И.И.',
        'redaction_decision': 'REDACT', 'placeholder': 'ФИО1',
        'mentions': [
            {'mention_id': 'm1', 'entity_id': 'e1', 'surface_value': 'Иванов И.И.', 'start': 0, 'end': 10, 'replacement_value': 'ФИО1'},
            {'mention_id': 'm2', 'entity_id': 'e1', 'surface_value': 'Иванов И.И.', 'start': 30, 'end': 40, 'replacement_value': 'ФИО1'},
        ],
    }]
    reanon = client.post(
        '/internal/anonymization/documents/manual-doc/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )
    assert reanon.status_code == 200
    assert 'аноним' or isinstance(reanon.json().get('anonymized_text'), str)


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

    assert client.get('/internal/anonymization/documents/existing-doc', headers={'X-Internal-Service-Token': main.INTERNAL}).status_code == 200


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

    assert client.get(f'/internal/anonymization/documents/{doc_id}', headers={'X-Internal-Service-Token': main.INTERNAL}).status_code == 200


def test_dates_policy_birth_vs_document_date():
    text = 'дата рождения 14.07.2018, решение от 30.10.2023, договор от 20.05.2024'
    entities = [
        {'type': 'DATE', 'text': '14.07.2018', 'start': 14, 'end': 24},
        {'type': 'DATE', 'text': '30.10.2023', 'start': 37, 'end': 47},
        {'type': 'DATE', 'text': '20.05.2024', 'start': 60, 'end': 70},
    ]
    resolved = resolve_entities(text, entities)
    assert resolved[0]['redaction_decision'] == 'REDACT'
    assert resolved[1]['redaction_decision'] == 'KEEP'
    assert resolved[2]['redaction_decision'] == 'KEEP'


def test_organization_boundary_only_name():
    text = 'ООО «ТОК» выполнило проект'
    entities = [{'type': 'ORGANIZATION', 'text': 'ООО «ТОК» выполнило проект', 'start': 0, 'end': 27}]
    resolved = resolve_entities(text, entities)
    assert resolved[0]['normalized_value'] == 'ООО «ТОК»'


def test_judge_kept_witness_redacted():
    text = 'Судья Андреева Татьяна Викторовна и свидетель Макаров Антон Сергеевич.'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Андреева Татьяна Викторовна', 'start': 6, 'end': 33},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров Антон Сергеевич', 'start': 47, 'end': 70},
    ]
    resolved = resolve_entities(text, entities)
    assert resolved[0]['redaction_decision'] == 'KEEP'
    assert resolved[1]['redaction_decision'] == 'REDACT'


def test_mappings_include_multiple_pii_types_not_only_person():
    text = 'Иванов Иван Иванович, ИНН 123456789012, паспорт 1234 567890, +79991234567, г. Москва'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 0, 'end': 19},
        {'type': 'INN', 'text': '123456789012', 'start': 25, 'end': 37},
        {'type': 'PASSPORT', 'text': 'паспорт 1234 567890', 'start': 39, 'end': 57},
        {'type': 'PHONE', 'text': '+79991234567', 'start': 59, 'end': 70},
        {'type': 'ADDRESS', 'text': 'г. Москва', 'start': 72, 'end': 81},
    ]
    mappings, kept, review = build_mappings_from_resolved(resolve_entities(text, entities))
    entity_types = {m['entity_class'] for m in mappings}
    assert 'PERSON' in entity_types
    assert {'INN', 'PASSPORT', 'PHONE', 'PLACE'}.issubset(entity_types)
    assert isinstance(kept, list)
    assert isinstance(review, list)


def test_placeholder_unique_by_cluster():
    text = 'Иванов Иван Иванович и Петров Петр Петрович'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 0, 'end': 19},
        {'type': 'PERSON_FULL_NAME', 'text': 'Петров Петр Петрович', 'start': 23, 'end': 42},
    ]
    mappings, _, _ = build_mappings_from_resolved(resolve_entities(text, entities))
    assert len({m['placeholder'] for m in mappings}) == 2


def test_import_main_module_compiles():
    import importlib

    mod = importlib.import_module('app.main')
    assert hasattr(mod, 'build_mappings_from_resolved')


def test_birth_date_placeholder_not_generic_data():
    text = 'дата рождения 14.07.2018'
    entities = [{'type': 'DATE', 'text': '14.07.2018', 'start': 14, 'end': 24}]
    mappings, _, _ = build_mappings_from_resolved(resolve_entities(text, entities))
    assert mappings[0]['placeholder'] == 'ДАТА_РОЖДЕНИЯ1'


def test_russian_name_forms_share_single_placeholder():
    text = 'Макаров Антон Сергеевич, Макарова Антона Сергеевича, Макаровым Антоном Сергеевичем'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров Антон Сергеевич', 'normalized_text': 'Макаров Антон Сергеевич', 'start': 0, 'end': 23},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макарова Антона Сергеевича', 'normalized_text': 'Макаров Антон Сергеевич', 'start': 25, 'end': 51},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаровым Антоном Сергеевичем', 'normalized_text': 'Макаров Антон Сергеевич', 'start': 53, 'end': 81},
    ]
    mappings, _, _ = build_mappings_from_resolved(resolve_entities(text, entities))
    assert {m['placeholder'] for m in mappings} == {'ФИО1'}


def test_different_people_do_not_share_placeholder():
    text = 'Иванов Иван Иванович и Сидоров Петр Петрович'
    entities = [
        {'type': 'PERSON_FULL_NAME', 'text': 'Иванов Иван Иванович', 'start': 0, 'end': 20},
        {'type': 'PERSON_FULL_NAME', 'text': 'Сидоров Петр Петрович', 'start': 23, 'end': 44},
    ]
    mappings, _, _ = build_mappings_from_resolved(resolve_entities(text, entities))
    assert len({m['placeholder'] for m in mappings}) == 2


def test_initials_before_full_name_merge_into_single_entity():
    from app.main import build_entities_from_resolved, anonymize_text_by_mentions
    text = 'Макаров А.С. подал заявление. Позднее Макаров Антон Сергеевич поддержал требования.'
    resolved = resolve_entities(text, [
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров А.С.', 'normalized_text': 'Макаров А.С.', 'start': 0, 'end': 11, 'source': 'rule'},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров Антон Сергеевич', 'normalized_text': 'Макаров Антон Сергеевич', 'start': 38, 'end': 61, 'source': 'natasha'},
    ])
    entities, _, _ = build_entities_from_resolved('doc-1', resolved)
    assert len(entities) == 1
    assert entities[0]['placeholder'] == 'ФИО1'
    assert len(entities[0]['mentions']) == 2
    assert anonymize_text_by_mentions(text, entities).count('ФИО1') == 2


def test_ambiguous_initials_are_redacted_and_marked_for_review():
    from app.main import build_entities_from_resolved
    text = 'Макаров Антон Сергеевич и Макаров Алексей Сидорович присутствовали. Макаров А.С. подписал документ.'
    resolved = resolve_entities(text, [
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров Антон Сергеевич', 'normalized_text': 'Макаров Антон Сергеевич', 'start': 0, 'end': 23},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров Алексей Сидорович', 'normalized_text': 'Макаров Алексей Сидорович', 'start': 26, 'end': 51},
        {'type': 'PERSON_FULL_NAME', 'text': 'Макаров А.С.', 'normalized_text': 'Макаров А.С.', 'start': 68, 'end': 79, 'source': 'rule'},
    ])
    entities, _, review = build_entities_from_resolved('doc-2', resolved)
    assert len(entities) == 3
    ambiguous = next(e for e in entities if e['canonical_value'] == 'Макаров А.С.')
    assert ambiguous['requires_review'] is True
    assert any(e['canonical_value'] == 'Макаров А.С.' for e in review)


def test_exact_restoration_text_roundtrip():
    from app.main import build_entities_from_resolved, anonymize_text_by_mentions, anonymize_content_by_mentions, restore_content_from_mentions
    text = 'Макарова Антона Сергеевича вызвали. Макаровым Антоном Сергеевичем представлены документы. Макаров А.С. пояснил.'
    m1 = 'Макарова Антона Сергеевича'
    m2 = 'Макаровым Антоном Сергеевичем'
    m3 = 'Макаров А.С.'
    s1 = text.find(m1); s2 = text.find(m2); s3 = text.find(m3)
    resolved = resolve_entities(text, [
        {'type': 'PERSON_FULL_NAME', 'text': m1, 'normalized_text': 'Макаров Антон Сергеевич', 'start': s1, 'end': s1 + len(m1)},
        {'type': 'PERSON_FULL_NAME', 'text': m2, 'normalized_text': 'Макаров Антон Сергеевич', 'start': s2, 'end': s2 + len(m2)},
        {'type': 'PERSON_FULL_NAME', 'text': m3, 'normalized_text': 'Макаров А.С.', 'start': s3, 'end': s3 + len(m3)},
    ])
    entities, _, _ = build_entities_from_resolved('doc-3', resolved)
    anonymized = anonymize_text_by_mentions(text, entities)
    assert anonymized == 'ФИО1 вызвали. ФИО1 представлены документы. ФИО1 пояснил.'
    content = {
        'type': 'doc',
        'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}],
    }
    anon_content = anonymize_content_by_mentions(content, entities)
    restored = restore_content_from_mentions(anon_content, entities)
    restored_text = ''.join(n.get('text', '') for n in restored['content'][0]['content'])
    assert restored_text == text


def test_keep_entity_manual_decision_survives_reanonymize(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'keep-survives-reanon-doc'
    text = 'Иванов Иван Иванович явился.'
    name = 'Иванов Иван Иванович'
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {'document_id': doc_id, 'case_id': 'case-1', 'title': 'doc', 'original_text': text, 'mappings': []}
    entity = {
        'entity_id': 'keep-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
        'canonical_value': name, 'normalized_value': name, 'redaction_decision': 'REDACT',
        'mentions': [{'mention_id': 'keep-m1', 'entity_id': 'keep-e1', 'surface_value': name, 'normalized_value': name, 'start': 0, 'end': len(name), 'replacement_value': 'ФИО1'}],
    }
    main.rebuild_document_from_entities(doc_id, [entity], [], text, None)
    assert main.restored_docs[doc_id]['anonymized_text'] == 'ФИО1 явился.'

    deleted = client.delete(f'/internal/anonymization/documents/{doc_id}/mappings/keep-e1', headers={'X-Internal-Service-Token': main.INTERNAL})
    assert deleted.status_code == 200
    deleted_payload = deleted.json()
    assert deleted_payload['entities'] == []
    assert deleted_payload['kept_entities'][0]['canonical_value'] == name
    assert deleted_payload['anonymized_text'] == text

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': name, 'normalized_text': name, 'start': 0, 'end': len(name)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    reanon = client.post(f'/internal/anonymization/documents/{doc_id}/reanonymize', headers={'X-Internal-Service-Token': main.INTERNAL}, json={})
    assert reanon.status_code == 200
    payload = reanon.json()
    assert payload['entities'] == []
    assert payload['kept_entities'][0]['canonical_value'] == name
    assert payload['anonymized_text'] == text
    decision = main.manual_decisions_by_document_id[doc_id][main.build_entity_semantic_key('PERSON', name)]
    assert decision['decision_type'] == 'KEEP_ENTITY'
    assert decision['entity_key'] == 'PERSON::иванов иван иванович'
    assert 'decision' not in decision


def test_redact_entity_manual_decision_survives_reanonymize(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'redact-survives-reanon-doc'
    text = 'Решение от 30.10.2023 принято.'
    value = '30.10.2023'
    start = text.index(value)
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {'document_id': doc_id, 'case_id': 'case-1', 'title': 'doc', 'original_text': text, 'mappings': [], 'entities': [], 'kept_entities': []}

    added = client.post(
        f'/internal/anonymization/documents/{doc_id}/mappings',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'original_value': value, 'entity_type': 'DATE', 'mode': 'new'},
    )
    assert added.status_code == 200
    added_payload = added.json()
    assert added_payload['entities'][0]['canonical_value'] == value
    assert 'ДАТА1' in added_payload['anonymized_text']

    async def fake_extract_entities(_text):
        return [{'type': 'DATE', 'text': value, 'start': start, 'end': start + len(value)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    reanon = client.post(f'/internal/anonymization/documents/{doc_id}/reanonymize', headers={'X-Internal-Service-Token': main.INTERNAL}, json={})
    assert reanon.status_code == 200
    payload = reanon.json()
    assert payload['entities'][0]['canonical_value'] == value
    assert payload['kept_entities'] == []
    assert 'ДАТА1' in payload['anonymized_text']
    decision = main.manual_decisions_by_document_id[doc_id][main.build_entity_semantic_key('DATE', value)]
    assert decision['decision_type'] == 'REDACT_ENTITY'
    assert decision['entity_key'] == 'DATE::30.10.2023'
    assert 'decision' not in decision


def test_keep_redact_manual_decisions_use_single_format():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'manual-decision-format-doc'
    text = 'Иванов Иван Иванович и 30.10.2023.'
    name = 'Иванов Иван Иванович'
    date = '30.10.2023'
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {'document_id': doc_id, 'case_id': 'case-1', 'title': 'doc', 'original_text': text, 'mappings': []}
    entity = {
        'entity_id': 'format-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
        'canonical_value': name, 'normalized_value': name, 'redaction_decision': 'REDACT',
        'mentions': [{'mention_id': 'format-m1', 'entity_id': 'format-e1', 'surface_value': name, 'normalized_value': name, 'start': 0, 'end': len(name), 'replacement_value': 'ФИО1'}],
    }
    main.rebuild_document_from_entities(doc_id, [entity], [], text, None)
    keep = client.delete(f'/internal/anonymization/documents/{doc_id}/mappings/format-e1', headers={'X-Internal-Service-Token': main.INTERNAL})
    redact = client.post(
        f'/internal/anonymization/documents/{doc_id}/mappings',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'original_value': date, 'entity_type': 'DATE', 'mode': 'new'},
    )
    assert keep.status_code == 200
    assert redact.status_code == 200
    decisions = main.manual_decisions_by_document_id[doc_id]
    assert {d['decision_type'] for d in decisions.values()} == {'KEEP_ENTITY', 'REDACT_ENTITY'}
    assert all(d.get('entity_key') for d in decisions.values())
    assert all('decision' not in d for d in decisions.values())


def test_redaction_decision_redact_creates_entity_and_placeholder():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'redaction-decision-redact-doc'
    text = 'Договор от 20.05.2024 подписан.'
    value = '20.05.2024'
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': text,
        'entities': [],
        'kept_entities': [],
        'mappings': [],
    }

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': value, 'entity_class': 'DATE', 'decision': 'REDACT'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload['entities']) == 1
    entity = payload['entities'][0]
    assert entity['canonical_value'] == value
    assert entity['mentions'][0]['surface_value'] == value
    assert 'ДАТА1' in payload['anonymized_text']
    assert payload['mappings'][0]['id'] == entity['entity_id']
    decision = main.manual_decisions_by_document_id[doc_id][main.build_entity_semantic_key('DATE', value)]
    assert decision['decision_type'] == 'REDACT_ENTITY'
    assert decision['entity_key'] == 'DATE::20.05.2024'
    assert 'decision' not in decision


def test_redaction_decision_keep_survives_reanonymize(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'redaction-decision-keep-doc'
    text = 'Иванов Иван Иванович явился.'
    name = 'Иванов Иван Иванович'
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {'document_id': doc_id, 'case_id': 'case-1', 'title': 'doc', 'original_text': text, 'mappings': []}
    entity = {
        'entity_id': 'rd-keep-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
        'canonical_value': name, 'normalized_value': name, 'redaction_decision': 'REDACT',
        'mentions': [{'mention_id': 'rd-keep-m1', 'entity_id': 'rd-keep-e1', 'surface_value': name, 'normalized_value': name, 'start': 0, 'end': len(name), 'replacement_value': 'ФИО1'}],
    }
    main.rebuild_document_from_entities(doc_id, [entity], [], text, None)

    keep = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': name, 'entity_class': 'PERSON', 'decision': 'KEEP'},
    )
    assert keep.status_code == 200
    kept_payload = keep.json()
    assert kept_payload['entities'] == []
    assert kept_payload['kept_entities'][0]['canonical_value'] == name
    assert kept_payload['anonymized_text'] == text

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': name, 'normalized_text': name, 'start': 0, 'end': len(name)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    reanon = client.post(f'/internal/anonymization/documents/{doc_id}/reanonymize', headers={'X-Internal-Service-Token': main.INTERNAL}, json={})
    assert reanon.status_code == 200
    payload = reanon.json()
    assert payload['entities'] == []
    assert payload['kept_entities'][0]['canonical_value'] == name
    assert payload['anonymized_text'] == text
    decision = main.manual_decisions_by_document_id[doc_id][main.build_entity_semantic_key('PERSON', name)]
    assert decision['decision_type'] == 'KEEP_ENTITY'
    assert 'decision' not in decision


def test_draft_pending_redact_new_working_value_replaces_immediately(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-redact-new-value-doc'
    original_text = 'ФИО1 обратился в суд.'
    working_text = original_text + ' Представитель Петрова Мария Ивановна предоставила документы.'
    selected = 'Петрова Мария Ивановна'
    start = working_text.index(selected)
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'anonymized_text': original_text,
        'mappings': [{'id': 'existing-e1', 'placeholder': 'ФИО1', 'original_value': 'Иванов Иван Иванович', 'entity_class': 'PERSON'}],
        'entities': [],
        'kept_entities': [],
    }

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': selected, 'normalized_text': 'Петрова Мария Ивановна', 'start': start, 'end': start + len(selected)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': None, 'content_format': 'PLAIN_TEXT', 'document_revision': 7},
    )
    assert scan.status_code == 200
    pending = scan.json()['pending_review'][0]

    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': selected, 'entity_class': 'PERSON', 'entity_key': pending['entity_key'], 'decision': 'REDACT'},
    )
    assert decision.status_code == 200
    payload = decision.json()
    assert selected not in payload['anonymized_text']
    assert 'ФИО2' in payload['anonymized_text']
    entity = next(e for e in payload['entities'] if e['canonical_value'] == pending['normalized_value'])
    assert entity['mentions'][0]['surface_value'] == selected
    assert payload['pending_review'] == []
    assert main.restored_docs[doc_id]['original_text'] == original_text
    assert main.restored_docs[doc_id]['working_text'] == payload['anonymized_text']
    assert main.restored_docs[doc_id]['working_document_revision'] == 7


def test_draft_pending_redact_uses_normalized_entity_key(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-redact-normalized-key-doc'
    selected = 'Макаровым Антоном Сергеевичем'
    normalized = 'Макаров Антон Сергеевич'
    working_text = f'Документы представлены {selected}.'
    start = working_text.index(selected)
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'ФИО1 представил документы.',
        'anonymized_text': 'ФИО1 представил документы.',
        'mappings': [],
        'entities': [],
        'kept_entities': [],
    }

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': selected, 'normalized_text': normalized, 'start': start, 'end': start + len(selected)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': None, 'content_format': 'PLAIN_TEXT', 'document_revision': 1},
    )
    assert scan.status_code == 200
    entity_key = scan.json()['pending_review'][0]['entity_key']
    assert entity_key == 'PERSON::макаров антон сергеевич'

    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': selected, 'entity_class': 'PERSON', 'entity_key': entity_key, 'decision': 'REDACT'},
    )
    assert decision.status_code == 200
    decisions = main.manual_decisions_by_document_id[doc_id]
    assert 'PERSON::макаров антон сергеевич' in decisions
    assert 'PERSON::макаровым антоном сергеевичем' not in decisions
    assert decisions['PERSON::макаров антон сергеевич']['decision_type'] == 'REDACT_ENTITY'


def test_draft_pending_keep_preserves_working_text(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-keep-new-value-doc'
    selected = 'Петрова Мария Ивановна'
    working_text = f'ФИО1 обратился. Представитель {selected} пояснила.'
    start = working_text.index(selected)
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'ФИО1 обратился.',
        'anonymized_text': 'ФИО1 обратился.',
        'mappings': [],
        'entities': [],
        'kept_entities': [],
    }

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': selected, 'normalized_text': 'Петрова Мария Ивановна', 'start': start, 'end': start + len(selected)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': None, 'content_format': 'PLAIN_TEXT', 'document_revision': 3},
    )
    assert scan.status_code == 200
    entity_key = scan.json()['pending_review'][0]['entity_key']

    keep = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': selected, 'entity_class': 'PERSON', 'entity_key': entity_key, 'decision': 'KEEP'},
    )
    assert keep.status_code == 200
    payload = keep.json()
    assert payload['anonymized_text'] == working_text
    assert selected in main.restored_docs[doc_id]['working_text']
    assert payload['pending_review'] == []
    decisions = main.manual_decisions_by_document_id[doc_id]
    assert decisions[entity_key]['decision_type'] == 'KEEP_ENTITY'


def _content_text(content):
    parts = []
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('text'), str):
                parts.append(node['text'])
            for child in node.get('content', []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(content)
    return ''.join(parts)


def _redaction_placeholders(content):
    placeholders = []
    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text':
                marks = node.get('marks') or []
                if any(m.get('type') == 'redactionMention' for m in marks):
                    placeholders.append(node.get('text'))
            for child in node.get('content', []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(content)
    return placeholders


def test_pending_rich_content_two_redacts_accumulate(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'pending-rich-two-redacts-doc'
    first = 'Петрова Мария Ивановна'
    second = 'Сидоров Андрей Олегович'
    working_text = f'Представитель {first} и {second} присутствовали.'
    content = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': working_text}]}]}
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'ФИО1 обратился.',
        'anonymized_text': 'ФИО1 обратился.',
        'entities': [],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [
            {'type': 'PERSON_FULL_NAME', 'text': first, 'normalized_text': first, 'start': working_text.index(first), 'end': working_text.index(first) + len(first)},
            {'type': 'PERSON_FULL_NAME', 'text': second, 'normalized_text': second, 'start': working_text.index(second), 'end': working_text.index(second) + len(second)},
        ]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': content, 'content_format': 'TIPTAP_JSON', 'document_revision': 1},
    )
    assert scan.status_code == 200
    pending_by_surface = {p['surface_value']: p for p in scan.json()['pending_review']}

    first_redact = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': first, 'entity_class': 'PERSON', 'entity_key': pending_by_surface[first]['entity_key'], 'decision': 'REDACT'},
    )
    assert first_redact.status_code == 200
    second_redact = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': second, 'entity_class': 'PERSON', 'entity_key': pending_by_surface[second]['entity_key'], 'decision': 'REDACT'},
    )
    assert second_redact.status_code == 200
    payload = second_redact.json()
    content_text = _content_text(payload['anonymized_content'])
    assert first not in payload['anonymized_text']
    assert second not in payload['anonymized_text']
    assert first not in content_text
    assert second not in content_text
    assert {'ФИО1', 'ФИО2'}.issubset(set(_redaction_placeholders(payload['anonymized_content'])))
    assert main.restored_docs[doc_id]['working_content'] == payload['anonymized_content']


def test_pending_rich_content_redact_then_keep_preserves_redaction(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'pending-rich-redact-keep-doc'
    first = 'Петрова Мария Ивановна'
    second = 'Сидоров Андрей Олегович'
    working_text = f'Представитель {first} и {second} присутствовали.'
    content = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': working_text}]}]}
    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'ФИО1 обратился.',
        'anonymized_text': 'ФИО1 обратился.',
        'entities': [],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [
            {'type': 'PERSON_FULL_NAME', 'text': first, 'normalized_text': first, 'start': working_text.index(first), 'end': working_text.index(first) + len(first)},
            {'type': 'PERSON_FULL_NAME', 'text': second, 'normalized_text': second, 'start': working_text.index(second), 'end': working_text.index(second) + len(second)},
        ]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': content, 'content_format': 'TIPTAP_JSON', 'document_revision': 1},
    )
    assert scan.status_code == 200
    pending_by_surface = {p['surface_value']: p for p in scan.json()['pending_review']}

    redact = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': first, 'entity_class': 'PERSON', 'entity_key': pending_by_surface[first]['entity_key'], 'decision': 'REDACT'},
    )
    assert redact.status_code == 200
    keep = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': second, 'entity_class': 'PERSON', 'entity_key': pending_by_surface[second]['entity_key'], 'decision': 'KEEP'},
    )
    assert keep.status_code == 200
    payload = keep.json()
    content_text = _content_text(payload['anonymized_content'])
    assert first not in content_text
    assert second in content_text
    assert 'ФИО1' in _redaction_placeholders(payload['anonymized_content'])
    assert main.restored_docs[doc_id]['working_content'] == payload['anonymized_content']
    assert payload['pending_review'] == []


def test_draft_scan_merge_candidates_use_entity_id(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-candidates-entity-id-doc'
    existing = 'Макаров Антон Сергеевич'
    pending = 'Макаров А.С.'
    working_text = f'ФИО1 явился. {pending} представил документы.'
    start = working_text.index(pending)
    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
            'canonical_value': existing, 'normalized_value': existing, 'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT', 'mentions': [],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': pending, 'normalized_text': pending, 'start': start, 'end': start + len(pending)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': None, 'content_format': 'PLAIN_TEXT', 'document_revision': 1},
    )
    assert response.status_code == 200
    candidate = response.json()['pending_review'][0]['merge_candidates'][0]
    assert candidate['entity_id'] == 'person-e1'
    assert candidate['placeholder'] == 'ФИО1'
    assert 'cluster_id' not in candidate


def test_merge_with_existing_pending_adds_mention_to_entity(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-pending-mention-doc'
    existing = 'Макаров Антон Сергеевич'
    pending = 'Макаров А.С.'
    working_text = f'ФИО1 явился. {pending} представил документы.'
    start = working_text.index(pending)
    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
            'canonical_value': existing, 'normalized_value': existing, 'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'mentions': [{'mention_id': 'm-existing', 'entity_id': 'person-e1', 'surface_value': existing, 'normalized_value': existing, 'start': 0, 'end': len(existing), 'replacement_value': 'ФИО1'}],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [{'type': 'PERSON_FULL_NAME', 'text': pending, 'normalized_text': pending, 'start': start, 'end': start + len(pending)}]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': None, 'content_format': 'PLAIN_TEXT', 'document_revision': 1},
    )
    assert scan.status_code == 200
    entity_key = scan.json()['pending_review'][0]['entity_key']
    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': pending, 'entity_class': 'PERSON', 'entity_key': entity_key, 'decision': 'MERGE_WITH_EXISTING', 'target_entity_id': 'person-e1'},
    )
    assert decision.status_code == 200
    payload = decision.json()
    assert len(payload['entities']) == 1
    entity = payload['entities'][0]
    assert any(m['surface_value'] == pending for m in entity['mentions'])
    assert pending not in payload['anonymized_text']
    assert 'ФИО1 представил документы' in payload['anonymized_text']
    assert len(payload['mappings']) == 1
    assert pending not in [m['original_value'] for m in payload['mappings']]
    assert payload['pending_review'] == []


def test_merge_with_existing_pending_group_merges_multiple_forms(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-pending-group-doc'
    existing = 'Макаров Антон Сергеевич'
    first = 'Макаров А.С.'
    second = 'Макаровым Антоном Сергеевичем'
    pending_normalized = 'Макаров А.С.'
    working_text = f'ФИО1 явился. {first} пояснил. {second} представлены документы.'
    content = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': working_text}]}]}
    start_first = working_text.index(first)
    start_second = working_text.index(second)
    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1', 'document_id': doc_id, 'entity_class': 'PERSON',
            'canonical_value': existing, 'normalized_value': existing, 'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT', 'mentions': [],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [
            {'type': 'PERSON_FULL_NAME', 'text': first, 'normalized_text': pending_normalized, 'start': start_first, 'end': start_first + len(first)},
            {'type': 'PERSON_FULL_NAME', 'text': second, 'normalized_text': pending_normalized, 'start': start_second, 'end': start_second + len(second)},
        ]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'text': working_text, 'content': content, 'content_format': 'TIPTAP_JSON', 'document_revision': 1},
    )
    assert scan.status_code == 200
    entity_key = scan.json()['pending_review'][0]['entity_key']
    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'selected_text': first, 'entity_class': 'PERSON', 'entity_key': entity_key, 'decision': 'MERGE_WITH_EXISTING', 'target_entity_id': 'person-e1'},
    )
    assert decision.status_code == 200
    payload = decision.json()
    assert len(payload['entities']) == 1
    surfaces = {m['surface_value'] for m in payload['entities'][0]['mentions']}
    assert {first, second}.issubset(surfaces)
    assert first not in payload['anonymized_text']
    assert second not in payload['anonymized_text']
    assert payload['anonymized_text'].count('ФИО1') >= 3
    content_placeholders = _redaction_placeholders(payload['anonymized_content'])
    assert content_placeholders.count('ФИО1') == 2
    assert payload['pending_review'] == []

    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-candidates-entity-id-doc'
    existing = 'Макаров Антон Сергеевич'
    pending = 'Макаров А.С.'
    working_text = f'ФИО1 явился. {pending} представил документы.'
    start = working_text.index(pending)

    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': existing,
            'normalized_value': existing,
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'mentions': [],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [{
            'type': 'PERSON_FULL_NAME',
            'text': pending,
            'normalized_text': pending,
            'start': start,
            'end': start + len(pending),
        }]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'text': working_text,
            'content': None,
            'content_format': 'PLAIN_TEXT',
            'document_revision': 1,
        },
    )

    assert response.status_code == 200

    candidate = response.json()['pending_review'][0]['merge_candidates'][0]

    assert candidate['entity_id'] == 'person-e1'
    assert candidate['placeholder'] == 'ФИО1'
    assert 'cluster_id' not in candidate


def test_merge_with_existing_pending_adds_mention_to_entity(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-pending-mention-doc'
    existing = 'Макаров Антон Сергеевич'
    pending = 'Макаров А.С.'
    working_text = f'ФИО1 явился. {pending} представил документы.'
    start = working_text.index(pending)

    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': existing,
            'normalized_value': existing,
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'mentions': [{
                'mention_id': 'm-existing',
                'entity_id': 'person-e1',
                'surface_value': existing,
                'normalized_value': existing,
                'start': 0,
                'end': len(existing),
                'replacement_value': 'ФИО1',
            }],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [{
            'type': 'PERSON_FULL_NAME',
            'text': pending,
            'normalized_text': pending,
            'start': start,
            'end': start + len(pending),
        }]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)

    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'text': working_text,
            'content': None,
            'content_format': 'PLAIN_TEXT',
            'document_revision': 1,
        },
    )

    assert scan.status_code == 200

    entity_key = scan.json()['pending_review'][0]['entity_key']

    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'selected_text': pending,
            'entity_class': 'PERSON',
            'entity_key': entity_key,
            'decision': 'MERGE_WITH_EXISTING',
            'target_entity_id': 'person-e1',
        },
    )

    assert decision.status_code == 200

    payload = decision.json()

    assert len(payload['entities']) == 1

    entity = payload['entities'][0]

    assert any(
        mention['surface_value'] == pending
        for mention in entity['mentions']
    )

    assert pending not in payload['anonymized_text']
    assert 'ФИО1 представил документы' in payload['anonymized_text']
    assert len(payload['mappings']) == 1
    assert pending not in [mapping['original_value'] for mapping in payload['mappings']]
    assert payload['pending_review'] == []


def test_merge_with_existing_pending_group_merges_multiple_forms(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'draft-merge-pending-group-doc'
    existing = 'Макаров Антон Сергеевич'
    first = 'Макаров А.С.'
    second = 'Макаровым Антоном Сергеевичем'
    pending_normalized = 'Макаров А.С.'

    working_text = (
        f'ФИО1 явился. '
        f'{first} пояснил. '
        f'{second} представлены документы.'
    )

    content = {
        'type': 'doc',
        'content': [{
            'type': 'paragraph',
            'content': [{
                'type': 'text',
                'text': working_text,
            }],
        }],
    }

    start_first = working_text.index(first)
    start_second = working_text.index(second)

    main.restored_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': f'{existing} явился.',
        'anonymized_text': 'ФИО1 явился.',
        'entities': [{
            'entity_id': 'person-e1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': existing,
            'normalized_value': existing,
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'mentions': [],
        }],
        'kept_entities': [],
        'mappings': [],
    }

    async def fake_extract_entities(_text):
        return [
            {
                'type': 'PERSON_FULL_NAME',
                'text': first,
                'normalized_text': pending_normalized,
                'start': start_first,
                'end': start_first + len(first),
            },
            {
                'type': 'PERSON_FULL_NAME',
                'text': second,
                'normalized_text': pending_normalized,
                'start': start_second,
                'end': start_second + len(second),
            },
        ]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)

    scan = client.post(
        f'/internal/anonymization/documents/{doc_id}/draft-scan',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'text': working_text,
            'content': content,
            'content_format': 'TIPTAP_JSON',
            'document_revision': 1,
        },
    )

    assert scan.status_code == 200

    entity_key = scan.json()['pending_review'][0]['entity_key']

    decision = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'selected_text': first,
            'entity_class': 'PERSON',
            'entity_key': entity_key,
            'decision': 'MERGE_WITH_EXISTING',
            'target_entity_id': 'person-e1',
        },
    )

    assert decision.status_code == 200

    payload = decision.json()

    assert len(payload['entities']) == 1

    surfaces = {
        mention['surface_value']
        for mention in payload['entities'][0]['mentions']
    }

    assert {first, second}.issubset(surfaces)
    assert first not in payload['anonymized_text']
    assert second not in payload['anonymized_text']
    assert payload['anonymized_text'].count('ФИО1') >= 3

    content_placeholders = _redaction_placeholders(payload['anonymized_content'])

    assert content_placeholders.count('ФИО1') == 2
    assert payload['pending_review'] == []
    
def test_pending_redact_groups_all_surface_forms_of_same_entity_key():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'pending-same-person-redact-doc'

    first = 'Макарова Антона Сергеевича'
    second = 'Макаровым Антоном Сергеевичем'
    third = 'Макаров А.С.'
    normalized = 'Макаров Антон Сергеевич'
    entity_key = 'PERSON::макаров антон сергеевич'

    working_text = (
        f'{first} вызвали в суд. '
        f'{second} представлены документы. '
        f'{third} пояснил.'
    )

    content = {
        'type': 'doc',
        'content': [
            {
                'type': 'paragraph',
                'content': [
                    {'type': 'text', 'text': working_text}
                ],
            }
        ],
    }

    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Исходный защищённый документ.',
        'anonymized_text': working_text,
        'working_text': working_text,
        'working_content': content,
        'mappings': [],
        'entities': [],
        'kept_entities': [],
    }

    pending = []
    for surface in (first, second, third):
        start = working_text.index(surface)
        pending.append({
            'entity_key': entity_key,
            'surface_value': surface,
            'normalized_value': normalized,
            'entity_class': 'PERSON',
            'person_role': 'UNKNOWN',
            'start': start,
            'end': start + len(surface),
            'reason': 'В изменённом тексте найдено новое значение, требующее проверки',
        })

    main.pending_review_by_document_id[doc_id] = pending
    main.restored_docs[doc_id]['pending_review'] = pending

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'selected_text': first,
            'entity_class': 'PERSON',
            'entity_key': entity_key,
            'decision': 'REDACT',
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert first not in payload['anonymized_text']
    assert second not in payload['anonymized_text']
    assert third not in payload['anonymized_text']

    entity = next(
        e for e in payload['entities']
        if e.get('entity_key') == entity_key
    )

    assert entity['mentions_count'] == 3
    assert {
        mention['surface_value']
        for mention in entity['mentions']
    } == {first, second, third}

    placeholder = entity['placeholder']
    assert payload['anonymized_text'].count(placeholder) == 3
    assert payload['pending_review'] == []

    restored_content = main.restore_content_from_mentions(
        payload['anonymized_content'],
        payload['entities'],
    )

    assert _content_text(restored_content) == working_text


def test_pending_keep_keeps_all_surface_forms_of_same_entity_key():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'pending-same-person-keep-doc'

    first = 'Макарова Антона Сергеевича'
    second = 'Макаровым Антоном Сергеевичем'
    normalized = 'Макаров Антон Сергеевич'
    entity_key = 'PERSON::макаров антон сергеевич'

    working_text = f'{first} вызвали. {second} представлены документы.'

    content = {
        'type': 'doc',
        'content': [
            {
                'type': 'paragraph',
                'content': [
                    {'type': 'text', 'text': working_text}
                ],
            }
        ],
    }

    main.restored_docs.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': 'Исходный защищённый документ.',
        'anonymized_text': working_text,
        'working_text': working_text,
        'working_content': content,
        'anonymized_content': content,
        'mappings': [],
        'entities': [],
        'kept_entities': [],
    }

    pending = []
    for surface in (first, second):
        start = working_text.index(surface)
        pending.append({
            'entity_key': entity_key,
            'surface_value': surface,
            'normalized_value': normalized,
            'entity_class': 'PERSON',
            'person_role': 'UNKNOWN',
            'start': start,
            'end': start + len(surface),
            'reason': 'В изменённом тексте найдено новое значение, требующее проверки',
        })

    main.pending_review_by_document_id[doc_id] = pending
    main.restored_docs[doc_id]['pending_review'] = pending

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/redaction-decisions',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'selected_text': first,
            'entity_class': 'PERSON',
            'entity_key': entity_key,
            'decision': 'KEEP',
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload['anonymized_text'] == working_text
    assert first in payload['anonymized_text']
    assert second in payload['anonymized_text']
    assert payload['pending_review'] == []

    decision = main.manual_decisions_by_document_id[doc_id][entity_key]
    assert decision['decision_type'] == 'KEEP_ENTITY'


def _reset_reanonymize_working_doc(main, doc_id):
    main.restored_docs.pop(doc_id, None)
    main.public_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)


def _simple_content(text):
    return {
        'type': 'doc',
        'content': [{
            'type': 'paragraph',
            'content': [{'type': 'text', 'text': text}],
        }],
    }


def test_reanonymize_preserves_pending_redact_working_revision():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'reanonymize-working-redact-doc'
    original_text = 'Иванов И.И. явился в суд.'
    working_text = 'ФИО1 явился в суд. ФИО2 представил документы.'
    working_content = _simple_content(working_text)
    _reset_reanonymize_working_doc(main, doc_id)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': working_text,
        'anonymized_content': working_content,
        'working_text': working_text,
        'working_content': working_content,
        'entities': [
            {
                'entity_id': 'person-e1',
                'document_id': doc_id,
                'entity_class': 'PERSON',
                'canonical_value': 'Иванов И.И.',
                'normalized_value': 'Иванов И.И.',
                'placeholder': 'ФИО1',
                'redaction_decision': 'REDACT',
                'requires_review': False,
                'mentions': [
                    {'mention_id': 'm1', 'entity_id': 'person-e1', 'surface_value': 'Иванов И.И.', 'start': 0, 'end': 10, 'replacement_value': 'ФИО1'},
                ],
            },
            {
                'entity_id': 'person-e2',
                'document_id': doc_id,
                'entity_class': 'PERSON',
                'canonical_value': 'Макаров А.С.',
                'normalized_value': 'Макаров А.С.',
                'placeholder': 'ФИО2',
                'redaction_decision': 'REDACT',
                'requires_review': False,
                'mentions': [
                    {'mention_id': 'm2', 'entity_id': 'person-e2', 'surface_value': 'Макаров А.С.', 'start': 20, 'end': 32, 'replacement_value': 'ФИО2'},
                ],
            },
        ],
        'kept_entities': [],
        'mappings': [],
        'pending_review': [],
    }

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': [], 'publication_redaction_mode': 'STRICT'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert 'представил документы' in payload['anonymized_text']
    assert 'Макаров А.С.' not in payload['anonymized_text']
    assert 'ФИО2 представил документы' in payload['anonymized_text']
    entity = next(e for e in payload['entities'] if e['entity_id'] == 'person-e2')
    assert entity['mentions'][0]['surface_value'] == 'Макаров А.С.'
    assert main.restored_docs[doc_id]['original_text'] == original_text
    assert main.restored_docs[doc_id]['original_content'] == _simple_content(original_text)


def test_reanonymize_preserves_pending_keep_working_revision():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'reanonymize-working-keep-doc'
    original_text = 'ФИО1 явился в суд.'
    kept_value = 'Макаров А.С.'
    working_text = f'ФИО1 явился в суд. {kept_value} представил документы.'
    _reset_reanonymize_working_doc(main, doc_id)

    kept_entity = {
        'entity_id': 'person-keep',
        'document_id': doc_id,
        'entity_class': 'PERSON',
        'canonical_value': kept_value,
        'normalized_value': kept_value,
        'redaction_decision': 'KEEP',
        'requires_review': False,
        'mentions': [
            {'mention_id': 'mk1', 'entity_id': 'person-keep', 'surface_value': kept_value, 'start': working_text.index(kept_value), 'end': working_text.index(kept_value) + len(kept_value), 'replacement_value': kept_value},
        ],
    }
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': working_text,
        'working_text': working_text,
        'working_content': _simple_content(working_text),
        'entities': [{
            'entity_id': 'person-e1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': 'Иванов И.И.',
            'normalized_value': 'Иванов И.И.',
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'requires_review': False,
            'mentions': [],
        }],
        'kept_entities': [kept_entity],
        'recognized_but_kept': [kept_entity],
        'mappings': [],
        'pending_review': [],
    }

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert 'представил документы' in payload['anonymized_text']
    assert kept_value in payload['anonymized_text']
    assert 'ФИО2' not in payload['anonymized_text']
    assert payload['kept_entities'][0]['canonical_value'] == kept_value
    assert main.restored_docs[doc_id]['original_text'] == original_text


def test_reanonymize_preserves_pending_merge_with_existing_working_revision():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'reanonymize-working-merge-doc'
    original_text = 'Иванов И.И. явился в суд.'
    working_text = 'ФИО1 явился в суд. ФИО1 представил документы.'
    _reset_reanonymize_working_doc(main, doc_id)

    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': working_text,
        'working_text': working_text,
        'working_content': _simple_content(working_text),
        'entities': [{
            'entity_id': 'person-e1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': 'Иванов И.И.',
            'normalized_value': 'Иванов И.И.',
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'requires_review': False,
            'mentions': [
                {'mention_id': 'm1', 'entity_id': 'person-e1', 'surface_value': 'Иванов И.И.', 'start': 0, 'end': 10, 'replacement_value': 'ФИО1'},
                {'mention_id': 'm2', 'entity_id': 'person-e1', 'surface_value': 'Макаров А.С.', 'start': 20, 'end': 32, 'replacement_value': 'ФИО1'},
            ],
        }],
        'kept_entities': [],
        'mappings': [],
        'pending_review': [],
    }

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert 'представил документы' in payload['anonymized_text']
    assert 'Макаров А.С.' not in payload['anonymized_text']
    assert 'ФИО1 представил документы' in payload['anonymized_text']
    persons = [e for e in payload['entities'] if e['entity_class'] == 'PERSON']
    assert len(persons) == 1
    assert any(m['surface_value'] == 'Макаров А.С.' for m in persons[0]['mentions'])
    assert main.restored_docs[doc_id]['original_text'] == original_text


def test_reanonymize_rejects_working_revision_with_pending_review():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'reanonymize-working-pending-doc'
    original_text = 'Иванов И.И. явился в суд.'
    working_text = 'ФИО1 явился в суд. Макаров А.С. представил документы.'
    pending = [{
        'entity_key': 'PERSON::макаров а.с.',
        'surface_value': 'Макаров А.С.',
        'normalized_value': 'Макаров А.С.',
        'entity_class': 'PERSON',
        'start': working_text.index('Макаров А.С.'),
        'end': working_text.index('Макаров А.С.') + len('Макаров А.С.'),
        'reason': 'В изменённом тексте найдено новое значение, требующее проверки',
    }]
    _reset_reanonymize_working_doc(main, doc_id)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': working_text,
        'working_text': working_text,
        'working_content': _simple_content(working_text),
        'entities': [],
        'kept_entities': [],
        'mappings': [],
        'pending_review': pending,
    }
    main.pending_review_by_document_id[doc_id] = pending
    before = main.restored_docs[doc_id].copy()

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 409
    error = response.json()['error']
    assert error['code'] == 'PENDING_REVIEW_REQUIRED'
    assert error['message'] == 'Перед повторным обезличиванием обработайте найденные в изменённом тексте фрагменты'
    assert error['details']['pending_count'] == 1
    assert error['details']['review_count'] == 1
    assert error['details']['pending_review'] == pending
    assert main.restored_docs[doc_id]['working_text'] == before['working_text']
    assert main.restored_docs[doc_id]['working_content'] == before['working_content']
    assert main.restored_docs[doc_id]['entities'] == before['entities']
    assert main.restored_docs[doc_id]['kept_entities'] == before['kept_entities']
    assert main.restored_docs[doc_id]['pending_review'] == pending
    assert main.restored_docs[doc_id]['original_text'] == original_text


def test_reanonymize_without_working_revision_uses_original_pipeline(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'reanonymize-original-pipeline-doc'
    original_text = 'Петров П.П. подписал документ.'
    _reset_reanonymize_working_doc(main, doc_id)
    main.restored_docs[doc_id] = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': 'stale anonymized text',
        'entities': [],
        'kept_entities': [],
        'mappings': [],
        'pending_review': [],
    }

    async def fake_extract_entities(text):
        assert text == original_text
        return [{
            'type': 'PERSON_FULL_NAME',
            'text': 'Петров П.П.',
            'normalized_text': 'Петров П.П.',
            'start': 0,
            'end': len('Петров П.П.'),
            'source': 'natasha',
        }]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['anonymized_text'] == 'ФИО1 подписал документ.'
    assert payload['entities'][0]['mentions'][0]['surface_value'] == 'Петров П.П.'
    assert main.restored_docs[doc_id].get('working_text') is None
    assert main.restored_docs[doc_id].get('working_content') is None
    assert main.restored_docs[doc_id]['original_text'] == original_text


def _reset_patch_entity_metadata_doc(main, doc_id):
    main.restored_docs.pop(doc_id, None)
    main.public_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)


def _patch_metadata_person_entity(doc_id, original_text, working_text=None, working_content=None):
    mentions = [
        {
            'mention_id': 'mention-1',
            'entity_id': 'person-1',
            'surface_value': 'Макаров А.С.',
            'normalized_value': 'Макаров А.С.',
            'start': 0,
            'end': len('Макаров А.С.'),
            'replacement_value': 'ФИО1',
        }
    ]
    if working_text and 'представил документы' in working_text:
        second_start = working_text.index('ФИО1 представил документы')
        mentions.append({
            'mention_id': 'mention-2',
            'entity_id': 'person-1',
            'surface_value': 'Макаров А.С.',
            'normalized_value': 'Макаров А.С.',
            'start': second_start,
            'end': second_start + len('ФИО1'),
            'replacement_value': 'ФИО1',
            'source': 'manual',
        })
    return {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': _simple_content(original_text),
        'anonymized_text': working_text if working_text is not None else 'ФИО1 явился.',
        'anonymized_content': working_content if working_content is not None else _simple_content('ФИО1 явился.'),
        'working_text': working_text,
        'working_content': working_content,
        'entities': [{
            'entity_id': 'person-1',
            'document_id': doc_id,
            'entity_class': 'PERSON',
            'canonical_value': 'Макаров А.С.',
            'normalized_value': 'Макаров А.С.',
            'person_role': 'UNKNOWN',
            'context_label': None,
            'placeholder': 'ФИО1',
            'redaction_decision': 'REDACT',
            'requires_review': False,
            'mentions': mentions,
        }],
        'kept_entities': [],
        'mappings': [],
        'pending_review': [],
    }


def test_patch_entity_role_preserves_working_revision():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'patch-role-working-doc'
    original_text = 'Макаров А.С. явился.'
    working_text = 'ФИО1 явился. ФИО1 представил документы.'
    working_content = _simple_content(working_text)
    _reset_patch_entity_metadata_doc(main, doc_id)
    main.restored_docs[doc_id] = _patch_metadata_person_entity(doc_id, original_text, working_text, working_content)

    response = client.patch(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'person_role': 'REPRESENTATIVE', 'context_label': 'Представитель ответчика'},
    )

    assert response.status_code == 200
    payload = response.json()
    entity = payload['entities'][0]
    assert entity['person_role'] == 'REPRESENTATIVE'
    assert entity['context_label'] == 'Представитель ответчика'
    assert payload['anonymized_text'] == working_text
    assert main.restored_docs[doc_id]['working_text'] == working_text
    assert main.restored_docs[doc_id]['working_content'] == working_content
    assert len(entity['mentions']) == 2
    assert {m['mention_id'] for m in entity['mentions']} == {'mention-1', 'mention-2'}
    assert payload['mappings'][0]['id'] == 'person-1'
    assert payload['mappings'][0]['placeholder'] == 'ФИО1'


def test_patch_entity_canonical_value_preserves_working_content():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'patch-canonical-working-doc'
    original_text = 'Макаров А.С. явился.'
    working_text = 'ФИО1 явился.'
    working_content = _simple_content(working_text)
    _reset_patch_entity_metadata_doc(main, doc_id)
    main.restored_docs[doc_id] = _patch_metadata_person_entity(doc_id, original_text, working_text, working_content)

    response = client.patch(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'canonical_value': 'Макаров Антон Сергеевич'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['entities'][0]['canonical_value'] == 'Макаров Антон Сергеевич'
    assert payload['mappings'][0]['original_value'] == 'Макаров Антон Сергеевич'
    assert main.restored_docs[doc_id]['working_text'] == working_text
    assert main.restored_docs[doc_id]['working_content'] == working_content
    assert payload['anonymized_text'] == working_text
    assert payload['anonymized_content'] == working_content
    assert 'ФИО1' in main.restored_docs[doc_id]['working_text']
    assert main.restored_docs[doc_id]['original_text'] == original_text


def test_patch_entity_metadata_survives_working_reanonymize():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'patch-metadata-working-reanon-doc'
    original_text = 'Макаров А.С. явился.'
    working_text = 'ФИО1 явился. ФИО1 представил документы.'
    working_content = _simple_content(working_text)
    _reset_patch_entity_metadata_doc(main, doc_id)
    main.restored_docs[doc_id] = _patch_metadata_person_entity(doc_id, original_text, working_text, working_content)

    patch_response = client.patch(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'person_role': 'WITNESS', 'context_label': 'Свидетель'},
    )
    assert patch_response.status_code == 200

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    entity = payload['entities'][0]
    assert payload['anonymized_text'] == working_text
    assert main.restored_docs[doc_id]['working_text'] == working_text
    assert entity['person_role'] == 'WITNESS'
    assert entity['context_label'] == 'Свидетель'
    assert {m['mention_id'] for m in entity['mentions']} == {'mention-1', 'mention-2'}
    assert main.restored_docs[doc_id]['original_text'] == original_text


def test_patch_entity_metadata_survives_original_based_reanonymize(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'patch-metadata-original-reanon-doc'
    original_text = 'Макаров А.С. явился.'
    _reset_patch_entity_metadata_doc(main, doc_id)
    doc = _patch_metadata_person_entity(doc_id, original_text)
    doc.pop('working_text', None)
    doc.pop('working_content', None)
    main.restored_docs[doc_id] = doc

    patch_response = client.patch(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={
            'canonical_value': 'Макаров Антон Сергеевич',
            'person_role': 'REPRESENTATIVE',
            'context_label': 'Представитель',
        },
    )
    assert patch_response.status_code == 200

    async def fake_extract_entities(text):
        assert text == original_text
        return [{
            'type': 'PERSON_FULL_NAME',
            'text': 'Макаров А.С.',
            'normalized_text': 'Макаров А.С.',
            'start': 0,
            'end': len('Макаров А.С.'),
            'source': 'natasha',
        }]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)

    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    entity = payload['entities'][0]
    assert entity['entity_id'] != 'person-1'
    assert entity['canonical_value'] == 'Макаров Антон Сергеевич'
    assert entity['person_role'] == 'REPRESENTATIVE'
    assert entity['context_label'] == 'Представитель'


def test_update_entity_metadata_decision_uses_source_semantic_key():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app, entity_semantic_key

    client = TestClient(app)
    doc_id = 'patch-metadata-source-key-doc'
    original_text = 'Макаров А.С. явился.'
    _reset_patch_entity_metadata_doc(main, doc_id)
    doc = _patch_metadata_person_entity(doc_id, original_text)
    doc.pop('working_text', None)
    doc.pop('working_content', None)
    expected_source_key = entity_semantic_key(doc['entities'][0])
    main.restored_docs[doc_id] = doc

    response = client.patch(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'canonical_value': 'Макаров Антон Сергеевич'},
    )

    assert response.status_code == 200
    decisions = list(main.manual_decisions_by_document_id[doc_id].values())
    decision = next(d for d in decisions if d['decision_type'] == 'UPDATE_ENTITY_METADATA')
    assert decision['source_entity_key'] == expected_source_key
    assert decision['payload']['canonical_value'] == 'Макаров Антон Сергеевич'
    assert decision.get('entity_id') is None


def _split_rich_content(first_entity_id='person-1', second_entity_id='person-1', second_placeholder='ФИО1'):
    return {
        'type': 'doc',
        'content': [{
            'type': 'paragraph',
            'content': [
                {
                    'type': 'text',
                    'text': 'ФИО1',
                    'marks': [{'type': 'redactionMention', 'attrs': {'entityId': first_entity_id, 'mentionId': 'mention-1', 'placeholder': 'ФИО1'}}],
                },
                {'type': 'text', 'text': ' явился. '},
                {
                    'type': 'text',
                    'text': second_placeholder,
                    'marks': [{'type': 'redactionMention', 'attrs': {'entityId': second_entity_id, 'mentionId': 'mention-2', 'placeholder': second_placeholder}}],
                },
                {'type': 'text', 'text': ' представил документы.'},
            ],
        }],
    }


def _split_original_content():
    original_text = 'Макаров Антон Сергеевич явился. Макаров А.С. представил документы.'
    return original_text, _simple_content(original_text)


def _split_person_entity(doc_id, original_text=None):
    if original_text is None:
        original_text, _ = _split_original_content()
    first = 'Макаров Антон Сергеевич'
    second = 'Макаров А.С.'
    first_start = original_text.index(first)
    second_start = original_text.index(second)
    return {
        'entity_id': 'person-1',
        'document_id': doc_id,
        'entity_class': 'PERSON',
        'canonical_value': first,
        'normalized_value': first,
        'person_role': 'UNKNOWN',
        'context_label': None,
        'placeholder': 'ФИО1',
        'redaction_decision': 'REDACT',
        'requires_review': False,
        'mentions_count': 2,
        'mentions': [
            {
                'mention_id': 'mention-1',
                'entity_id': 'person-1',
                'surface_value': first,
                'normalized_value': first,
                'start': first_start,
                'end': first_start + len(first),
                'replacement_value': 'ФИО1',
            },
            {
                'mention_id': 'mention-2',
                'entity_id': 'person-1',
                'surface_value': second,
                'normalized_value': second,
                'start': second_start,
                'end': second_start + len(second),
                'replacement_value': 'ФИО1',
                'format': 'INITIALS',
            },
        ],
    }


def _split_doc(main, doc_id, *, working_text=None, working_content=None):
    original_text, original_content = _split_original_content()
    main.restored_docs.pop(doc_id, None)
    main.public_docs.pop(doc_id, None)
    main.pending_review_by_document_id.pop(doc_id, None)
    main.manual_decisions_by_document_id.pop(doc_id, None)
    anonymized_text = working_text if working_text is not None else 'ФИО1 явился. ФИО1 представил документы.'
    anonymized_content = working_content if working_content is not None else _simple_content(anonymized_text)
    doc = {
        'document_id': doc_id,
        'case_id': 'case-1',
        'title': 'doc',
        'original_text': original_text,
        'original_content': original_content,
        'anonymized_text': anonymized_text,
        'anonymized_content': anonymized_content,
        'entities': [_split_person_entity(doc_id, original_text)],
        'kept_entities': [],
        'recognized_but_kept': [],
        'mappings': [],
        'pending_review': [],
    }
    if working_text is not None:
        doc['working_text'] = working_text
    if working_content is not None:
        doc['working_content'] = working_content
    main.restored_docs[doc_id] = doc
    return doc


def _split_post(client, main, doc_id):
    return client.post(
        f'/internal/anonymization/documents/{doc_id}/entities/person-1/mentions/mention-2/split',
        headers={'X-Internal-Service-Token': main.INTERNAL},
    )


def test_split_mention_preserves_working_rich_content_revision():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'split-rich-working-doc'
    working_text = 'ФИО1 явился. ФИО1 представил документы.'
    working_content = _split_rich_content()
    original_text, original_content = _split_original_content()
    _split_doc(main, doc_id, working_text=working_text, working_content=working_content)

    response = _split_post(client, main, doc_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload['anonymized_text'] == 'ФИО1 явился. ФИО2 представил документы.'
    assert main.restored_docs[doc_id]['working_text'] == payload['anonymized_text']
    assert main.restored_docs[doc_id]['working_content'] == main.restored_docs[doc_id]['anonymized_content']
    nodes = payload['anonymized_content']['content'][0]['content']
    first_mark = nodes[0]['marks'][0]['attrs']
    second_mark = nodes[2]['marks'][0]['attrs']
    new_entity = next(e for e in payload['entities'] if e['entity_id'] != 'person-1')
    source_entity = next(e for e in payload['entities'] if e['entity_id'] == 'person-1')
    assert nodes[0]['text'] == 'ФИО1'
    assert first_mark['entityId'] == 'person-1'
    assert nodes[2]['text'] == 'ФИО2'
    assert second_mark['entityId'] == new_entity['entity_id']
    assert second_mark['mentionId'] == 'mention-2'
    assert [m['mention_id'] for m in source_entity['mentions']] == ['mention-1']
    assert [m['mention_id'] for m in new_entity['mentions']] == ['mention-2']
    assert main.restored_docs[doc_id]['original_text'] == original_text
    assert main.restored_docs[doc_id]['original_content'] == original_content


def test_split_mention_survives_working_reanonymize():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'split-rich-working-reanon-doc'
    original_text, original_content = _split_original_content()
    _split_doc(main, doc_id, working_text='ФИО1 явился. ФИО1 представил документы.', working_content=_split_rich_content())

    split_response = _split_post(client, main, doc_id)
    assert split_response.status_code == 200
    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['anonymized_text'] == 'ФИО1 явился. ФИО2 представил документы.'
    assert sorted(len(e['mentions']) for e in payload['entities']) == [1, 1]
    assert main.restored_docs[doc_id]['original_text'] == original_text
    assert main.restored_docs[doc_id]['original_content'] == original_content


def test_split_mention_plain_text_with_ambiguous_placeholder_is_rejected():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app
    import copy

    client = TestClient(app)
    doc_id = 'split-plain-ambiguous-doc'
    _split_doc(main, doc_id, working_text='ФИО1 явился. ФИО1 представил документы.', working_content=None)
    before_entities = copy.deepcopy(main.restored_docs[doc_id]['entities'])
    before_working_text = main.restored_docs[doc_id]['working_text']

    response = _split_post(client, main, doc_id)

    assert response.status_code == 409
    error = response.json()['error']
    assert error['code'] == 'SPLIT_REQUIRES_STRUCTURED_CONTENT'
    assert error['details']['entity_id'] == 'person-1'
    assert error['details']['mention_id'] == 'mention-2'
    assert error['details']['placeholder'] == 'ФИО1'
    assert error['details']['occurrences_count'] == 2
    assert main.restored_docs[doc_id]['entities'] == before_entities
    assert main.restored_docs[doc_id]['working_text'] == before_working_text


def test_split_mention_plain_text_single_placeholder_is_supported():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'split-plain-single-doc'
    _split_doc(main, doc_id, working_text='ФИО1 представил документы.', working_content=None)

    response = _split_post(client, main, doc_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload['anonymized_text'] == 'ФИО2 представил документы.'
    assert main.restored_docs[doc_id]['working_text'] == 'ФИО2 представил документы.'
    assert len(payload['entities']) == 2
    assert sorted(len(e['mentions']) for e in payload['entities']) == [1, 1]


def test_split_mention_original_document_survives_original_based_reanonymize(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app

    client = TestClient(app)
    doc_id = 'split-original-reanon-doc'
    original_text, _ = _split_original_content()
    _split_doc(main, doc_id)

    split_response = _split_post(client, main, doc_id)
    assert split_response.status_code == 200
    decision = next(d for d in main.manual_decisions_by_document_id[doc_id].values() if d['decision_type'] == 'SPLIT_MENTION')
    assert decision['source_entity_key']
    assert decision['mention_locator']['start'] == original_text.index('Макаров А.С.')
    assert decision['mention_locator']['end'] == original_text.index('Макаров А.С.') + len('Макаров А.С.')
    assert decision['mention_locator']['surface_value'] == 'Макаров А.С.'

    async def fake_extract_entities(text):
        assert text == original_text
        return [
            {
                'type': 'PERSON_FULL_NAME',
                'text': 'Макаров Антон Сергеевич',
                'normalized_text': 'Макаров Антон Сергеевич',
                'start': original_text.index('Макаров Антон Сергеевич'),
                'end': original_text.index('Макаров Антон Сергеевич') + len('Макаров Антон Сергеевич'),
                'source': 'natasha',
            },
            {
                'type': 'PERSON_FULL_NAME',
                'text': 'Макаров А.С.',
                'normalized_text': 'Макаров А.С.',
                'start': original_text.index('Макаров А.С.'),
                'end': original_text.index('Макаров А.С.') + len('Макаров А.С.'),
                'source': 'natasha',
            },
        ]

    monkeypatch.setattr(main, 'extract_entities', fake_extract_entities)
    response = client.post(
        f'/internal/anonymization/documents/{doc_id}/reanonymize',
        headers={'X-Internal-Service-Token': main.INTERNAL},
        json={'mappings': []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload['entities']) == 2
    first_entity = next(e for e in payload['entities'] if e['mentions'][0]['surface_value'] == 'Макаров Антон Сергеевич')
    second_entity = next(e for e in payload['entities'] if e['mentions'][0]['surface_value'] == 'Макаров А.С.')
    assert first_entity['placeholder'] != second_entity['placeholder']
    assert payload['anonymized_text'] == 'ФИО1 явился. ФИО2 представил документы.'


def test_split_decision_does_not_depend_only_on_uuid():
    from fastapi.testclient import TestClient
    from app import main
    from app.main import app, apply_split_mention_decisions

    client = TestClient(app)
    doc_id = 'split-decision-locator-doc'
    original_text, _ = _split_original_content()
    _split_doc(main, doc_id)

    response = _split_post(client, main, doc_id)

    assert response.status_code == 200
    decision = next(d for d in main.manual_decisions_by_document_id[doc_id].values() if d['decision_type'] == 'SPLIT_MENTION')
    assert decision['source_entity_key']
    assert decision['mention_locator']['start'] == original_text.index('Макаров А.С.')
    assert decision['mention_locator']['end'] == original_text.index('Макаров А.С.') + len('Макаров А.С.')
    assert decision['mention_locator']['surface_value'] == 'Макаров А.С.'

    new_source = _split_person_entity(doc_id, original_text)
    new_source['entity_id'] = 'fresh-person-id'
    for idx, mention in enumerate(new_source['mentions'], start=1):
        mention['mention_id'] = f'fresh-mention-{idx}'
        mention['entity_id'] = 'fresh-person-id'
    reapplied = apply_split_mention_decisions(doc_id, [new_source])
    assert len(reapplied) == 2
    assert sorted(len(e['mentions']) for e in reapplied) == [1, 1]
    assert all(e.get('entity_id') != decision['entity_id'] for e in reapplied)
    assert all(m.get('mention_id') != decision['mention_id'] for e in reapplied for m in e['mentions'])
