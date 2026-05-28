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


class EntityPatchRequest(BaseModel):
    canonical_value: str | None = None
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
                e['redaction_reason']='Сокращённое ФИО соответствует нескольким найденным лицам'
                e['merge_candidates'] = full_candidates
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
        ent['mentions'].append(mention)
        person_key_first_pos[key] = min(person_key_first_pos.get(key, mention.get('start') or 0), mention.get('start') or 0)
        ent['requires_review']=ent['requires_review'] or mention['requires_review']
        if mention['review_reason']:
            ent['review_reason']=mention['review_reason']
        if mention.get('merge_candidates'):
            ent['merge_candidates'] = mention['merge_candidates']
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


def anonymize_content_by_mentions(content: dict | None, entities: list[dict]) -> dict | None:
    if not content:
        return None
    data = copy.deepcopy(content)
    mentions = []
    for ent in entities:
        if ent.get('redaction_decision') != 'REDACT':
            continue
        for m in ent.get('mentions', []):
            if isinstance(m.get('start'), int) and isinstance(m.get('end'), int):
                mentions.append((m['start'], m['end'], ent['entity_id'], m['mention_id'], ent['placeholder']))
    mentions.sort(key=lambda x: x[0])
    idx = 0
    offset = 0

    def split_text_node(node: dict) -> list[dict]:
        nonlocal idx, offset
        text = node.get('text') or ''
        marks = node.get('marks', [])
        start_local = offset
        end_local = start_local + len(text)
        out: list[dict] = []
        cursor = 0
        while idx < len(mentions):
            ms, me, entity_id, mention_id, placeholder = mentions[idx]
            if ms >= end_local:
                break
            if me <= start_local:
                idx += 1
                continue
            if ms < start_local or me > end_local:
                break
            rel_s, rel_e = ms - start_local, me - start_local
            if rel_s > cursor:
                out.append({'type': 'text', 'text': text[cursor:rel_s], 'marks': copy.deepcopy(marks)})
            out.append({
                'type': 'text',
                'text': placeholder,
                'marks': copy.deepcopy(marks) + [{'type': 'redactionMention', 'attrs': {'entityId': entity_id, 'mentionId': mention_id, 'placeholder': placeholder}}],
            })
            cursor = rel_e
            idx += 1
        if cursor == 0:
            offset = end_local
            return [node]
        if cursor < len(text):
            out.append({'type': 'text', 'text': text[cursor:], 'marks': copy.deepcopy(marks)})
        offset = end_local
        return out

    def walk(node):
        if isinstance(node, dict) and isinstance(node.get('content'), list):
            new_content = []
            for ch in node['content']:
                if isinstance(ch, dict) and ch.get('type') == 'text' and isinstance(ch.get('text'), str):
                    new_content.extend(split_text_node(ch))
                else:
                    walk(ch)
                    new_content.append(ch)
            node['content'] = new_content
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
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
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data

def content_plain_text(content: dict | None) -> str:
    parts: list[str] = []
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('text'), str):
                parts.append(node['text'])
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(content)
    return ''.join(parts)

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
    entities, recognized_but_kept, review_entities = build_entities_from_resolved(body.document_id, resolved, body.publication_redaction_mode)
    rebuilt = rebuild_document_from_entities(body.document_id, entities, recognized_but_kept, body.text, body.original_content)
    mappings = rebuilt.get('mappings', [])
    anonymized = rebuilt.get('anonymized_text', '')
    save_document(
        body.document_id, body.case_id, body.title, body.text, anonymized, mappings,
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
            if isinstance(node.get('marks'), list):
                node['marks'] = [m for m in node['marks'] if m.get('type') != 'redactionMention']
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
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')

    doc = restored_docs[document_id]
    validate_non_empty(body.original_value, 'original_value')
    validate_non_empty(body.entity_type, 'entity_type')
    positions = [m.start() for m in re.finditer(re.escape(body.original_value), doc.get('original_text', ''))]
    if not positions:
        return anonymization_result_response(doc)
    entity_class = 'PERSON' if body.entity_type in {'PERSON_FULL_NAME', 'PERSON'} else body.entity_type
    if body.mode == 'existing':
        target = next((e for e in doc.get('entities', []) if e.get('placeholder') == body.placeholder or e.get('entity_id') == body.placeholder), None)
        if not target:
            _error(400, 'BAD_REQUEST', 'Целевая сущность не найдена')
    else:
        target = next((e for e in doc.get('entities', []) if e.get('entity_class') == entity_class and (e.get('canonical_value') == body.original_value or e.get('normalized_value') == body.original_value)), None)
        if not target:
            target = {'entity_id': str(uuid.uuid4()), 'document_id': document_id, 'entity_class': entity_class, 'canonical_value': body.original_value, 'normalized_value': body.original_value, 'redaction_decision': 'REDACT', 'mentions': []}
            doc.setdefault('entities', []).append(target)
    existing_ranges = {(m.get('start'), m.get('end')) for m in target.get('mentions', [])}
    for pos in positions:
        rng = (pos, pos + len(body.original_value))
        if rng in existing_ranges:
            continue
        target.setdefault('mentions', []).append({'mention_id': str(uuid.uuid4()), 'entity_id': target['entity_id'], 'surface_value': body.original_value, 'start': pos, 'end': pos + len(body.original_value), 'replacement_value': target.get('placeholder') or ''})
    target['mentions_count'] = len(target.get('mentions', []))
    manual_decisions_by_document_id.setdefault(document_id, {})[f'REDACT_ENTITY::{entity_class}::{body.original_value}'] = {
        'decision_id': str(uuid.uuid4()), 'document_id': document_id, 'decision_type': 'REDACT_ENTITY',
        'entity_id': target['entity_id'], 'canonical_value': target.get('canonical_value'), 'payload': {'mode': body.mode}, 'created_at': now_iso(), 'updated_at': now_iso(),
    }
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)

@app.patch('/internal/anonymization/documents/{document_id}/mappings/{mapping_id}')
def update_mapping(document_id: str, mapping_id: str, body: MappingPatchRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    validate_non_empty(body.placeholder, 'placeholder')
    validate_non_empty(body.original_value, 'original_value')
    validate_non_empty(body.entity_type, 'entity_type')
    doc = restored_docs[document_id]
    target = next((e for e in doc.get('entities', []) if e.get('entity_id') == mapping_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Элемент таблицы соответствия не найден')
    data = body.model_dump(exclude_unset=True)
    if data.get('original_value'):
        target['canonical_value'] = data['original_value'].strip()
    if data.get('entity_type'):
        target['entity_class'] = data['entity_type'].strip()
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)


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
    kept = doc.setdefault('kept_entities', [])
    redacted = []
    for e in doc.get('entities', []):
        if e.get('entity_id') == mapping_id:
            e['redaction_decision'] = 'KEEP'
            kept.append(e)
        else:
            redacted.append(e)
    rebuild_document_from_entities(document_id, redacted, kept, doc.get('original_text', ''), doc.get('original_content'))
    manual_mappings_by_document_id[document_id] = [m for m in doc.get('mappings', []) if m.get('source') == 'manual']
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/mappings/merge')
def merge_document_mappings(document_id: str, body: MergeMappingsRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    target = next((e for e in doc.get('entities', []) if e.get('entity_id') == body.target_mapping_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Целевой элемент таблицы соответствия не найден')
    if not body.source_mapping_ids:
        _error(400, 'BAD_REQUEST', 'source_mapping_ids не должен быть пустым')
    source_ids = set(body.source_mapping_ids)
    sources = [e for e in doc.get('entities', []) if e.get('entity_id') in source_ids]
    if len(sources) != len(source_ids):
        _error(404, 'NOT_FOUND', 'Один или несколько исходных элементов таблицы соответствия не найдены')
    for src in sources:
        target.setdefault('mentions', []).extend(src.get('mentions', []))
        doc['entities'].remove(src)
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)



@app.post('/internal/anonymization/documents/{document_id}/mappings/repair-placeholders')
def repair_placeholders(document_id: str, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    audit_log.append({'id': str(uuid.uuid4()), 'document_id': document_id, 'action': 'REPAIR_PLACEHOLDERS', 'created_at': now_iso(), 'details': {}})
    return anonymization_result_response(doc)

@app.post('/internal/anonymization/documents/{document_id}/reanonymize')
async def reanonymize(document_id: str, body: ReanonymizeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    if document_id not in restored_docs:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    doc = restored_docs[document_id]
    original_text = doc.get('original_text', '')
    entities = await extract_entities(original_text)
    resolved = resolve_entities(original_text, entities, body.publication_redaction_mode)
    entities_view, recognized_but_kept, review_entities = build_entities_from_resolved(document_id, resolved, body.publication_redaction_mode)
    for d in manual_decisions_by_document_id.get(document_id, {}).values():
        ent = next((e for e in entities_view if e['entity_id'] == d.get('entity_id') or e.get('canonical_value') == d.get('canonical_value')), None)
        if ent and d.get('decision') == 'FORCE_KEEP':
            ent['redaction_decision'] = 'KEEP'
        if ent and d.get('decision') == 'FORCE_REDACT':
            ent['redaction_decision'] = 'REDACT'
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
    for e in doc.get('entities', []):
        if e.get('canonical_value') == body.selected_text or e.get('normalized_value') == body.selected_text:
            if body.decision == 'KEEP':
                e['redaction_decision'] = 'KEEP'
            elif body.decision in {'REDACT', 'MERGE_WITH_EXISTING'}:
                e['redaction_decision'] = 'REDACT'
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
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
    placeholder_patterns = [r'ФИО\d+', r'ПАСПОРТ\d+', r'ИНН\d+', r'АДРЕС\d+', r'ДАТА\d+', r'ТЕЛЕФОН\d+', r'СНИЛС\d+', r'ЭЛЕКТРОННАЯ_ПОЧТА\d+']
    for e in resolve_entities(body.text, entities, 'NORMATIVE'):
        surface = e.get('surface_value', '')
        if any(re.fullmatch(pat, surface) for pat in placeholder_patterns):
            continue
        key = f"{e.get('entity_class','OTHER')}::{normalize_spaces(surface)}"
        if decisions.get(key, {}).get('decision') == 'FORCE_KEEP':
            continue
        merge_candidates = [{'cluster_id': m.get('cluster_id'), 'placeholder': m.get('placeholder'), 'normalized_value': m.get('normalized_value')} for m in mappings if m.get('entity_class') == e.get('entity_class') and m.get('cluster_id')]
        pending.append({'entity_key': key, 'surface_value': surface, 'normalized_value': e.get('normalized_value', surface), 'entity_class': e.get('entity_class', 'OTHER'), 'person_role': e.get('person_role', 'UNKNOWN'), 'start': e.get('start', 0), 'end': e.get('end', 0), 'reason': 'В изменённом тексте найдено новое значение, требующее проверки', 'suggested_action': 'REDACT', 'merge_candidates': merge_candidates})
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


@app.patch('/internal/anonymization/documents/{document_id}/entities/{entity_id}')
def patch_entity(document_id: str, entity_id: str, body: EntityPatchRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    ent = next((e for e in doc.get('entities', []) if e.get('entity_id') == entity_id), None)
    if not ent:
        _error(404, 'NOT_FOUND', 'Сущность не найдена')
    for k, v in body.model_dump(exclude_unset=True).items():
        ent[k] = v
    manual_decisions_by_document_id.setdefault(document_id, {})[f'UPDATE_ENTITY_ROLE::{entity_id}'] = {
        'decision_id': str(uuid.uuid4()), 'document_id': document_id, 'decision_type': 'UPDATE_ENTITY_ROLE',
        'entity_id': entity_id, 'payload': body.model_dump(exclude_unset=True), 'created_at': now_iso(), 'updated_at': now_iso(),
    }
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)


@app.post('/internal/anonymization/documents/{document_id}/entities/merge')
def merge_entities(document_id: str, body: EntityMergeRequest, x_internal_service_token: str | None = Header(None)):
    require_internal(x_internal_service_token)
    doc = restored_docs.get(document_id)
    if not doc:
        _error(404, 'NOT_FOUND', 'Документ не найден')
    entities = doc.get('entities', [])
    target = next((e for e in entities if e.get('entity_id') == body.target_entity_id), None)
    if not target:
        _error(404, 'NOT_FOUND', 'Целевая сущность не найдена')
    for sid in body.source_entity_ids:
        src = next((e for e in entities if e.get('entity_id') == sid), None)
        if not src:
            continue
        for m in src.get('mentions', []):
            m['entity_id'] = target['entity_id']
            m['replacement_value'] = target['placeholder']
            target.setdefault('mentions', []).append(m)
        entities.remove(src)
    manual_decisions_by_document_id.setdefault(document_id, {})[f'MERGE_ENTITIES::{target["entity_id"]}'] = {
        'decision_id': str(uuid.uuid4()), 'document_id': document_id, 'decision_type': 'MERGE_ENTITIES',
        'entity_id': target['entity_id'], 'payload': {'source_entity_ids': body.source_entity_ids}, 'created_at': now_iso(), 'updated_at': now_iso(),
    }
    rebuild_document_from_entities(document_id, entities, doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)


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
    src['mentions'] = [m for m in src.get('mentions', []) if m.get('mention_id') != mention_id]
    new_ent = copy.deepcopy(src)
    new_ent['entity_id'] = str(uuid.uuid4())
    new_ent['placeholder'] = next_placeholder('PERSON', [{'placeholder': e.get('placeholder')} for e in doc.get('entities', [])])
    mention['entity_id'] = new_ent['entity_id']
    mention['replacement_value'] = new_ent['placeholder']
    new_ent['mentions'] = [mention]
    doc['entities'].append(new_ent)
    manual_decisions_by_document_id.setdefault(document_id, {})[f'SPLIT_MENTION::{mention_id}'] = {
        'decision_id': str(uuid.uuid4()), 'document_id': document_id, 'decision_type': 'SPLIT_MENTION',
        'entity_id': entity_id, 'mention_id': mention_id, 'target_entity_id': new_ent['entity_id'], 'payload': {}, 'created_at': now_iso(), 'updated_at': now_iso(),
    }
    rebuild_document_from_entities(document_id, doc.get('entities', []), doc.get('kept_entities', []), doc.get('original_text', ''), doc.get('original_content'))
    return anonymization_result_response(doc)
