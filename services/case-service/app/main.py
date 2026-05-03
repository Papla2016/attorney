from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uuid, os, httpx
from jose import jwt

app=FastAPI(title='case-service')
SECRET=os.getenv('JWT_SECRET','secret'); ALG=os.getenv('JWT_ALGORITHM','HS256')
INTERNAL=os.getenv('INTERNAL_SERVICE_TOKEN','internal-secret-token')
ANON=os.getenv('ANONYMIZATION_SERVICE_URL','http://anonymization-service:8000')

def err(code,msg,status=403): raise HTTPException(status,detail={'error':{'code':code,'message':msg,'details':{}}})
def claims(auth:str|None):
  if not auth: return {'roles':['PUBLIC'],'sub':None}
  try:return jwt.decode(auth.replace('Bearer ',''),SECRET,algorithms=[ALG])
  except Exception: return {'roles':['PUBLIC'],'sub':None}

def allowed(c,need): return any(r in c.get('roles',[]) for r in need)

courts=[{'id':str(uuid.uuid4()),'name':'Центральный районный суд','court_type':'DISTRICT_COURT','region':'Забайкальский край'}]
cases=[]; docs=[]; fav=[]; participants=[]
sample_case={'id':str(uuid.uuid4()),'court_id':courts[0]['id'],'case_number':'2-3701/2025','status':'PUBLISHED','created_by_user_id':'seed'}
cases.append(sample_case)
sample_doc={'id':str(uuid.uuid4()),'case_id':sample_case['id'],'title':'Решение','act_type':'DECISION','status':'PUBLISHED','public_anonymized_document_id':None}
docs.append(sample_doc)

class CreateCase(BaseModel): court_id:str; case_number:str; document_number:str; document_date:str; instance:str; region:str; legal_article:str; judicial_practice:str; judge_names:list[str]=[]; staff_user_ids:list[str]=[]
class UploadDoc(BaseModel): title:str; act_type:str; text:str

@app.get('/health')
def health(): return {'status':'ok'}
@app.get('/ready')
def ready(): return {'status':'ready'}

@app.get('/api/cases/public/documents')
def pub_docs(authorization:str|None=Header(None)):
  c=claims(authorization)
  items=[{'document_id':d['id'],'case_id':d['case_id'],'title':d['title'],'court_name':courts[0]['name'],'case_number':'2-3701/2025','document_number':'2-3701','document_date':'2025-10-21','act_type':d['act_type'],'instance':'FIRST','region':'Забайкальский край','legal_article':'ст. 454 ГК РФ','judicial_practice':'...','is_favorite': any(x for x in fav if x['user_id']==c.get('sub') and x['document_id']==d['id'])} for d in docs if d['status']=='PUBLISHED']
  return {'items':items,'page':1,'size':20,'total':len(items)}

@app.post('/api/cases')
def create_case(body:CreateCase, authorization:str|None=Header(None)):
  c=claims(authorization)
  if not allowed(c,['COURT_STAFF','JUDGE','COURT_CLERK','ADMIN']): err('ACCESS_DENIED','Недостаточно прав')
  obj={'id':str(uuid.uuid4()),'court_id':body.court_id,'case_number':body.case_number,'status':'DRAFT','created_by_user_id':c['sub']}
  cases.append(obj); return obj

@app.post('/api/cases/{case_id}/documents')
async def upload(case_id:str, body:UploadDoc, authorization:str|None=Header(None)):
  c=claims(authorization)
  if not allowed(c,['COURT_STAFF','JUDGE','COURT_CLERK','ADMIN']): err('ACCESS_DENIED','Недостаточно прав')
  d={'id':str(uuid.uuid4()),'case_id':case_id,'title':body.title,'act_type':body.act_type,'status':'PROCESSING'}; docs.append(d)
  async with httpx.AsyncClient() as cl:
    r=await cl.post(f'{ANON}/internal/anonymization/process',headers={'X-Internal-Service-Token':INTERNAL},json={'case_id':case_id,'document_id':d['id'],'title':body.title,'text':body.text,'metadata':{}})
  p=r.json(); d['status']='ANONYMIZED'; d['anonymization_job_id']=p['job_id']; d['public_anonymized_document_id']=d['id']
  return {'document_id':d['id'],'status':d['status'],'anonymization_job_id':d['anonymization_job_id']}

@app.get('/api/cases/public/documents/{document_id}')
async def pub_doc(document_id:str):
  async with httpx.AsyncClient() as cl:
    r=await cl.get(f'{ANON}/internal/anonymization/documents/{document_id}/public',headers={'X-Internal-Service-Token':INTERNAL})
  return r.json()

@app.get('/api/cases/{case_id}/restored')
async def restored(case_id:str,authorization:str|None=Header(None)):
  c=claims(authorization)
  if c.get('sub') is None: err('ACCESS_DENIED','Недостаточно прав')
  related=[x for x in participants if x['case_id']==case_id and x['user_id']==c['sub']]
  if not (allowed(c,['ADMIN','COURT_STAFF','JUDGE','COURT_CLERK']) or related): err('ACCESS_DENIED','Недостаточно прав')
  ds=[d for d in docs if d['case_id']==case_id]
  out=[]
  async with httpx.AsyncClient() as cl:
    for d in ds:
      rr=await cl.get(f'{ANON}/internal/anonymization/documents/{d["id"]}/restored',headers={'X-Internal-Service-Token':INTERNAL}); out.append({'document_id':d['id'],'title':d['title'],**rr.json()})
  return {'case':next(x for x in cases if x['id']==case_id),'documents':out}
