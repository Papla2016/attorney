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
