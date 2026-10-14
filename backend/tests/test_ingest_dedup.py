from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.connectors.base import (BaseConnector, ConnectorError, FetchResult, HttpClient, JobRecord,
                                 RobotsDisallowed)
from app.connectors.registry import register
from app.db import connect
from app.services import ingest
from app.services.dedup import classify_pair, description_similarity, jaccard

# --------------------------------------------------------------------------- test connectors
STATE = {"records": [], "complete": True, "errors": [], "boom": False}


@register
class ScriptedConnector(BaseConnector):
    key = "scripted"

    def fetch(self):
        if STATE["boom"]:
            raise ConnectorError("source is down")
        return FetchResult(list(STATE["records"]), STATE["complete"], list(STATE["errors"]))


@register
class AlwaysBroken(BaseConnector):
    key = "always_broken"

    def fetch(self):
        raise RuntimeError("kaboom")


def rec(i="1", title="Python Developer", employer="Acme (Pty) Ltd", **kw):
    base = dict(source_job_id=i, title=title, source_url=f"https://acme.example.invalid/{i}",
                employer=employer, description="Build APIs in Flask and PostgreSQL for our clients.",
                location_text="Cape Town", city="Cape Town", province="Western Cape",
                published_at=date(2026, 10, 1), extraction_confidence=0.9)
    base.update(kw)
    return JobRecord(**base)


@pytest.fixture(autouse=True)
def reset_state():
    STATE.update(records=[], complete=True, errors=[], boom=False)


def run(db_url, slug="src-a", **kw):
    return ingest.run_source(db_url, slug, force=True, **kw)


def jobs(db_url, where="true"):
    with connect(db_url) as c:
        return c.execute(f"SELECT * FROM jobs WHERE {where} ORDER BY id").fetchall()


# --------------------------------------------------------------------------- ingestion
def test_new_listing_created_with_provenance(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1")]
    r = run(db_url)
    assert (r["status"], r["created"]) == ("success", 1)
    j = jobs(db_url)[0]
    assert j["source_job_id"] == "1" and j["source_url"].startswith("https://acme")
    assert j["status"] == "active" and j["first_seen_at"] and j["last_verified_at"]
    assert j["salary_min"] is None            # unknown stays unknown


def test_unchanged_listing_not_rewritten_and_no_new_version(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1")]
    run(db_url)
    r = run(db_url)
    assert (r["created"], r["updated"], r["unchanged"]) == (0, 0, 1)
    with connect(db_url) as c:
        assert c.execute("SELECT count(*) n FROM job_versions").fetchone()["n"] == 1


def test_updated_listing_tracks_history_and_invalidates_ai_status(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1")]
    run(db_url)
    with connect(db_url) as c:
        c.execute("UPDATE jobs SET ai_analysis_status = 'complete'"); c.commit()
    STATE["records"] = [rec("1", salary_min=Decimal(50000), salary_max=Decimal(60000), salary_period="month",
                            salary_currency="ZAR")]
    r = run(db_url)
    assert r["updated"] == 1
    with connect(db_url) as c:
        v = c.execute("SELECT changed_fields FROM job_versions ORDER BY id DESC LIMIT 1").fetchone()
        assert {"salary_min", "salary_max", "salary_period"} <= set(v["changed_fields"])
        assert c.execute("SELECT ai_analysis_status s FROM jobs").fetchone()["s"] == "pending"


def test_missing_optional_fields_ingest_fine(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [JobRecord(source_job_id="x", title="Bare job", source_url="https://e.invalid/x")]
    assert run(db_url)["created"] == 1
    j = jobs(db_url)[0]
    assert j["employer"] is None and j["needs_review"] and "employer_unknown" in j["review_reasons"]


def test_invalid_record_is_isolated_not_fatal(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1"), JobRecord(source_job_id="2", title="  ", source_url="https://e.invalid/2"),
                        rec("3", title="Another")]
    r = run(db_url)
    assert (r["created"], r["errors"], r["status"]) == (2, 1, "partial")
    with connect(db_url) as c:
        assert c.execute("SELECT count(*) n FROM ingestion_errors WHERE stage='store'").fetchone()["n"] == 1


def test_source_failure_does_not_stop_other_sources(db_url, source_factory):
    source_factory(slug="good", connector="scripted")
    source_factory(slug="bad", connector="always_broken")
    STATE["records"] = [rec("1")]
    out = {r["source"]: r for r in ingest.run_all(db_url, max_workers=2)}
    assert out["bad"]["status"] == "failed" and out["good"]["status"] == "success"
    with connect(db_url) as c:
        bad = c.execute("SELECT health, consecutive_failures FROM sources WHERE slug='bad'").fetchone()
        assert bad["health"] == "degraded" and bad["consecutive_failures"] == 1
        assert c.execute("SELECT health FROM sources WHERE slug='good'").fetchone()["health"] == "healthy"


def test_repeated_failures_mark_source_failing_and_failure_never_expires_jobs(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1")]
    run(db_url)
    STATE["boom"] = True
    for _ in range(3):
        run(db_url)
    with connect(db_url) as c:
        assert c.execute("SELECT health FROM sources").fetchone()["health"] == "failing"
    assert jobs(db_url)[0]["status"] == "active"          # outage must not expire anything


def test_missing_from_complete_snapshot_expires(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1"), rec("2", title="Other role")]
    run(db_url)
    STATE["records"] = [rec("1")]
    r = run(db_url)
    assert r["expired"] == 1
    st = {j["source_job_id"]: j["status"] for j in jobs(db_url)}
    assert st == {"1": "active", "2": "expired"}


def test_missing_from_partial_snapshot_does_not_expire(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [rec("1"), rec("2", title="Other role")]
    run(db_url)
    STATE.update(records=[rec("1")], complete=False)
    assert run(db_url)["expired"] == 0


def test_closing_date_expires_and_reappearance_reactivates(db_url, source_factory):
    source_factory(connector="scripted")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    STATE["records"] = [rec("1", closing_at=past)]
    run(db_url)
    assert jobs(db_url)[0]["status"] == "expired"
    STATE["records"] = [rec("1", closing_at=datetime.now(timezone.utc) + timedelta(days=10))]
    run(db_url)
    assert jobs(db_url)[0]["status"] == "active"


def test_min_interval_prevents_refetching(db_url, source_factory):
    source_factory(connector="scripted", min_interval_secs=3600)
    STATE["records"] = [rec("1")]
    assert ingest.run_source(db_url, "src-a")["status"] == "success"
    assert ingest.run_source(db_url, "src-a")["reason"] == "min_interval not elapsed"


def test_prohibited_and_disabled_sources_are_never_fetched(db_url, source_factory):
    source_factory(slug="no", connector="always_broken", terms_status="prohibited")
    source_factory(slug="off", connector="always_broken", enabled=False)
    assert ingest.run_source(db_url, "no", force=True)["status"] == "skipped"
    assert ingest.run_source(db_url, "off")["status"] == "skipped"


def test_dev_data_flag_propagates(db_url, source_factory):
    source_factory(connector="scripted", is_dev_data=True)
    STATE["records"] = [rec("1")]
    run(db_url)
    assert jobs(db_url)[0]["is_dev_data"] is True


def test_data_quality_flags(db_url, source_factory):
    source_factory(connector="scripted")
    STATE["records"] = [
        rec("1", salary_min=Decimal(900000), salary_max=Decimal(900000), salary_period="month"),
        rec("2", title="B", salary_min=Decimal(30000), salary_max=Decimal(20000), salary_period="month"),
        rec("3", title="C", published_at=date(2026, 10, 10),
            closing_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=400)),
        rec("4", title="D", salary_min=Decimal(30000), salary_max=Decimal(30000)),
    ]
    run(db_url)
    reasons = {j["source_job_id"]: set(j["review_reasons"]) for j in jobs(db_url)}
    assert "suspicious_salary" in reasons["1"]
    assert "salary_range_inverted" in reasons["2"]
    assert "salary_period_unknown" in reasons["4"]
    assert not reasons["3"]


# --------------------------------------------------------------------------- dedup
A = dict(employer="Acme (Pty) Ltd", title="Senior Python Developer", city="Cape Town",
         province="Western Cape", location_text="Cape Town", source_id=1,
         description="Build and maintain Flask APIs backed by PostgreSQL for enterprise clients across Africa.",
         published_at=date(2026, 10, 1), status="active", application_url=None, reference_no=None)


def test_similar_title_alone_never_links():
    other = {**A, "employer": "Different Co", "source_id": 2}
    assert classify_pair(other, A) is None
    same_emp_other_city = {**A, "source_id": 2, "city": "Durban", "province": "KwaZulu-Natal",
                           "location_text": "Durban", "description": "Entirely different description text here."}
    assert classify_pair(same_emp_other_city, A) is None      # only 'title' signal


def test_unknown_employer_never_links():
    assert classify_pair({**A, "employer": None, "source_id": 2}, A) is None


def test_same_vacancy_on_two_sources_links():
    new = {**A, "source_id": 2, "published_at": date(2026, 10, 3)}
    res = classify_pair(new, A)
    assert res["relation"] == "same_vacancy_other_source" and {"title", "location", "description"} <= set(res["signals"])


def test_application_url_plus_location_links_even_if_title_differs():
    old = {**A, "application_url": "https://acme.example.invalid/apply/9?utm=1"}
    new = {**A, "source_id": 2, "title": "Python Engineer", "description": "x",
           "application_url": "http://www.acme.example.invalid/apply/9/"}
    res = classify_pair(new, old)
    assert res and "application_url" in res["signals"]


def test_repost_after_first_ended_or_long_gap():
    ended = {**A, "status": "expired"}
    new = {**A, "source_id": 2, "published_at": date(2026, 10, 20)}
    assert classify_pair(new, ended)["relation"] == "repost"
    gap = {**A, "source_id": 2, "published_at": date(2026, 12, 20)}
    assert classify_pair(gap, A)["relation"] == "repost"


def test_same_source_second_id_is_duplicate():
    new = {**A, "published_at": date(2026, 10, 2)}
    assert classify_pair(new, A)["relation"] == "duplicate"


def test_similar_but_distinct_positions_not_linked():
    new = {**A, "source_id": 2, "title": "Junior Python Developer", "city": "Pretoria",
           "province": "Gauteng", "location_text": "Pretoria",
           "description": "Support the data team with reporting dashboards and spreadsheets."}
    assert classify_pair(new, A) is None


def test_similarity_helpers():
    assert jaccard("Python Developer", "python  developer!") == 1.0
    assert description_similarity("a b c", "a b c") == 0.0      # too short to shingle: never "similar"


def test_cross_source_link_end_to_end_keeps_both_rows(db_url, source_factory):
    source_factory(slug="src-a", connector="scripted")
    run(db_url)  # nothing yet
    STATE["records"] = [rec("1", title="Senior Python Developer")]
    run(db_url, "src-a")
    # second source publishes the same vacancy
    source_factory(slug="src-b", connector="scripted")
    STATE["records"] = [rec("zz9", title="Senior Python Developer")]
    run(db_url, "src-b")
    rows = jobs(db_url, "true")
    assert len(rows) == 2
    linked = [r for r in rows if r["canonical_job_id"]]
    assert len(linked) == 1 and linked[0]["dup_relation"] == "same_vacancy_other_source"


# --------------------------------------------------------------------------- HTTP client
class FakeResp:
    def __init__(self, status, text="", headers=None, js=None):
        self.status_code, self.text, self.headers, self._js, self.content = status, text, headers or {}, js, text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ConnectorError(f"HTTP {self.status_code}")

    def json(self):
        return self._js


class FakeSession:
    def __init__(self, script, robots=(404, "")):
        self.headers, self.script, self.calls, self.robots = {}, list(script), [], robots

    def get(self, url, **kw):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResp(*self.robots)
        return self.script.pop(0)


def test_http_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession([FakeResp(503), FakeResp(503), FakeResp(200, "ok")])
    resp = HttpClient("ua", max_retries=3, session=s).get("https://e.invalid/a")
    assert resp.text == "ok" and sum(1 for c in s.calls if not c.endswith("robots.txt")) == 3


def test_http_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession([FakeResp(500)] * 5)
    with pytest.raises(ConnectorError, match="Giving up"):
        HttpClient("ua", max_retries=3, session=s).get("https://e.invalid/a")
    assert len([c for c in s.calls if not c.endswith("robots.txt")]) == 3


def test_http_never_works_around_access_refusal(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession([FakeResp(403), FakeResp(200, "should not be reached")])
    with pytest.raises(ConnectorError, match="Access refused"):
        HttpClient("ua", session=s).get("https://e.invalid/a")
    assert len([c for c in s.calls if not c.endswith("robots.txt")]) == 1


def test_robots_disallow_is_respected():
    s = FakeSession([FakeResp(200, "should not be fetched")], robots=(200, "User-agent: *\nDisallow: /private"))
    with pytest.raises(RobotsDisallowed):
        HttpClient("ua", session=s).get("https://e.invalid/private/jobs")


def test_unverifiable_robots_means_do_not_crawl():
    s = FakeSession([FakeResp(200, "x")], robots=(403, ""))
    with pytest.raises(RobotsDisallowed):
        HttpClient("ua", session=s).get("https://e.invalid/jobs")
