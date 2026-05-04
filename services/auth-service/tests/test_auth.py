from fastapi.testclient import TestClient
from app.main import app

c=TestClient(app)

def test_register_login():
  r=c.post('/api/auth/register',json={'username':'u1','email':'u1@e.com','password':'p1'})
  assert r.status_code==200
  l=c.post('/api/auth/login',json={'username':'u1','password':'p1'})
  assert l.status_code==200 and 'access_token' in l.json()
