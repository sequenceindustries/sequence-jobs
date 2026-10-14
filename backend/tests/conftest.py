import os
import sys
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_URL = os.environ.get("TEST_DATABASE_URL",
                          "postgresql://postgres@/sequence_jobs_test?host=/tmp&port=5433")

from app.config import Config          # noqa: E402
from app.db import connect, migrate, reset_schema   # noqa: E402


class TestConfig(Config):
    ENV = "test"
    DATABASE_URL = TEST_URL


@pytest.fixture()
def db_url():
    reset_schema(TEST_URL)
    migrate(TEST_URL)
    return TEST_URL


@pytest.fixture()
def conn(db_url):
    with connect(db_url) as c:
        yield c


def make_source(db_url, slug="src-a", connector="fixture", config=None, **over):
    row = dict(slug=slug, name=slug, connector=connector, access_method="test",
               terms_status="verified_permitted", republication="full", enabled=True,
               is_dev_data=False, min_interval_secs=0)
    row.update(over)
    with connect(db_url) as c:
        cols = list(row)
        c.execute(f"INSERT INTO sources ({','.join(cols)}, config) VALUES ({','.join(['%s']*len(cols))}, %s)",
                  [row[k] for k in cols] + [Jsonb(config or {})])
        c.commit()
    return slug


@pytest.fixture()
def source_factory(db_url):
    return lambda **kw: make_source(db_url, **kw)


class AuthClient:
    """Test client wrapper that carries the CSRF token automatically."""
    def __init__(self, app):
        self.c = app.test_client()
        self.token = self.c.get("/api/auth/csrf").get_json()["csrf_token"]

    def _h(self, kw):
        kw.setdefault("headers", {})["X-CSRF-Token"] = self.token
        return kw

    def get(self, *a, **kw): return self.c.get(*a, **kw)
    def post(self, *a, **kw): return self.c.post(*a, **self._h(kw))
    def put(self, *a, **kw): return self.c.put(*a, **self._h(kw))
    def patch(self, *a, **kw): return self.c.patch(*a, **self._h(kw))
    def delete(self, *a, **kw): return self.c.delete(*a, **self._h(kw))

    def login(self, email, password="correct-horse-battery"):
        r = self.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.get_json()
        self.token = r.get_json()["csrf_token"]
        return r

    def logout(self):
        r = self.post("/api/auth/logout")
        self.token = r.get_json()["csrf_token"]
        return r

    def register(self, email, password="correct-horse-battery"):
        r = self.post("/api/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.get_json()
        self.token = r.get_json()["csrf_token"]
        return r.get_json()["id"]


def make_client(db_url, ai=None, config=TestConfig):
    from app import create_app
    config.SECRET_KEY = "test-secret"
    return AuthClient(create_app(config, ai_gateway=ai))
