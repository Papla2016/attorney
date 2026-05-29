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
    surfaces = {e['text'] for e in person_full}
    assert 'Макаров Антон Сергеевич' in surfaces
    assert 'Макарова Антона Сергеевича' in surfaces
    assert 'Макаровым Антоном Сергеевичем' in surfaces
    for s in ['Макаров Антон Сергеевич', 'Макарова Антона Сергеевича', 'Макаровым Антоном Сергеевичем']:
        variants = [e for e in person_full if e['text'] == s]
        assert variants
        assert all(v.get('normalized_text') == 'Макаров Антон Сергеевич' for v in variants)


def test_regex_provider_does_not_treat_heading_phrase_as_person():
    from app.main import RegexRuleNerProvider

    text = 'Время Судебный Заседание указано в протоколе.'
    entities = RegexRuleNerProvider().extract(text)

    assert not any(e.type == 'PERSON_FULL_NAME' and e.text == 'Время Судебный Заседание' for e in entities)


def test_regex_provider_detects_full_name_with_patronymic_forms():
    from app.main import RegexRuleNerProvider

    text = 'Макаров Антон Сергеевич. Макарова Антона Сергеевича. Макаровым Антоном Сергеевичем.'
    entities = RegexRuleNerProvider().extract(text)
    persons = {e.text for e in entities if e.type == 'PERSON_FULL_NAME'}

    assert 'Макаров Антон Сергеевич' in persons
    assert 'Макарова Антона Сергеевича' in persons
    assert 'Макаровым Антоном Сергеевичем' in persons


def test_regex_provider_detects_initials_person():
    from app.main import RegexRuleNerProvider

    entities = RegexRuleNerProvider().extract('Макаров А.С. подписал документ.')

    assert any(e.type == 'PERSON_FULL_NAME' and e.text == 'Макаров А.С.' for e in entities)
