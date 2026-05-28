from fastapi.testclient import TestClient
from app.main import INTERNAL, app


def test_extract_court_entities_have_offsets_confidence_and_source():
    client = TestClient(app)
    response = client.post(
        '/internal/ner/extract',
        headers={'X-Internal-Service-Token': INTERNAL},
        json={'text': 'Судья Светашова С.Н. рассмотрела дело с участием Иванова Ивана Ивановича.', 'language': 'ru'},
    )

    assert response.status_code == 200
    entities = response.json()['entities']
    assert entities
    assert any(entity['type'] in {'PERSON_FULL_NAME', 'JUDGE', 'CASE_PARTICIPANT'} for entity in entities)
    assert all(isinstance(entity['start'], int) and isinstance(entity['end'], int) for entity in entities)
    assert all('confidence' in entity and entity['confidence'] > 0 for entity in entities)
    assert all(entity['source'] in {'natasha', 'regex', 'rule'} for entity in entities)


def test_person_normalization_cases_and_initials_signature():
    from app.main import RussianPersonNormalizer

    n = RussianPersonNormalizer(object())
    for case in ['Макаров Антон Сергеевич', 'Макарова Антона Сергеевича', 'Макаровым Антоном Сергеевичем', 'макаровым антоном сергеевичем']:
        normalized, meta = n.normalize(case)
        assert normalized == 'Макаров Антон Сергеевич'
        assert meta['format'] == 'FULL'

    normalized_short, meta_short = n.normalize('Макаров А.С.')
    assert normalized_short
    assert meta_short['format'] == 'INITIALS'
    assert meta_short['initials'].lower() == 'ас'


def test_extract_normalized_text_is_same_for_declensions():
    client = TestClient(app)
    text = 'Макаров Антон Сергеевич, Макарова Антона Сергеевича, Макаровым Антоном Сергеевичем'
    response = client.post(
        '/internal/ner/extract',
        headers={'X-Internal-Service-Token': INTERNAL},
        json={'text': text, 'language': 'ru'},
    )
    assert response.status_code == 200
    person_full = [e for e in response.json()['entities'] if e['type'] == 'PERSON_FULL_NAME']
    assert person_full
    assert any(e.get('normalized_text') == 'Макаров Антон Сергеевич' for e in person_full)
