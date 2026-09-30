"""API and security regression tests. Each test class maps to a hardening item."""
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
_DB_FILE = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["CORS_ORIGINS"] = "http://frontend.test"
sys.path.insert(0, str(BACKEND))

import jwt  # noqa: E402
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

ORIGIN = "http://frontend.test"
PASSWORD = "StrongPassword123!"


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def migrate(url: str, target: str = "head", direction: str = "upgrade") -> None:
    previous = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = url  # env.py prefers DATABASE_URL
    try:
        getattr(command, direction)(alembic_config(url), target)
    finally:
        os.environ["DATABASE_URL"] = previous


migrate(os.environ["DATABASE_URL"])
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    main._rate_windows.clear()
    yield


def register(name="User"):
    email = f"{name.lower()}-{uuid.uuid4()}@example.com"
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"email": email, "token": body["access_token"], "user_id": body["user"]["id"],
            "workspace_id": body["workspace"]["id"], "h": {"Authorization": f"Bearer {body['access_token']}"}}


def forge(payload: dict, secret: str | None = None) -> dict:
    token = jwt.encode(payload, secret or os.environ["JWT_SECRET"], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def now():
    return datetime.now(timezone.utc)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


class TestCorsAndMiddlewareOrder:
    def test_preflight_to_protected_route_is_answered_by_cors(self):
        r = client.options("/api/projects", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                                     "Access-Control-Request-Headers": "authorization"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == ORIGIN

    def test_401_carries_cors_and_request_id_headers(self):
        r = client.get("/api/projects", headers={"Origin": ORIGIN})
        assert r.status_code == 401
        assert r.headers["access-control-allow-origin"] == ORIGIN
        assert "x-request-id" in r.headers

    def test_unknown_origin_gets_no_cors_grant(self):
        r = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in r.headers


class TestFailClosed:
    def test_no_token_is_rejected(self):
        for path in ("/api/projects", "/api/work-items", "/api/contacts", "/api/auth/me", "/api/reports/monthly"):
            assert client.get(path).status_code == 401, path

    def test_garbage_token_is_rejected_not_defaulted(self):
        assert client.get("/api/projects", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401

    def test_no_bootstrap_account_is_created(self):
        with TestClient(main.app):  # runs startup
            pass
        with Session(main.engine) as db:
            assert db.scalar(sa.select(main.User).where(main.User.email == "local@workos.dev")) is None


class TestSecret:
    def test_token_signed_with_old_default_secret_is_rejected(self):
        a = register("Forge")
        h = forge({"sub": a["user_id"], "workspace_id": a["workspace_id"], "ver": 0,
                   "iat": now(), "exp": now() + timedelta(hours=1)}, secret="development-only-change-me")
        assert client.get("/api/auth/me", headers=h).status_code == 401

    @pytest.mark.parametrize("bad", ["", "short", "development-only-change-me", "replace-with-a-long-random-secret"])
    def test_weak_secret_refuses_to_issue_tokens(self, monkeypatch, bad):
        monkeypatch.setenv("JWT_SECRET", bad)
        with pytest.raises(RuntimeError):
            main.jwt_secret()

    def test_startup_fails_without_secret(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET")
        with pytest.raises(RuntimeError):
            with TestClient(main.app):
                pass


class TestTokenLifetime:
    def test_issued_token_has_expiry(self):
        a = register("Exp")
        claims = jwt.decode(a["token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
        assert {"exp", "iat", "sub", "workspace_id", "ver"} <= claims.keys()

    def test_expired_token_is_rejected(self):
        a = register("Expired")
        past = now() - timedelta(hours=2)
        h = forge({"sub": a["user_id"], "workspace_id": a["workspace_id"], "ver": 0,
                   "iat": past, "exp": past + timedelta(minutes=5)})
        assert client.get("/api/auth/me", headers=h).status_code == 401

    def test_token_without_expiry_is_rejected(self):
        a = register("NoExp")
        h = forge({"sub": a["user_id"], "workspace_id": a["workspace_id"], "ver": 0, "iat": now()})
        assert client.get("/api/auth/me", headers=h).status_code == 401

    def test_logout_revokes_all_existing_tokens(self):
        a = register("Logout")
        second = client.post("/api/auth/login", json={"email": a["email"], "password": PASSWORD}).json()["access_token"]
        assert client.post("/api/auth/logout", headers=a["h"]).status_code == 204
        assert client.get("/api/auth/me", headers=a["h"]).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {second}"}).status_code == 401
        fresh = client.post("/api/auth/login", json={"email": a["email"], "password": PASSWORD}).json()["access_token"]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200

    def test_deactivated_user_is_locked_out(self):
        a = register("Inactive")
        with Session(main.engine) as db:
            db.get(main.User, uuid.UUID(a["user_id"])).is_active = False
            db.commit()
        assert client.get("/api/auth/me", headers=a["h"]).status_code == 401
        assert client.post("/api/auth/login", json={"email": a["email"], "password": PASSWORD}).status_code == 401


class TestRegistration:
    def test_registration_closed_by_default(self, monkeypatch):
        monkeypatch.delenv("ALLOW_REGISTRATION")
        r = client.post("/api/auth/register", json={"name": "X", "email": f"{uuid.uuid4()}@example.com", "password": PASSWORD})
        assert r.status_code == 403

    def test_register_login_me(self):
        a = register("Flow")
        me = client.get("/api/auth/me", headers=a["h"])
        assert me.status_code == 200 and me.json()["user"]["email"] == a["email"]
        assert client.post("/api/auth/login", json={"email": a["email"], "password": PASSWORD}).status_code == 200

    def test_invalid_login_is_rejected(self):
        r = client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrong-password"})
        assert r.status_code == 401


class TestWorkspaceIsolation:
    def test_other_workspace_cannot_read_projects_or_items(self):
        a, b = register("Alice"), register("Bob")
        project = client.post("/api/projects", json={"name": "Secret", "code": "SEC"}, headers=a["h"]).json()
        item = client.post("/api/work-items", json={"title": "Private", "project_id": project["id"], "type": "Bug",
                                                    "priority": "High"}, headers=a["h"]).json()
        assert client.get(f"/api/projects/{project['id']}", headers=b["h"]).status_code == 404
        assert client.get(f"/api/work-items/{item['id']}", headers=b["h"]).status_code == 404
        assert client.get(f"/api/work-items/{item['id']}/activities", headers=b["h"]).status_code == 404
        assert client.get(f"/api/work-items/{item['id']}/communications", headers=b["h"]).status_code == 404
        assert all(p["id"] != project["id"] for p in client.get("/api/projects", headers=b["h"]).json())
        assert client.get("/api/work-items", headers=b["h"]).json()["total"] == 0

    def test_other_workspace_cannot_write_into_project_or_item(self):
        a, b = register("Carol"), register("Dave")
        project = client.post("/api/projects", json={"name": "Mine", "code": "MIN"}, headers=a["h"]).json()
        item = client.post("/api/work-items", json={"title": "Mine", "project_id": project["id"], "type": "Task",
                                                    "priority": "Low"}, headers=a["h"]).json()
        assert client.post("/api/work-items", json={"title": "x", "project_id": project["id"], "type": "Task",
                                                    "priority": "Low"}, headers=b["h"]).status_code == 404
        assert client.post(f"/api/work-items/{item['id']}/activities", json={"note": "x"}, headers=b["h"]).status_code == 404
        assert client.patch(f"/api/work-items/{item['id']}/status?status=Completed", headers=b["h"]).status_code == 404
        assert client.patch(f"/api/projects/{project['id']}/archive", headers=b["h"]).status_code == 404

    def test_token_for_workspace_user_is_not_member_of_is_rejected(self):
        a, b = register("Eve"), register("Frank")
        h = forge({"sub": a["user_id"], "workspace_id": b["workspace_id"], "ver": 0,
                   "iat": now(), "exp": now() + timedelta(hours=1)})
        assert client.get("/api/projects", headers=h).status_code == 401


class TestMigrations:
    def test_fresh_database_upgrades_and_downgrades(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'fresh.db'}"
        migrate(url)
        tables = set(sa.inspect(sa.create_engine(url)).get_table_names())
        assert {"users", "workspaces", "work_items", "activities", "alembic_version"} <= tables
        migrate(url, "base", direction="downgrade")
        assert set(sa.inspect(sa.create_engine(url)).get_table_names()) == {"alembic_version"}

    def test_legacy_create_all_database_is_adopted(self, tmp_path):
        """A database built by the old startup create_all() (no alembic_version) must upgrade cleanly."""
        url = f"sqlite:///{tmp_path / 'legacy.db'}"
        migrate(url, "0001_initial")
        with sa.create_engine(url).begin() as conn:
            conn.execute(sa.text("DROP TABLE alembic_version"))
        migrate(url)
        columns = {c["name"] for c in sa.inspect(sa.create_engine(url)).get_columns("users")}
        assert "token_version" in columns

    def test_models_match_migrations(self, tmp_path):
        from alembic.autogenerate import compare_metadata
        from alembic.runtime.migration import MigrationContext
        url = f"sqlite:///{tmp_path / 'drift.db'}"
        migrate(url)
        with sa.create_engine(url).connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), main.Base.metadata)
        assert diff == [], f"Models changed without a migration: {diff}"
