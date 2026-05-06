from datetime import datetime
import os
import uuid

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from jose import jwt
from pydantic import BaseModel

app = FastAPI(title='case-service')
SECRET = os.getenv('JWT_SECRET', 'secret')
ALG = os.getenv('JWT_ALGORITHM', 'HS256')
INTERNAL = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-secret-token')
ANON = os.getenv('ANONYMIZATION_SERVICE_URL', 'http://anonymization-service:8000')
AUTH = os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8000')
NER = os.getenv('NER_SERVICE_URL', 'http://ner-service:8000')

USER_ID = "00000000-0000-0000-0000-000000000002"
JUDGE_ID = "00000000-0000-0000-0000-000000000004"
SEED_CASE_ID = "00000000-0000-0000-0000-000000000101"
SEED_COURT_ID = "00000000-0000-0000-0000-000000000201"
SEED_DOC_ID = "00000000-0000-0000-0000-000000000301"


def err(code, msg, status=403, details=None):
    raise HTTPException(status_code=status, detail={'error': {'code': code, 'message': msg, 'details': details or {}}})


def claims(auth: str | None):
    if not auth:
        return {'roles': ['PUBLIC'], 'sub': None, 'username': None}
    try:
        return jwt.decode(auth.replace('Bearer ', ''), SECRET, algorithms=[ALG])
    except Exception:
        return {'roles': ['PUBLIC'], 'sub': None, 'username': None}


def allowed(c, need):
    return any(r in c.get('roles', []) for r in need)


def now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def audit(user_id: str | None, action: str, resource_type: str, resource_id: str, details: dict | None = None):
    audit_log.append({'id': str(uuid.uuid4()), 'user_id': user_id, 'action': action, 'resource_type': resource_type, 'resource_id': resource_id, 'created_at': now_iso(), 'details': details or {}})


courts = [
    {'id': SEED_COURT_ID, 'name': 'Белгородский районный суд Белгородской области', 'court_type': 'DISTRICT_COURT', 'region': 'Белгородская область', 'address': 'Белгородская область'},
    {'id': '00000000-0000-0000-0000-000000000202', 'name': 'Центральный районный суд г. Читы', 'court_type': 'DISTRICT_COURT', 'region': 'Забайкальский край', 'address': 'г. Чита'},
]
case_staff: dict[str, set[str]] = {}
favorites: dict[str, set[str]] = {}
participants: list[dict] = []
audit_log: list[dict] = []

SEED_ORIGINAL_TEXT = """Материал № 5-262/2017 г.

ПОСТАНОВЛЕНИЕ

01 апреля 2017 года г. Белгород

Белгородский районный суд Белгородской области в составе председательствующего судьи Светашовой С.Н., с участием лица, привлекаемого к административной ответственности ФИО1, рассмотрел материалы дела об административном правонарушении, предусмотренном ч. 1 ст. 20.1 КоАП РФ.

УСТАНОВИЛ:

31.03.2017 г. около 20 часов 05 минут в ТРЦ Сити-Молл Белгородский гражданин Захарян нарушил общественный порядок и выразил явное неуважение к обществу. Вина подтверждается материалами дела, протоколом, рапортом и объяснениями свидетелей.

Суд квалифицирует действия по ч. 1 ст. 20.1 КоАП РФ и учитывает характер совершенного правонарушения, данные о личности и обстоятельства дела.

ПОСТАНОВИЛ:

Признать ФИО1 виновным в совершении административного правонарушения, предусмотренного ч. 1 ст. 20.1 КоАП РФ, и назначить наказание в виде административного ареста сроком на 5 суток.

Постановление может быть обжаловано в 10-дневный срок в Белгородский областной суд.

Судья Светашова С.Н.
"""

SEED_ANONYMIZED_TEXT = SEED_ORIGINAL_TEXT.replace('Светашовой С.Н.', 'ФИО2').replace('Светашова С.Н.', 'ФИО2').replace('Захарян', 'ФИО3')
SEED_MAPPINGS = [
    {'placeholder': 'ФИО1', 'original_value': 'ФИО1', 'entity_type': 'CASE_PARTICIPANT'},
    {'placeholder': 'ФИО2', 'original_value': 'Светашова С.Н.', 'entity_type': 'PERSON_FULL_NAME'},
    {'placeholder': 'ФИО3', 'original_value': 'Захарян', 'entity_type': 'PERSON_LAST_NAME'},
]

seed_case = {
    'id': SEED_CASE_ID, 'court_id': SEED_COURT_ID, 'court_name': 'Белгородский районный суд Белгородской области',
    'case_number': '5-262/2017', 'document_number': '5-262/2017', 'document_date': '2017-04-01', 'instance': 'FIRST',
    'region': 'Белгородская область', 'legal_article': 'ч. 1 ст. 20.1 КоАП РФ',
    'judicial_practice': 'Судебная практика по делам об административных правонарушениях. Мелкое хулиганство. Применение ч. 1 ст. 20.1 КоАП РФ.',
    'judge_names': ['Светашова С.Н.'], 'judge_user_ids': [JUDGE_ID], 'staff_user_ids': [JUDGE_ID], 'status': 'PUBLISHED', 'created_by_user_id': JUDGE_ID, 'created_at': now_iso(),
}
cases = [seed_case]
case_staff[SEED_CASE_ID] = {JUDGE_ID}
participants.append({'case_id': SEED_CASE_ID, 'user_id': USER_ID, 'role': 'лицо, привлекаемое к административной ответственности', 'display_name': 'ФИО1'})
docs = [{'id': SEED_DOC_ID, 'case_id': SEED_CASE_ID, 'title': 'Постановление по делу № 5-262/2017', 'act_type': 'RULING', 'status': 'PUBLISHED', 'public_anonymized_document_id': SEED_DOC_ID, 'anonymization_job_id': 'seed-job', 'document_date': '2017-04-01', 'original_text': SEED_ORIGINAL_TEXT, 'anonymized_text': SEED_ANONYMIZED_TEXT, 'mappings': SEED_MAPPINGS}]


class CreateCase(BaseModel):
    court_id: str | None = None
    case_number: str
    document_number: str | None = None
    document_date: str | None = None
    instance: str | None = None
    region: str | None = None
    legal_article: str | None = None
    judicial_practice: str | None = None
    judge_names: list[str] | None = None
    staff_user_ids: list[str] | None = None
    law_article: str | None = None
    practice_topic: str | None = None
    judges: list[str] | str | None = None
    staff_ids: list[str] | None = None


class UploadDoc(BaseModel):
    title: str
    act_type: str
    text: str


class CourtIn(BaseModel):
    name: str
    court_type: str = 'DISTRICT_COURT'
    region: str
    address: str | None = ''


def normalize_judges(body: CreateCase) -> list[str]:
    if body.judge_names:
        return body.judge_names
    if isinstance(body.judges, list):
        return [x.strip() for x in body.judges if str(x).strip()]
    if isinstance(body.judges, str):
        return [x.strip() for x in body.judges.split(',') if x.strip()]
    return []


def can_access_case(c: dict, cs: dict) -> bool:
    if 'ADMIN' in c.get('roles', []):
        return True
    user_id = c.get('sub')
    if not user_id:
        return False
    return any(p['case_id'] == cs['id'] and p['user_id'] == user_id for p in participants) or user_id in case_staff.get(cs['id'], set()) or user_id in cs.get('judge_user_ids', []) or cs.get('created_by_user_id') == user_id


@app.get('/health')
def health(): return {'status': 'ok'}


@app.get('/ready')
def ready(): return {'status': 'ready'}


@app.get('/api/cases/public/documents')
def pub_docs(authorization: str | None = Header(None), q: str | None = None, court_id: str | None = None, region: str | None = None, act_type: str | None = None, instance: str | None = None, legal_article: str | None = None, judge: str | None = None, document_date_from: str | None = None, document_date_to: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1)):
    c = claims(authorization)
    items = []
    for d in docs:
        if d['status'] != 'PUBLISHED':
            continue
        cs = next((x for x in cases if x['id'] == d['case_id']), None)
        if not cs:
            continue
        searchable = ' '.join([cs.get('case_number', ''), cs.get('document_number', ''), d.get('title', ''), cs.get('legal_article', ''), cs.get('court_name', '')])
        if q and q.lower() not in searchable.lower(): continue
        if court_id and cs['court_id'] != court_id: continue
        if region and cs['region'] != region: continue
        if act_type and d['act_type'] != act_type: continue
        if instance and cs['instance'] != instance: continue
        if legal_article and legal_article.lower() not in cs['legal_article'].lower(): continue
        if judge and not any(judge.lower() in jn.lower() for jn in cs.get('judge_names', [])): continue
        if document_date_from and cs['document_date'] < document_date_from: continue
        if document_date_to and cs['document_date'] > document_date_to: continue
        items.append({'document_id': d['id'], 'case_id': d['case_id'], 'title': d['title'], 'court_name': cs['court_name'], 'case_number': cs['case_number'], 'document_number': cs['document_number'], 'document_date': cs['document_date'], 'act_type': d['act_type'], 'instance': cs['instance'], 'region': cs['region'], 'legal_article': cs['legal_article'], 'judicial_practice': cs['judicial_practice'], 'is_favorite': d['id'] in favorites.get(c.get('sub'), set())})
    start = (page - 1) * size
    return {'items': items[start:start + size], 'page': page, 'size': size, 'total': len(items)}


@app.post('/api/cases')
@app.post('/api/cases/')
def create_case(body: CreateCase, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')
    legal_article = (body.legal_article or body.law_article or '').strip()
    judicial_practice = (body.judicial_practice or body.practice_topic or '').strip()
    missing = []
    if not body.case_number: missing.append('case_number')
    if not legal_article: missing.append('legal_article')
    if not judicial_practice: missing.append('judicial_practice')
    if missing:
        err('BAD_REQUEST', 'Не заполнены обязательные поля дела', 400, {'missing': missing})
    court = next((x for x in courts if x['id'] == body.court_id), None)
    staff_ids = list(body.staff_user_ids or body.staff_ids or [])
    user_id = c.get('sub')
    if user_id and allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK']) and user_id not in staff_ids:
        staff_ids.append(user_id)
    obj = {'id': str(uuid.uuid4()), 'court_id': body.court_id or '', 'court_name': court['name'] if court else '', 'case_number': body.case_number, 'document_number': body.document_number or '', 'document_date': body.document_date or '', 'instance': body.instance or 'FIRST', 'region': body.region or (court['region'] if court else ''), 'legal_article': legal_article, 'judicial_practice': judicial_practice, 'judge_names': normalize_judges(body), 'judge_user_ids': [user_id] if user_id and 'JUDGE' in c.get('roles', []) else [], 'staff_user_ids': staff_ids, 'status': 'DRAFT', 'created_by_user_id': user_id, 'created_at': now_iso()}
    cases.append(obj)
    case_staff[obj['id']] = set(staff_ids)
    audit(user_id, 'CREATE_CASE', 'CASE', obj['id'], {'case_number': obj['case_number']})
    return obj


@app.get('/api/cases/staff/my')
def my_staff_cases(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']): err('ACCESS_DENIED', 'Недостаточно прав')
    if 'ADMIN' in c.get('roles', []):
        items = cases
    elif 'JUDGE' in c.get('roles', []):
        items = [cs for cs in cases if c['sub'] in cs.get('judge_user_ids', []) or c['sub'] in case_staff.get(cs['id'], set())]
    else:
        items = [cs for cs in cases if c['sub'] in case_staff.get(cs['id'], set()) or cs.get('created_by_user_id') == c['sub']]
    return {'items': items, 'total': len(items)}


@app.get('/api/cases/me/participating')
def my_participating(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'): err('UNAUTHORIZED', 'invalid token', 401)
    items = []
    for p in participants:
        if p['user_id'] != c['sub']: continue
        cs = next((x for x in cases if x['id'] == p['case_id']), None)
        if cs:
            items.append({**cs, 'participant_role': p['role']})
    return {'items': items, 'total': len(items)}


@app.get('/api/cases/me/favorites')
def get_favorites(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'): err('UNAUTHORIZED', 'invalid token', 401)
    ids = favorites.get(c['sub'], set())
    items = []
    for d in docs:
        if d['id'] in ids:
            cs = next((x for x in cases if x['id'] == d['case_id']), None)
            if cs:
                items.append({'document_id': d['id'], 'case_id': cs['id'], 'title': d['title'], 'court_name': cs['court_name'], 'case_number': cs['case_number'], 'document_number': cs['document_number'], 'document_date': cs['document_date'], 'act_type': d['act_type'], 'instance': cs['instance'], 'region': cs['region'], 'legal_article': cs['legal_article'], 'judicial_practice': cs['judicial_practice']})
    return {'items': items, 'total': len(items)}


@app.post('/api/cases/me/favorites/{document_id}')
@app.post('/api/cases/documents/{document_id}/favorite')
def add_fav(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'): err('UNAUTHORIZED', 'invalid token', 401)
    favorites.setdefault(c['sub'], set()).add(document_id)
    return {'ok': True}


@app.delete('/api/cases/me/favorites/{document_id}')
@app.delete('/api/cases/documents/{document_id}/favorite')
def del_fav(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'): err('UNAUTHORIZED', 'invalid token', 401)
    favorites.setdefault(c['sub'], set()).discard(document_id)
    return {'ok': True}


@app.get('/api/cases/{case_id}')
def case_details(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'): err('UNAUTHORIZED', 'invalid token', 401)
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs: err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_access_case(c, cs): err('ACCESS_DENIED', 'Недостаточно прав')
    return {**cs, 'participants': [p for p in participants if p['case_id'] == case_id], 'documents': [d for d in docs if d['case_id'] == case_id]}


@app.post('/api/cases/{case_id}/documents')
async def upload(case_id: str, body: UploadDoc, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']): err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs: err('NOT_FOUND', 'Дело не найдено', 404)
    d = {'id': str(uuid.uuid4()), 'case_id': case_id, 'title': body.title, 'act_type': body.act_type, 'status': 'PROCESSING', 'document_date': cs.get('document_date', '')}
    docs.append(d)
    async with httpx.AsyncClient(timeout=25.0) as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/process', headers={'X-Internal-Service-Token': INTERNAL}, json={'case_id': case_id, 'document_id': d['id'], 'title': body.title, 'text': body.text, 'metadata': {}})
    if r.status_code >= 400:
        d['status'] = 'ERROR'; err('BAD_REQUEST', 'Не удалось обезличить документ', 400, {'response': r.text})
    p = r.json(); d['status'] = 'ANONYMIZED'; d['anonymization_job_id'] = p['job_id']; d['public_anonymized_document_id'] = d['id']
    audit(c.get('sub'), 'UPLOAD_DOCUMENT', 'DOCUMENT', d['id'], {'case_id': case_id})
    return {'document_id': d['id'], 'status': d['status'], 'anonymization_job_id': d['anonymization_job_id']}


@app.get('/api/cases/public/documents/{document_id}')
async def pub_doc(document_id: str):
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d or d.get('status') != 'PUBLISHED': err('NOT_FOUND', 'Документ не найден', 404)
    if d.get('anonymized_text'):
        return {'document_id': d['id'], 'case_id': d['case_id'], 'title': d['title'], 'anonymized_text': d['anonymized_text'], 'metadata': {}}
    async with httpx.AsyncClient() as cl:
        r = await cl.get(f'{ANON}/internal/anonymization/documents/{document_id}/public', headers={'X-Internal-Service-Token': INTERNAL})
    if r.status_code >= 400: err('NOT_FOUND', 'Документ не найден', 404)
    return r.json()


@app.get('/api/cases/{case_id}/restored')
async def restored(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if c.get('sub') is None: err('ACCESS_DENIED', 'Недостаточно прав')
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs: err('NOT_FOUND', 'Дело не найдено', 404)
    if not can_access_case(c, cs): err('ACCESS_DENIED', 'Недостаточно прав')
    out = []
    async with httpx.AsyncClient() as cl:
        for d in [d for d in docs if d['case_id'] == case_id]:
            if d.get('original_text'):
                out.append({'document_id': d['id'], 'title': d['title'], 'original_text': d.get('original_text', ''), 'anonymized_text': d.get('anonymized_text', ''), 'mappings': d.get('mappings', [])})
            else:
                rr = await cl.get(f'{ANON}/internal/anonymization/documents/{d["id"]}/restored', headers={'X-Internal-Service-Token': INTERNAL})
                if rr.status_code < 400: out.append({'document_id': d['id'], 'title': d['title'], **rr.json()})
    audit(c.get('sub'), 'VIEW_RESTORED_CASE', 'CASE', case_id)
    return {'case': cs, 'documents': out}


@app.get('/api/cases/documents/{document_id}/status')
def doc_status(document_id: str, authorization: str | None = Header(None)):
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d: err('NOT_FOUND', 'Документ не найден', 404)
    return {'document_id': d['id'], 'status': d.get('status'), 'anonymization_job_id': d.get('anonymization_job_id'), 'case_id': d.get('case_id')}


@app.post('/api/cases/documents/{document_id}/publish')
def publish(document_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']): err('ACCESS_DENIED', 'Недостаточно прав')
    d = next((x for x in docs if x['id'] == document_id), None)
    if not d: err('NOT_FOUND', 'Документ не найден', 404)
    if d.get('status') not in ['ANONYMIZED', 'PUBLISHED']: err('BAD_REQUEST', 'Документ ещё не готов к публикации', 400)
    d['status'] = 'PUBLISHED'; audit(c.get('sub'), 'PUBLISH_DOCUMENT', 'DOCUMENT', document_id)
    return {'ok': True, 'document_id': document_id, 'status': d['status']}


@app.get('/api/cases/admin/courts')
def list_courts(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    return {'items': courts, 'total': len(courts)}


@app.post('/api/cases/admin/courts')
def create_court(body: CourtIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    court = {'id': str(uuid.uuid4()), 'name': body.name, 'court_type': body.court_type, 'region': body.region, 'address': body.address or ''}
    courts.append(court); audit(c.get('sub'), 'CREATE_COURT', 'COURT', court['id'])
    return court


@app.patch('/api/cases/admin/courts/{court_id}')
def update_court(court_id: str, body: CourtIn, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    court = next((x for x in courts if x['id'] == court_id), None)
    if not court: err('NOT_FOUND', 'Суд не найден', 404)
    court.update({'name': body.name, 'court_type': body.court_type, 'region': body.region, 'address': body.address or ''}); audit(c.get('sub'), 'UPDATE_COURT', 'COURT', court_id)
    return court


@app.delete('/api/cases/admin/courts/{court_id}')
def delete_court(court_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    global courts
    if not any(x['id'] == court_id for x in courts): err('NOT_FOUND', 'Суд не найден', 404)
    courts = [x for x in courts if x['id'] != court_id]; audit(c.get('sub'), 'DELETE_COURT', 'COURT', court_id)
    return {'ok': True}


@app.get('/api/cases/admin/audit')
def get_audit(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    return {'items': list(reversed(audit_log)), 'total': len(audit_log)}


@app.get('/api/cases/admin/system-health')
async def system_health(authorization: str | None = Header(None)):
    c = claims(authorization)
    if 'ADMIN' not in c.get('roles', []): err('ACCESS_DENIED', 'Недостаточно прав')
    targets = [('auth-service', f'{AUTH}/health'), ('case-service', None), ('ner-service', f'{NER}/health'), ('anonymization-service', f'{ANON}/health')]
    services = []
    async with httpx.AsyncClient(timeout=3.0) as cl:
        for name, url in targets:
            if url is None:
                services.append({'name': name, 'status': 'ok'}); continue
            try:
                r = await cl.get(url); services.append({'name': name, 'status': 'ok' if r.status_code < 400 else 'unavailable'})
            except Exception:
                services.append({'name': name, 'status': 'unavailable'})
    return {'services': services}
