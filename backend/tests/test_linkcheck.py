import pytest

from app.db import connect
from app.services import ingest, linkcheck
from tests.test_ingest_dedup import FakeResp, STATE, rec


class Sess:
    def __init__(self, status):
        self.headers, self.status, self.urls = {}, status, []

    def get(self, url, **kw):
        if url.endswith("/robots.txt"):
            return FakeResp(404, "")
        self.urls.append(url)
        if isinstance(self.status, Exception):
            raise self.status
        return FakeResp(self.status, "x")


def client(status):
    from app.connectors.base import HttpClient
    return HttpClient("ua", session=Sess(status), max_retries=1)


@pytest.fixture()
def live(db_url, source_factory):
    source_factory(slug="real", connector="scripted", terms_status="verified_permitted", enabled=True, is_dev_data=False)
    STATE.update(records=[rec("1", title="Clerk")], complete=True, errors=[], boom=False)
    ingest.run_source(db_url, "real", force=True)
    return db_url


def row(db_url):
    with connect(db_url) as c:
        return c.execute("SELECT status, needs_review, review_reasons FROM jobs").fetchone()


def test_flagged_only_after_two_consecutive_gone_and_never_expired(live):
    linkcheck.check_links(live, client(404), delay=0)
    r = row(live)
    assert not r["needs_review"] and "link_gone_once" in r["review_reasons"]
    s = linkcheck.check_links(live, client(410), delay=0)
    r = row(live)
    assert s["flagged"] == 1 and r["needs_review"] and "link_broken" in r["review_reasons"] and r["status"] == "active"


def test_recovery_clears_flags(live):
    linkcheck.check_links(live, client(404), delay=0)
    linkcheck.check_links(live, client(200), delay=0)
    r = row(live)
    assert r["review_reasons"] == [] and not r["needs_review"]


@pytest.mark.parametrize("status", [500, 403, 429, __import__("requests").ConnectionError("x")])
def test_uncertain_results_change_nothing(live, status):
    s = linkcheck.check_links(live, client(status), delay=0)
    assert s["unknown"] == 1 and row(live)["review_reasons"] == []


def test_dev_restricted_and_disabled_sources_not_checked(db_url, source_factory):
    source_factory(slug="dev", connector="scripted", terms_status="verified_permitted", enabled=True, is_dev_data=True)
    STATE.update(records=[rec("1")], complete=True, errors=[], boom=False)
    ingest.run_source(db_url, "dev", force=True)
    sess = client(404)
    assert linkcheck.check_links(db_url, sess, delay=0)["checked"] == 0 and sess.session.urls == []
