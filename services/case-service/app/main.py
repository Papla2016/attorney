from datetime import datetime
import os
import uuid
import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import jwt
from pydantic import BaseModel, ConfigDict

app = FastAPI(title='case-service')
SECRET = os.getenv('JWT_SECRET', 'secret')
ALG = os.getenv('JWT_ALGORITHM', 'HS256')
INTERNAL = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-secret-token')
ANON = os.getenv('ANONYMIZATION_SERVICE_URL', 'http://anonymization-service:8000')
NER = os.getenv('NER_SERVICE_URL', 'http://ner-service:8000')
AUTH = os.getenv('AUTH_SERVICE_URL')

USER_ID = "00000000-0000-0000-0000-000000000002"
STAFF_ID = "00000000-0000-0000-0000-000000000003"
JUDGE_ID = "00000000-0000-0000-0000-000000000004"


def error_payload(code: str, message: str, details: dict | None = None):
    return {'error': {'code': code, 'message': message, 'details': details or {}}}


def err(code, msg, status=403, details: dict | None = None):
    raise HTTPException(status_code=status, detail=error_payload(code, msg, details))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and 'error' in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=error_payload('HTTP_ERROR', str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=error_payload('BAD_REQUEST', 'Некорректный запрос', {'validation_errors': exc.errors()}),
    )


def now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def normalize_mapping_source(source: str | None) -> str:
    if source == 'ner':
        return 'natasha'
    if source in {'manual', 'natasha', 'regex', 'rule'}:
        return source
    return source or 'manual'


def ensure_mapping_metadata(mapping: dict) -> dict:
    now = now_iso()
    if not mapping.get('id'):
        mapping['id'] = str(uuid.uuid4())
    if not mapping.get('created_at'):
        mapping['created_at'] = mapping.get('updated_at') or now
    if not mapping.get('updated_at'):
        mapping['updated_at'] = now
    mapping['source'] = normalize_mapping_source(mapping.get('source'))
    return mapping


def ensure_doc_mappings(d: dict) -> list[dict]:
    d['mappings'] = [ensure_mapping_metadata(m) for m in d.get('mappings', [])]
    return d['mappings']

def claims(auth: str | None):
    if not auth:
        return {'roles': ['PUBLIC'], 'sub': None}
    try:
        return jwt.decode(auth.replace('Bearer ', ''), SECRET, algorithms=[ALG])
    except Exception:
        return {'roles': ['PUBLIC'], 'sub': None}


def allowed(c, need):
    return any(r in c.get('roles', []) for r in need)


def split_judges(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [part.strip() for part in value.split(',') if part.strip()]


def audit(user_id: str | None, action: str, resource_type: str, resource_id: str, details: dict | None = None):
    audit_log.append({
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'action': action,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'created_at': now_iso(),
        'details': details or {},
    })


seed_court_id = str(uuid.uuid4())
courts = [
    {
        'id': seed_court_id,
        'name': 'Белгородский районный суд Белгородской области',
        'court_type': 'DISTRICT_COURT',
        'region': 'Белгородская область',
        'address': '',
    }
]
case_staff: dict[str, set[str]] = {}
favorites: dict[str, set[str]] = {}
participants: list[dict] = []
audit_log: list[dict] = []

seed_original_text = '''Постановление по делу № 5-262/2017

31 марта 2017 года судья Белгородского районного суда Белгородской области Светашова С.Н., рассмотрев материал об административном правонарушении, предусмотренном ч. 1 ст. 20.1 КоАП РФ, в отношении ФИО1, установила обстоятельства дела.

Из материалов следует, что ФИО1 в общественном месте выражался нецензурной бранью, нарушал общественный порядок и спокойствие граждан. В судебном заседании ФИО1 вину признал. Объяснения гражданина Захаряна, рапорт сотрудника полиции и иные материалы подтверждают событие административного правонарушения.

Действия ФИО1 суд квалифицирует по ч. 1 ст. 20.1 КоАП РФ как мелкое хулиганство. Руководствуясь ст. 29.9-29.10 КоАП РФ, суд постановил признать ФИО1 виновным и назначить административное наказание.'''
seed_anonymized_text = seed_original_text.replace('Светашова С.Н.', 'ФИО2').replace('Захаряна', 'ФИО3')
seed_mappings = [
    {'placeholder': 'ФИО1', 'original_value': 'ФИО1', 'entity_type': 'PERSON_FULL_NAME'},
    {'placeholder': 'ФИО2', 'original_value': 'Светашова С.Н.', 'entity_type': 'PERSON_FULL_NAME'},
    {'placeholder': 'ФИО3', 'original_value': 'Захарян', 'entity_type': 'PERSON_FULL_NAME'},
]
seed_case = {
    'id': str(uuid.uuid4()),
    'court_id': seed_court_id,
    'court_name': 'Белгородский районный суд Белгородской области',
    'case_number': '5-262/2017',
    'document_number': '5-262/2017',
    'document_date': '2017-04-01',
    'instance': 'FIRST',
    'region': 'Белгородская область',
    'legal_article': 'ч. 1 ст. 20.1 КоАП РФ',
    'judicial_practice': 'Судебная практика по делам об административных правонарушениях. Мелкое хулиганство. Применение ч. 1 ст. 20.1 КоАП РФ.',
    'judge_names': ['Светашова С.Н.'],
    'judge_user_ids': [JUDGE_ID],
    'staff_user_ids': [JUDGE_ID],
    'status': 'PUBLISHED',
    'created_by_user_id': JUDGE_ID,
    'created_at': now_iso(),
}
cases = [seed_case]
case_staff[seed_case['id']] = {JUDGE_ID}
participants.append({
    'case_id': seed_case['id'],
    'user_id': USER_ID,
    'role': 'лицо, привлекаемое к административной ответственности',
    'display_name': 'ФИО1',
})
seed_doc_id = str(uuid.uuid4())
docs = [{
    'id': seed_doc_id,
    'case_id': seed_case['id'],
    'title': 'Постановление по делу № 5-262/2017',
    'act_type': 'RULING',
    'status': 'PUBLISHED',
    'document_date': '2017-04-01',
    'anonymization_job_id': None,
    'public_anonymized_document_id': seed_doc_id,
    'original_text': seed_original_text,
    'anonymized_text': seed_anonymized_text,
    'mappings': seed_mappings,
}]

for _doc in docs:
    ensure_doc_mappings(_doc)


class CreateCase(BaseModel):
    model_config = ConfigDict(extra='ignore')

    court_id: str
    case_number: str
    document_number: str
    document_date: str
    instance: str
    region: str
    legal_article: str | None = None
    judicial_practice: str | None = None
    judge_names: list[str] = []
    law_article: str | None = None
    practice_topic: str | None = None
    judges: list[str] | str | None = None
    staff_user_ids: list[str] = []


class UploadDoc(BaseModel):
    title: str
    act_type: str
    text: str
    content_format: str = 'PLAIN_TEXT'
    content: dict | None = None
    publication_redaction_mode: str = 'NORMATIVE'


class CourtIn(BaseModel):
    name: str
    court_type: str
    region: str
    address: str = ''


class CourtPatch(BaseModel):
    name: str | None = None
    court_type: str | None = None
    region: str | None = None
    address: str | None = None


class CaseStatusPatch(BaseModel):
    status: str


class ParticipantPatch(BaseModel):
    user_id: str | None = None
    role: str | None = None
    display_name: str | None = None


class CasePatch(BaseModel):
    model_config = ConfigDict(extra='ignore')

    court_id: str | None = None
    court_name: str | None = None
    case_number: str | None = None
    document_number: str | None = None
    document_date: str | None = None
    instance: str | None = None
    region: str | None = None
    legal_article: str | None = None
    judicial_practice: str | None = None
    judge_names: list[str] | str | None = None
    participant_user_ids: list[str] | None = None
    participants: list[ParticipantPatch] | None = None
    judge_user_ids: list[str] | None = None
    staff_user_ids: list[str] | None = None


class MappingIn(BaseModel):
    original_value: str
    placeholder: str | None = None
    entity_type: str
    mode: str = 'new'


class MappingPatchIn(BaseModel):
    placeholder: str | None = None
    original_value: str | None = None
    entity_type: str | None = None


class MergeMappingsIn(BaseModel):
    target_mapping_id: str
    source_mapping_ids: list[str]


class ReanonymizeIn(BaseModel):
    mappings: list[dict] = []
    publication_redaction_mode: str = 'NORMATIVE'




class RedactionDecisionIn(BaseModel):
    entity_key: str | None = None
    selected_text: str
    decision: str
    entity_class: str = 'PERSON'
    target_cluster_id: str | None = None
    reason: str = 'Решение пользователя'


class MergeEntityIn(BaseModel):
    target_cluster_id: str
class SaveAnonymizationIn(BaseModel):
    anonymized_text: str
    anonymized_content: dict | None = None
    content_format: str = 'TIPTAP_JSON'
    mappings: list[dict] = []
    recognized_but_kept: list[dict] | None = None
    review_entities: list[dict] | None = None
    review_markers: list[dict] | None = None
    pending_review: list[dict] | None = None
    pending_markers: list[dict] | None = None
    manual_decisions: list[dict] | None = None


class DraftScanIn(BaseModel):
    text: str
    content: dict | None = None
    content_format: str = 'TIPTAP_JSON'
    document_revision: int = 0


@app.get('/api/cases/dictionaries/entity-types')
def entity_types_dictionary():
    return [
        {'value': 'PERSON_FULL_NAME', 'label': 'ФИО'},
        {'value': 'CASE_PARTICIPANT', 'label': 'Участник дела'},
        {'value': 'JUDGE', 'label': 'Судья'},
        {'value': 'COURT_SECRETARY', 'label': 'Секретарь судебного заседания'},
        {'value': 'ADDRESS', 'label': 'Адрес'},
        {'value': 'LOCATION', 'label': 'Место'},
        {'value': 'ORGANIZATION', 'label': 'Организация'},
        {'value': 'PHONE', 'label': 'Телефон'},
        {'value': 'EMAIL', 'label': 'Электронная почта'},
        {'value': 'PASSPORT', 'label': 'Паспортные данные'},
        {'value': 'SNILS', 'label': 'СНИЛС'},
        {'value': 'INN', 'label': 'ИНН'},
        {'value': 'BIRTH_DATE', 'label': 'Дата рождения'},
        {'value': 'DATE', 'label': 'Дата'},
        {'value': 'OTHER', 'label': 'Иные данные'},
    ]


@app.get('/health')
def health(): return {'status': 'ok'}


@app.get('/ready')
def ready(): return {'status': 'ready'}


def case_summary(cs: dict, participant_role: str | None = None):
    item = {
        'id': cs['id'],
        'case_number': cs['case_number'],
        'document_number': cs['document_number'],
        'document_date': cs['document_date'],
        'court_name': cs['court_name'],
        'region': cs['region'],
        'instance': cs['instance'],
        'legal_article': cs['legal_article'],
        'judicial_practice': cs['judicial_practice'],
        'status': cs['status'],
    }
    if participant_role is not None:
        item['participant_role'] = participant_role
    return item


def can_access_case(c: dict, cs: dict):
    if 'ADMIN' in c.get('roles', []):
        return True
    user_id = c.get('sub')
    if not user_id:
        return False
    if any(p['case_id'] == cs['id'] and p['user_id'] == user_id for p in participants):
        return True
    return user_id in case_staff.get(cs['id'], set()) or user_id in cs.get('judge_user_ids', []) or cs.get('created_by_user_id') == user_id


def can_manage_case_status(c: dict, cs: dict):
    if 'ADMIN' in c.get('roles', []):
        return True
    user_id = c.get('sub')
    if not user_id:
        return False
    if 'JUDGE' in c.get('roles', []) and (user_id in case_staff.get(cs['id'], set()) or user_id in cs.get('judge_user_ids', [])):
        return True
    if allowed(c, ['COURT_STAFF', 'COURT_CLERK']) and (user_id in case_staff.get(cs['id'], set()) or user_id in cs.get('staff_user_ids', [])):
        return True
    return False


def can_manage_case(c: dict, cs: dict):
    if 'ADMIN' in c.get('roles', []):
        return True
    user_id = c.get('sub')
    if not user_id:
        return False
    if 'JUDGE' in c.get('roles', []) and (user_id in cs.get('judge_user_ids', []) or user_id in case_staff.get(cs['id'], set())):
        return True
    if allowed(c, ['COURT_STAFF', 'COURT_CLERK']) and (
        user_id in cs.get('staff_user_ids', []) or user_id in case_staff.get(cs['id'], set()) or cs.get('created_by_user_id') == user_id
    ):
        return True
    return False


def case_card(cs: dict):
    return {**cs, 'participants': [p for p in participants if p['case_id'] == cs['id']], 'documents': [public_doc(d) for d in docs if d['case_id'] == cs['id']]}


def find_document_and_case(document_id: str):
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d:
        err('NOT_FOUND', 'Документ не найден', 404)
    cs = next((x for x in cases if x['id'] == d['case_id']), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    return d, cs


def sync_doc_from_anonymization(d: dict, payload: dict):
    if 'anonymized_text' in payload:
        d['anonymized_text'] = payload.get('anonymized_text') or ''
    if 'mappings' in payload:
        d['mappings'] = [ensure_mapping_metadata(m) for m in (payload.get('mappings') or [])]
    if 'original_text' in payload:
        d['original_text'] = payload.get('original_text') or d.get('original_text', '')
    for k in ['entities','recognized_but_kept','review_entities','publication_redaction_mode','content_format','original_content','ner_provider','anonymized_content','review_markers','pending_review','pending_markers','manual_decisions']:
        if k in payload:
            d[k]=payload.get(k)


apply_doc_sync = sync_doc_from_anonymization


def anonymization_result_response(document: dict, case: dict | None = None) -> dict:
    return {
        'document_id': document['id'],
        'case_id': document.get('case_id') or (case.get('id') if case else None),
        'title': document.get('title'),
        'anonymized_text': document.get('anonymized_text', ''),
        'anonymized_content': document.get('anonymized_content'),
        'content_format': document.get('content_format', 'PLAIN_TEXT'),
        'entities': document.get('entities', []),
        'kept_entities': document.get('kept_entities', document.get('recognized_but_kept', [])),
        'pending_entities': document.get('pending_entities', document.get('pending_review', [])),
        'mappings': document.get('mappings', []),
        'recognized_but_kept': document.get('recognized_but_kept', []),
        'review_entities': document.get('review_entities', []),
        'review_markers': document.get('review_markers', []),
        'pending_review': document.get('pending_review', []),
        'pending_markers': document.get('pending_markers', []),
        'manual_decisions': document.get('manual_decisions', []),
        'publication_redaction_mode': document.get('publication_redaction_mode', 'NORMATIVE'),
        'ner_provider': document.get('ner_provider'),
    }


def _strip_redaction_marks(content: dict | None) -> dict | None:
    if not content:
        return content
    import copy
    data = copy.deepcopy(content)
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('marks'), list):
                node['marks'] = [m for m in node['marks'] if m.get('type') != 'redactionMention']
            if isinstance(node.get('content'), list):
                for ch in node['content']:
                    walk(ch)
        elif isinstance(node, list):
            for ch in node:
                walk(ch)
    walk(data)
    return data


def document_metadata(cs: dict):
    return {
        'case_number': cs.get('case_number'),
        'document_number': cs.get('document_number'),
        'court_name': cs.get('court_name'),
        'region': cs.get('region'),
        'document_date': cs.get('document_date'),
        'legal_article': cs.get('legal_article'),
        'judge_names': cs.get('judge_names', []),
    }


def public_doc(d: dict):
    return {
        'id': d['id'],
        'title': d['title'],
        'act_type': d['act_type'],
        'status': d['status'],
        'document_date': d.get('document_date'),
    }


@app.get('/api/cases/public/documents')
def pub_docs(
    authorization: str | None = Header(None), q: str | None = None, court_id: str | None = None, region: str | None = None,
    act_type: str | None = None, instance: str | None = None, legal_article: str | None = None, judge: str | None = None,
    document_date_from: str | None = None, document_date_to: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1)
):
    c = claims(authorization)
    items = []
    for d in docs:
        if d['status'] != 'PUBLISHED':
            continue
        cs = next((x for x in cases if x['id'] == d['case_id']), None)
        if not cs or cs.get('status') != 'PUBLISHED':
            continue
        if q and q.lower() not in (cs['case_number'] + ' ' + d['title']).lower():
            continue
        if court_id and cs['court_id'] != court_id:
            continue
        if region and cs['region'] != region:
            continue
        if act_type and d['act_type'] != act_type:
            continue
        if instance and cs['instance'] != instance:
            continue
        if legal_article and legal_article.lower() not in cs['legal_article'].lower():
            continue
        if judge and not any(judge.lower() in jn.lower() for jn in cs.get('judge_names', [])):
            continue
        if document_date_from and cs['document_date'] < document_date_from:
            continue
        if document_date_to and cs['document_date'] > document_date_to:
            continue
        items.append({'document_id': d['id'], 'case_id': d['case_id'], 'title': d['title'], 'court_name': cs['court_name'], 'case_number': cs['case_number'],
                      'document_number': cs['document_number'], 'document_date': cs['document_date'], 'act_type': d['act_type'], 'instance': cs['instance'],
                      'region': cs['region'], 'legal_article': cs['legal_article'], 'judicial_practice': cs['judicial_practice'],
                      'is_favorite': d['id'] in favorites.get(c.get('sub'), set())})
    start = (page - 1) * size
    return {'items': items[start:start + size], 'page': page, 'size': size, 'total': len(items)}


@app.post('/api/cases')
@app.post('/api/cases/')
def create_case(body: CreateCase, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')

    final_legal_article = body.legal_article or body.law_article
    final_judicial_practice = body.judicial_practice or body.practice_topic
    final_judge_names = body.judge_names or split_judges(body.judges)
    missing = []
    if not final_legal_article:
        missing.append('legal_article')
    if not final_judicial_practice:
        missing.append('judicial_practice')
    if missing:
        err('BAD_REQUEST', 'Не заполнены обязательные поля дела', 400, {'missing': missing})

    staff_user_ids = list(dict.fromkeys(body.staff_user_ids.copy()))
    judge_user_ids: list[str] = []
    if allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK']) and c.get('sub'):
        staff_user_ids.append(c['sub'])
    if 'JUDGE' in c.get('roles', []) and c.get('sub'):
        judge_user_ids.append(c['sub'])
    staff_user_ids = list(dict.fromkeys(staff_user_ids))
    judge_user_ids = list(dict.fromkeys(judge_user_ids))

    obj = {'id': str(uuid.uuid4()), 'court_id': body.court_id, 'court_name': next((x['name'] for x in courts if x['id'] == body.court_id), ''),
           'case_number': body.case_number, 'document_number': body.document_number, 'document_date': body.document_date,
           'instance': body.instance, 'region': body.region, 'legal_article': final_legal_article, 'judicial_practice': final_judicial_practice,
           'judge_names': final_judge_names, 'judge_user_ids': judge_user_ids, 'staff_user_ids': staff_user_ids, 'status': 'DRAFT',
           'created_by_user_id': c['sub'], 'created_at': now_iso()}
    case_staff[obj['id']] = set(staff_user_ids)
    cases.append(obj)
    audit(c.get('sub'), 'CREATE_CASE', 'CASE', obj['id'], {'case_number': obj['case_number']})
    return obj


@app.get('/api/cases/staff/my')
def my_staff_cases(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    if 'ADMIN' in c.get('roles', []):
        items = cases
    elif 'JUDGE' in c.get('roles', []):
        items = [cs for cs in cases if c['sub'] in cs.get('judge_user_ids', []) or c['sub'] in cs.get('staff_user_ids', [])]
    else:
        items = [cs for cs in cases if c['sub'] in cs.get('staff_user_ids', []) or cs.get('created_by_user_id') == c['sub']]
    return {'items': items, 'total': len(items)}


@app.get('/api/cases/me/participating')
def my_participating(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    case_roles = {(p['case_id'], p['role']) for p in participants if p['user_id'] == c['sub']}
    items = []
    for case_id, role in case_roles:
        cs = next((x for x in cases if x['id'] == case_id), None)
        if cs:
            items.append(case_summary(cs, role))
    return {'items': items, 'total': len(items)}


@app.get('/api/cases/admin/courts')
def admin_courts(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    return {'items': courts, 'total': len(courts)}


@app.post('/api/cases/admin/courts')
def create_court(body: CourtIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    court = {'id': str(uuid.uuid4()), **body.model_dump()}
    courts.append(court)
    audit(c.get('sub'), 'CREATE_COURT', 'COURT', court['id'])
    return court

@app.patch('/api/cases/admin/courts/{court_id}')
def update_court(court_id: str, body: CourtPatch, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    court = next((x for x in courts if x['id'] == court_id), None)
    if not court:
        err('NOT_FOUND', 'Суд не найден', 404)
    court.update(body.model_dump(exclude_none=True))
    audit(c.get('sub'), 'UPDATE_COURT', 'COURT', court_id)
    return court


@app.delete('/api/cases/admin/courts/{court_id}')
def delete_court(court_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    court = next((x for x in courts if x['id'] == court_id), None)
    if not court:
        err('NOT_FOUND', 'Суд не найден', 404)
    courts.remove(court)
    audit(c.get('sub'), 'DELETE_COURT', 'COURT', court_id)
    return {'ok': True}


@app.get('/api/cases/admin/audit')
def admin_audit(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    return {'items': audit_log, 'total': len(audit_log)}


async def check_service(name: str, url: str | None):
    if not url:
        return {'name': name, 'status': 'unknown'}
    try:
        async with httpx.AsyncClient(timeout=1.5) as cl:
            r = await cl.get(url)
        return {'name': name, 'status': 'ok' if r.status_code < 500 else 'unavailable'}
    except Exception:
        return {'name': name, 'status': 'unavailable'}


@app.get('/api/cases/admin/system-health')
async def system_health(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []):
        err('ACCESS_DENIED', 'Недостаточно прав')
    auth_url = f'{AUTH.rstrip("/")}/health' if AUTH else None
    return {'services': [
        await check_service('auth-service', auth_url),
        {'name': 'case-service', 'status': 'ok'},
        await check_service('ner-service', f'{NER}/health'),
        await check_service('anonymization-service', f'{ANON}/health'),
    ]}


@app.get('/api/cases/admin/ner-health')
async def ner_health(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['ADMIN', 'COURT_STAFF', 'JUDGE', 'COURT_CLERK']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=5.0) as cl:
        r = await cl.get(f'{NER}/health')
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=error_payload('NER_UNAVAILABLE', 'Сервис NER недоступен'))
    return r.json()


@app.get('/api/cases/me/favorites')
def get_favorites(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    ids = favorites.get(c['sub'], set())
    items = []
    for d in docs:
        if d['id'] in ids:
            cs = next((x for x in cases if x['id'] == d['case_id']), None)
            if cs:
                items.append({'document_id': d['id'], 'case_id': cs['id'], 'title': d['title'], 'court_name': cs['court_name'], 'case_number': cs['case_number'],
                              'document_number': cs['document_number'], 'document_date': cs['document_date'], 'act_type': d['act_type'], 'instance': cs['instance'],
                              'region': cs['region'], 'legal_article': cs['legal_article'], 'judicial_practice': cs['judicial_practice']})
    return {'items': items, 'total': len(items)}


@app.post('/api/cases/me/favorites/{document_id}')
@app.post('/api/cases/documents/{document_id}/favorite')
def add_fav(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    favorites.setdefault(c['sub'], set()).add(document_id)
    return {'ok': True}


@app.delete('/api/cases/me/favorites/{document_id}')
@app.delete('/api/cases/documents/{document_id}/favorite')
def del_fav(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    favorites.setdefault(c['sub'], set()).discard(document_id)
    return {'ok': True}

@app.patch('/api/cases/{case_id}/status')
def update_case_status(case_id: str, body: CaseStatusPatch, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['ADMIN', 'JUDGE', 'COURT_STAFF', 'COURT_CLERK']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    if body.status not in {'DRAFT', 'PUBLISHED', 'ARCHIVED'}:
        err('BAD_REQUEST', 'Недопустимый статус дела', 400, {'allowed': ['DRAFT', 'PUBLISHED', 'ARCHIVED']})
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_manage_case_status(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    old_status = cs.get('status')
    cs['status'] = body.status
    audit(c.get('sub'), 'UPDATE_CASE_STATUS', 'CASE', case_id, {'old_status': old_status, 'new_status': body.status})
    return cs

@app.patch('/api/cases/{case_id}')
def update_case(case_id: str, body: CasePatch, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['ADMIN', 'JUDGE', 'COURT_STAFF', 'COURT_CLERK']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')

    data = body.model_dump(exclude_unset=True)
    changed = {}
    for field in ['court_id', 'court_name', 'case_number', 'document_number', 'document_date', 'instance', 'region', 'legal_article', 'judicial_practice', 'judge_user_ids', 'staff_user_ids']:
        if field in data:
            changed[field] = {'old': cs.get(field), 'new': data[field]}
            cs[field] = data[field]
    if 'court_id' in data and 'court_name' not in data:
        cs['court_name'] = next((x['name'] for x in courts if x['id'] == data['court_id']), cs.get('court_name', ''))
    if 'judge_names' in data:
        new_judges = split_judges(data['judge_names'])
        changed['judge_names'] = {'old': cs.get('judge_names', []), 'new': new_judges}
        cs['judge_names'] = new_judges
    if 'staff_user_ids' in data:
        case_staff[case_id] = set(data['staff_user_ids'] or [])
    if 'participants' in data:
        participants[:] = [p for p in participants if p['case_id'] != case_id]
        for p in data['participants'] or []:
            item = p if isinstance(p, dict) else p.model_dump(exclude_none=True)
            if item.get('user_id'):
                participants.append({'case_id': case_id, 'user_id': item['user_id'], 'role': item.get('role', ''), 'display_name': item.get('display_name', '')})
        changed['participants'] = {'updated': True}
    elif 'participant_user_ids' in data:
        existing = {p['user_id'] for p in participants if p['case_id'] == case_id}
        for user_id in data['participant_user_ids'] or []:
            if user_id not in existing:
                participants.append({'case_id': case_id, 'user_id': user_id, 'role': '', 'display_name': ''})
        changed['participant_user_ids'] = {'new': data['participant_user_ids']}
    audit(c.get('sub'), 'UPDATE_CASE', 'CASE', case_id, changed)
    return case_card(cs)


@app.get('/api/cases/{case_id}')
def case_details(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_access_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    return case_card(cs)


@app.post('/api/cases/{case_id}/documents')
async def upload(case_id: str, body: UploadDoc, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    d = {'id': str(uuid.uuid4()), 'case_id': case_id, 'title': body.title, 'act_type': body.act_type, 'status': 'PROCESSING',
         'document_date': cs.get('document_date'), 'original_text': body.text, 'anonymized_text': body.text, 'mappings': [], 'content_format': body.content_format, 'original_content': body.content, 'publication_redaction_mode': body.publication_redaction_mode, 'recognized_but_kept': [], 'review_entities': []}
    docs.append(d)
    try:
        async with httpx.AsyncClient() as cl:
            r = await cl.post(f'{ANON}/internal/anonymization/process', headers={'X-Internal-Service-Token': INTERNAL}, json={'case_id': case_id, 'document_id': d['id'], 'title': body.title, 'text': body.text, 'metadata': {}, 'content_format': body.content_format, 'original_content': body.content, 'publication_redaction_mode': body.publication_redaction_mode})
        p = r.json()
        d['anonymization_job_id'] = p.get('job_id')
        sync_doc_from_anonymization(d, p)
        d['publication_redaction_mode'] = p.get('publication_redaction_mode', body.publication_redaction_mode)
    except Exception:
        d['anonymization_job_id'] = None
    d['status'] = 'ANONYMIZED'
    d['public_anonymized_document_id'] = d['id']
    audit(c.get('sub'), 'UPLOAD_DOCUMENT', 'DOCUMENT', d['id'], {'case_id': case_id})
    return anonymization_result_response(d, cs)


@app.patch('/api/cases/documents/{document_id}/entities/{entity_id}')
async def update_document_entity(document_id: str, entity_id: str, body: dict, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.patch(f'{ANON}/internal/anonymization/documents/{document_id}/entities/{entity_id}', headers={'X-Internal-Service-Token': INTERNAL}, json=body)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    sync_doc_from_anonymization(d, r.json())
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/entities/merge')
async def merge_entities(document_id: str, body: dict, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/entities/merge', headers={'X-Internal-Service-Token': INTERNAL}, json=body)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    sync_doc_from_anonymization(d, r.json())
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/entities/{entity_id}/mentions/{mention_id}/split')
async def split_mention(document_id: str, entity_id: str, mention_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/entities/{entity_id}/mentions/{mention_id}/split', headers={'X-Internal-Service-Token': INTERNAL})
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    sync_doc_from_anonymization(d, r.json())
    return anonymization_result_response(d, cs)


@app.delete('/api/cases/{case_id}/documents/{document_id}')
async def delete_document(case_id: str, document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['ADMIN', 'JUDGE', 'COURT_STAFF', 'COURT_CLERK']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    d = next((x for x in docs if x['id'] == document_id and x['case_id'] == case_id), None)
    if not d:
        err('NOT_FOUND', 'Документ не найден', 404)
    details = {'case_id': case_id, 'title': d.get('title')}
    docs.remove(d)
    try:
        async with httpx.AsyncClient(timeout=2.0) as cl:
            r = await cl.delete(f'{ANON}/internal/anonymization/documents/{document_id}', headers={'X-Internal-Service-Token': INTERNAL})
        if r.status_code >= 400:
            details['internal_delete'] = 'unavailable'
            details['internal_status_code'] = r.status_code
    except Exception as exc:
        details['internal_delete'] = 'unavailable'
        details['internal_error'] = str(exc)
    audit(c.get('sub'), 'DELETE_DOCUMENT', 'DOCUMENT', document_id, details)
    return {'ok': True}


@app.get('/api/cases/documents/{document_id}/anonymization')
async def get_document_anonymization(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    try:
        async with httpx.AsyncClient(timeout=5.0) as cl:
            r = await cl.get(f'{ANON}/internal/anonymization/documents/{document_id}', headers={'X-Internal-Service-Token': INTERNAL})
        if r.status_code < 400:
            sync_doc_from_anonymization(d, r.json())
    except Exception:
        pass
    ensure_doc_mappings(d)
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/mappings')
async def add_document_mapping(document_id: str, body: MappingIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/mappings', headers={'X-Internal-Service-Token': INTERNAL}, json=body.model_dump(exclude_none=True))
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    audit(c.get('sub'), 'ADD_MANUAL_MAPPING', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id'], 'original_value': body.original_value, 'placeholder': body.placeholder, 'mode': body.mode})
    return anonymization_result_response(d, cs)

@app.patch('/api/cases/documents/{document_id}/mappings/{mapping_id}')
async def update_document_mapping(document_id: str, mapping_id: str, body: MappingPatchIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.patch(
            f'{ANON}/internal/anonymization/documents/{document_id}/mappings/{mapping_id}',
            headers={'X-Internal-Service-Token': INTERNAL},
            json=body.model_dump(exclude_unset=True),
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    audit(c.get('sub'), 'UPDATE_MAPPING', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id'], 'mapping_id': mapping_id})
    return anonymization_result_response(d, cs)


@app.delete('/api/cases/documents/{document_id}/mappings/{mapping_id}')
async def delete_document_mapping(document_id: str, mapping_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.delete(f'{ANON}/internal/anonymization/documents/{document_id}/mappings/{mapping_id}', headers={'X-Internal-Service-Token': INTERNAL})
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    audit(c.get('sub'), 'DELETE_MAPPING', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id'], 'mapping_id': mapping_id})
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/mappings/merge')
async def merge_document_mappings(document_id: str, body: MergeMappingsIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(
            f'{ANON}/internal/anonymization/documents/{document_id}/mappings/merge',
            headers={'X-Internal-Service-Token': INTERNAL},
            json=body.model_dump(),
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    audit(c.get('sub'), 'MERGE_MAPPINGS', 'DOCUMENT', document_id, {
        'document_id': document_id,
        'case_id': d['case_id'],
        'target_mapping_id': body.target_mapping_id,
        'source_mapping_ids': body.source_mapping_ids,
    })
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/mappings/repair-placeholders')
async def repair_document_placeholders(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/mappings/repair-placeholders', headers={'X-Internal-Service-Token': INTERNAL})
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    audit(c.get('sub'), 'REPAIR_PLACEHOLDERS', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id']})
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/reanonymize')
async def reanonymize_document(document_id: str, body: ReanonymizeIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=20.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/reanonymize', headers={'X-Internal-Service-Token': INTERNAL}, json=body.model_dump())
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    sync_doc_from_anonymization(d, payload)
    d['status'] = 'ANONYMIZED'
    audit(c.get('sub'), 'REANONYMIZE_DOCUMENT', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id']})
    return anonymization_result_response(d, cs)




@app.post('/api/cases/documents/{document_id}/redaction-decisions')
async def redaction_decisions(document_id: str, body: RedactionDecisionIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d:
        err('NOT_FOUND', 'Документ не найден', 404)
    cs = next((x for x in cases if x['id'] == d['case_id']), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not allowed(c, ['ADMIN','JUDGE','COURT_STAFF','COURT_CLERK']) or not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав', 403)
    async with httpx.AsyncClient(timeout=30.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/documents/{document_id}/redaction-decisions', headers={'X-Internal-Service-Token': INTERNAL}, json=body.model_dump(exclude_none=True))
    if r.status_code >= 400:
        detail = r.json() if r.headers.get('content-type','').startswith('application/json') else error_payload('UPSTREAM_ERROR','Ошибка сервиса обезличивания')
        raise HTTPException(status_code=r.status_code, detail=detail if isinstance(detail, dict) else error_payload('UPSTREAM_ERROR', str(detail)))
    apply_doc_sync(d, r.json())
    return anonymization_result_response(d, cs)
@app.post('/api/cases/documents/{document_id}/save-anonymization')
def save_anonymization(document_id: str, body: SaveAnonymizationIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    d['anonymized_text'] = body.anonymized_text
    d['anonymized_content'] = body.anonymized_content
    d['content_format'] = body.content_format
    d['mappings'] = [ensure_mapping_metadata(m) for m in body.mappings]
    for fld in ['recognized_but_kept', 'review_entities', 'review_markers', 'pending_review', 'pending_markers', 'manual_decisions']:
        val = getattr(body, fld)
        if val is not None:
            d[fld] = val
    if d.get('status') == 'PROCESSING':
        d['status'] = 'ANONYMIZED'
    audit(c.get('sub'), 'SAVE_ANONYMIZATION', 'DOCUMENT', document_id, {'document_id': document_id, 'case_id': d['case_id'], 'action': 'SAVE_EDITED_ANONYMIZED_DOCUMENT'})
    return anonymization_result_response(d, cs)


@app.post('/api/cases/documents/{document_id}/draft-scan')
async def draft_scan(document_id: str, body: DraftScanIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    d, cs = find_document_and_case(document_id)
    if not allowed(c, ['ADMIN', 'JUDGE', 'COURT_STAFF', 'COURT_CLERK']) or not can_manage_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    async with httpx.AsyncClient(timeout=20.0) as cl:
        r = await cl.post(
            f'{ANON}/internal/anonymization/documents/{document_id}/draft-scan',
            headers={'X-Internal-Service-Token': INTERNAL},
            json=body.model_dump(),
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    payload = r.json()
    d['pending_review'] = payload.get('pending_review', [])
    d['pending_markers'] = payload.get('pending_markers', [])
    audit(c.get('sub'), 'SCAN_EDITED_DRAFT', 'DOCUMENT', document_id, {'case_id': cs['id'], 'pending_count': len(d['pending_review'])})
    return payload


@app.post('/api/cases/documents/{document_id}/publish')
def publish_document(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d:
        err('NOT_FOUND', 'Документ не найден', 404)
    cs = next((x for x in cases if x['id'] == d['case_id']), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_manage_case_status(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    if not (d.get('anonymized_text') or '').strip():
        err('DOCUMENT_TEXT_NOT_READY', 'Текст документа ещё не готов', 409)
    if d['status'] not in ['ANONYMIZED', 'PUBLISHED']:
        err('BAD_REQUEST', 'Документ должен быть обезличен перед публикацией', 400)
    pending_entities = d.get('pending_review', [])
    review_entities = d.get('review_entities', [])
    pending_entity_count = len(pending_entities)
    pending_mention_count = sum(int(x.get('mentions_count') or 1) for x in pending_entities)
    review_entity_count = len(review_entities)
    review_mention_count = sum(len(x.get('mentions', [])) if isinstance(x.get('mentions'), list) and x.get('mentions') else int(x.get('occurrences_count') or 1) for x in review_entities)
    if pending_entity_count > 0 or review_entity_count > 0:
        audit(c.get('sub'), 'BLOCK_PUBLICATION_REVIEW_REQUIRED', 'DOCUMENT', document_id, {'case_id': d['case_id'], 'pending_entity_count': pending_entity_count, 'review_entity_count': review_entity_count})
        err('PENDING_REDACTION_REVIEW', 'Документ содержит сведения, требующие проверки перед публикацией.', 409, {'pending_entity_count': pending_entity_count, 'pending_mention_count': pending_mention_count, 'review_entity_count': review_entity_count, 'review_mention_count': review_mention_count})
    d['status'] = 'PUBLISHED'
    if any(doc['case_id'] == cs['id'] and doc['status'] == 'PUBLISHED' for doc in docs):
        cs['status'] = 'PUBLISHED'
    audit(c.get('sub'), 'PUBLISH_DOCUMENT', 'DOCUMENT', document_id, {'case_id': d['case_id']})
    return {'ok': True, 'document_id': d['id'], 'document_status': d['status'], 'case_id': d['case_id'], 'case_status': cs['status']}


@app.get('/api/cases/documents/{document_id}/status')
def document_status(document_id: str, authorization: str | None = Header(None)):
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d:
        err('NOT_FOUND', 'Документ не найден', 404)
    return {'document_id': d['id'], 'status': d['status'], 'anonymization_job_id': d.get('anonymization_job_id'), 'case_id': d['case_id']}


@app.get('/api/cases/public/documents/{document_id}')
async def pub_doc(document_id: str):
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d or d.get('status') != 'PUBLISHED':
        err('NOT_FOUND', 'Документ не найден', 404)
    cs = next((x for x in cases if x['id'] == d['case_id']), None)
    if not cs or cs.get('status') != 'PUBLISHED':
        err('NOT_FOUND', 'Документ не найден', 404)

    anonymized_text = d.get('anonymized_text') or ''
    if not anonymized_text.strip() and d.get('public_anonymized_document_id'):
        async with httpx.AsyncClient() as cl:
            r = await cl.get(
                f'{ANON}/internal/anonymization/documents/{d["public_anonymized_document_id"]}/public',
                headers={'X-Internal-Service-Token': INTERNAL},
            )
        if r.status_code < 400:
            anonymized_text = r.json().get('anonymized_text') or ''

    if not anonymized_text.strip():
        err('DOCUMENT_TEXT_NOT_READY', 'Текст документа ещё не готов или не опубликован', 409)

    return {
        'document_id': d['id'],
        'case_id': cs['id'],
        'title': d['title'],
        'anonymized_text': anonymized_text,
        'anonymized_content': _strip_redaction_marks(d.get('anonymized_content')),
        'content_format': d.get('content_format', 'PLAIN_TEXT'),
        'metadata': document_metadata(cs),
    }


@app.get('/api/cases/{case_id}/restored')
async def restored(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if c.get('sub') is None:
        err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_access_case(c, cs):
        err('ACCESS_DENIED', 'Недостаточно прав')
    ds = [d for d in docs if d['case_id'] == case_id]
    out = []
    for d in ds:
        if d.get('original_text') is not None:
            out.append({
                'document_id': d['id'],
                'title': d['title'],
                'original_text': d.get('original_text', ''),
                'original_content': d.get('original_content'),
                'anonymized_text': d.get('anonymized_text', ''),
                'anonymized_content': d.get('anonymized_content'),
                'content_format': d.get('content_format', 'PLAIN_TEXT'),
                'mappings': d.get('mappings', []),
            })
        else:
            async with httpx.AsyncClient() as cl:
                rr = await cl.get(f'{ANON}/internal/anonymization/documents/{d["id"]}/restored', headers={'X-Internal-Service-Token': INTERNAL})
            out.append({'document_id': d['id'], 'title': d['title'], **rr.json()})
    audit(c.get('sub'), 'VIEW_RESTORED_CASE', 'CASE', case_id)
    return {'case': cs, 'documents': out}
