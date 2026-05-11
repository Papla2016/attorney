from collections import defaultdict
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
manual_mappings_by_document_id: dict[str, list[dict]] = {}


class ProcessRequest(BaseModel):
    case_id: str
    document_id: str
    title: str
    text: str
    metadata: dict = {}


class MappingRequest(BaseModel):
    original_value: str
    placeholder: str | None = None
    entity_type: str
    mode: str = 'new'


class ReanonymizeRequest(BaseModel):
    mappings: list[dict] = []


def error_payload(code: str, message: str, details: dict | None = None):
    return {'error': {'code': code, 'message': message, 'details': details or {}}}


def _error(status: int, code: str, message: str, details: dict | None = None):
    raise HTTPException(status_code=status, detail=error_payload(code, message, details))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and 'error' in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=error_payload('HTTP_ERROR', str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content=error_payload('BAD_REQUEST', 'Некорректный запрос', {'validation_errors': exc.errors()}))


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
        mappings.append({'placeholder': text_to_placeholder[original], 'original_value': original, 'entity_type': entity_type, 'source': e.get('source', 'ner')})

    anonymized = text
    for e in sorted(entities, key=lambda x: x['start'], reverse=True):
        anonymized = anonymized[:e['start']] + text_to_placeholder[e['text']] + anonymized[e['end']:]
    return anonymized, mappings


def require_internal(token: str | None):
    if token != INTERNAL:
        _error(403, 'ACCESS_DENIED', 'Недостаточно прав')


def next_placeholder(entity_type: str, mappings: list[dict]) -> str:
    used = {m.get('placeholder') for m in mappings}
    idx = 1
    while make_placeholder(entity_type, idx) in used:
        idx += 1
    return make_placeholder(entity_type, idx)


def merge_mappings(existing: list[dict], incoming: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for m in [*existing, *incoming]:
        original = (m.get('original_value') or '').strip()
        placeholder = (m.get('placeholder') or '').strip()
        if not original or not placeholder:
            continue
        key = (original, placeholder)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            'placeholder': placeholder,
            'original_value': original,
            'entity_type': m.get('entity_type') or 'UNKNOWN',
            'source': m.get('source') or 'manual',
        })
    return result


def replace_by_mappings(text: str, mappings: list[dict]) -> str:
    anonymized = text
    for m in sorted(mappings, key=lambda x: len(x.get('original_value') or ''), reverse=True):
        original = m.get('original_value') or ''
        placeholder = m.get('placeholder') or ''
        if original and placeholder:
            anonymized = anonymized.replace(original, placeholder)
    return anonymized


async def extract_entities(text: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            ner = await client.post(
                f'{NER}/internal/ner/extract',
                headers={'X-Internal-Service-Token': INTERNAL},
                json={'text': text, 'language': 'ru'},
            )
        if ner.status_code >= 400:
            return []
        return ner.json().get('entities', [])
    except Exception:
        return []


def save_document(document_id: str, case_id: str, title: str, original_text: str, anonymized_text: str, mappings: list[dict], metadata: dict | None = None):
    public_docs[document_id] = {
        'document_id': document_id,
        'case_id': case_id,
        'title': title,
        'anonymized_text': anonymized_text,
        'metadata': metadata or {},
    }
    restored_docs[document_id] = {
        'document_id': document_id,
        'case_id': case_id,
        'title': title,
        'original_text': original_text,
        'anonymized_text': anonymized_text,
        'mappings': mappings,
    }


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/ready')
def ready():
    return {'status': 'ready'}


@app.post('/internal/anonymization/process')
async def process(body: ProcessRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'id': job_id, 'case_id': body.case_id, 'document_id': body.document_id, 'status': 'NER_PROCESSING'}

    entities = await extract_entities(body.text)

    anonymized, mappings = apply_anonymization(body.text, entities)
    manual_mappings_by_document_id.setdefault(body.document_id, [])
    mappings = merge_mappings(manual_mappings_by_document_id[body.document_id], mappings)
    anonymized = replace_by_mappings(body.text, mappings)

    save_document(body.document_id, body.case_id, body.title, body.text, anonymized, mappings, body.metadata)
    jobs[job_id]['status'] = 'COMPLETED'
    return {'job_id': job_id, 'status': 'COMPLETED', 'anonymized_document_id': body.document_id, 'anonymized_text': anonymized, 'mappings': mappings}


@app.get('/internal/anonymization/documents/{document_id}/public')
def public(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in public_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    return public_docs[document_id]


@app.get('/internal/anonymization/documents/{document_id}/restored')
def restored(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    return restored_docs[document_id]



@app.get('/internal/anonymization/documents/{document_id}')
def get_document(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    return restored_docs[document_id]


@app.post('/internal/anonymization/documents/{document_id}/mappings')
def add_mapping(document_id: str, body: MappingRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if body.mode not in {'new', 'existing'}:
        _error(400, 'BAD_REQUEST', 'Недопустимый режим', {'allowed': ['new', 'existing']})
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')

    doc = restored_docs[document_id]
    existing = doc.get('mappings', [])
    manual = manual_mappings_by_document_id.setdefault(document_id, [m for m in existing if m.get('source') == 'manual'])
    if any(m.get('original_value') == body.original_value for m in manual + existing):
        return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': existing}

    placeholder = body.placeholder if body.mode == 'existing' else next_placeholder(body.entity_type, existing + manual)
    if not placeholder:
        _error(400, 'BAD_REQUEST', 'placeholder is required for existing mode')
    manual_mapping = {'placeholder': placeholder, 'original_value': body.original_value, 'entity_type': body.entity_type, 'source': 'manual'}
    manual.append(manual_mapping)
    doc['mappings'] = merge_mappings(manual, existing)
    return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': doc['mappings']}


@app.post('/internal/anonymization/documents/{document_id}/reanonymize')
async def reanonymize(document_id: str, body: ReanonymizeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    original_text = doc.get('original_text', '')
    incoming_mappings = body.mappings or doc.get('mappings', [])
    manual = [m for m in incoming_mappings if m.get('source') == 'manual']
    manual_mappings_by_document_id[document_id] = merge_mappings(manual_mappings_by_document_id.get(document_id, []), manual)

    entities = await extract_entities(original_text)
    _, ner_mappings = apply_anonymization(original_text, entities)
    base_mappings = merge_mappings(incoming_mappings, ner_mappings)
    mappings = merge_mappings(manual_mappings_by_document_id[document_id], base_mappings)
    anonymized = replace_by_mappings(original_text, mappings)
    save_document(document_id, doc.get('case_id', ''), doc.get('title', ''), original_text, anonymized, mappings, public_docs.get(document_id, {}).get('metadata', {}))
    return {'document_id': document_id, 'anonymized_text': anonymized, 'mappings': mappings}


@app.delete('/internal/anonymization/documents/{document_id}')
def delete_document(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    public_docs.pop(document_id, None)
    restored_docs.pop(document_id, None)
    manual_mappings_by_document_id.pop(document_id, None)
    return {'ok': True}


@app.get('/internal/anonymization/jobs/{job_id}')
def job(job_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if job_id not in jobs:
        _error(404, 'NOT_FOUND', 'Задание не найдено')
    return jobs[job_id]
