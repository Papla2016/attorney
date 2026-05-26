from collections import defaultdict
import copy
import re
from datetime import datetime
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
manual_decisions_by_document_id: dict[str, dict[str, dict]] = {}
pending_review_by_document_id: dict[str, list[dict]] = {}
audit_log: list[dict] = []


class ProcessRequest(BaseModel):
    case_id: str
    document_id: str
    title: str
    text: str
    content_format: str = 'PLAIN_TEXT'
    original_content: dict | None = None
    metadata: dict = {}
    publication_redaction_mode: str = 'NORMATIVE'


class MappingRequest(BaseModel):
    original_value: str
    placeholder: str | None = None
    entity_type: str
    mode: str = 'new'


class MappingPatchRequest(BaseModel):
    placeholder: str | None = None
    original_value: str | None = None
    entity_type: str | None = None


class MergeMappingsRequest(BaseModel):
    target_mapping_id: str
    source_mapping_ids: list[str]


class ReanonymizeRequest(BaseModel):
    mappings: list[dict] = []
    publication_redaction_mode: str = 'NORMATIVE'


class RedactionDecisionRequest(BaseModel):
    entity_key: str | None = None
    selected_text: str
    decision: str
    entity_class: str = 'PERSON'
    person_role: str | None = None
    target_cluster_id: str | None = None
    reason: str = 'Исправлено пользователем'


class DraftScanRequest(BaseModel):
    text: str
    content: dict | None = None
    content_format: str = 'TIPTAP_JSON'
    document_revision: int = 0


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


def now_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def normalize_source(source: str | None) -> str:
    if source == 'ner':
        return 'natasha'
    if source in {'manual', 'natasha', 'regex', 'rule'}:
        return source
    return source or 'manual'


def ensure_mapping_metadata(mapping: dict, *, touch_updated: bool = False) -> dict:
    now = now_iso()
    if not mapping.get('id'):
        mapping['id'] = str(uuid.uuid4())
    if not mapping.get('created_at'):
        mapping['created_at'] = mapping.get('updated_at') or now
    if not mapping.get('updated_at') or touch_updated:
        mapping['updated_at'] = now
    mapping['source'] = normalize_source(mapping.get('source'))
    return mapping


def ensure_document_mappings(document_id: str) -> list[dict]:
    doc = restored_docs.get(document_id)
    if not doc:
        return []
    doc['mappings'] = [ensure_mapping_metadata(m) for m in doc.get('mappings', [])]
    manual_mappings_by_document_id[document_id] = [m for m in doc['mappings'] if m.get('source') == 'manual']
    return doc['mappings']


def validate_non_empty(value: str | None, field: str):
    if value is not None and not value.strip():
        _error(400, 'BAD_REQUEST', f'{field} не должен быть пустым', {'field': field})


def normalize_quotes(value: str) -> str:
    return value.replace('"', '«').replace('“', '«').replace('”', '»').replace('„', '«').replace("'", '’')


def normalize_spaces(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def normalize_person_name(value: str) -> tuple[str, dict]:
    cleaned = normalize_spaces(normalize_quotes(value)).replace(' .', '.')
    short = re.match(r'^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.$', cleaned)
    if short:
        surname, i1, i2 = short.groups()
        return cleaned, {'surname': surname.lower(), 'initials': f'{i1}{i2}'.lower(), 'is_short': True}
    parts = cleaned.split()
    if len(parts) >= 3:
        initials = ''.join(p[0] for p in parts[1:3] if p)
        return f'{parts[0]} {parts[1]} {parts[2]}', {'surname': parts[0].lower(), 'initials': initials.lower(), 'is_short': False}
    return cleaned, {'surname': (parts[0].lower() if parts else cleaned.lower()), 'initials': '', 'is_short': False}


def detect_person_role(text: str, start: int, end: int) -> str:
    prefix = text[max(0, start - 120):start].lower()
    if re.search(r'председательствующего\s+судьи\s*$', prefix) or re.search(r'судьи\s*$', prefix):
        return 'JUDGE'
    if re.search(r'при\s+секретаре\s*$', prefix):
        return 'COURT_SECRETARY'
    if re.search(r'(по\s+иску|истцом)\s*$', prefix):
        return 'PLAINTIFF'
    if re.search(r'индивидуальным\s+предпринимателем\s*$', prefix):
        return 'INDIVIDUAL_ENTREPRENEUR'
    return 'UNKNOWN'


def decide_redaction(entity: dict, mode: str) -> tuple[str, str, bool]:
    etype = entity.get('entity_class')
    role = entity.get('person_role')
    ctx = entity.get('context_kind')
    if etype == 'PERSON':
        if role in {'JUDGE', 'COURT_SECRETARY'}:
            return 'KEEP', 'ФИО судьи/секретаря оставлено в нормативном режиме', False
        if role == 'UNKNOWN':
            return 'REDACT', 'ФИО лица подлежит обезличиванию', True
        return 'REDACT', 'ФИО лица подлежит обезличиванию', False
    if etype == 'ORGANIZATION':
        return 'KEEP', 'Организация не обезличивается в нормативном режиме', False
    if etype == 'DATE':
        if ctx == 'BIRTH_DATE':
            return 'REDACT', 'Дата рождения подлежит обезличиванию', False
        if ctx == 'UNKNOWN_DATE':
            return 'REDACT', 'Дата скрыта до ручной проверки', True
        return 'KEEP', 'Обычная дата документа/события', False
    if etype == 'EMAIL':
        if mode == 'EXTENDED_SAFE':
            return 'REDACT', 'Email скрыт в расширенном режиме', False
        return 'REDACT', 'Email скрыт до ручной проверки', True
    if etype == 'PLACE' and entity.get('context_kind') == 'UNKNOWN_LOCATION':
        return 'REDACT', 'Адрес/место скрыто до ручной проверки', True
    return ('REDACT', 'Сведения подлежат обезличиванию', False) if etype in {'PHONE', 'SNILS', 'PASSPORT', 'INN'} else ('KEEP', 'Оставлено политикой публикации', False)

def make_placeholder(entity_type: str, idx: int) -> str:
    if entity_type in {'PERSON_FULL_NAME', 'JUDGE', 'CASE_PARTICIPANT', 'COURT_SECRETARY'} or entity_type.startswith('PERSON_'):
        return f'ФИО{idx}'
    mapping = {
        'ADDRESS': 'АДРЕС',
        'LOCATION': 'МЕСТО',
        'ORGANIZATION': 'ОРГАНИЗАЦИЯ',
        'PHONE': 'ТЕЛЕФОН',
        'EMAIL': 'ЭЛЕКТРОННАЯ_ПОЧТА',
        'PASSPORT': 'ПАСПОРТ',
        'SNILS': 'СНИЛС',
        'INN': 'ИНН',
        'BIRTH_DATE': 'ДАТА_РОЖДЕНИЯ',
        'DATE': 'ДАТА',
        'PLACE': 'АДРЕС',
        'PERSON': 'ФИО',
        'BANK_ACCOUNT': 'СЧЕТ',
        'CARD_NUMBER': 'КАРТА',
    }
    return f"{mapping.get(entity_type, 'ДАННЫЕ')}{idx}"


def resolve_entities(text: str, entities: list[dict], mode: str = 'NORMATIVE') -> list[dict]:
    resolved = []
    for raw in entities:
        source_type = raw.get('type', 'UNKNOWN')
        value = normalize_spaces(raw.get('text', ''))
        item = {
            'id': str(uuid.uuid4()),
            'surface_value': value,
            'normalized_value': value,
            'entity_class': source_type,
            'entity_subtype': None,
            'person_role': None,
            'context_kind': None,
            'start': raw.get('start', 0),
            'end': raw.get('end', 0),
            'confidence': raw.get('confidence', 0.5),
            'source': normalize_source(raw.get('source', 'natasha')),
            'requires_review': False,
        }
        if source_type in {'PERSON_FULL_NAME', 'JUDGE', 'COURT_SECRETARY', 'CASE_PARTICIPANT'}:
            item['entity_class'] = 'PERSON'
            norm, sign = normalize_person_name(raw.get('normalized_text') or value)
            item['normalized_value'] = norm
            item['signature'] = sign
            item['person_role'] = detect_person_role(text, item['start'], item['end'])
        elif source_type == 'ORGANIZATION':
            m = re.search(r'\b(?:ООО|АО|ПАО|ЗАО|ОАО)\s+[«"][^»"]+[»"]', value)
            if m:
                item['normalized_value'] = normalize_quotes(m.group(0)).replace('»', '»')
                item['surface_value'] = m.group(0)
        elif source_type in {'BIRTH_DATE', 'DATE'}:
            item['entity_class'] = 'DATE'
            ctx = text[max(0, item['start'] - 40): item['end'] + 10].lower()
            if re.search(r'дата рождения|родил[а-я]+|года рождения', ctx):
                item['context_kind'] = 'BIRTH_DATE'
            elif re.search(r'решение от|постановление от|договор от|акт от|определение от|судебн\w+\s+заседан', ctx):
                item['context_kind'] = 'DOCUMENT_DATE'
            else:
                item['context_kind'] = 'UNKNOWN_DATE'
        elif source_type in {'ADDRESS', 'LOCATION'}:
            item['entity_class'] = 'PLACE'
            item['context_kind'] = 'UNKNOWN_LOCATION'
        dec, reason, review = decide_redaction(item, mode)
        item['redaction_decision'] = dec
        item['redaction_reason'] = reason
        item['requires_review'] = review
        resolved.append(item)
    return resolved


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
    seen_originals = set()
    for m in [*existing, *incoming]:
        original = (m.get('original_value') or '').strip()
        placeholder = (m.get('placeholder') or '').strip()
        if not original or not placeholder:
            continue
        if original in seen_originals:
            continue
        seen_originals.add(original)
        item = {**m, 'placeholder': placeholder, 'original_value': original, 'entity_type': m.get('entity_type') or 'UNKNOWN', 'source': normalize_source(m.get('source'))}
        result.append(ensure_mapping_metadata(item))
    return result


def replace_by_mappings(text: str, mappings: list[dict]) -> str:
    anonymized = text
    for m in sorted(mappings, key=lambda x: len(x.get('original_value') or ''), reverse=True):
        original = m.get('original_value') or ''
        placeholder = m.get('placeholder') or ''
        if original and placeholder:
            anonymized = anonymized.replace(original, placeholder)
    return anonymized


def replace_content_by_mappings(content: dict | None, mappings: list[dict]) -> dict | None:
    if not content:
        return None
    data = copy.deepcopy(content)
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('text'), str):
                node['text'] = replace_by_mappings(node['text'], mappings)
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data


def build_mappings_from_resolved(resolved: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    cluster_to_placeholder: dict[str, str] = {}
    counters: dict[str, int] = defaultdict(int)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in resolved:
        if e.get('redaction_decision') != 'REDACT':
            continue
        key = f"{e['entity_class']}::{e['normalized_value']}"
        if e['entity_class'] == 'PERSON' and e.get('signature', {}).get('initials'):
            key = f"PERSON::{e['signature']['surname']}::{e['signature']['initials']}"
        e['cluster_id'] = key
        grouped[key].append(e)
    mappings = []
    for cluster_id, items in grouped.items():
        sample = items[0]
        entity_class = sample['entity_class']
        placeholder_type = entity_class
        if entity_class == 'DATE' and sample.get('context_kind') == 'BIRTH_DATE':
            placeholder_type = 'BIRTH_DATE'
        elif entity_class == 'PLACE' and sample.get('context_kind') in {'RESIDENCE_ADDRESS', 'PROPERTY_LOCATION'}:
            placeholder_type = 'PLACE'
        prefix = 'ФИО' if entity_class == 'PERSON' else make_placeholder(placeholder_type, 0)[:-1]
        if cluster_id not in cluster_to_placeholder:
            counters[prefix] += 1
            cluster_to_placeholder[cluster_id] = f'{prefix}{counters[prefix]}'
        placeholder = cluster_to_placeholder[cluster_id]
        aliases = sorted({i['surface_value'] for i in items[1:]})
        mappings.append(ensure_mapping_metadata({
            'cluster_id': cluster_id, 'placeholder': placeholder, 'original_value': sample['surface_value'],
            'normalized_value': sample['normalized_value'], 'aliases': aliases, 'entity_class': entity_class,
            'entity_subtype': sample.get('entity_subtype'), 'person_role': sample.get('person_role'),
            'redaction_decision': 'REDACT', 'redaction_reason': sample.get('redaction_reason'), 'source': sample.get('source'),
            'requires_review': any(i.get('requires_review') for i in items),
            'entity_type': entity_class,
        }))
    kept=[]
    kept_grouped={}
    for e in resolved:
        if e['redaction_decision']!='KEEP':
            continue
        key=f"{e['entity_class']}::{e.get('normalized_value',e['surface_value'])}"
        bucket=kept_grouped.setdefault(key,{'cluster_id':key,'original_value':e['surface_value'],'normalized_value':e.get('normalized_value'),'entity_class':e['entity_class'],'redaction_decision':'KEEP','redaction_reason':e['redaction_reason'],'occurrences':[],'source':e.get('source')})
        bucket['occurrences'].append({'surface_value':e['surface_value'],'start':e.get('start',0),'end':e.get('end',0)})
    kept=[{**v,'occurrences_count':len(v['occurrences'])} for v in kept_grouped.values()]
    review = [{'original_value': e['surface_value'], 'normalized_value': e.get('normalized_value'), 'entity_class': e['entity_class'], 'redaction_decision': e['redaction_decision'], 'requires_review': e.get('requires_review', False), 'review_reason': e['redaction_reason'], 'source': e.get('source')} for e in resolved if e.get('requires_review')]
    return mappings, kept, review




def apply_manual_decisions(document_id: str, resolved: list[dict]) -> list[dict]:
    decisions = manual_decisions_by_document_id.get(document_id, {})
    for e in resolved:
        key = e.get('cluster_id') or f"{e['entity_class']}::{e.get('normalized_value', e['surface_value'])}"
        d = decisions.get(key)
        if not d:
            continue
        if d['decision'] == 'FORCE_KEEP':
            e['redaction_decision'] = 'KEEP'
            e['requires_review'] = False
            e['redaction_reason'] = 'Оставлено пользователем'
        elif d['decision'] == 'FORCE_REDACT':
            e['redaction_decision'] = 'REDACT'
            e['redaction_reason'] = 'Обезличено пользователем'
            e['requires_review'] = False
    return resolved


def rebuild_document(document_id: str, mode: str):
    doc = restored_docs[document_id]
    text = doc.get('original_text', '')
    return text
def apply_anonymization(text: str, entities: list[dict]) -> tuple[str, list[dict]]:
    resolved = resolve_entities(text, entities, 'NORMATIVE')
    mappings, _, _ = build_mappings_from_resolved(resolved)
    return replace_by_mappings(text, mappings), mappings


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


def save_document(document_id: str, case_id: str, title: str, original_text: str, anonymized_text: str, mappings: list[dict], metadata: dict | None = None, recognized_but_kept: list[dict] | None = None):
    existing = restored_docs.get(document_id, {})
    public_docs[document_id] = {
        'document_id': document_id,
        'case_id': case_id,
        'title': title,
        'anonymized_text': anonymized_text,
        'recognized_but_kept': recognized_but_kept or [],
        'metadata': metadata or {},
    }
    restored_docs[document_id] = {
        'document_id': document_id,
        'case_id': case_id,
        'title': title,
        'original_text': original_text,
        'anonymized_text': anonymized_text,
        'mappings': [ensure_mapping_metadata(m) for m in mappings],
        'recognized_but_kept': recognized_but_kept or [],
        'content_format': existing.get('content_format', 'PLAIN_TEXT'),
        'original_content': existing.get('original_content'),
        'anonymized_content': replace_content_by_mappings(existing.get('original_content'), mappings),
        'review_entities': existing.get('review_entities', []),
        'review_markers': existing.get('review_markers', []),
        'pending_review': existing.get('pending_review', []),
        'pending_markers': existing.get('pending_markers', []),
        'manual_decisions': existing.get('manual_decisions', list(manual_decisions_by_document_id.get(document_id, {}).values())),
        'publication_redaction_mode': existing.get('publication_redaction_mode', 'NORMATIVE'),
        'ner_provider': existing.get('ner_provider', 'hybrid'),
    }


def anonymization_result_response(document: dict) -> dict:
    return {
        'document_id': document['document_id'],
        'case_id': document.get('case_id'),
        'title': document.get('title'),
        'anonymized_text': document.get('anonymized_text', ''),
        'anonymized_content': document.get('anonymized_content'),
        'content_format': document.get('content_format', 'PLAIN_TEXT'),
        'mappings': document.get('mappings', []),
        'recognized_but_kept': document.get('recognized_but_kept', []),
        'review_entities': document.get('review_entities', []),
        'review_markers': document.get('review_markers', []),
        'pending_review': document.get('pending_review', []),
        'pending_markers': document.get('pending_markers', []),
        'manual_decisions': document.get('manual_decisions', []),
        'publication_redaction_mode': document.get('publication_redaction_mode', 'NORMATIVE'),
        'ner_provider': document.get('ner_provider', 'hybrid'),
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

    resolved = resolve_entities(body.text, entities, body.publication_redaction_mode)
    mappings, recognized_but_kept, review_entities = build_mappings_from_resolved(resolved)
    manual_mappings_by_document_id.setdefault(body.document_id, [])
    mappings = merge_mappings(manual_mappings_by_document_id[body.document_id], mappings)
    anonymized = replace_by_mappings(body.text, mappings)

    save_document(body.document_id, body.case_id, body.title, body.text, anonymized, mappings, body.metadata, recognized_but_kept)
    jobs[job_id]['status'] = 'COMPLETED'
    restored_docs[body.document_id]['review_entities']=review_entities
    restored_docs[body.document_id]['publication_redaction_mode']=body.publication_redaction_mode
    restored_docs[body.document_id]['content_format']=body.content_format
    restored_docs[body.document_id]['original_content']=body.original_content
    restored_docs[body.document_id]['anonymized_content'] = replace_content_by_mappings(body.original_content, mappings)
    restored_docs[body.document_id]['pending_review'] = []
    restored_docs[body.document_id]['pending_markers'] = []
    return {'job_id': job_id, 'status': 'COMPLETED', 'anonymized_document_id': body.document_id, 'anonymized_text': anonymized, 'anonymized_content': restored_docs[body.document_id].get('anonymized_content'), 'content_format': body.content_format, 'mappings': mappings, 'recognized_but_kept': recognized_but_kept, 'review_entities': review_entities, 'review_markers': [], 'pending_review': [], 'pending_markers': [], 'manual_decisions': list(manual_decisions_by_document_id.get(body.document_id, {}).values()), 'publication_redaction_mode': body.publication_redaction_mode, 'ner_provider': 'hybrid'}


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
    ensure_document_mappings(document_id)
    return restored_docs[document_id]


@app.post('/internal/anonymization/documents/{document_id}/mappings')
def add_mapping(document_id: str, body: MappingRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if body.mode not in {'new', 'existing'}:
        _error(400, 'BAD_REQUEST', 'Недопустимый режим', {'allowed': ['new', 'existing']})
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')

    doc = restored_docs[document_id]
    existing = ensure_document_mappings(document_id)
    manual = manual_mappings_by_document_id.setdefault(document_id, [m for m in existing if m.get('source') == 'manual'])
    validate_non_empty(body.original_value, 'original_value')
    validate_non_empty(body.entity_type, 'entity_type')
    validate_non_empty(body.placeholder, 'placeholder')
    if any(m.get('original_value') == body.original_value for m in manual + existing):
        return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': existing}

    placeholder = body.placeholder if body.mode == 'existing' else next_placeholder(body.entity_type, existing + manual)
    if not placeholder:
        _error(400, 'BAD_REQUEST', 'placeholder is required for existing mode')
    manual_mapping = ensure_mapping_metadata({'placeholder': placeholder, 'original_value': body.original_value, 'entity_type': body.entity_type, 'source': 'manual'})
    manual.append(manual_mapping)
    doc['mappings'] = merge_mappings(manual, existing)
    return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': doc['mappings']}

@app.patch('/internal/anonymization/documents/{document_id}/mappings/{mapping_id}')
def update_mapping(document_id: str, mapping_id: str, body: MappingPatchRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    validate_non_empty(body.placeholder, 'placeholder')
    validate_non_empty(body.original_value, 'original_value')
    validate_non_empty(body.entity_type, 'entity_type')
    doc = restored_docs[document_id]
    mappings = ensure_document_mappings(document_id)
    mapping = next((m for m in mappings if m.get('id') == mapping_id), None)
    if not mapping:
        _error(404, 'NOT_FOUND', 'Элемент таблицы соответствия не найден')
    data = body.model_dump(exclude_unset=True)
    for field in ['placeholder', 'original_value', 'entity_type']:
        if field in data:
            mapping[field] = data[field].strip()
    mapping['source'] = 'manual'
    ensure_mapping_metadata(mapping, touch_updated=True)
    doc['mappings'] = merge_mappings([m for m in mappings if m.get('source') == 'manual'], [m for m in mappings if m.get('source') != 'manual'])
    manual_mappings_by_document_id[document_id] = [m for m in doc['mappings'] if m.get('source') == 'manual']
    return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': doc['mappings']}


@app.delete('/internal/anonymization/documents/{document_id}/mappings/{mapping_id}')
def delete_mapping(document_id: str, mapping_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    mappings = ensure_document_mappings(document_id)
    mapping = next((m for m in mappings if m.get('id') == mapping_id), None)
    if not mapping:
        _error(404, 'NOT_FOUND', 'Элемент таблицы соответствия не найден')
    entity_key = mapping.get('cluster_id') or f"{mapping.get('entity_class', mapping.get('entity_type','OTHER'))}::{mapping.get('normalized_value', mapping.get('original_value',''))}"
    manual_decisions_by_document_id.setdefault(document_id, {})[entity_key] = {'entity_key': entity_key, 'decision': 'FORCE_KEEP', 'target_cluster_id': None, 'reason': 'Оставлено пользователем', 'created_at': now_iso(), 'updated_at': now_iso()}
    doc['mappings'] = [m for m in mappings if m.get('id') != mapping_id]
    doc['anonymized_text'] = replace_by_mappings(doc.get('original_text',''), doc['mappings'])
    manual_mappings_by_document_id[document_id] = [m for m in doc['mappings'] if m.get('source') == 'manual']
    return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': doc['mappings']}


@app.post('/internal/anonymization/documents/{document_id}/mappings/merge')
def merge_document_mappings(document_id: str, body: MergeMappingsRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    mappings = ensure_document_mappings(document_id)
    target = next((m for m in mappings if m.get('id') == body.target_mapping_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Целевой элемент таблицы соответствия не найден')
    if not body.source_mapping_ids:
        _error(400, 'BAD_REQUEST', 'source_mapping_ids не должен быть пустым')
    source_ids = set(body.source_mapping_ids)
    sources = [m for m in mappings if m.get('id') in source_ids]
    if len(sources) != len(source_ids):
        _error(404, 'NOT_FOUND', 'Один или несколько исходных элементов таблицы соответствия не найдены')
    target_placeholder = target.get('placeholder')
    target_type = target.get('entity_type') or 'UNKNOWN'
    for m in sources:
        m['placeholder'] = target_placeholder
        m['entity_type'] = m.get('entity_type') or target_type
        m['source'] = 'manual'
        ensure_mapping_metadata(m, touch_updated=True)
    target['source'] = 'manual'
    ensure_mapping_metadata(target, touch_updated=True)
    doc['mappings'] = merge_mappings([m for m in mappings if m.get('source') == 'manual'], [m for m in mappings if m.get('source') != 'manual'])
    manual_mappings_by_document_id[document_id] = [m for m in doc['mappings'] if m.get('source') == 'manual']
    return {'document_id': document_id, 'anonymized_text': doc.get('anonymized_text', ''), 'mappings': doc['mappings']}



@app.post('/internal/anonymization/documents/{document_id}/mappings/repair-placeholders')
def repair_placeholders(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    mappings = ensure_document_mappings(document_id)
    counters = defaultdict(int)
    by_cluster = {}
    for m in mappings:
        cluster = m.get('cluster_id') or f"{m.get('entity_class','OTHER')}::{m.get('normalized_value', m.get('original_value',''))}"
        et = m.get('entity_class') or m.get('entity_type') or 'OTHER'
        prefix = 'ФИО' if et == 'PERSON' else make_placeholder(et, 0)[:-1]
        if cluster not in by_cluster:
            counters[prefix]+=1
            by_cluster[cluster]=f"{prefix}{counters[prefix]}"
        m['placeholder']=by_cluster[cluster]
    doc['mappings']=mappings
    doc['anonymized_text']=replace_by_mappings(doc.get('original_text',''), mappings)
    audit_log.append({'id': str(uuid.uuid4()), 'document_id': document_id, 'action': 'REPAIR_PLACEHOLDERS', 'created_at': now_iso(), 'details': {}})
    return anonymization_result_response(doc)

@app.post('/internal/anonymization/documents/{document_id}/reanonymize')
async def reanonymize(document_id: str, body: ReanonymizeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    original_text = doc.get('original_text', '')
    ensure_document_mappings(document_id)
    incoming_mappings = [ensure_mapping_metadata(m) for m in (body.mappings or doc.get('mappings', []))]
    manual = [m for m in incoming_mappings if m.get('source') == 'manual']
    manual_mappings_by_document_id[document_id] = merge_mappings(manual_mappings_by_document_id.get(document_id, []), manual)

    entities = await extract_entities(original_text)
    resolved = resolve_entities(original_text, entities, body.publication_redaction_mode)
    ner_mappings, recognized_but_kept, review_entities = build_mappings_from_resolved(resolved)
    base_mappings = merge_mappings(incoming_mappings, ner_mappings)
    mappings = merge_mappings(manual_mappings_by_document_id[document_id], base_mappings)
    anonymized = replace_by_mappings(original_text, mappings)
    save_document(document_id, doc.get('case_id', ''), doc.get('title', ''), original_text, anonymized, mappings, public_docs.get(document_id, {}).get('metadata', {}), recognized_but_kept)
    restored_docs[document_id]['review_entities']=review_entities
    restored_docs[document_id]['publication_redaction_mode']=body.publication_redaction_mode
    return anonymization_result_response(restored_docs[document_id])


@app.delete('/internal/anonymization/documents/{document_id}')
def delete_document(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    public_docs.pop(document_id, None)
    restored_docs.pop(document_id, None)
    manual_mappings_by_document_id.pop(document_id, None)
    return {'ok': True}


@app.post('/internal/anonymization/documents/{document_id}/redaction-decisions')
def redaction_decision(document_id: str, body: RedactionDecisionRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    if body.decision not in {'REDACT', 'KEEP', 'MERGE_WITH_EXISTING'}:
        _error(400, 'BAD_REQUEST', 'Недопустимое решение', {'allowed': ['REDACT', 'KEEP', 'MERGE_WITH_EXISTING']})
    audit_log.append({'id': str(uuid.uuid4()), 'document_id': document_id, 'action': 'REDACTION_DECISION', 'details': body.model_dump(), 'created_at': now_iso()})
    doc = restored_docs[document_id]
    entity_key = body.entity_key or f"{body.entity_class}::{normalize_spaces(body.selected_text)}"
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    if body.decision == 'REDACT':
        decisions[entity_key] = {'entity_key': entity_key, 'decision': 'FORCE_REDACT', 'target_cluster_id': body.target_cluster_id, 'reason': body.reason, 'created_at': now_iso(), 'updated_at': now_iso()}
        mapping = ensure_mapping_metadata({'original_value': body.selected_text, 'entity_type': body.entity_class, 'entity_class': body.entity_class, 'placeholder': next_placeholder(body.entity_class, doc.get('mappings', [])), 'source': 'manual'})
        doc.setdefault('mappings', []).append(mapping)
    elif body.decision == 'KEEP':
        decisions[entity_key] = {'entity_key': entity_key, 'decision': 'FORCE_KEEP', 'target_cluster_id': body.target_cluster_id, 'reason': body.reason, 'created_at': now_iso(), 'updated_at': now_iso()}
        doc['mappings'] = [m for m in doc.get('mappings', []) if m.get('original_value') != body.selected_text]
    elif body.decision == 'MERGE_WITH_EXISTING':
        target = next((m for m in doc.get('mappings', []) if m.get('cluster_id') == body.target_cluster_id), None)
        if not target:
            _error(400, 'BAD_REQUEST', 'Целевой cluster не найден')
        decisions[entity_key] = {'entity_key': entity_key, 'decision': 'MERGE_WITH_CLUSTER', 'target_cluster_id': body.target_cluster_id, 'reason': body.reason, 'created_at': now_iso(), 'updated_at': now_iso()}
        doc.setdefault('mappings', []).append(ensure_mapping_metadata({'original_value': body.selected_text, 'entity_type': body.entity_class, 'entity_class': body.entity_class, 'cluster_id': body.target_cluster_id, 'placeholder': target.get('placeholder'), 'source': 'manual'}))
    original_text = doc.get('original_text', '')
    doc['anonymized_text'] = replace_by_mappings(original_text, doc.get('mappings', []))
    doc['anonymized_content'] = replace_content_by_mappings(doc.get('original_content'), doc.get('mappings', []))
    pending = [p for p in pending_review_by_document_id.get(document_id, []) if p.get('entity_key') != entity_key]
    pending_review_by_document_id[document_id] = pending
    doc['pending_review'] = pending
    doc['pending_markers'] = [{'entity_key': p['entity_key'], 'surface_value': p['surface_value'], 'start': p['start'], 'end': p['end'], 'reason': p['reason']} for p in pending]
    doc['manual_decisions'] = list(decisions.values())
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/draft-scan')
async def draft_scan(document_id: str, body: DraftScanRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    entities = await extract_entities(body.text)
    pending = []
    decisions = manual_decisions_by_document_id.get(document_id, {})
    mappings = restored_docs[document_id].get('mappings', [])
    for e in resolve_entities(body.text, entities, 'NORMATIVE'):
        if e.get('entity_class') != 'PERSON':
            continue
        surface = e.get('surface_value', '')
        if re.fullmatch(r'ФИО\d+', surface):
            continue
        key = f"PERSON::{normalize_spaces(surface)}"
        if decisions.get(key, {}).get('decision') == 'FORCE_KEEP':
            continue
        merge_candidates = [{'cluster_id': m.get('cluster_id'), 'placeholder': m.get('placeholder'), 'normalized_value': m.get('normalized_value')} for m in mappings if m.get('entity_class') == 'PERSON' and m.get('cluster_id')]
        pending.append({'entity_key': key, 'surface_value': surface, 'normalized_value': e.get('normalized_value', surface), 'entity_class': 'PERSON', 'person_role': e.get('person_role', 'UNKNOWN'), 'start': e.get('start', 0), 'end': e.get('end', 0), 'reason': 'В изменённом тексте найдено возможное ФИО, ещё не включённое в таблицу соответствия', 'suggested_action': 'REDACT', 'merge_candidates': merge_candidates})
    pending_review_by_document_id[document_id] = pending
    restored_docs[document_id]['pending_review'] = pending
    restored_docs[document_id]['pending_markers'] = [{'entity_key': p['entity_key'], 'surface_value': p['surface_value'], 'start': p['start'], 'end': p['end'], 'reason': p['reason']} for p in pending]
    return {'document_id': document_id, 'document_revision': body.document_revision, 'pending_review': pending, 'pending_markers': restored_docs[document_id]['pending_markers']}


@app.get('/internal/anonymization/documents/{document_id}/preview')
def markdown_preview(document_id: str, format: str = 'markdown', x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    if format != 'markdown':
        _error(400, 'BAD_REQUEST', 'Поддерживается только markdown')
    return {'format': 'markdown', 'content': restored_docs[document_id].get('anonymized_text', '')}


@app.get('/internal/anonymization/jobs/{job_id}')
def job(job_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if job_id not in jobs:
        _error(404, 'NOT_FOUND', 'Задание не найдено')
    return jobs[job_id]
