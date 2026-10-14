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
