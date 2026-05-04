from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from jose import jwt
from passlib.context import CryptContext
import os, uuid

app = FastAPI(title="auth-service")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET=os.getenv("JWT_SECRET","secret")
ALG=os.getenv("JWT_ALGORITHM","HS256")
INTERNAL=os.getenv("INTERNAL_SERVICE_TOKEN","internal-secret-token")

roles={"admin":["ADMIN"],"user":["REGISTERED_USER"],"staff":["COURT_STAFF"],"judge":["JUDGE"]}
users={}
for u,p,e in [("admin","admin123","admin@example.com"),("user","user123","user@example.com"),("staff","staff123","staff@example.com"),("judge","judge123","judge@example.com")]:
    uid=str(uuid.uuid4())
    users[u]={"id":uid,"username":u,"email":e,"password_hash":pwd.hash(p),"roles":roles[u]}

class RegisterIn(BaseModel): username:str; email:str|None=None; password:str
class LoginIn(BaseModel): username:str; password:str
class RolesIn(BaseModel): roles:list[str]

def make_token(u):
    payload={"sub":u["id"],"username":u["username"],"roles":u["roles"],"exp":datetime.now(timezone.utc)+timedelta(minutes=60)}
    return jwt.encode(payload,SECRET,algorithm=ALG)

def get_current(auth:str=Header(...,alias="Authorization")):
    token=auth.replace("Bearer ","")
    try:return jwt.decode(token,SECRET,algorithms=[ALG])
    except Exception: raise HTTPException(401,"invalid token")

@app.get('/health')
def health(): return {"status":"ok"}
@app.get('/ready')
def ready(): return {"status":"ready"}

@app.post('/api/auth/register')
def register(data:RegisterIn):
    if data.username in users: raise HTTPException(400,"exists")
    uid=str(uuid.uuid4());users[data.username]={"id":uid,"username":data.username,"email":data.email,"password_hash":pwd.hash(data.password),"roles":["REGISTERED_USER"]}
    return {"id":uid,"username":data.username,"email":data.email}

@app.post('/api/auth/login')
def login(data:LoginIn):
    u=users.get(data.username)
    if not u or not pwd.verify(data.password,u['password_hash']): raise HTTPException(401,"bad creds")
    return {"access_token":make_token(u),"token_type":"bearer","user":{"id":u['id'],"username":u['username'],"roles":u['roles']}}

@app.get('/api/auth/me')
def me(claims=Depends(get_current)):
    for u in users.values():
      if u['id']==claims['sub']: return {"id":u['id'],"username":u['username'],"email":u['email'],"roles":u['roles']}
    raise HTTPException(404)

@app.get('/api/auth/users/{user_id}')
def get_user(user_id:str, x_internal_service_token:str|None=Header(None), claims=Depends(get_current)):
    if x_internal_service_token!=INTERNAL and 'ADMIN' not in claims.get('roles',[]): raise HTTPException(403)
    for u in users.values():
      if u['id']==user_id:return {"id":u['id'],"username":u['username'],"email":u['email'],"roles":u['roles']}
    raise HTTPException(404)

@app.post('/api/auth/users/{user_id}/roles')
def set_roles(user_id:str,data:RolesIn,claims=Depends(get_current)):
    if 'ADMIN' not in claims.get('roles',[]): raise HTTPException(403)
    for u in users.values():
      if u['id']==user_id: u['roles']=data.roles; return {"ok":True}
    raise HTTPException(404)
