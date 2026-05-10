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
