import uuid
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'

def test_register_login_and_me():
    email = f"test-{uuid.uuid4()}@example.com"
    registration = client.post('/api/auth/register', json={
        'name': 'Automated Test User', 'email': email, 'password': 'StrongPassword123!'
    })
    assert registration.status_code == 201
    token = registration.json()['access_token']
    me = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200
    assert me.json()['user']['email'] == email

def test_invalid_login_is_rejected():
    response = client.post('/api/auth/login', json={'email': 'missing@example.com', 'password': 'wrong-password'})
    assert response.status_code in (401, 422)
