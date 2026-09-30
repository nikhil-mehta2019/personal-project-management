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


# ---------------------------------------------------------------- P1 hardening


def make_item(user, code=None, **extra):
    code = code or f"P{uuid.uuid4().hex[:6].upper()}"
    project = client.post("/api/projects", json={"name": code, "code": code}, headers=user["h"]).json()
    body = {"title": "Item", "project_id": project["id"], "type": "Bug", "priority": "High", **extra}
    r = client.post("/api/work-items", json=body, headers=user["h"])
    return project, r


def full_payload(item, **changes):
    keys = ("title", "project_id", "type", "priority", "status", "source", "description", "reported_by_contact_id",
            "assigned_to_user_id", "due_date", "root_cause", "solution", "testing_notes", "current_blocker")
    body = {k: item.get(k) for k in keys}
    body.update(changes)
    return body


def activities(user, item_id):
    return client.get(f"/api/work-items/{item_id}/activities", headers=user["h"]).json()


class TestCrossWorkspaceReferences:
    def test_foreign_contact_rejected_on_create(self):
        a, b = register("RefA"), register("RefB")
        foreign = client.post("/api/contacts", json={"name": "B's client"}, headers=b["h"]).json()
        _, r = make_item(a, reported_by_contact_id=foreign["id"])
        assert r.status_code == 422

    def test_foreign_assignee_rejected_on_create(self):
        a, b = register("AsgA"), register("AsgB")
        _, r = make_item(a, assigned_to_user_id=b["user_id"])
        assert r.status_code == 422
        _, ok = make_item(a, assigned_to_user_id=a["user_id"])
        assert ok.status_code == 201

    def test_foreign_references_rejected_on_update(self):
        a, b = register("UpdA"), register("UpdB")
        foreign = client.post("/api/contacts", json={"name": "Other"}, headers=b["h"]).json()
        _, r = make_item(a)
        item = r.json()
        bad = client.put(f"/api/work-items/{item['id']}", json=full_payload(item, reported_by_contact_id=foreign["id"]), headers=a["h"])
        assert bad.status_code == 422
        bad = client.put(f"/api/work-items/{item['id']}", json=full_payload(item, assigned_to_user_id=b["user_id"]), headers=a["h"])
        assert bad.status_code == 422

    def test_foreign_contact_rejected_on_communication_and_import(self):
        a, b = register("ComA"), register("ComB")
        foreign = client.post("/api/contacts", json={"name": "Other"}, headers=b["h"]).json()
        project, r = make_item(a)
        item = r.json()
        c = client.post(f"/api/work-items/{item['id']}/communications",
                        json={"communication_type": "Email", "contact_id": foreign["id"], "content": "hi"}, headers=a["h"])
        assert c.status_code == 422
        imp = client.post("/api/message-imports/commit", json={"content": "Subject: something broke", "channel": "Email",
                          "project_id": project["id"], "contact_id": foreign["id"], "confirm": True}, headers=a["h"])
        assert imp.status_code == 422


class TestHistoryIntegrity:
    @pytest.mark.parametrize("kind", ["Status changed", "created", "Updated", "MOVED"])
    def test_client_cannot_write_system_events(self, kind):
        a = register("Hist")
        _, r = make_item(a)
        forged = client.post(f"/api/work-items/{r.json()['id']}/activities",
                             json={"activity_type": kind, "note": "fake", "old_value": "New", "new_value": "Completed"}, headers=a["h"])
        assert forged.status_code == 422

    def test_work_log_entries_still_allowed_and_values_ignored(self):
        a = register("Log")
        _, r = make_item(a)
        ok = client.post(f"/api/work-items/{r.json()['id']}/activities",
                         json={"activity_type": "Investigation", "note": "traced payload", "old_value": "x", "new_value": "y"}, headers=a["h"])
        assert ok.status_code == 201
        entry = [e for e in activities(a, r.json()["id"]) if e["activity_type"] == "Investigation"][0]
        assert entry["old_value"] is None and entry["new_value"] is None

    def test_edits_and_moves_are_recorded(self):
        a = register("Track")
        _, r = make_item(a)
        item = r.json()
        other = client.post("/api/projects", json={"name": "Other", "code": "OTHR"}, headers=a["h"]).json()
        up = client.put(f"/api/work-items/{item['id']}", json=full_payload(item, title="Renamed", project_id=other["id"]), headers=a["h"])
        assert up.status_code == 200
        log = {e["activity_type"]: e for e in activities(a, item["id"])}
        assert log["Moved"]["new_value"] == "OTHR"
        assert "title" in log["Updated"]["note"]

    def test_status_bookkeeping(self):
        a = register("Status")
        _, r = make_item(a)
        iid = r.json()["id"]
        assert client.patch(f"/api/work-items/{iid}/status?status=In%20Progress", headers=a["h"]).json()["started_at"]
        done = client.patch(f"/api/work-items/{iid}/status?status=Completed", headers=a["h"]).json()
        assert done["completed_at"]
        again = client.patch(f"/api/work-items/{iid}/status?status=Completed", headers=a["h"]).json()
        assert again["completed_at"] == done["completed_at"]  # no-op, no duplicate history
        reopened = client.put(f"/api/work-items/{iid}", json=full_payload(again, status="In Progress"), headers=a["h"]).json()
        assert reopened["completed_at"] is None
        changes = [e for e in activities(a, iid) if e["activity_type"] == "Status changed"]
        assert [(e["old_value"], e["new_value"]) for e in changes] == [("New", "In Progress"), ("In Progress", "Completed"), ("Completed", "In Progress")]


class TestNumbering:
    def test_numbers_are_per_workspace(self):
        a, b = register("NumA"), register("NumB")
        _, ra = make_item(a)
        _, rb = make_item(b)
        year = datetime.now(timezone.utc).year
        assert ra.json()["work_item_number"] == f"WRK-{year}-00001"
        assert rb.json()["work_item_number"] == f"WRK-{year}-00001"
        _, ra2 = make_item(a)
        assert ra2.json()["work_item_number"] == f"WRK-{year}-00002"

    def test_numbers_sort_past_99999(self):
        a = register("Big")
        with Session(main.engine) as db:
            db.add(main.WorkItemCounter(workspace_id=uuid.UUID(a["workspace_id"]), year=datetime.now(timezone.utc).year, last_value=99999))
            db.commit()
        _, r = make_item(a)
        _, r2 = make_item(a)
        assert r.json()["work_item_number"].endswith("-100000")
        assert r2.json()["work_item_number"].endswith("-100001")


class TestMessageImportMatching:
    def test_wildcard_sender_does_not_match_existing_contact(self):
        a = register("Wild")
        client.post("/api/contacts", json={"name": "Canute Fernandes"}, headers=a["h"])
        project, _ = make_item(a)
        r = client.post("/api/message-imports/commit", json={"content": "Subject: hello there world", "channel": "Email",
                        "project_id": project["id"], "sender_name": "%", "confirm": True}, headers=a["h"]).json()
        contacts = {c["id"]: c["name"] for c in client.get("/api/contacts", headers=a["h"]).json()}
        assert contacts[r["contact_id"]] == "%"

    def test_same_sender_reuses_contact_case_insensitively(self):
        a = register("Reuse")
        project, _ = make_item(a)
        ids = {client.post("/api/message-imports/commit", json={"content": "Subject: issue number one", "channel": "Email",
               "project_id": project["id"], "sender_name": name, "confirm": True}, headers=a["h"]).json()["contact_id"]
               for name in ("Priya Shah", "priya shah")}
        assert len(ids) == 1


class TestClientIp:
    class Req:
        def __init__(self, headers, host="10.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    def test_defaults_to_socket_address_and_ignores_spoofable_headers(self, monkeypatch):
        monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        req = self.Req({"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"})
        assert main.client_ip(req) == "10.0.0.1"

    def test_configured_edge_header(self, monkeypatch):
        monkeypatch.setenv("CLIENT_IP_HEADER", "CF-Connecting-IP")
        assert main.client_ip(self.Req({"CF-Connecting-IP": "5.6.7.8"})) == "5.6.7.8"
        assert main.client_ip(self.Req({})) == "10.0.0.1"

    def test_trusted_hops_read_from_the_right(self, monkeypatch):
        monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
        assert main.client_ip(self.Req({"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})) == "203.0.113.9"

    def test_rate_limit_is_per_client_and_memory_is_bounded(self, monkeypatch):
        monkeypatch.setenv("CLIENT_IP_HEADER", "X-Test-Client")
        for i in range(10):
            client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}, headers={"X-Test-Client": "attacker"})
        blocked = client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}, headers={"X-Test-Client": "attacker"})
        other = client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}, headers={"X-Test-Client": "owner"})
        assert blocked.status_code == 429 and other.status_code == 401
        main._rate_state["window"] = -1  # simulate the next minute
        client.get("/api/health")
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}, headers={"X-Test-Client": "owner"})
        assert set(main._rate_windows) == {"owner:auth"}


class TestNumberingMigration:
    def test_counters_backfilled_from_legacy_numbers(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'backfill.db'}"
        migrate(url, "0002_token_version")
        engine = sa.create_engine(url)
        ws, user, proj = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO workspaces (id,name,created_at,updated_at) VALUES (:i,'W',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"i": ws.hex})
            conn.execute(sa.text("INSERT INTO projects (id,workspace_id,name,code,status,color,created_at,updated_at) VALUES (:p,:w,'P','P','Active','#000',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"p": proj.hex, "w": ws.hex})
            for n in ("WRK-2026-00007", "WRK-2026-00012", "WRK-2025-00003"):
                conn.execute(sa.text("INSERT INTO work_items (id,workspace_id,project_id,work_item_number,title,type,priority,status,created_at,updated_at) VALUES (:i,:w,:p,:n,'t','Bug','High','New',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                             {"i": uuid.uuid4().hex, "w": ws.hex, "p": proj.hex, "n": n})
        migrate(url)
        with engine.connect() as conn:
            rows = dict(conn.execute(sa.text("SELECT year, last_value FROM work_item_counters")).all())
        assert rows == {2026: 12, 2025: 3}
