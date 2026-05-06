from datetime import datetime, timedelta, timezone
import os
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

app = FastAPI(title="auth-service")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET = os.getenv("JWT_SECRET", "secret")
ALG = os.getenv("JWT_ALGORITHM", "HS256")
INTERNAL = os.getenv("INTERNAL_SERVICE_TOKEN", "internal-secret-token")

SEED_IDS = {
    "admin": "00000000-0000-0000-0000-000000000001",
    "user": "00000000-0000-0000-0000-000000000002",
    "staff": "00000000-0000-0000-0000-000000000003",
    "judge": "00000000-0000-0000-0000-000000000004",
}
SEED_ROLES = {
    "admin": ["ADMIN"],
    "user": ["REGISTERED_USER"],
    "staff": ["COURT_STAFF"],
    "judge": ["JUDGE"],
}


def error_payload(code: str, message: str, details: dict | None = None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error(status: int, code: str, message: str, details: dict | None = None):
    raise HTTPException(status_code=status, detail=error_payload(code, message, details))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=error_payload("HTTP_ERROR", str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content=error_payload("BAD_REQUEST", "Некорректный запрос", {"validation_errors": exc.errors()}))


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


audit_log: list[dict] = []


def audit(actor_user_id: str | None, action: str, resource_type: str, resource_id: str, details: dict | None = None):
    audit_log.append({
        "id": str(uuid.uuid4()),
        "user_id": actor_user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "created_at": now_iso(),
        "details": details or {},
    })


users: dict[str, dict] = {}
for username, password, email in [
    ("admin", "admin123", "admin@example.com"),
    ("user", "user123", "user@example.com"),
    ("staff", "staff123", "staff@example.com"),
    ("judge", "judge123", "judge@example.com"),
]:
    users[username] = {
        "id": SEED_IDS[username],
        "username": username,
        "email": email,
        "password_hash": pwd.hash(password),
        "roles": SEED_ROLES[username],
    }


class RegisterIn(BaseModel):
    username: str
    email: str | None = None
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class RolesIn(BaseModel):
    roles: list[str] | None = None
    role: str | None = None


class UpdateMeIn(BaseModel):
    username: str | None = None
    email: str | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


def make_token(u: dict):
    payload = {
        "sub": u["id"],
        "username": u["username"],
        "roles": u["roles"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    return jwt.encode(payload, SECRET, algorithm=ALG)


def get_current(auth: str = Header(..., alias="Authorization")):
    token = auth.replace("Bearer ", "")
    try:
        return jwt.decode(token, SECRET, algorithms=[ALG])
    except Exception:
        error(401, "UNAUTHORIZED", "invalid token")


def get_user_by_id(user_id: str):
    for u in users.values():
        if u["id"] == user_id:
            return u
    return None


@app.get('/health')
def health(): return {"status": "ok"}


@app.get('/ready')
def ready(): return {"status": "ready"}


@app.post('/api/auth/register')
def register(data: RegisterIn):
    if data.username in users:
        error(400, "USERNAME_ALREADY_EXISTS", "username already exists")
    uid = str(uuid.uuid4())
    users[data.username] = {"id": uid, "username": data.username, "email": data.email, "password_hash": pwd.hash(data.password), "roles": ["REGISTERED_USER"]}
    return {"id": uid, "username": data.username, "email": data.email}


@app.post('/api/auth/login')
def login(data: LoginIn):
    u = users.get(data.username)
    if not u or not pwd.verify(data.password, u['password_hash']):
        error(401, "UNAUTHORIZED", "bad creds")
    return {"access_token": make_token(u), "token_type": "bearer", "user": {"id": u['id'], "username": u['username'], "roles": u['roles']}}


@app.get('/api/auth/me')
def me(claims=Depends(get_current)):
    u = get_user_by_id(claims["sub"])
    if not u:
        error(404, "NOT_FOUND", "user not found")
    return {"id": u['id'], "username": u['username'], "email": u['email'], "roles": u['roles']}


@app.patch('/api/auth/me')
def update_me(data: UpdateMeIn, claims=Depends(get_current)):
    user = get_user_by_id(claims["sub"])
    if not user:
        error(404, "NOT_FOUND", "user not found")
    if data.username is not None and data.username.strip():
        for u in users.values():
            if u["username"] == data.username and u["id"] != user["id"]:
                error(400, "USERNAME_ALREADY_EXISTS", "username already exists")
        if data.username != user["username"]:
            users.pop(user["username"])
            user["username"] = data.username
            users[user["username"]] = user
    if data.email is not None:
        user["email"] = data.email
    return {"user": {"id": user['id'], "username": user['username'], "email": user['email'], "roles": user['roles']}, "access_token": make_token(user)}


@app.post('/api/auth/me/change-password')
def change_password(data: ChangePasswordIn, claims=Depends(get_current)):
    user = get_user_by_id(claims["sub"])
    if not user:
        error(404, "NOT_FOUND", "user not found")
    if not pwd.verify(data.current_password, user["password_hash"]):
        error(400, "INVALID_CURRENT_PASSWORD", "Текущий пароль указан неверно")
    if len(data.new_password) < 8:
        error(400, "BAD_REQUEST", "Пароль должен быть длиной минимум 8 символов")
    user["password_hash"] = pwd.hash(data.new_password)
    return {"ok": True}


@app.get('/api/auth/users')
def list_users(claims=Depends(get_current)):
    if 'ADMIN' not in claims.get('roles', []):
        error(403, "ACCESS_DENIED", "Недостаточно прав")
    return [{"id": u['id'], "username": u['username'], "email": u['email'], "roles": u['roles']} for u in users.values()]


@app.get('/api/auth/users/{user_id}')
def get_user(user_id: str, x_internal_service_token: str | None = Header(None), claims=Depends(get_current)):
    if x_internal_service_token != INTERNAL and 'ADMIN' not in claims.get('roles', []):
        error(403, "ACCESS_DENIED", "Недостаточно прав")
    u = get_user_by_id(user_id)
    if not u:
        error(404, "NOT_FOUND", "user not found")
    return {"id": u['id'], "username": u['username'], "email": u['email'], "roles": u['roles']}


@app.post('/api/auth/users/{user_id}/roles')
def set_roles(user_id: str, data: RolesIn, claims=Depends(get_current)):
    if 'ADMIN' not in claims.get('roles', []):
        error(403, "ACCESS_DENIED", "Недостаточно прав")
    u = get_user_by_id(user_id)
    if not u:
        error(404, "NOT_FOUND", "user not found")
    next_roles = data.roles if data.roles is not None else ([data.role] if data.role else None)
    if not next_roles:
        error(400, "BAD_REQUEST", "roles is required")
    previous_roles = u['roles'].copy()
    u['roles'] = next_roles
    audit(claims.get("sub"), "UPDATE_USER_ROLES", "USER", u["id"], {"previous_roles": previous_roles, "roles": next_roles})
    return {"id": u['id'], "username": u['username'], "email": u['email'], "roles": u['roles']}


@app.get('/api/auth/admin/audit')
def admin_audit(claims=Depends(get_current)):
    if 'ADMIN' not in claims.get('roles', []):
        error(403, "ACCESS_DENIED", "Недостаточно прав")
    return {"items": audit_log, "total": len(audit_log)}
