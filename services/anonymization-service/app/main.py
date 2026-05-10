from collections import defaultdict
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os
import uuid
import httpx

app = FastAPI(title='anonymization-service')
INTERNAL = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-secret-token')
NER = os.getenv('NER_SERVICE_URL', 'http://ner-service:8000')

jobs: dict[str, dict] = {}
public_docs: dict[str, dict] = {}
restored_docs: dict[str, dict] = {}


class ProcessRequest(BaseModel):
    case_id: str
    document_id: str
    title: str
    text: str
    metadata: dict = {}


def _error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={'error': {'code': code, 'message': message, 'details': {}}})


def make_placeholder(entity_type: str, idx: int) -> str:
    if entity_type in {'PERSON_FULL_NAME', 'JUDGE', 'CASE_PARTICIPANT', 'COURT_SECRETARY'} or entity_type.startswith('PERSON_'):
        return f'ФИО{idx}'
    mapping = {
        'ADDRESS': 'АДРЕС',
        'LOCATION': 'МЕСТО',
        'ORGANIZATION': 'ОРГАНИЗАЦИЯ',
        'PHONE': 'ТЕЛЕФОН',
        'EMAIL': 'EMAIL',
        'PASSPORT': 'ПАСПОРТ',
        'SNILS': 'СНИЛС',
        'INN': 'ИНН',
        'BIRTH_DATE': 'ДАТА',
        'BANK_ACCOUNT': 'СЧЕТ',
        'CARD_NUMBER': 'КАРТА',
    }
    return f"{mapping.get(entity_type, 'ДАННЫЕ')}{idx}"


def apply_anonymization(text: str, entities: list[dict]) -> tuple[str, list[dict]]:
    by_type: dict[str, int] = defaultdict(int)
    text_to_placeholder: dict[str, str] = {}
    mappings = []
    for e in entities:
        original = e['text']
        entity_type = e['type']
        if original not in text_to_placeholder:
            by_type[entity_type] += 1
            text_to_placeholder[original] = make_placeholder(entity_type, by_type[entity_type])
        mappings.append({'placeholder': text_to_placeholder[original], 'original_value': original, 'entity_type': entity_type})

    anonymized = text
    for e in sorted(entities, key=lambda x: x['start'], reverse=True):
        anonymized = anonymized[:e['start']] + text_to_placeholder[e['text']] + anonymized[e['end']:]
    return anonymized, mappings


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/ready')
def ready():
    return {'status': 'ready'}


@app.post('/internal/anonymization/process')
async def process(body: ProcessRequest, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        _error(403, 'ACCESS_DENIED', 'Недостаточно прав')

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'id': job_id, 'case_id': body.case_id, 'document_id': body.document_id, 'status': 'NER_PROCESSING'}

    async with httpx.AsyncClient(timeout=20.0) as client:
        ner = await client.post(
            f'{NER}/internal/ner/extract',
            headers={'X-Internal-Service-Token': INTERNAL},
            json={'text': body.text, 'language': 'ru'},
        )
    entities = ner.json().get('entities', [])

    anonymized, mappings = apply_anonymization(body.text, entities)

    public_docs[body.document_id] = {
        'document_id': body.document_id,
        'case_id': body.case_id,
        'title': body.title,
        'anonymized_text': anonymized,
        'metadata': body.metadata,
    }
    restored_docs[body.document_id] = {
        'document_id': body.document_id,
        'case_id': body.case_id,
        'title': body.title,
        'original_text': body.text,
        'anonymized_text': anonymized,
        'mappings': mappings,
    }
    jobs[job_id]['status'] = 'COMPLETED'
    return {'job_id': job_id, 'status': 'COMPLETED', 'anonymized_document_id': body.document_id}


@app.get('/internal/anonymization/documents/{document_id}/public')
def public(document_id: str, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        _error(403, 'ACCESS_DENIED', 'Недостаточно прав')
    if document_id not in public_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    return public_docs[document_id]


@app.get('/internal/anonymization/documents/{document_id}/restored')
def restored(document_id: str, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        _error(403, 'ACCESS_DENIED', 'Недостаточно прав')
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    return restored_docs[document_id]


@app.get('/internal/anonymization/jobs/{job_id}')
def job(job_id: str, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        _error(403, 'ACCESS_DENIED', 'Недостаточно прав')
    if job_id not in jobs:
        _error(404, 'NOT_FOUND', 'Задание не найдено')
    return jobs[job_id]
