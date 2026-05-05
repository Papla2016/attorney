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

USER_ID = "00000000-0000-0000-0000-000000000002"
STAFF_ID = "00000000-0000-0000-0000-000000000003"
JUDGE_ID = "00000000-0000-0000-0000-000000000004"


def err(code, msg, status=403):
    raise HTTPException(status_code=status, detail={'error': {'code': code, 'message': msg, 'details': {}}})


def claims(auth: str | None):
    if not auth:
        return {'roles': ['PUBLIC'], 'sub': None}
    try:
        return jwt.decode(auth.replace('Bearer ', ''), SECRET, algorithms=[ALG])
    except Exception:
        return {'roles': ['PUBLIC'], 'sub': None}


def allowed(c, need):
    return any(r in c.get('roles', []) for r in need)


courts = [{'id': str(uuid.uuid4()), 'name': 'Центральный районный суд', 'court_type': 'DISTRICT_COURT', 'region': 'Забайкальский край'}]
case_staff: dict[str, set[str]] = {}
favorites: dict[str, set[str]] = {}
participants: list[dict] = []

seed_case = {
    'id': str(uuid.uuid4()), 'court_id': courts[0]['id'], 'court_name': courts[0]['name'], 'case_number': '2-3701/2025',
    'document_number': '2-3701/2025~М-2392/2025', 'document_date': '2025-10-21', 'instance': 'FIRST', 'region': 'Забайкальский край',
    'legal_article': 'ст. 454 ГК РФ', 'judicial_practice': 'Судебная практика по договору купли-продажи', 'judge_names': ['judge'],
    'judge_user_ids': [JUDGE_ID], 'staff_user_ids': [JUDGE_ID], 'status': 'PUBLISHED', 'created_by_user_id': JUDGE_ID,
    'created_at': datetime.utcnow().isoformat() + 'Z'
}
cases = [seed_case]
case_staff[seed_case['id']] = {JUDGE_ID}
participants.append({'case_id': seed_case['id'], 'user_id': USER_ID, 'role': 'подсудимый'})
docs = [{'id': str(uuid.uuid4()), 'case_id': seed_case['id'], 'title': 'Решение', 'act_type': 'DECISION', 'status': 'PUBLISHED', 'public_anonymized_document_id': None}]


class CreateCase(BaseModel):
    court_id: str
    case_number: str
    document_number: str
    document_date: str
    instance: str
    region: str
    legal_article: str
    judicial_practice: str
    judge_names: list[str] = []
    staff_user_ids: list[str] = []


class UploadDoc(BaseModel):
    title: str
    act_type: str
    text: str


@app.get('/health')
def health(): return {'status': 'ok'}


@app.get('/ready')
def ready(): return {'status': 'ready'}


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
        if not cs:
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
    obj = {'id': str(uuid.uuid4()), 'court_id': body.court_id, 'court_name': next((x['name'] for x in courts if x['id'] == body.court_id), ''),
           'case_number': body.case_number, 'document_number': body.document_number, 'document_date': body.document_date,
           'instance': body.instance, 'region': body.region, 'legal_article': body.legal_article, 'judicial_practice': body.judicial_practice,
           'judge_names': body.judge_names, 'judge_user_ids': [], 'staff_user_ids': body.staff_user_ids.copy(), 'status': 'DRAFT',
           'created_by_user_id': c['sub'], 'created_at': datetime.utcnow().isoformat() + 'Z'}
    if allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK']):
        obj['staff_user_ids'].append(c['sub'])
        case_staff[obj['id']] = set(obj['staff_user_ids'])
    else:
        case_staff[obj['id']] = set(obj['staff_user_ids'])
    if 'JUDGE' in c.get('roles', []):
        obj['judge_user_ids'].append(c['sub'])
    cases.append(obj)
    return obj


@app.get('/api/cases/staff/my')
def my_staff_cases(authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']):
        err('ACCESS_DENIED', 'Недостаточно прав')
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
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    case_roles = {(p['case_id'], p['role']) for p in participants if p['user_id'] == c['sub']}
    items = []
    for case_id, role in case_roles:
        cs = next((x for x in cases if x['id'] == case_id), None)
        if cs:
            items.append({'id': cs['id'], 'case_number': cs['case_number'], 'court_name': cs['court_name'], 'region': cs['region'], 'status': cs['status'], 'participant_role': role})
    return {'items': items, 'total': len(items)}


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


@app.get('/api/cases/{case_id}')
def case_details(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not c.get('sub'):
        err('UNAUTHORIZED', 'invalid token', 401)
    cs = next((x for x in cases if x['id'] == case_id), None)
    if not cs:
        err('NOT_FOUND', 'Дело не найдено', 404)
    is_participant = any(p['case_id'] == case_id and p['user_id'] == c['sub'] for p in participants)
    is_staff_related = c['sub'] in case_staff.get(case_id, set()) or c['sub'] in cs.get('judge_user_ids', []) or cs.get('created_by_user_id') == c['sub']
    if 'ADMIN' not in c.get('roles', []) and not is_participant and not is_staff_related:
        err('ACCESS_DENIED', 'Недостаточно прав')
    return {**cs, 'participants': [p for p in participants if p['case_id'] == case_id], 'documents': [d for d in docs if d['case_id'] == case_id]}

@app.post('/api/cases/{case_id}/documents')
async def upload(case_id: str, body: UploadDoc, authorization: str | None = Header(None)):
    c = claims(authorization)
    if not allowed(c, ['COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN']): err('ACCESS_DENIED', 'Недостаточно прав')
    d = {'id': str(uuid.uuid4()), 'case_id': case_id, 'title': body.title, 'act_type': body.act_type, 'status': 'PROCESSING'}; docs.append(d)
    async with httpx.AsyncClient() as cl:
        r = await cl.post(f'{ANON}/internal/anonymization/process', headers={'X-Internal-Service-Token': INTERNAL}, json={'case_id': case_id, 'document_id': d['id'], 'title': body.title, 'text': body.text, 'metadata': {}})
    p = r.json(); d['status'] = 'ANONYMIZED'; d['anonymization_job_id'] = p['job_id']; d['public_anonymized_document_id'] = d['id']
    return {'document_id': d['id'], 'status': d['status'], 'anonymization_job_id': d['anonymization_job_id']}


@app.get('/api/cases/public/documents/{document_id}')
async def pub_doc(document_id: str):
    async with httpx.AsyncClient() as cl:
        r = await cl.get(f'{ANON}/internal/anonymization/documents/{document_id}/public', headers={'X-Internal-Service-Token': INTERNAL})
    return r.json()


@app.get('/api/cases/{case_id}/restored')
async def restored(case_id: str, authorization: str | None = Header(None)):
    c = claims(authorization)
    if c.get('sub') is None: err('ACCESS_DENIED', 'Недостаточно прав')
    related = [x for x in participants if x['case_id'] == case_id and x['user_id'] == c['sub']]
    if not (allowed(c, ['ADMIN', 'COURT_STAFF', 'JUDGE', 'COURT_CLERK']) or related): err('ACCESS_DENIED', 'Недостаточно прав')
    ds = [d for d in docs if d['case_id'] == case_id]
    out = []
    async with httpx.AsyncClient() as cl:
        for d in ds:
            rr = await cl.get(f'{ANON}/internal/anonymization/documents/{d["id"]}/restored', headers={'X-Internal-Service-Token': INTERNAL}); out.append({'document_id': d['id'], 'title': d['title'], **rr.json()})
    return {'case': next(x for x in cases if x['id'] == case_id), 'documents': out}
