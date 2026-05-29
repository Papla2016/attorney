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
    entity_id: str | None = None
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
    target_entity_id: str | None = None
    reason: str = 'Исправлено пользователем'


class DraftScanRequest(BaseModel):
    text: str
    content: dict | None = None
    content_format: str = 'TIPTAP_JSON'
    document_revision: int = 0


class EntityPatchRequest(BaseModel):
    canonical_value: str | None = None
    entity_class: str | None = None
    person_role: str | None = None
    context_label: str | None = None


class EntityMergeRequest(BaseModel):
    target_entity_id: str
    source_entity_ids: list[str]


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




def build_entity_semantic_key(entity_class: str, normalized_value: str | None, person_role: str | None = None) -> str:
    cls = ' '.join(str(entity_class or 'OTHER').split()).upper()
    value = ' '.join(str(normalized_value or '').split()).lower()
    return f'{cls}::{value}'


def entity_semantic_key(entity: dict) -> str:
    return build_entity_semantic_key(
        entity.get('entity_class') or entity.get('entity_type') or 'OTHER',
        entity.get('normalized_value') or entity.get('canonical_value') or entity.get('original_value') or entity.get('surface_value') or '',
        entity.get('person_role'),
    )



def store_merge_entities_decision(document_id: str, target: dict, sources: list[dict]) -> dict:
    now = now_iso()
    target_key = entity_semantic_key(target)
    source_keys = [entity_semantic_key(source) for source in sources]
    decision_key = f"MERGE_ENTITIES::{target_key}::{','.join(source_keys)}"
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    existing = decisions.get(decision_key, {})
    decision = {
        'decision_id': existing.get('decision_id') or str(uuid.uuid4()),
        'document_id': document_id,
        'decision_type': 'MERGE_ENTITIES',
        'target_entity_key': target_key,
        'source_entity_keys': source_keys,
        'target_entity_id': target.get('entity_id'),
        'source_entity_ids': [source.get('entity_id') for source in sources],
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    decisions[decision_key] = decision
    return decision


def merge_entities_in_state(entities: list[dict], target: dict, sources: list[dict]) -> list[dict]:
    existing_mention_ids = {
        mention.get('mention_id')
        for mention in target.get('mentions', [])
        if mention.get('mention_id')
    }
    target_mentions = target.setdefault('mentions', [])
    for source in sources:
        for mention in source.get('mentions', []):
            mention_id = mention.get('mention_id')
            if mention_id and mention_id in existing_mention_ids:
                continue
            moved = copy.deepcopy(mention)
            moved['entity_id'] = target.get('entity_id')
            moved['replacement_value'] = target.get('placeholder')
            moved['requires_review'] = False
            moved['review_reason'] = None
            moved.pop('merge_candidates', None)
            target_mentions.append(moved)
            if mention_id:
                existing_mention_ids.add(mention_id)
    target['mentions_count'] = len(target_mentions)
    target['updated_at'] = now_iso()
    source_ids = {source.get('entity_id') for source in sources}
    return [entity for entity in entities if entity.get('entity_id') not in source_ids]


def update_working_content_for_merge(content: dict, mention_ids: set[str], target: dict) -> tuple[dict, set[str]]:
    data = copy.deepcopy(content)
    updated_mention_ids: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                for mark in node['marks']:
                    if mark.get('type') != 'redactionMention':
                        continue
                    attrs = mark.setdefault('attrs', {})
                    mention_id = attrs.get('mentionId')
                    if mention_id in mention_ids:
                        node['text'] = target.get('placeholder', node.get('text', ''))
                        attrs['entityId'] = target.get('entity_id')
                        attrs['placeholder'] = target.get('placeholder')
                        attrs['mentionId'] = mention_id
                        updated_mention_ids.add(mention_id)
                        break
            if isinstance(node.get('content'), list):
                for child in node['content']:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(data)
    return data, updated_mention_ids

def store_keep_redact_decision(document_id: str, decision_type: str, entity: dict, *, reason: str | None = None, explicit_entity_key: str | None = None) -> dict:
    if decision_type not in {'KEEP_ENTITY', 'REDACT_ENTITY'}:
        raise ValueError('Unsupported keep/redact manual decision')
    key = explicit_entity_key or entity_semantic_key(entity)
    now = now_iso()
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    existing = decisions.get(key, {})
    decision = {
        'decision_id': existing.get('decision_id') or str(uuid.uuid4()),
        'document_id': document_id,
        'decision_type': decision_type,
        'entity_key': key,
        'entity_class': entity.get('entity_class') or entity.get('entity_type') or 'OTHER',
        'canonical_value': entity.get('canonical_value') or entity.get('normalized_value') or entity.get('original_value') or entity.get('surface_value'),
        'reason': reason,
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    decisions[key] = decision
    return decision


def build_split_operation_key(source_entity_key: str, mention_locator: dict) -> str:
    return (
        'SPLIT_MENTION::'
        + str(source_entity_key)
        + '::'
        + str(mention_locator.get('start'))
        + '::'
        + str(mention_locator.get('end'))
        + '::'
        + str(mention_locator.get('surface_value'))
    )


def build_split_origin(source_entity_key: str, mention_locator: dict) -> dict:
    locator = {
        'surface_value': mention_locator.get('surface_value'),
        'normalized_value': mention_locator.get('normalized_value') or mention_locator.get('surface_value'),
        'start': mention_locator.get('start'),
        'end': mention_locator.get('end'),
    }
    return {
        'split_key': build_split_operation_key(source_entity_key, locator),
        'source_entity_key': source_entity_key,
        'mention_locator': locator,
    }


def store_entity_metadata_decision(document_id: str, source_entity_key: str, entity: dict) -> dict:
    now = now_iso()
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    decision_key = f'UPDATE_ENTITY_METADATA::{source_entity_key}'
    existing = decisions.get(decision_key, {})
    decision = {
        'decision_id': existing.get('decision_id') or str(uuid.uuid4()),
        'document_id': document_id,
        'decision_type': 'UPDATE_ENTITY_METADATA',
        'source_entity_key': source_entity_key,
        'payload': {
            'canonical_value': entity.get('canonical_value'),
            'entity_class': entity.get('entity_class'),
            'person_role': entity.get('person_role'),
            'context_label': entity.get('context_label'),
        },
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    decisions[decision_key] = decision
    return decision


def store_split_entity_metadata_decision(document_id: str, entity: dict) -> dict:
    split_origin = entity.get('split_origin') or {}
    split_key = split_origin.get('split_key')
    source_entity_key = split_origin.get('source_entity_key')
    locator = split_origin.get('mention_locator') or {}
    if not split_key or not source_entity_key or not locator:
        source_entity_key = source_entity_key or entity_semantic_key(entity)
        first_mention = next(iter(entity.get('mentions', []) or []), {})
        locator = locator or mention_locator_from_mention(first_mention)
        split_key = build_split_operation_key(source_entity_key, locator)
    now = now_iso()
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    decision_key = f'UPDATE_SPLIT_ENTITY_METADATA::{split_key}'
    existing = decisions.get(decision_key, {})
    decision = {
        'decision_id': existing.get('decision_id') or str(uuid.uuid4()),
        'document_id': document_id,
        'decision_type': 'UPDATE_SPLIT_ENTITY_METADATA',
        'split_key': split_key,
        'split_source_entity_key': source_entity_key,
        'mention_locator': {
            'surface_value': locator.get('surface_value'),
            'normalized_value': locator.get('normalized_value') or locator.get('surface_value'),
            'start': locator.get('start'),
            'end': locator.get('end'),
        },
        'payload': {
            'canonical_value': entity.get('canonical_value'),
            'entity_class': entity.get('entity_class'),
            'person_role': entity.get('person_role'),
            'context_label': entity.get('context_label'),
        },
        'entity_id': entity.get('entity_id'),
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    decisions[decision_key] = decision
    return decision

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
        def title(word: str) -> str:
            return word[:1].upper() + word[1:].lower() if word else word
        return f'{title(parts[0])} {title(parts[1])} {title(parts[2])}', {'surname': parts[0].lower(), 'initials': initials.lower(), 'is_short': False}
    return cleaned, {'surname': (parts[0].lower() if parts else cleaned.lower()), 'initials': '', 'is_short': False}


def detect_person_role(text: str, start: int, end: int) -> str:
    prefix = text[max(0, start - 120):start].lower()
    parts = re.split(r'[,.;\n]', prefix)
    local = parts[-1].strip() if parts else prefix.strip()
    role_patterns = [
        ('JUDGE', r'председательствующ\w*\s+суд\w*|\bсудья\b'),
        ('COURT_SECRETARY', r'при\s+секретар\w*'),
        ('WITNESS', r'\bсвидетел\w*\b'),
        ('PLAINTIFF', r'\bист(ец|цом|ца)\b|по\s+иску'),
        ('DEFENDANT', r'\bответчик\w*\b'),
        ('REPRESENTATIVE', r'\bпредставител\w*\b'),
        ('APPLICANT', r'\bзаявител\w*\b'),
        ('VICTIM', r'\bпотерпевш\w*\b'),
    ]
    best = ('UNKNOWN', -1)
    for role, pattern in role_patterns:
        for m in re.finditer(pattern, local):
            if m.end() > best[1]:
                best = (role, m.end())
    if best[0] != 'UNKNOWN':
        return best[0]
    if re.search(r'индивидуальным\s+предпринимателем\s*$', local):
        return 'INDIVIDUAL_ENTREPRENEUR'
    return 'UNKNOWN'


def decide_redaction(entity: dict, mode: str) -> tuple[str, str, bool]:
    etype = entity.get('entity_class')
    role = entity.get('person_role')
    ctx = entity.get('context_kind')
    if etype == 'PERSON':
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
            full_prefix = text[:item['start']].lower()
            ctx = re.split(r'[.;\n,]', full_prefix)[-1][-60:]
            if re.search(r'дата рождения|родил[а-я]+|года рождения', ctx):
                item['context_kind'] = 'BIRTH_DATE'
            elif re.search(r'решение от|постановление от|договор от|акт от|определение от|судебн\w+\s+заседан|дата договора|дата решения', ctx):
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






def _mention_payload(entity: dict, mention: dict) -> dict:
    return {
        'mention_id': mention['mention_id'],
        'entity_id': entity['entity_id'],
        'surface_value': mention['surface_value'],
        'normalized_value': mention.get('normalized_value'),
        'start': mention.get('start'),
        'end': mention.get('end'),
        'format': mention.get('format', 'FULL'),
        'grammatical_case': mention.get('grammatical_case', 'UNKNOWN'),
        'word_order': mention.get('word_order', 'UNKNOWN'),
        'replacement_value': mention.get('replacement_value', entity['placeholder']),
        'source': mention.get('source', entity.get('source', 'natasha')),
        'requires_review': mention.get('requires_review', False),
        'review_reason': mention.get('review_reason'),
    }


def build_entities_from_resolved(document_id: str, resolved: list[dict], mode: str = 'NORMATIVE') -> tuple[list[dict], list[dict], list[dict]]:
    entities=[]
    by_key={}
    person_full_keys_by_signature: dict[tuple[str, str], list[str]] = defaultdict(list)
    person_key_first_pos: dict[str, int] = {}

    redacted = [e for e in resolved if e.get('redaction_decision') == 'REDACT']
    person_full = [e for e in redacted if e.get('entity_class') == 'PERSON' and not (e.get('signature') or {}).get('is_short')]
    person_short = [e for e in redacted if e.get('entity_class') == 'PERSON' and (e.get('signature') or {}).get('is_short')]
    others = [e for e in redacted if e.get('entity_class') != 'PERSON']

    ordered = person_full + person_short + others
    for e in ordered:
        if e.get('redaction_decision')!='REDACT':
            continue
        cls=e.get('entity_class','OTHER')
        norm=e.get('normalized_value') or e.get('surface_value')
        key=f"{cls}::{norm.lower()}"
        sig=e.get('signature') or {}
        mention_format='FULL'
        if cls=='PERSON' and sig.get('is_short'):
            mention_format='INITIALS'
            signature_key = (sig.get('surname') or '', sig.get('initials') or '')
            full_candidates = person_full_keys_by_signature.get(signature_key, [])
            if len(full_candidates)==1:
                key=full_candidates[0]
            elif len(full_candidates)>1:
                key=f"{cls}::short-amb::{norm.lower()}::{e.get('start')}"
                e['requires_review']=True
                e['redaction_reason']='Сокращённое ФИО соответствует нескольким найденным лицам. Выберите связанную запись.'
                e['merge_candidate_keys'] = full_candidates
            else:
                key=f"{cls}::short-alone::{norm.lower()}::{e.get('start')}"
                e['requires_review']=False
                e['redaction_reason']=None
        ent=by_key.get(key)
        if not ent:
            ent={
                'entity_id': str(uuid.uuid4()),
                'document_id': document_id,
                'placeholder': '',
                'entity_class': cls,
                'canonical_value': norm,
                'normalized_value': norm,
                'person_role': e.get('person_role'),
                'redaction_decision': 'REDACT',
                'requires_review': e.get('requires_review', False),
                'review_reason': e.get('redaction_reason') if e.get('requires_review') else None,
                'source': e.get('source','natasha'),
                'created_at': now_iso(),
                'updated_at': now_iso(),
                'mentions': [],
                'signature': e.get('signature'),
                'is_short_person': bool(sig.get('is_short')),
            }
            by_key[key]=ent
            entities.append(ent)
            if cls == 'PERSON' and not ent.get('is_short_person'):
                sig_key = ((ent.get('signature') or {}).get('surname') or '', (ent.get('signature') or {}).get('initials') or '')
                person_full_keys_by_signature[sig_key].append(key)
            person_key_first_pos[key] = e.get('start') or 0
            audit_log.append({'action':'CREATE_REDACTION_ENTITY','document_id':document_id,'entity_id':ent['entity_id'],'entity_class':cls,'placeholder':ent['placeholder'],'mentions_count':0,'created_at':now_iso()})
        mention={
            'mention_id': str(uuid.uuid4()),
            'entity_id': ent['entity_id'],
            'surface_value': e.get('surface_value'),
            'normalized_value': e.get('normalized_value'),
            'start': e.get('start'),
            'end': e.get('end'),
            'format': mention_format,
            'grammatical_case': 'UNKNOWN',
            'word_order': 'UNKNOWN',
            'replacement_value': ent['placeholder'],
            'source': e.get('source','natasha'),
            'requires_review': e.get('requires_review',False),
            'review_reason': e.get('redaction_reason') if e.get('requires_review') else None,
        }
        if e.get('merge_candidates'):
            mention['merge_candidates'] = e.get('merge_candidates')
        if e.get('merge_candidate_keys'):
            mention['merge_candidate_keys'] = e.get('merge_candidate_keys')
        ent['mentions'].append(mention)
        person_key_first_pos[key] = min(person_key_first_pos.get(key, mention.get('start') or 0), mention.get('start') or 0)
        ent['requires_review']=ent['requires_review'] or mention['requires_review']
        if mention['review_reason']:
            ent['review_reason']=mention['review_reason']
        if mention.get('merge_candidates'):
            ent['merge_candidates'] = mention['merge_candidates']
        if mention.get('merge_candidate_keys'):
            ent['merge_candidate_keys'] = mention['merge_candidate_keys']
        audit_log.append({'action':'ADD_ENTITY_MENTION','document_id':document_id,'entity_id':ent['entity_id'],'entity_class':cls,'placeholder':ent['placeholder'],'mentions_count':len(ent['mentions']),'created_at':now_iso()})
    # stable placeholder numbering by first mention position
    per_class_counter: dict[str, int] = defaultdict(int)
    for ent in sorted(entities, key=lambda x: min((m.get('start') or 0) for m in x.get('mentions', []) or [0])):
        cls = ent.get('entity_class', 'OTHER')
        prefix = 'ФИО' if cls == 'PERSON' else make_placeholder(cls, 0)[:-1]
        per_class_counter[prefix] += 1
        ent['placeholder'] = f'{prefix}{per_class_counter[prefix]}'
        for m in ent.get('mentions', []):
            m['replacement_value'] = ent['placeholder']


    entity_by_key = {key: ent for key, ent in by_key.items()}
    for ent in entities:
        candidate_keys = ent.pop('merge_candidate_keys', None)
        if not candidate_keys:
            continue
        candidates = []
        for candidate_key in candidate_keys:
            candidate = entity_by_key.get(candidate_key)
            if not candidate:
                continue
            candidates.append({
                'entity_id': candidate.get('entity_id'),
                'placeholder': candidate.get('placeholder'),
                'canonical_value': candidate.get('canonical_value'),
                'normalized_value': candidate.get('normalized_value'),
                'entity_class': candidate.get('entity_class'),
            })
        ent['merge_candidates'] = candidates
        for mention in ent.get('mentions', []):
            if mention.pop('merge_candidate_keys', None) is not None or mention.get('requires_review'):
                mention['merge_candidates'] = candidates

    kept_by_key = {}
    for e in resolved:
        if e.get('redaction_decision') != 'KEEP':
            continue
        cls = e.get('entity_class', 'OTHER')
        normalized = e.get('normalized_value') or e.get('surface_value')
        role = e.get('person_role')
        key = f'{cls}::{normalized}::{role or ""}'
        ent = kept_by_key.get(key)
        if not ent:
            ent = {
                'entity_id': str(uuid.uuid4()),
                'document_id': document_id,
                'entity_class': cls,
                'canonical_value': normalized,
                'normalized_value': normalized,
                'person_role': role,
                'entity_key': build_entity_semantic_key(cls, normalized, role),
                'redaction_decision': 'KEEP',
                'requires_review': False,
                'source': e.get('source', 'natasha'),
                'mentions': [],
            }
            kept_by_key[key] = ent
        ent['mentions'].append({
            'mention_id': str(uuid.uuid4()),
            'entity_id': ent['entity_id'],
            'surface_value': e.get('surface_value'),
            'normalized_value': e.get('normalized_value'),
            'start': e.get('start'),
            'end': e.get('end'),
            'replacement_value': e.get('surface_value'),
        })
    kept = list(kept_by_key.values())
    for ent in kept:
        ent['mentions_count'] = len(ent.get('mentions', []))
    review=[]
    for ent in entities:
        if ent['requires_review']:
            review.append(ent)
    return entities, kept, review


def anonymize_text_by_mentions(text: str, entities: list[dict]) -> str:
    mentions=[]
    for ent in entities:
        if ent.get('redaction_decision')!='REDACT':
            continue
        mentions.extend(ent.get('mentions',[]))
    out=text
    for m in sorted([x for x in mentions if isinstance(x.get('start'), int) and isinstance(x.get('end'), int)], key=lambda x: x['start'], reverse=True):
        out=out[:m['start']] + (m.get('replacement_value') or '') + out[m['end']:]
    return out


def build_mappings_from_entities(entities: list[dict]) -> list[dict]:
    mappings = []
    for e in entities:
        if e.get('redaction_decision') != 'REDACT':
            continue
        mappings.append(ensure_mapping_metadata({
            'id': e['entity_id'],
            'placeholder': e.get('placeholder'),
            'original_value': e.get('canonical_value'),
            'normalized_value': e.get('normalized_value'),
            'entity_class': e.get('entity_class'),
            'entity_type': e.get('entity_class'),
            'aliases': [m.get('surface_value') for m in e.get('mentions', []) if m.get('surface_value') != e.get('canonical_value')],
        }))
    return mappings


def rebuild_document_from_entities(document_id: str, redacted_entities: list[dict], kept_entities: list[dict], original_text: str, original_content: dict | None):
    # stable placeholders by first mention position
    counters: dict[str, int] = defaultdict(int)
    entities = redacted_entities + kept_entities
    for e in sorted(redacted_entities, key=lambda x: min((m.get('start') or 0) for m in x.get('mentions', []) or [0])):
        prefix = 'ФИО' if e.get('entity_class') == 'PERSON' else make_placeholder(e.get('entity_class', 'OTHER'), 0)[:-1]
        counters[prefix] += 1
        e['placeholder'] = f'{prefix}{counters[prefix]}'
        for m in e.get('mentions', []):
            m['replacement_value'] = e['placeholder']
    anonymized_text = anonymize_text_by_mentions(original_text, entities)
    anonymized_content = anonymize_content_by_mentions(original_content, entities)
    mappings = build_mappings_from_entities(redacted_entities)
    review_entities = [e for e in redacted_entities if e.get('requires_review')]
    pending_entities = restored_docs.get(document_id, {}).get('pending_review', [])
    doc = restored_docs.get(document_id, {})
    doc.update({
        'entities': redacted_entities,
        'anonymized_text': anonymized_text,
        'anonymized_content': anonymized_content,
        'mappings': mappings,
        'kept_entities': kept_entities,
        'recognized_but_kept': kept_entities,
        'review_entities': review_entities,
        'pending_entities': pending_entities,
    })
    restored_docs[document_id] = doc
    if document_id in public_docs:
        public_docs[document_id]['anonymized_text'] = anonymized_text
        public_docs[document_id]['anonymized_content'] = anonymized_content
        public_docs[document_id]['content_format'] = doc.get('content_format', 'PLAIN_TEXT')
    return doc



TEXT_BLOCK_TYPES = {'paragraph', 'heading'}


def _tiptap_text_node_segments(node: dict, path: tuple[int, ...], block_index: int, block_start: int) -> tuple[str, list[dict]]:
    text_parts: list[str] = []
    segments: list[dict] = []

    def walk(current, current_path: tuple[int, ...]):
        if isinstance(current, dict):
            if current.get('type') == 'text' and isinstance(current.get('text'), str):
                text = current.get('text') or ''
                local_start = sum(len(part) for part in text_parts)
                text_parts.append(text)
                segments.append({
                    'path': current_path,
                    'block_index': block_index,
                    'text': text,
                    'global_start': block_start + local_start,
                    'global_end': block_start + local_start + len(text),
                    'marks': copy.deepcopy(current.get('marks', [])),
                })
                return
            if isinstance(current.get('content'), list):
                for idx, child in enumerate(current['content']):
                    walk(child, current_path + (idx,))
        elif isinstance(current, list):
            for idx, child in enumerate(current):
                walk(child, current_path + (idx,))

    walk(node, path)
    return ''.join(text_parts), segments


def _tiptap_text_blocks(content: dict | None) -> list[dict]:
    blocks: list[dict] = []
    canonical_offset = 0

    def walk(node, path: tuple[int, ...]):
        nonlocal canonical_offset
        if isinstance(node, dict):
            if node.get('type') in TEXT_BLOCK_TYPES:
                block_index = len(blocks)
                block_start = canonical_offset + (1 if block_index > 0 else 0)
                block_text, segments = _tiptap_text_node_segments(node, path, block_index, block_start)
                for segment in segments:
                    segment['block_start'] = block_start
                    segment['block_end'] = block_start + len(block_text)
                blocks.append({
                    'path': path,
                    'type': node.get('type'),
                    'block_index': block_index,
                    'text': block_text,
                    'global_start': block_start,
                    'global_end': block_start + len(block_text),
                    'segments': segments,
                })
                canonical_offset = block_start + len(block_text)
                return
            if isinstance(node.get('content'), list):
                for idx, child in enumerate(node['content']):
                    walk(child, path + (idx,))
        elif isinstance(node, list):
            for idx, child in enumerate(node):
                walk(child, path + (idx,))

    walk(content, ())
    return blocks


def flatten_tiptap_text_segments(content: dict | None) -> list[dict]:
    segments: list[dict] = []
    for block in _tiptap_text_blocks(content):
        segments.extend(copy.deepcopy(block['segments']))
    return segments


def content_plain_text(content: dict | None) -> str:
    return '\n'.join(block['text'] for block in _tiptap_text_blocks(content))


def canonical_text_for_content(text: str | None, content: dict | None, content_format: str | None) -> str:
    if content_format == 'TIPTAP_JSON' and content:
        return content_plain_text(content)
    return text or ''


def _get_node_by_path(data: dict, path: tuple[int, ...]) -> dict:
    node = data
    for index in path:
        node = node['content'][index]
    return node


def _redaction_mark(entity_id: str, mention_id: str, placeholder: str) -> dict:
    return {'type': 'redactionMention', 'attrs': {'entityId': entity_id, 'mentionId': mention_id, 'placeholder': placeholder}}


def anonymize_content_by_mentions(content: dict | None, entities: list[dict]) -> dict | None:
    if not content:
        return None
    data = copy.deepcopy(content)
    segments = flatten_tiptap_text_segments(content)
    mentions = []
    for ent in entities:
        if ent.get('redaction_decision') != 'REDACT':
            continue
        for m in ent.get('mentions', []):
            if isinstance(m.get('start'), int) and isinstance(m.get('end'), int):
                mentions.append({
                    'start': m['start'],
                    'end': m['end'],
                    'entity_id': ent['entity_id'],
                    'mention_id': m['mention_id'],
                    'placeholder': m.get('replacement_value') or ent.get('placeholder') or '',
                    'surface_value': m.get('surface_value'),
                })
    replacements_by_path: dict[tuple[int, ...], list[dict]] = defaultdict(list)
    for mention in sorted(mentions, key=lambda item: item['start']):
        containing = [
            segment for segment in segments
            if segment['global_start'] <= mention['start'] and mention['end'] <= segment['global_end']
        ]
        if len(containing) != 1:
            _error(
                409,
                'CROSS_TEXT_NODE_MENTION_UNSUPPORTED',
                'Упоминание пересекает несколько text-node TipTap и не может быть безопасно заменено автоматически',
                {
                    'mention_id': mention.get('mention_id'),
                    'entity_id': mention.get('entity_id'),
                    'start': mention.get('start'),
                    'end': mention.get('end'),
                    'surface_value': mention.get('surface_value'),
                },
            )
        segment = containing[0]
        rel_start = mention['start'] - segment['global_start']
        rel_end = mention['end'] - segment['global_start']
        replacements_by_path[tuple(segment['path'])].append({**mention, 'rel_start': rel_start, 'rel_end': rel_end})

    for path, replacements in replacements_by_path.items():
        replacements.sort(key=lambda item: item['rel_start'])
        cursor = 0
        for replacement in replacements:
            if replacement['rel_start'] < cursor:
                _error(
                    409,
                    'OVERLAPPING_MENTIONS_UNSUPPORTED',
                    'Пересекающиеся упоминания не могут быть безопасно заменены автоматически',
                    {'mention_id': replacement.get('mention_id')},
                )
            cursor = replacement['rel_end']

    for path in sorted(replacements_by_path.keys(), key=lambda p: p, reverse=True):
        parent = _get_node_by_path(data, path[:-1]) if path else data
        original_node = parent['content'][path[-1]] if path else parent
        text = original_node.get('text') or ''
        marks = copy.deepcopy(original_node.get('marks', []))
        new_nodes: list[dict] = []
        cursor = 0
        for replacement in replacements_by_path[path]:
            rel_start = replacement['rel_start']
            rel_end = replacement['rel_end']
            if rel_start > cursor:
                node = {'type': 'text', 'text': text[cursor:rel_start]}
                if marks:
                    node['marks'] = copy.deepcopy(marks)
                new_nodes.append(node)
            placeholder_node = {'type': 'text', 'text': replacement['placeholder']}
            placeholder_marks = copy.deepcopy(marks) + [_redaction_mark(replacement['entity_id'], replacement['mention_id'], replacement['placeholder'])]
            if placeholder_marks:
                placeholder_node['marks'] = placeholder_marks
            new_nodes.append(placeholder_node)
            cursor = rel_end
        if cursor < len(text):
            node = {'type': 'text', 'text': text[cursor:]}
            if marks:
                node['marks'] = copy.deepcopy(marks)
            new_nodes.append(node)
        if path:
            parent['content'][path[-1]:path[-1] + 1] = new_nodes
        else:
            data = new_nodes[0] if len(new_nodes) == 1 else {'type': 'doc', 'content': new_nodes}
    return data

def restore_content_from_mentions(anonymized_content: dict | None, entities: list[dict]) -> dict | None:
    if not anonymized_content:
        return None
    data = copy.deepcopy(anonymized_content)
    mention_by_id: dict[str, dict] = {}
    for e in entities:
        for m in e.get('mentions', []):
            mention_by_id[m.get('mention_id')] = m

    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                redaction_mark = next((m for m in node['marks'] if m.get('type') == 'redactionMention'), None)
                if redaction_mark:
                    mention_id = (redaction_mark.get('attrs') or {}).get('mentionId')
                    mention = mention_by_id.get(mention_id)
                    if mention:
                        node['text'] = mention.get('surface_value', node.get('text', ''))
                    node['marks'] = [m for m in node['marks'] if m.get('type') != 'redactionMention']
                    if not node['marks']:
                        node.pop('marks', None)
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
                merged = []
                for ch in node['content']:
                    if (
                        merged
                        and isinstance(ch, dict)
                        and isinstance(merged[-1], dict)
                        and ch.get('type') == 'text'
                        and merged[-1].get('type') == 'text'
                        and ch.get('marks', []) == merged[-1].get('marks', [])
                    ):
                        merged[-1]['text'] = (merged[-1].get('text') or '') + (ch.get('text') or '')
                    else:
                        merged.append(ch)
                node['content'] = merged
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data


def has_working_revision(doc: dict) -> bool:
    return doc.get('working_text') is not None or doc.get('working_content') is not None


def sync_public_document(document_id: str, doc: dict) -> None:
    if document_id in public_docs:
        public_docs[document_id]['anonymized_text'] = doc.get('anonymized_text', '')
        public_docs[document_id]['anonymized_content'] = doc.get('anonymized_content')
        public_docs[document_id]['content_format'] = doc.get('content_format', 'PLAIN_TEXT')


def audit_mapping_action(document_id: str, action: str, details: dict | None = None) -> None:
    audit_log.append({'id': str(uuid.uuid4()), 'document_id': document_id, 'action': action, 'created_at': now_iso(), 'details': details or {}})


def apply_entity_metadata_update(document_id: str, doc: dict, ent: dict, payload: dict) -> dict:
    source_entity_key = entity_semantic_key(ent)
    for key in ('canonical_value', 'person_role', 'context_label'):
        if key in payload:
            ent[key] = payload[key]
    if 'entity_class' in payload:
        ent['entity_class'] = payload['entity_class']
    ent['updated_at'] = now_iso()
    if ent.get('split_origin'):
        store_split_entity_metadata_decision(document_id, ent)
    else:
        store_entity_metadata_decision(document_id, source_entity_key, ent)
    if has_working_revision(doc):
        doc['mappings'] = build_mappings_from_entities(doc.get('entities', []))
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
        if doc.get('working_text') is not None:
            doc['anonymized_text'] = doc.get('working_text', '')
        if doc.get('working_content') is not None:
            doc['anonymized_content'] = doc.get('working_content')
    else:
        rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    sync_public_document(document_id, doc)
    return doc


def restore_entity_in_working_content(content: dict, entity: dict) -> tuple[dict, set[str]]:
    data = copy.deepcopy(content)
    mentions = {m.get('mention_id'): m for m in entity.get('mentions', []) if m.get('mention_id')}
    restored: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                new_marks = []
                replaced = False
                for mark in node['marks']:
                    if mark.get('type') == 'redactionMention':
                        attrs = mark.get('attrs') or {}
                        mention_id = attrs.get('mentionId')
                        if mention_id in mentions:
                            if not replaced:
                                node['text'] = mentions[mention_id].get('surface_value', node.get('text', ''))
                                replaced = True
                            restored.add(mention_id)
                            continue
                    new_marks.append(mark)
                node['marks'] = new_marks
                if not node['marks']:
                    node.pop('marks', None)
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data, restored



def keep_redacted_entity_in_document(document_id: str, doc: dict, target_entity: dict, *, reason: str = 'Оставлено пользователем', explicit_entity_key: str | None = None) -> None:
    entity_id = target_entity.get('entity_id')
    entity_key = explicit_entity_key or target_entity.get('entity_key') or entity_semantic_key(target_entity)
    working = has_working_revision(doc)
    updated_content = None
    updated_text = None

    if working and doc.get('working_content') is not None:
        updated_content, restored_mentions = restore_entity_in_working_content(doc.get('working_content'), target_entity)
        expected_mentions = {m.get('mention_id') for m in target_entity.get('mentions', []) if m.get('mention_id')}
        missing = sorted(expected_mentions - restored_mentions)
        if missing:
            _error(409, 'KEEP_ENTITY_MARK_NOT_FOUND', 'Разметка одного или нескольких упоминаний не найдена', {'missing_mention_ids': missing})
        updated_text = content_plain_text(updated_content)
    elif working:
        surface_values = sorted({m.get('surface_value') for m in target_entity.get('mentions', []) if m.get('surface_value')})
        if len(surface_values) > 1:
            _error(409, 'KEEP_REQUIRES_STRUCTURED_CONTENT', 'Невозможно восстановить разные варианты написания без разметки документа', {'entity_id': entity_id, 'placeholder': target_entity.get('placeholder'), 'surface_values': surface_values})
        replacement = surface_values[0] if surface_values else (target_entity.get('canonical_value') or '')
        updated_text = replace_placeholder_boundary(doc.get('working_text') or '', target_entity.get('placeholder') or '', replacement)

    store_keep_redact_decision(document_id, 'KEEP_ENTITY', target_entity, reason=reason, explicit_entity_key=entity_key)
    redacted = []
    kept = [
        e for e in doc.get('kept_entities', [])
        if e.get('entity_id') != entity_id and e.get('entity_key') != entity_key and entity_semantic_key(e) != entity_key
    ]
    for entity in doc.get('entities', []):
        if entity.get('entity_id') == entity_id:
            entity['redaction_decision'] = 'KEEP'
            entity['requires_review'] = False
            entity['entity_key'] = entity_key
            kept.append(entity)
        else:
            redacted.append(entity)

    if working and doc.get('working_content') is not None:
        doc['entities'] = redacted
        doc['kept_entities'] = kept
        doc['recognized_but_kept'] = kept
        doc['working_content'] = updated_content
        doc['anonymized_content'] = updated_content
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        doc['mappings'] = build_mappings_from_entities(redacted)
        doc['review_entities'] = [e for e in redacted if e.get('requires_review')]
    elif working:
        doc['entities'] = redacted
        doc['kept_entities'] = kept
        doc['recognized_but_kept'] = kept
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        doc['mappings'] = build_mappings_from_entities(redacted)
        doc['review_entities'] = [e for e in redacted if e.get('requires_review')]
    else:
        rebuild_document_from_entities(document_id, redacted, kept, doc.get('original_text', ''), doc.get('original_content'))

def replace_placeholder_boundary(text: str, placeholder: str, value: str) -> str:
    return re.sub(rf'(?<!\w){re.escape(placeholder)}(?!\w)', value, text)


def assign_unique_placeholders_for_entities(entities: list[dict]) -> dict[str, str]:
    counters: dict[str, int] = defaultdict(int)
    desired: dict[str, str] = {}
    def first_pos(entity: dict) -> int:
        positions = [m.get('start') for m in entity.get('mentions', []) if isinstance(m.get('start'), int)]
        return min(positions) if positions else 0
    for entity in sorted(entities, key=first_pos):
        entity_class = entity.get('entity_class') or entity.get('entity_type') or 'OTHER'
        prefix = 'ФИО' if entity_class == 'PERSON' else make_placeholder(entity_class, 0)[:-1]
        counters[prefix] += 1
        desired[entity.get('entity_id')] = f'{prefix}{counters[prefix]}'
    return desired


def update_working_content_placeholders(content: dict, entity_placeholders: dict[str, str]) -> tuple[dict, set[str]]:
    data = copy.deepcopy(content)
    updated_mentions: set[str] = set()
    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                for mark in node['marks']:
                    if mark.get('type') != 'redactionMention':
                        continue
                    attrs = mark.setdefault('attrs', {})
                    entity_id = attrs.get('entityId')
                    mention_id = attrs.get('mentionId')
                    if entity_id in entity_placeholders and mention_id:
                        placeholder = entity_placeholders[entity_id]
                        node['text'] = placeholder
                        attrs['placeholder'] = placeholder
                        attrs['entityId'] = entity_id
                        attrs['mentionId'] = mention_id
                        updated_mentions.add(mention_id)
                        break
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data, updated_mentions


def find_open_value_positions(text: str, value: str) -> list[int]:
    return [m.start() for m in re.finditer(re.escape(value), text or '')]


def entity_response_items(entities: list[dict]) -> list[dict]:
    return [
        {**entity, 'entity_key': entity.get('entity_key') or entity_semantic_key(entity)}
        for entity in entities
    ]


def mention_locator_from_mention(mention: dict) -> dict:
    return {
        'surface_value': mention.get('surface_value'),
        'normalized_value': mention.get('normalized_value') or mention.get('surface_value'),
        'start': mention.get('start'),
        'end': mention.get('end'),
    }


def store_split_mention_decision(document_id: str, source_entity_key: str, source_entity_id: str, mention: dict, target_entity_id: str) -> dict:
    now = now_iso()
    locator = mention_locator_from_mention(mention)
    decision_key = build_split_operation_key(source_entity_key, locator)
    decisions = manual_decisions_by_document_id.setdefault(document_id, {})
    existing = decisions.get(decision_key, {})
    decision = {
        'decision_id': existing.get('decision_id') or str(uuid.uuid4()),
        'document_id': document_id,
        'decision_type': 'SPLIT_MENTION',
        'source_entity_key': source_entity_key,
        'mention_locator': locator,
        'entity_id': source_entity_id,
        'mention_id': mention.get('mention_id'),
        'target_entity_id': target_entity_id,
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    decisions[decision_key] = decision
    return decision


def split_entity_mention_in_state(document_id: str, entities: list[dict], source_entity: dict, mention: dict, source_entity_key: str | None = None) -> tuple[list[dict], dict]:
    original_placeholder = source_entity.get('placeholder')
    remaining_mentions = [m for m in source_entity.get('mentions', []) if m.get('mention_id') != mention.get('mention_id')]
    split_singleton = not remaining_mentions
    new_entity = copy.deepcopy(source_entity)
    new_entity['entity_id'] = str(uuid.uuid4())
    new_entity['document_id'] = document_id
    new_entity['redaction_decision'] = 'REDACT'
    new_entity['placeholder'] = (
        original_placeholder
        if split_singleton
        else next_placeholder(source_entity.get('entity_class', 'PERSON'), [{'placeholder': e.get('placeholder')} for e in entities])
    )
    moved_mention = copy.deepcopy(mention)
    moved_mention['entity_id'] = new_entity['entity_id']
    moved_mention['replacement_value'] = new_entity['placeholder']
    new_entity['mentions'] = [moved_mention]
    new_entity['mentions_count'] = 1
    new_entity['created_at'] = now_iso()
    new_entity['updated_at'] = now_iso()
    split_source_key = source_entity_key or entity_semantic_key(source_entity)
    new_entity['split_origin'] = build_split_origin(split_source_key, mention_locator_from_mention(mention))

    if split_singleton:
        updated_entities = [e for e in entities if e is not source_entity and e.get('entity_id') != source_entity.get('entity_id')]
    else:
        source_entity['mentions'] = remaining_mentions
        source_entity['mentions_count'] = len(remaining_mentions)
        source_entity['updated_at'] = now_iso()
        updated_entities = entities
    updated_entities.append(new_entity)
    return updated_entities, new_entity

def has_redaction_mention_mark(content: dict | None, mention_id: str) -> bool:
    if not content:
        return False

    found = False

    def walk(node):
        nonlocal found

        if found:
            return

        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                for mark in node['marks']:
                    if mark.get('type') != 'redactionMention':
                        continue

                    attrs = mark.get('attrs') or {}
                    if attrs.get('mentionId') == mention_id:
                        found = True
                        return

            if isinstance(node.get('content'), list):
                for child in node['content']:
                    walk(child)

        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(content)
    return found

def update_working_content_for_split(content: dict, mention_id: str, new_entity: dict) -> tuple[dict, bool]:
    data = copy.deepcopy(content)
    updated = False

    def walk(node):
        nonlocal updated
        if isinstance(node, dict):
            if node.get('type') == 'text' and isinstance(node.get('marks'), list):
                for mark in node['marks']:
                    if mark.get('type') != 'redactionMention':
                        continue
                    attrs = mark.setdefault('attrs', {})
                    if attrs.get('mentionId') == mention_id:
                        node['text'] = new_entity.get('placeholder', node.get('text', ''))
                        attrs['entityId'] = new_entity.get('entity_id')
                        attrs['placeholder'] = new_entity.get('placeholder')
                        attrs['mentionId'] = mention_id
                        updated = True
                        break
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)

    walk(data)
    return data, updated


def split_mention_locator_matches(mention: dict, locator: dict) -> bool:
    return (
        mention.get('start') == locator.get('start')
        and mention.get('end') == locator.get('end')
        and mention.get('surface_value') == locator.get('surface_value')
    )


def apply_split_mention_decisions(document_id: str, redacted_entities: list[dict]) -> list[dict]:
    decisions = [d for d in manual_decisions_by_document_id.get(document_id, {}).values() if d.get('decision_type') == 'SPLIT_MENTION']
    entities = redacted_entities
    for decision in decisions:
        source_entity_key = decision.get('source_entity_key')
        locator = decision.get('mention_locator') or {}
        if not source_entity_key or not locator:
            continue
        source_entity = _find_entity_by_semantic_key(entities, source_entity_key)
        if not source_entity:
            continue
        mention = next((m for m in source_entity.get('mentions', []) if split_mention_locator_matches(m, locator)), None)
        if not mention:
            continue
        entities, _new_entity = split_entity_mention_in_state(document_id, entities, source_entity, mention, source_entity_key)
    return entities



def _entities_by_semantic_key(entities: list[dict], entity_key: str) -> list[dict]:
    return [entity for entity in entities if entity.get('entity_key') == entity_key or entity_semantic_key(entity) == entity_key]


def apply_merge_entity_decisions(document_id: str, redacted_entities: list[dict]) -> list[dict]:
    decisions = [
        decision
        for decision in manual_decisions_by_document_id.get(document_id, {}).values()
        if decision.get('decision_type') == 'MERGE_ENTITIES'
    ]
    entities = redacted_entities
    for decision in decisions:
        target_key = decision.get('target_entity_key')
        source_keys = decision.get('source_entity_keys') or []
        if not target_key or not source_keys:
            continue
        target_matches = _entities_by_semantic_key(entities, target_key)
        if len(target_matches) != 1:
            continue
        sources = []
        ambiguous = False
        for source_key in source_keys:
            source_matches = [
                entity
                for entity in _entities_by_semantic_key(entities, source_key)
                if entity.get('entity_id') != target_matches[0].get('entity_id')
            ]
            if len(source_matches) != 1:
                ambiguous = True
                break
            sources.append(source_matches[0])
        if ambiguous:
            continue
        entities = merge_entities_in_state(entities, target_matches[0], sources)
    return entities


def _validate_merge_semantic_keys_are_replayable(entities: list[dict], target: dict, sources: list[dict]):
    target_key = entity_semantic_key(target)
    source_keys = [entity_semantic_key(source) for source in sources]
    if target_key in source_keys or len(source_keys) != len(set(source_keys)):
        _error(
            409,
            'MERGE_REQUIRES_DISTINCT_ENTITY_KEYS',
            'Невозможно устойчиво сохранить объединение сущностей с одинаковыми идентификаторами',
        )
    for key in [target_key, *source_keys]:
        if len(_entities_by_semantic_key(entities, key)) != 1:
            _error(
                409,
                'MERGE_REQUIRES_DISTINCT_ENTITY_KEYS',
                'Невозможно устойчиво сохранить объединение сущностей с одинаковыми идентификаторами',
            )

def apply_manual_decisions(document_id: str, resolved: list[dict]) -> list[dict]:
    decisions = manual_decisions_by_document_id.get(document_id, {})
    for e in resolved:
        key = build_entity_semantic_key(e.get('entity_class', 'OTHER'), e.get('normalized_value') or e.get('surface_value'), e.get('person_role'))
        d = decisions.get(key)
        if not d:
            continue
        if d.get('decision_type') == 'KEEP_ENTITY':
            e['redaction_decision'] = 'KEEP'
            e['requires_review'] = False
            e['redaction_reason'] = 'Оставлено пользователем'
        elif d.get('decision_type') == 'REDACT_ENTITY':
            e['redaction_decision'] = 'REDACT'
            e['redaction_reason'] = 'Обезличено пользователем'
            e['requires_review'] = False
    return resolved




def _find_entity_by_semantic_key(entities: list[dict], entity_key: str) -> dict | None:
    return next((e for e in entities if e.get('entity_key') == entity_key or entity_semantic_key(e) == entity_key), None)


def apply_split_entity_metadata_decisions(document_id: str, redacted_entities: list[dict]) -> list[dict]:
    decisions = [d for d in manual_decisions_by_document_id.get(document_id, {}).values() if d.get('decision_type') == 'UPDATE_SPLIT_ENTITY_METADATA']
    by_split_key = {
        (entity.get('split_origin') or {}).get('split_key'): entity
        for entity in redacted_entities
        if (entity.get('split_origin') or {}).get('split_key')
    }
    for decision in decisions:
        split_key = decision.get('split_key')
        if not split_key:
            continue
        ent = by_split_key.get(split_key)
        if not ent:
            continue
        payload = decision.get('payload') or {}
        for field in ('canonical_value', 'entity_class', 'person_role', 'context_label'):
            if field in payload:
                ent[field] = payload.get(field)
        ent['updated_at'] = now_iso()
    return redacted_entities


def apply_entity_metadata_decisions(document_id: str, redacted_entities: list[dict], kept_entities: list[dict]) -> tuple[list[dict], list[dict]]:
    decisions = [d for d in manual_decisions_by_document_id.get(document_id, {}).values() if d.get('decision_type') == 'UPDATE_ENTITY_METADATA']
    by_key = {entity_semantic_key(e): e for e in [*redacted_entities, *kept_entities]}
    for d in decisions:
        source_entity_key = d.get('source_entity_key')
        if not source_entity_key:
            continue
        ent = by_key.get(source_entity_key)
        if not ent:
            continue
        payload = d.get('payload') or {}
        for field in ('canonical_value', 'entity_class', 'person_role', 'context_label'):
            if field in payload:
                ent[field] = payload.get(field)
        ent['updated_at'] = now_iso()
    return redacted_entities, kept_entities


def apply_keep_redact_entity_decisions(document_id: str, redacted_entities: list[dict], kept_entities: list[dict], original_text: str) -> tuple[list[dict], list[dict]]:
    decisions = [d for d in manual_decisions_by_document_id.get(document_id, {}).values() if d.get('decision_type') in {'KEEP_ENTITY', 'REDACT_ENTITY'}]
    redacted = list(redacted_entities)
    kept = list(kept_entities)

    for d in decisions:
        entity_key = d.get('entity_key')
        if not entity_key:
            continue
        if d.get('decision_type') == 'KEEP_ENTITY':
            ent = _find_entity_by_semantic_key(redacted, entity_key)
            if ent:
                redacted.remove(ent)
                ent['redaction_decision'] = 'KEEP'
                ent['requires_review'] = False
                kept = [e for e in kept if e.get('entity_id') != ent.get('entity_id') and entity_semantic_key(e) != entity_key]
                kept.append(ent)
        elif d.get('decision_type') == 'REDACT_ENTITY':
            ent = _find_entity_by_semantic_key(kept, entity_key)
            if ent:
                kept.remove(ent)
                ent['redaction_decision'] = 'REDACT'
                ent['requires_review'] = False
                redacted = [e for e in redacted if e.get('entity_id') != ent.get('entity_id') and entity_semantic_key(e) != entity_key]
                redacted.append(ent)
            elif not _find_entity_by_semantic_key(redacted, entity_key):
                value = d.get('canonical_value') or ''
                if value:
                    positions = [m.start() for m in re.finditer(re.escape(value), original_text)]
                    if positions:
                        entity_class = d.get('entity_class') or 'OTHER'
                        ent = {
                            'entity_id': str(uuid.uuid4()),
                            'document_id': document_id,
                            'entity_class': entity_class,
                            'canonical_value': value,
                            'normalized_value': value,
                            'redaction_decision': 'REDACT',
                            'requires_review': False,
                            'mentions': [],
                        }
                        for pos in positions:
                            ent['mentions'].append({
                                'mention_id': str(uuid.uuid4()),
                                'entity_id': ent['entity_id'],
                                'surface_value': value,
                                'normalized_value': value,
                                'start': pos,
                                'end': pos + len(value),
                                'replacement_value': '',
                            })
                        ent['mentions_count'] = len(ent['mentions'])
                        redacted.append(ent)
    return redacted, kept

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


def save_document(document_id: str, case_id: str, title: str, original_text: str, anonymized_text: str, mappings: list[dict], metadata: dict | None = None, recognized_but_kept: list[dict] | None = None, anonymized_content: dict | None = None, entities: list[dict] | None = None, kept_entities: list[dict] | None = None, review_entities: list[dict] | None = None):
    existing = restored_docs.get(document_id, {})
    public_docs[document_id] = {
        'document_id': document_id,
        'case_id': case_id,
        'title': title,
        'anonymized_text': anonymized_text,
        'recognized_but_kept': recognized_but_kept or [],
        'anonymized_content': anonymized_content,
        'content_format': existing.get('content_format', 'PLAIN_TEXT'),
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
        'entities': entities or existing.get('entities', []),
        'kept_entities': kept_entities or existing.get('kept_entities', []),
        'content_format': existing.get('content_format', 'PLAIN_TEXT'),
        'original_content': existing.get('original_content'),
        'anonymized_content': anonymized_content if anonymized_content is not None else existing.get('anonymized_content'),
        'review_entities': review_entities or existing.get('review_entities', []),
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
        'entities': document.get('entities', []),
        'mappings': document.get('mappings', []),
        'kept_entities': entity_response_items(document.get('kept_entities', document.get('recognized_but_kept', []))),
        'recognized_but_kept': entity_response_items(document.get('recognized_but_kept', [])),
        'review_entities': entity_response_items(document.get('review_entities', [])),
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

    original_text = canonical_text_for_content(body.text, body.original_content, body.content_format)
    entities = await extract_entities(original_text)

    resolved = resolve_entities(original_text, entities, body.publication_redaction_mode)
    entities, recognized_but_kept, review_entities = build_entities_from_resolved(body.document_id, resolved, body.publication_redaction_mode)
    rebuilt = rebuild_document_from_entities(body.document_id, entities, recognized_but_kept, original_text, body.original_content)
    mappings = rebuilt.get('mappings', [])
    anonymized = rebuilt.get('anonymized_text', '')
    save_document(
        body.document_id, body.case_id, body.title, original_text, anonymized, mappings,
        body.metadata, recognized_but_kept, rebuilt.get('anonymized_content'), rebuilt.get('entities'),
        rebuilt.get('kept_entities'), review_entities
    )
    jobs[job_id]['status'] = 'COMPLETED'
    restored_docs[body.document_id]['entities']=entities
    restored_docs[body.document_id]['review_entities']=review_entities
    restored_docs[body.document_id]['publication_redaction_mode']=body.publication_redaction_mode
    restored_docs[body.document_id]['content_format']=body.content_format
    restored_docs[body.document_id]['original_content']=body.original_content
    restored_docs[body.document_id]['anonymized_content'] = rebuilt.get('anonymized_content')
    restored_docs[body.document_id]['pending_review'] = []
    restored_docs[body.document_id]['pending_markers'] = []
    return {
        'job_id': job_id,
        'status': 'COMPLETED',
        'anonymized_document_id': body.document_id,
        'anonymized_text': anonymized,
        'anonymized_content': restored_docs[body.document_id].get('anonymized_content'),
        'content_format': body.content_format,
        'entities': entities,
        'kept_entities': recognized_but_kept,
        'review_entities': review_entities,
        'mappings': mappings,
        'recognized_but_kept': recognized_but_kept,
        'review_markers': [],
        'pending_review': [],
        'pending_markers': [],
        'manual_decisions': list(manual_decisions_by_document_id.get(body.document_id, {}).values()),
        'publication_redaction_mode': body.publication_redaction_mode,
        'ner_provider': 'hybrid',
    }


@app.get('/internal/anonymization/documents/{document_id}/public')
def public(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in public_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    payload = copy.deepcopy(public_docs[document_id])
    def strip_marks(node):
        if isinstance(node, dict):
            for key in ['entityId', 'mentionId', 'split_origin', 'manual_decision', 'manual_decisions']:
                node.pop(key, None)
            if isinstance(node.get('attrs'), dict):
                for key in ['entityId', 'mentionId', 'split_origin', 'manual_decision', 'manual_decisions']:
                    node['attrs'].pop(key, None)
            if isinstance(node.get('marks'), list):
                clean_marks = []
                for mark in node['marks']:
                    if mark.get('type') == 'redactionMention':
                        continue
                    if isinstance(mark.get('attrs'), dict):
                        for key in ['entityId', 'mentionId', 'split_origin', 'manual_decision', 'manual_decisions']:
                            mark['attrs'].pop(key, None)
                    clean_marks.append(mark)
                node['marks'] = clean_marks
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    strip_marks(ch)
        elif isinstance(node, list):
            for ch in node:
                strip_marks(ch)
    strip_marks(payload.get('anonymized_content'))
    return payload


@app.get('/internal/anonymization/documents/{document_id}/restored')
def restored(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = copy.deepcopy(restored_docs[document_id])
    restored_content = restore_content_from_mentions(doc.get('anonymized_content'), doc.get('entities', []))
    if restored_content is not None:
        doc['restored_content'] = restored_content
        doc['restored_text'] = content_plain_text(restored_content)
    return doc


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
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')

    validate_non_empty(body.original_value, 'original_value')
    validate_non_empty(body.entity_type, 'entity_type')
    entity_class = 'PERSON' if body.entity_type in {'PERSON_FULL_NAME', 'PERSON'} else body.entity_type
    working = has_working_revision(doc)
    search_text = (content_plain_text(doc.get('working_content')) if doc.get('working_content') is not None else doc.get('working_text', '')) if working else doc.get('original_text', '')
    positions = find_open_value_positions(search_text or '', body.original_value)
    if working and not positions:
        _error(400, 'VALUE_NOT_FOUND_IN_WORKING_DOCUMENT', 'Выбранное значение отсутствует в текущей версии документа')
    if not positions:
        return anonymization_result_response(doc)

    before_doc = copy.deepcopy(doc)
    before_decisions = copy.deepcopy(manual_decisions_by_document_id.get(document_id, {}))
    try:
        if body.mode == 'existing':
            target_ref = body.entity_id or body.placeholder
            target = next((e for e in doc.get('entities', []) if e.get('entity_id') == target_ref or e.get('placeholder') == target_ref), None)
            if not target:
                _error(400, 'BAD_REQUEST', 'Целевая сущность не найдена')
        else:
            target = next((e for e in doc.get('entities', []) if e.get('entity_class') == entity_class and (e.get('canonical_value') == body.original_value or e.get('normalized_value') == body.original_value)), None)
            if not target:
                target = {
                    'entity_id': str(uuid.uuid4()),
                    'document_id': document_id,
                    'entity_class': entity_class,
                    'canonical_value': body.original_value,
                    'normalized_value': body.original_value,
                    'redaction_decision': 'REDACT',
                    'placeholder': next_placeholder(entity_class, build_mappings_from_entities(doc.get('entities', []))),
                    'mentions': [],
                }
                doc.setdefault('entities', []).append(target)
        target['placeholder'] = target.get('placeholder') or next_placeholder(target.get('entity_class', entity_class), build_mappings_from_entities(doc.get('entities', [])))

        existing_ranges = {(m.get('start'), m.get('end')) for m in target.get('mentions', [])}
        new_mentions = []
        for pos in positions:
            rng = (pos, pos + len(body.original_value))
            if rng in existing_ranges:
                continue
            mention = {
                'mention_id': str(uuid.uuid4()),
                'entity_id': target['entity_id'],
                'surface_value': body.original_value,
                'normalized_value': body.original_value,
                'start': pos,
                'end': pos + len(body.original_value),
                'replacement_value': target.get('placeholder') or '',
            }
            target.setdefault('mentions', []).append(mention)
            new_mentions.append(mention)
            existing_ranges.add(rng)
        target['mentions_count'] = len(target.get('mentions', []))
        store_keep_redact_decision(document_id, 'REDACT_ENTITY', target, reason='Обезличено пользователем')

        if working and doc.get('working_content') is not None:
            updated_content = anonymize_content_by_mentions(doc.get('working_content'), [{**target, 'mentions': new_mentions}])
            updated_text = content_plain_text(updated_content)
            doc['working_content'] = updated_content
            doc['anonymized_content'] = updated_content
            doc['working_text'] = updated_text
            doc['anonymized_text'] = updated_text
            doc['mappings'] = build_mappings_from_entities(doc.get('entities', []))
            doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
        elif working:
            updated_text = search_text or ''
            for mention in sorted(new_mentions, key=lambda m: m['start'], reverse=True):
                updated_text = updated_text[:mention['start']] + target.get('placeholder', '') + updated_text[mention['end']:]
            doc['working_text'] = updated_text
            doc['anonymized_text'] = updated_text
            doc['mappings'] = build_mappings_from_entities(doc.get('entities', []))
            doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
        else:
            rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    except HTTPException:
        restored_docs[document_id] = before_doc
        manual_decisions_by_document_id[document_id] = before_decisions
        raise
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    sync_public_document(document_id, doc)
    audit_mapping_action(document_id, 'ADD_MAPPING_COMPAT', {'entity_id': target.get('entity_id'), 'mode': body.mode})
    return anonymization_result_response(doc)


@app.patch('/internal/anonymization/documents/{document_id}/mappings/{mapping_id}')
def update_mapping(document_id: str, mapping_id: str, body: MappingPatchRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    target = next((e for e in doc.get('entities', []) if e.get('entity_id') == mapping_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Элемент таблицы соответствия не найден')
    data = body.model_dump(exclude_unset=True)
    if 'placeholder' in data and data.get('placeholder') != target.get('placeholder'):
        _error(400, 'PLACEHOLDER_MANAGED_AUTOMATICALLY', 'Условное обозначение формируется системой и не редактируется вручную')
    payload = {}
    if data.get('original_value') is not None:
        validate_non_empty(data.get('original_value'), 'original_value')
        payload['canonical_value'] = data['original_value'].strip()
    if data.get('entity_type') is not None:
        validate_non_empty(data.get('entity_type'), 'entity_type')
        payload['entity_class'] = data['entity_type'].strip()
    apply_entity_metadata_update(document_id, doc, target, payload)
    audit_mapping_action(document_id, 'UPDATE_MAPPING_COMPAT', {'entity_id': mapping_id})
    return anonymization_result_response(doc)


@app.delete('/internal/anonymization/documents/{document_id}/mappings/{mapping_id}')
def delete_mapping(document_id: str, mapping_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    target_entity = next((e for e in doc.get('entities', []) if e.get('entity_id') == mapping_id), None)
    if not target_entity:
        _error(404, 'NOT_FOUND', 'Сущность для элемента таблицы соответствия не найдена')

    keep_redacted_entity_in_document(document_id, doc, target_entity, reason='Оставлено пользователем')
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    manual_mappings_by_document_id[document_id] = [m for m in doc.get('mappings', []) if m.get('source') == 'manual']
    sync_public_document(document_id, doc)
    audit_mapping_action(document_id, 'DELETE_MAPPING_COMPAT', {'entity_id': mapping_id})
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/mappings/merge')
def merge_document_mappings(document_id: str, body: MergeMappingsRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    response = merge_entities_operation(document_id, body.target_mapping_id, body.source_mapping_ids)
    audit_mapping_action(document_id, 'MERGE_MAPPINGS_COMPAT', {'target_entity_id': body.target_mapping_id, 'source_entity_ids': body.source_mapping_ids})
    return response


@app.post('/internal/anonymization/documents/{document_id}/mappings/repair-placeholders')
def repair_placeholders(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    working = has_working_revision(doc)
    redacted = [e for e in doc.get('entities', []) if e.get('redaction_decision') == 'REDACT']
    desired = assign_unique_placeholders_for_entities(redacted)
    changed = {e.get('entity_id'): desired.get(e.get('entity_id')) for e in redacted if desired.get(e.get('entity_id')) and desired.get(e.get('entity_id')) != e.get('placeholder')}

    if working and doc.get('working_content') is not None:
        missing_mention_ids = sorted(
            m.get('mention_id')
            for e in redacted
            if e.get('entity_id') in changed
            for m in e.get('mentions', [])
            if m.get('mention_id') and not has_redaction_mention_mark(doc.get('working_content'), m.get('mention_id'))
        )
        if missing_mention_ids:
            _error(409, 'REPAIR_PLACEHOLDERS_MARK_NOT_FOUND', 'Разметка одного или нескольких упоминаний не найдена', {'missing_mention_ids': missing_mention_ids})
        updated_content, updated_mentions = update_working_content_placeholders(doc.get('working_content'), changed)
        expected_mentions = {m.get('mention_id') for e in redacted if e.get('entity_id') in changed for m in e.get('mentions', []) if m.get('mention_id')}
        missing_after = sorted(expected_mentions - updated_mentions)
        if missing_after:
            _error(409, 'REPAIR_PLACEHOLDERS_MARK_NOT_FOUND', 'Разметка одного или нескольких упоминаний не найдена', {'missing_mention_ids': missing_after})
        for entity in redacted:
            if entity.get('entity_id') in changed:
                entity['placeholder'] = changed[entity.get('entity_id')]
                for mention in entity.get('mentions', []):
                    mention['replacement_value'] = entity['placeholder']
        updated_text = content_plain_text(updated_content)
        doc['working_content'] = updated_content
        doc['anonymized_content'] = updated_content
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        doc['mappings'] = build_mappings_from_entities(doc.get('entities', []))
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
    elif working:
        placeholders = [e.get('placeholder') for e in redacted if e.get('placeholder')]
        conflict = len(placeholders) != len(set(placeholders))
        if conflict:
            _error(409, 'REPAIR_REQUIRES_STRUCTURED_CONTENT', 'Невозможно исправить одинаковые обозначения без разметки документа')
        return anonymization_result_response(doc)
    else:
        rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    sync_public_document(document_id, doc)
    audit_mapping_action(document_id, 'REPAIR_PLACEHOLDERS_COMPAT', {'changed_entity_ids': list(changed.keys())})
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/reanonymize')
async def reanonymize(document_id: str, body: ReanonymizeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]

    has_working_revision = (
        doc.get('working_text') is not None
        or doc.get('working_content') is not None
    )

    if has_working_revision:
        pending_review = pending_review_by_document_id.get(document_id, []) or doc.get('pending_review', [])
        if pending_review:
            _error(
                409,
                'PENDING_REVIEW_REQUIRED',
                'Перед повторным обезличиванием обработайте найденные в изменённом тексте фрагменты',
                {
                    'pending_count': len(pending_review),
                    'review_count': len(pending_review),
                    'pending_review': pending_review,
                },
            )

        entities = doc.get('entities', [])
        kept_entities = doc.get('kept_entities', doc.get('recognized_but_kept', []))
        mappings = build_mappings_from_entities(entities)
        review_entities = [e for e in entities if e.get('requires_review')]

        if doc.get('working_text') is not None:
            doc['anonymized_text'] = doc.get('working_text', '')
        if doc.get('working_content') is not None:
            doc['anonymized_content'] = doc.get('working_content')
        doc['entities'] = entities
        doc['kept_entities'] = kept_entities
        doc['recognized_but_kept'] = kept_entities
        doc['mappings'] = mappings
        doc['review_entities'] = review_entities
        doc['pending_review'] = []
        doc['pending_entities'] = []
        doc['pending_markers'] = []
        doc['publication_redaction_mode'] = body.publication_redaction_mode
        doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
        pending_review_by_document_id[document_id] = []

        if document_id in public_docs:
            public_docs[document_id]['anonymized_text'] = doc.get('anonymized_text', '')
            public_docs[document_id]['anonymized_content'] = doc.get('anonymized_content')
            public_docs[document_id]['content_format'] = doc.get('content_format', 'PLAIN_TEXT')

        return anonymization_result_response(doc)

    original_text = doc.get('original_text', '')
    entities = await extract_entities(original_text)
    resolved = resolve_entities(original_text, entities, body.publication_redaction_mode)
    resolved = apply_manual_decisions(document_id, resolved)
    entities_view, recognized_but_kept, review_entities = build_entities_from_resolved(document_id, resolved, body.publication_redaction_mode)
    entities_view, recognized_but_kept = apply_keep_redact_entity_decisions(document_id, entities_view, recognized_but_kept, original_text)
    entities_view, recognized_but_kept = apply_entity_metadata_decisions(document_id, entities_view, recognized_but_kept)
    entities_view = apply_split_mention_decisions(document_id, entities_view)
    entities_view = apply_split_entity_metadata_decisions(document_id, entities_view)
    entities_view = apply_merge_entity_decisions(document_id, entities_view)
    review_entities = [e for e in entities_view if e.get('requires_review')]
    rebuilt = rebuild_document_from_entities(document_id, entities_view, recognized_but_kept, original_text, doc.get('original_content'))
    mappings = rebuilt.get('mappings', [])
    anonymized = rebuilt.get('anonymized_text', '')
    save_document(
        document_id, doc.get('case_id', ''), doc.get('title', ''), original_text, anonymized, mappings,
        public_docs.get(document_id, {}).get('metadata', {}), recognized_but_kept, rebuilt.get('anonymized_content'),
        rebuilt.get('entities'), rebuilt.get('kept_entities'), review_entities
    )
    restored_docs[document_id]['entities'] = rebuilt.get('entities', [])
    restored_docs[document_id]['anonymized_content'] = rebuilt.get('anonymized_content')
    restored_docs[document_id]['review_entities']=review_entities
    restored_docs[document_id]['publication_redaction_mode']=body.publication_redaction_mode
    restored_docs[document_id]['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
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
    entity_class = 'PERSON' if body.entity_class in {'PERSON_FULL_NAME', 'PERSON'} else body.entity_class
    pending_items = pending_review_by_document_id.get(document_id, []) or doc.get('pending_review', [])
    pending_item = next((p for p in pending_items if (body.entity_key and p.get('entity_key') == body.entity_key) or (p.get('surface_value') == body.selected_text and p.get('entity_class') == entity_class)), None)
    entity_key = body.entity_key or (pending_item or {}).get('entity_key') or build_entity_semantic_key(entity_class, body.selected_text, body.person_role)
    canonical_value = (pending_item or {}).get('normalized_value') or body.selected_text
    decision_entity = {'entity_class': entity_class, 'canonical_value': canonical_value, 'normalized_value': canonical_value, 'surface_value': body.selected_text, 'entity_key': entity_key}
    redacted_entities = list(doc.get('entities', []))
    kept_entities = list(doc.get('kept_entities', []))
    is_pending_decision = pending_item is not None
    pending_group = (
        [p for p in pending_items if p.get('entity_key') == entity_key]
        if is_pending_decision
        else []
    )

    if body.decision == 'REDACT' and not is_pending_decision:
        target = _find_entity_by_semantic_key(redacted_entities, entity_key)
        if target and target.get('requires_review') is True:
            store_keep_redact_decision(document_id, 'REDACT_ENTITY', target, reason=body.reason, explicit_entity_key=entity_key)
            target['redaction_decision'] = 'REDACT'
            target['requires_review'] = False
            target['review_reason'] = None
            for mention in target.get('mentions', []):
                mention['requires_review'] = False
                mention['review_reason'] = None
            doc['entities'] = redacted_entities
            doc['kept_entities'] = kept_entities
            doc['recognized_but_kept'] = kept_entities
            doc['mappings'] = build_mappings_from_entities(redacted_entities)
            doc['review_entities'] = [e for e in redacted_entities if e.get('requires_review')]
            pending = [p for p in pending_items if p.get('entity_key') != entity_key]
            pending_review_by_document_id[document_id] = pending
            doc['pending_review'] = pending
            doc['pending_markers'] = [{'entity_key': p['entity_key'], 'surface_value': p['surface_value'], 'start': p['start'], 'end': p['end'], 'reason': p['reason']} for p in pending]
            doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
            sync_public_document(document_id, doc)
            return anonymization_result_response(doc)

    if body.decision == 'REDACT':
        before_doc = copy.deepcopy(doc)
        before_decisions = copy.deepcopy(manual_decisions_by_document_id.get(document_id, {}))
        try:
            store_keep_redact_decision(document_id, 'REDACT_ENTITY', decision_entity, reason=body.reason, explicit_entity_key=entity_key)
            target = _find_entity_by_semantic_key(redacted_entities, entity_key)
            if not target:
                target = _find_entity_by_semantic_key(kept_entities, entity_key)
                if target:
                    kept_entities.remove(target)
                    target['redaction_decision'] = 'REDACT'
                    target['requires_review'] = False
                    target['entity_key'] = entity_key
                    redacted_entities.append(target)
            if not target:
                target = {
                    'entity_id': str(uuid.uuid4()),
                    'document_id': document_id,
                    'entity_class': entity_class,
                    'canonical_value': canonical_value,
                    'normalized_value': canonical_value,
                    'entity_key': entity_key,
                    'redaction_decision': 'REDACT',
                    'requires_review': False,
                    'mentions': [],
                }
                redacted_entities.append(target)
            target['entity_key'] = entity_key
            working = has_working_revision(doc)
            search_text = (content_plain_text(doc.get('working_content')) if doc.get('working_content') is not None else doc.get('working_text', '')) if working else doc.get('original_text', '')

            previous_mentions = list(target.get('mentions', []))
            if working and not is_pending_decision:
                target['mentions'] = []
                existing_ranges = set()
            else:
                existing_ranges = {
                    (m.get('start'), m.get('end'))
                    for m in target.get('mentions', [])
                }
            accepted_ranges = set(existing_ranges)
            new_mentions = []

            if is_pending_decision:
                # Решение REDACT относится ко всей сущности, а не только
                # к одной выбранной пользователем форме написания.
                surface_to_normalized = {}
                for pending in pending_group:
                    surface = pending.get('surface_value')
                    if not surface:
                        continue
                    surface_to_normalized[surface] = (
                        pending.get('normalized_value') or canonical_value
                    )

                # Более длинные варианты обрабатываем первыми,
                # чтобы короткая форма не перекрыла длинную.
                surfaces_to_redact = sorted(
                    surface_to_normalized.keys(),
                    key=len,
                    reverse=True,
                )
            else:
                surface_to_normalized = {body.selected_text: canonical_value}
                if working:
                    for previous in previous_mentions:
                        surface = previous.get('surface_value')
                        if surface:
                            surface_to_normalized[surface] = previous.get('normalized_value') or canonical_value
                surfaces_to_redact = sorted(surface_to_normalized.keys(), key=len, reverse=True)

            def overlaps_existing(start: int, end: int) -> bool:
                return any(
                    start < existing_end and existing_start < end
                    for existing_start, existing_end in accepted_ranges
                )

            for surface in surfaces_to_redact:
                normalized_value = surface_to_normalized[surface]

                for match in re.finditer(re.escape(surface), search_text or ''):
                    start = match.start()
                    end = match.end()

                    if overlaps_existing(start, end):
                        continue

                    mention = {
                        'mention_id': str(uuid.uuid4()),
                        'entity_id': target['entity_id'],
                        'surface_value': surface,
                        'normalized_value': normalized_value,
                        'start': start,
                        'end': end,
                        'replacement_value': target.get('placeholder') or '',
                    }

                    target.setdefault('mentions', []).append(mention)
                    new_mentions.append(mention)
                    accepted_ranges.add((start, end))

            target['mentions_count'] = len(target.get('mentions', []))
            if is_pending_decision or working:
                target['placeholder'] = target.get('placeholder') or next_placeholder(entity_class, doc.get('mappings', []))
                for mention in new_mentions:
                    mention['replacement_value'] = target['placeholder']
                updated_text = search_text or ''
                for mention in sorted(new_mentions, key=lambda m: m['start'], reverse=True):
                    updated_text = updated_text[:mention['start']] + target['placeholder'] + updated_text[mention['end']:]
                doc['working_text'] = updated_text
                doc['anonymized_text'] = updated_text
                working_content = doc.get('working_content')
                if working_content:
                    updated_content = anonymize_content_by_mentions(working_content, [{**target, 'mentions': new_mentions}])
                    updated_text = content_plain_text(updated_content)
                    doc['working_content'] = updated_content
                    doc['anonymized_content'] = updated_content
                    doc['working_text'] = updated_text
                    doc['anonymized_text'] = updated_text
                doc['entities'] = redacted_entities
                doc['kept_entities'] = kept_entities
                doc['recognized_but_kept'] = kept_entities
                doc['mappings'] = build_mappings_from_entities(redacted_entities)
                doc['review_entities'] = [e for e in redacted_entities if e.get('requires_review')]
            else:
                rebuild_document_from_entities(document_id, redacted_entities, kept_entities, doc.get('original_text', ''), doc.get('original_content'))
        except HTTPException:
            restored_docs[document_id] = before_doc
            manual_decisions_by_document_id[document_id] = before_decisions
            raise
    elif body.decision == 'KEEP':
        if not is_pending_decision:
            target = _find_entity_by_semantic_key(redacted_entities, entity_key)
            if target:
                keep_redacted_entity_in_document(document_id, doc, target, reason=body.reason, explicit_entity_key=entity_key)
            else:
                store_keep_redact_decision(document_id, 'KEEP_ENTITY', decision_entity, reason=body.reason, explicit_entity_key=entity_key)
        else:
            store_keep_redact_decision(document_id, 'KEEP_ENTITY', decision_entity, reason=body.reason, explicit_entity_key=entity_key)
            if doc.get('working_text') is not None:
                doc['anonymized_text'] = doc.get('working_text', '')
            if doc.get('working_content') is not None:
                doc['anonymized_content'] = doc.get('working_content')
    elif body.decision == 'MERGE_WITH_EXISTING':
        if not body.target_entity_id:
            _error(400, 'BAD_REQUEST', 'target_entity_id обязателен для MERGE_WITH_EXISTING')
        target = next((e for e in redacted_entities if e.get('entity_id') == body.target_entity_id), None)
        if not target:
            _error(404, 'NOT_FOUND', 'Целевая сущность не найдена')
        before_doc = copy.deepcopy(doc)
        before_decisions = copy.deepcopy(
            manual_decisions_by_document_id.get(document_id, {})
        )
        target['placeholder'] = target.get('placeholder') or next_placeholder(target.get('entity_class', entity_class), doc.get('mappings', []))
        pending_group = [p for p in pending_items if p.get('entity_key') == entity_key] or [{
            'surface_value': body.selected_text,
            'normalized_value': canonical_value,
            'entity_class': entity_class,
        }]
        search_text = content_plain_text(doc.get('working_content')) if doc.get('working_content') is not None else (doc.get('working_text') if doc.get('working_text') is not None else doc.get('original_text', ''))
        existing_ranges = {(m.get('start'), m.get('end')) for m in target.get('mentions', [])}
        new_mentions = []
        for pending in pending_group:
            surface = pending.get('surface_value') or body.selected_text
            normalized = pending.get('normalized_value') or surface
            for match in re.finditer(re.escape(surface), search_text or ''):
                rng = (match.start(), match.end())
                if rng in existing_ranges:
                    continue
                mention = {
                    'mention_id': str(uuid.uuid4()),
                    'entity_id': target['entity_id'],
                    'surface_value': surface,
                    'normalized_value': normalized,
                    'start': match.start(),
                    'end': match.end(),
                    'replacement_value': target['placeholder'],
                }
                target.setdefault('mentions', []).append(mention)
                new_mentions.append(mention)
                existing_ranges.add(rng)
        target['mentions_count'] = len(target.get('mentions', []))
        updated_text = search_text or ''
        for mention in sorted(new_mentions, key=lambda m: m['start'], reverse=True):
            updated_text = updated_text[:mention['start']] + target['placeholder'] + updated_text[mention['end']:]
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        working_content = doc.get('working_content')
        if working_content:
            try:
                updated_content = anonymize_content_by_mentions(
                    working_content,
                    [{**target, 'mentions': new_mentions}],
                )
            except HTTPException:
                restored_docs[document_id] = before_doc
                manual_decisions_by_document_id[document_id] = before_decisions
                raise

            doc['working_content'] = updated_content
            doc['anonymized_content'] = updated_content
            doc['working_text'] = content_plain_text(updated_content)
            doc['anonymized_text'] = doc['working_text']
        doc['entities'] = redacted_entities
        doc['kept_entities'] = kept_entities
        doc['recognized_but_kept'] = kept_entities
        doc['mappings'] = build_mappings_from_entities(redacted_entities)
        doc['review_entities'] = [e for e in redacted_entities if e.get('requires_review')]
        now = now_iso()
        decisions = manual_decisions_by_document_id.setdefault(document_id, {})
        decisions[f'MERGE_PENDING_WITH_ENTITY::{entity_key}::{target["entity_id"]}'] = {
            'decision_id': str(uuid.uuid4()),
            'document_id': document_id,
            'decision_type': 'MERGE_PENDING_WITH_ENTITY',
            'entity_key': entity_key,
            'target_entity_id': target['entity_id'],
            'target_entity_key': entity_semantic_key(target),
            'created_at': now,
            'updated_at': now,
        }

    pending = [p for p in pending_items if p.get('entity_key') != entity_key]
    pending_review_by_document_id[document_id] = pending
    doc['pending_review'] = pending
    doc['pending_markers'] = [{'entity_key': p['entity_key'], 'surface_value': p['surface_value'], 'start': p['start'], 'end': p['end'], 'reason': p['reason']} for p in pending]
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/draft-scan')
async def draft_scan(document_id: str, body: DraftScanRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)

    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')

    doc = restored_docs[document_id]

    def current_scan_response(stale: bool = False) -> dict:
        current_doc = restored_docs[document_id]
        response = {
            'document_id': document_id,
            'document_revision': current_doc.get('working_document_revision', body.document_revision),
            'pending_review': current_doc.get('pending_review', []),
            'pending_markers': current_doc.get('pending_markers', []),
        }
        if stale:
            response['stale'] = True
        return response

    current_revision = doc.get('working_document_revision')
    if not isinstance(current_revision, int):
        current_revision = -1

    if body.document_revision < current_revision:
        return current_scan_response(stale=True)

    working_text = canonical_text_for_content(body.text, body.content, body.content_format)
    doc['working_text'] = working_text
    doc['working_content'] = body.content
    doc['working_content_format'] = body.content_format
    doc['working_document_revision'] = body.document_revision

    entities = await extract_entities(working_text)

    if restored_docs[document_id].get('working_document_revision') != body.document_revision:
        return current_scan_response(stale=True)

    pending = []
    decisions = manual_decisions_by_document_id.get(document_id, {})
    existing_entities = doc.get('entities', [])
    placeholder_patterns = [r'ФИО\d+', r'ПАСПОРТ\d+', r'ИНН\d+', r'АДРЕС\d+', r'ДАТА\d+', r'ТЕЛЕФОН\d+', r'СНИЛС\d+', r'ЭЛЕКТРОННАЯ_ПОЧТА\d+']
    for e in resolve_entities(working_text, entities, 'NORMATIVE'):
        surface = e.get('surface_value', '')
        if any(re.fullmatch(pat, surface) for pat in placeholder_patterns):
            continue
        key = build_entity_semantic_key(e.get('entity_class','OTHER'), e.get('normalized_value') or surface, e.get('person_role'))
        if decisions.get(key, {}).get('decision_type') == 'KEEP_ENTITY':
            continue
        merge_candidates = [
            {
                'entity_id': ent.get('entity_id'),
                'placeholder': ent.get('placeholder'),
                'canonical_value': ent.get('canonical_value'),
                'normalized_value': ent.get('normalized_value'),
                'entity_class': ent.get('entity_class'),
            }
            for ent in existing_entities
            if ent.get('redaction_decision', 'REDACT') == 'REDACT'
            and ent.get('entity_class') == e.get('entity_class')
            and ent.get('entity_id')
            and entity_semantic_key(ent) != key
        ]
        pending.append({'entity_key': key, 'surface_value': surface, 'normalized_value': e.get('normalized_value', surface), 'entity_class': e.get('entity_class', 'OTHER'), 'person_role': e.get('person_role', 'UNKNOWN'), 'start': e.get('start', 0), 'end': e.get('end', 0), 'reason': 'В изменённом тексте найдено новое значение, требующее проверки', 'suggested_action': 'REDACT', 'merge_candidates': merge_candidates})
    pending_review_by_document_id[document_id] = pending
    doc['pending_review'] = pending
    doc['pending_markers'] = [
        {
            'entity_key': p['entity_key'],
            'surface_value': p['surface_value'],
            'start': p['start'],
            'end': p['end'],
            'reason': p['reason'],
        }
        for p in pending
    ]

    return current_scan_response()

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


@app.patch('/internal/anonymization/documents/{document_id}/entities/{entity_id}')
def patch_entity(document_id: str, entity_id: str, body: EntityPatchRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    ent = next((e for e in doc.get('entities', []) if e.get('entity_id') == entity_id), None)
    if not ent:
        _error(404, 'NOT_FOUND', 'Сущность не найдена')
    apply_entity_metadata_update(document_id, doc, ent, body.model_dump(exclude_unset=True))
    return anonymization_result_response(doc)


def merge_entities_operation(document_id: str, target_entity_id: str, source_entity_ids: list[str]):
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    if not source_entity_ids:
        _error(400, 'BAD_REQUEST', 'Не указаны исходные сущности для объединения')
    if target_entity_id in source_entity_ids:
        _error(400, 'BAD_REQUEST', 'Целевая сущность не может быть исходной сущностью')

    entities = doc.get('entities', [])
    target = next((e for e in entities if e.get('entity_id') == target_entity_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Целевая сущность не найдена')

    sources = []
    for source_id in source_entity_ids:
        source = next((e for e in entities if e.get('entity_id') == source_id), None)
        if not source:
            _error(404, 'NOT_FOUND', 'Исходная сущность не найдена', {'source_entity_id': source_id})
        sources.append(source)

    target_class = target.get('entity_class') or target.get('entity_type')
    for source in sources:
        source_class = source.get('entity_class') or source.get('entity_type')
        if source_class != target_class:
            _error(400, 'BAD_REQUEST', 'Нельзя объединить сущности разных классов')
    if target.get('redaction_decision') != 'REDACT' or any(source.get('redaction_decision') != 'REDACT' for source in sources):
        _error(400, 'BAD_REQUEST', 'Можно объединять только обезличиваемые сущности')

    working = has_working_revision(doc)
    if not working:
        _validate_merge_semantic_keys_are_replayable(entities, target, sources)

    source_mention_ids = {
        mention.get('mention_id')
        for source in sources
        for mention in source.get('mentions', [])
        if mention.get('mention_id')
    }

    updated_content = None
    if working and doc.get('working_content') is not None:
        missing_mention_ids = sorted(
            mention_id
            for mention_id in source_mention_ids
            if not has_redaction_mention_mark(doc.get('working_content'), mention_id)
        )
        if missing_mention_ids:
            _error(409, 'MERGE_ENTITIES_MARK_NOT_FOUND', 'Разметка одного или нескольких объединяемых упоминаний не найдена', {'missing_mention_ids': missing_mention_ids})
        updated_content, updated_mention_ids = update_working_content_for_merge(doc.get('working_content'), source_mention_ids, target)
        missing_after_update = sorted(source_mention_ids - updated_mention_ids)
        if missing_after_update:
            _error(409, 'MERGE_ENTITIES_MARK_NOT_FOUND', 'Разметка одного или нескольких объединяемых упоминаний не найдена', {'missing_mention_ids': missing_after_update})

    store_merge_entities_decision(document_id, target, sources)
    merged_entities = merge_entities_in_state(entities, target, sources)

    if working and doc.get('working_content') is not None:
        updated_text = content_plain_text(updated_content)
        doc['entities'] = merged_entities
        doc['working_content'] = updated_content
        doc['anonymized_content'] = updated_content
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        doc['mappings'] = build_mappings_from_entities(doc['entities'])
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
    elif working:
        updated_text = doc.get('working_text') or ''
        target_placeholder = target.get('placeholder') or ''
        for source in sources:
            source_placeholder = source.get('placeholder') or ''
            if source_placeholder:
                updated_text = replace_placeholder_boundary(updated_text, source_placeholder, target_placeholder)
        doc['entities'] = merged_entities
        doc['working_text'] = updated_text
        doc['anonymized_text'] = updated_text
        doc['mappings'] = build_mappings_from_entities(doc['entities'])
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
    else:
        rebuild_document_from_entities(document_id, merged_entities, doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))

    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    sync_public_document(document_id, doc)
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/entities/merge')
def merge_entities(document_id: str, body: EntityMergeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    return merge_entities_operation(document_id, body.target_entity_id, body.source_entity_ids)


@app.post('/internal/anonymization/documents/{document_id}/entities/{entity_id}/mentions/{mention_id}/split')
def split_mention(document_id: str, entity_id: str, mention_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    src = next((e for e in doc.get('entities', []) if e.get('entity_id') == entity_id), None)
    if not src:
        _error(404, 'NOT_FOUND', 'Сущность не найдена')
    mention = next((m for m in src.get('mentions', []) if m.get('mention_id') == mention_id), None)
    if not mention:
        _error(404, 'NOT_FOUND', 'Упоминание не найдено')

    source_entity_key = entity_semantic_key(src)
    has_working_revision = (
        doc.get('working_text') is not None
        or doc.get('working_content') is not None
    )

    if has_working_revision and doc.get('working_content') is None:
        placeholder = src.get('placeholder') or ''
        occurrences_count = (doc.get('working_text') or '').count(placeholder)
        if occurrences_count > 1:
            _error(
                409,
                'SPLIT_REQUIRES_STRUCTURED_CONTENT',
                'Невозможно однозначно разделить упоминание в текстовом режиме без разметки документа',
                {
                    'entity_id': entity_id,
                    'mention_id': mention_id,
                    'placeholder': placeholder,
                    'occurrences_count': occurrences_count,
                },
            )
    if has_working_revision and doc.get('working_content') is not None:
        if not has_redaction_mention_mark(doc.get('working_content'), mention_id):
            _error(
                409,
                'SPLIT_MENTION_MARK_NOT_FOUND',
                'Разметка выбранного упоминания не найдена',
                {
                    'entity_id': entity_id,
                    'mention_id': mention_id,
                },
            )
            
    updated_entities, new_ent = split_entity_mention_in_state(document_id, doc.get('entities', []), src, mention, source_entity_key)
    store_split_mention_decision(document_id, source_entity_key, entity_id, mention, new_ent['entity_id'])

    if has_working_revision and doc.get('working_content') is not None:
        updated_content, updated_mark = update_working_content_for_split(doc.get('working_content'), mention_id, new_ent)
        if not updated_mark:
            _error(409, 'SPLIT_MENTION_MARK_NOT_FOUND', 'Разметка выбранного упоминания не найдена', {'entity_id': entity_id, 'mention_id': mention_id})
        doc['entities'] = updated_entities
        doc['working_content'] = updated_content
        doc['anonymized_content'] = updated_content
        doc['working_text'] = content_plain_text(updated_content)
        doc['anonymized_text'] = doc['working_text']
        doc['mappings'] = build_mappings_from_entities(doc['entities'])
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
        doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
        if document_id in public_docs:
            public_docs[document_id]['anonymized_text'] = doc.get('anonymized_text', '')
            public_docs[document_id]['anonymized_content'] = doc.get('anonymized_content')
            public_docs[document_id]['content_format'] = doc.get('content_format', 'PLAIN_TEXT')
        return anonymization_result_response(doc)

    if has_working_revision:
        working_text = doc.get('working_text') or ''
        old_placeholder = src.get('placeholder') or ''
        doc['entities'] = updated_entities
        doc['working_text'] = working_text.replace(old_placeholder, new_ent.get('placeholder') or '', 1)
        doc['anonymized_text'] = doc['working_text']
        doc['mappings'] = build_mappings_from_entities(doc['entities'])
        doc['review_entities'] = [e for e in doc.get('entities', []) if e.get('requires_review')]
        doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
        if document_id in public_docs:
            public_docs[document_id]['anonymized_text'] = doc.get('anonymized_text', '')
            public_docs[document_id]['anonymized_content'] = doc.get('anonymized_content')
            public_docs[document_id]['content_format'] = doc.get('content_format', 'PLAIN_TEXT')
        return anonymization_result_response(doc)

    doc['entities'] = updated_entities
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    doc['manual_decisions'] = list(manual_decisions_by_document_id.get(document_id, {}).values())
    return anonymization_result_response(doc)
