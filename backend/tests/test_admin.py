import pytest

from app.db import connect
from app.services import accounts, ingest
from tests.conftest import make_client
from tests.test_ingest_dedup import STATE, rec


@pytest.fixture()
def env(db_url, source_factory):
    source_factory(slug="ok-src", connector="scripted", is_dev_data=True)
    source_factory(slug="restricted-src", connector="scripted", terms_status="restricted", enabled=False)
    STATE.update(records=[rec("1", title="Clerk", employer=None, description="Filing")], complete=True, errors=[], boom=False)
    ingest.run_source(db_url, "ok-src", force=True)
    accounts.create_user(db_url, "boss@example.com", "correct-horse-battery", role="admin")
    admin = make_client(db_url); admin.login("boss@example.com")
    user = make_client(db_url); user.register("plain@example.com")
    return admin, user, make_client(db_url)


ROUTES = ["/stats", "/sources", "/runs", "/ai-usage", "/data-quality", "/audit"]


def test_admin_requires_admin_role(env):
    admin, user, anon = env
    for r in ROUTES:
        assert anon.get("/api/admin" + r).status_code == 401, r
        assert user.get("/api/admin" + r).status_code == 403, r
        assert admin.get("/api/admin" + r).status_code == 200, r
    assert user.patch("/api/admin/sources/ok-src", json={"enabled": False}).status_code == 403
    assert user.post("/api/admin/sources/ok-src/run").status_code == 403


def test_stats_and_data_quality(env):
    admin, *_ = env
    s = admin.get("/api/admin/stats").get_json()
    assert any(r["status"] == "active" for r in s["jobs_by_status"]) and s["per_source"]
    dq = admin.get("/api/admin/data-quality").get_json()["checks"]
    assert dq["missing_employer"]["count"] == 1


def test_cannot_enable_unverified_or_restricted_source(env, db_url):
    admin, *_ = env
    r = admin.patch("/api/admin/sources/restricted-src", json={"enabled": True})
    assert r.status_code == 409 and r.get_json()["error"] == "terms_not_verified"
    with connect(db_url) as c:
        assert c.execute("SELECT enabled FROM sources WHERE slug='restricted-src'").fetchone()["enabled"] is False
    assert admin.post("/api/admin/sources/restricted-src/run").get_json()["status"] == "skipped"


def test_admin_actions_are_audited(env):
    admin, *_ = env
    admin.patch("/api/admin/sources/ok-src", json={"enabled": False})
    admin.patch("/api/admin/sources/restricted-src", json={"enabled": True})
    actions = [e["action"] for e in admin.get("/api/admin/audit").get_json()["entries"]]
    assert "admin.source.update" in actions and "admin.source.enable_refused" in actions


def test_patch_validation(env):
    admin, *_ = env
    assert admin.patch("/api/admin/sources/ok-src", json={"min_interval_secs": 5}).status_code == 400
    assert admin.patch("/api/admin/sources/nope", json={"enabled": False}).status_code == 404
