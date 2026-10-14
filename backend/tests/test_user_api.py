import io
from datetime import datetime, timedelta, timezone

import pytest

from app.db import connect
from app.services import alerts as alerts_svc
from app.services import ingest, retention
from tests.conftest import make_client
from tests.helpers import SAMPLE_CV, make_docx, make_pdf
from tests.test_ingest_dedup import STATE, rec


@pytest.fixture(autouse=True)
def reset_state():
    STATE.update(records=[], complete=True, errors=[], boom=False)


@pytest.fixture()
def world(db_url, source_factory):
    """Active jobs + two registered users (A and B), each with their own client."""
    source_factory(connector="scripted", is_dev_data=True)
    STATE["records"] = [
        rec("1", title="Junior Graphic Designer", employer="Studio A", city="Johannesburg", province="Gauteng",
            location_text="Sandton, Gauteng", description="Design layouts with Photoshop and Illustrator for social media",
            requirements_text="Diploma in graphic design. 0-2 years experience.", work_mode="hybrid",
            employment_type="Full time"),
        rec("2", title="Python Developer", employer="Soft C", city="Cape Town", province="Western Cape",
            description="Flask and PostgreSQL APIs", requirements_text="Degree. 3 years Python experience.",
            work_mode="remote"),
        rec("3", title="Finance Clerk", employer="Hold D", city="Durban", province="KwaZulu-Natal",
            description="Reconciliation and bookkeeping with Pastel", requirements_text="Accounting diploma. 1 year experience."),
    ]
    ingest.run_source(db_url, "src-a", force=True)
    a, b = make_client(db_url), make_client(db_url)
    a.uid, b.uid = a.register("a@example.com"), b.register("b@example.com")
    return a, b


def job_id(db_url, title):
    with connect(db_url) as c:
        return c.execute("SELECT id FROM jobs WHERE title = %s", (title,)).fetchone()["id"]


# ------------------------------------------------------------------------------------------------ auth
def test_all_user_endpoints_require_login(db_url):
    anon = make_client(db_url)
    for method, path in [("get", "/api/profile"), ("get", "/api/cv"), ("get", "/api/applications"), ("get", "/api/alerts"),
                         ("get", "/api/notifications"), ("get", "/api/recommendations"), ("get", "/api/saved"),
                         ("post", "/api/match"), ("post", "/api/applications"), ("post", "/api/cv")]:
        r = getattr(anon, method)(path, json={}) if method == "post" else anon.get(path)
        assert r.status_code == 401, (method, path)


# ---------------------------------------------------------------------------------------------- profile
def test_profile_roundtrip_and_protected_fields(world):
    a, _ = world
    assert a.put("/api/profile", json={"skills": ["Python"], "work_modes": ["remote"]}).status_code == 200
    assert a.get("/api/profile").get_json()["profile"]["skills"] == ["python"]
    r = a.put("/api/profile", json={"gender": "x"})
    assert r.status_code == 400 and r.get_json()["error"] == "protected_field"
    assert a.delete("/api/profile").status_code == 200 and a.get("/api/profile").get_json()["profile"] == {}


# ------------------------------------------------------------------------------------------------- CVs
def test_cv_upload_txt_docx_pdf_and_json(world):
    a, _ = world
    for name, data in [("cv.txt", SAMPLE_CV.encode()), ("cv.docx", make_docx(SAMPLE_CV.split("\n"))), ("cv.pdf", make_pdf(SAMPLE_CV))]:
        r = a.post("/api/cv", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")
        assert r.status_code == 201, (name, r.get_json())
        assert "photoshop" in r.get_json()["parsed"]["skills"]
    assert a.post("/api/cv", json={"text": SAMPLE_CV}).status_code == 201


def test_cv_upload_rejections_over_http(world):
    a, _ = world
    r = a.post("/api/cv", data={"file": (io.BytesIO(b"MZ" + b"x" * 200), "cv.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["error"] == "type_mismatch"
    r = a.post("/api/cv", data={"file": (io.BytesIO(b"hello" * 100), "cv.exe")}, content_type="multipart/form-data")
    assert r.get_json()["error"] == "unsupported_type"
    big = io.BytesIO(b"a" * (2 * 1024 * 1024 + 10_000))
    r = a.post("/api/cv", data={"file": (big, "cv.txt")}, content_type="multipart/form-data")
    assert r.status_code == 413 and r.get_json()["error"] == "file_too_large"
    assert a.post("/api/cv", json={"text": "short"}).status_code == 400


def test_raw_upload_is_not_stored_only_text_with_expiry(world, db_url):
    a, _ = world
    r = a.post("/api/cv", json={"text": SAMPLE_CV})
    with connect(db_url) as c:
        cols = {x["column_name"] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='cvs'")}
        row = c.execute("SELECT expires_at, created_at FROM cvs").fetchone()
    assert not ({"data", "file", "content", "blob", "raw"} & cols)
    assert timedelta(days=29) < row["expires_at"] - row["created_at"] < timedelta(days=31)
    assert "not kept" in r.get_json()["retention_note"]


def test_cv_limit_and_delete(world):
    a, _ = world
    ids = [a.post("/api/cv", json={"text": SAMPLE_CV}).get_json()["id"] for _ in range(5)]
    assert a.post("/api/cv", json={"text": SAMPLE_CV}).status_code == 400
    assert a.delete(f"/api/cv/{ids[0]}").status_code == 200 and a.get(f"/api/cv/{ids[0]}").status_code == 404


def test_expired_cvs_are_purged_and_unreadable(world, db_url):
    a, _ = world
    cid = a.post("/api/cv", json={"text": SAMPLE_CV}).get_json()["id"]
    with connect(db_url) as c:
        c.execute("UPDATE cvs SET expires_at = now() - interval '1 minute'"); c.commit()
    assert a.get(f"/api/cv/{cid}").status_code == 404                      # unreadable as soon as expired
    assert retention.purge_expired(db_url)["cvs_deleted"] == 1


# ------------------------------------------------------------------------------------------------ match
def test_match_endpoint(world, db_url):
    a, _ = world
    cid = a.post("/api/cv", json={"text": SAMPLE_CV}).get_json()["id"]
    jid = job_id(db_url, "Junior Graphic Designer")
    m = a.post("/api/match", json={"job_id": jid, "cv_id": cid}).get_json()
    assert m["overall_score"] >= 70 and "photoshop" in m["skills_evidence"]["confirmed_in_cv"]
    assert a.post("/api/match", json={"job_id": 999999, "cv_id": cid}).status_code == 404
    assert a.post("/api/match", json={"cv_id": cid}).status_code == 400


# ----------------------------------------------------------------------------------------- isolation
def test_users_cannot_see_or_use_each_others_data(world, db_url):
    a, b = world
    cid = a.post("/api/cv", json={"text": SAMPLE_CV}).get_json()["id"]
    app_id = a.post("/api/applications", json={"job_title": "Secret role", "notes": "private note"}).get_json()["application"]["id"]
    alert_id = a.post("/api/alerts", json={"filters": {"keywords": ["python"]}}).get_json()["alert"]["id"]
    a.put("/api/profile", json={"skills": ["python"]})
    jid = job_id(db_url, "Python Developer")

    # B cannot read, match with, delete or modify A's resources: always 404, never 403 (no existence leak)
    assert b.get(f"/api/cv/{cid}").status_code == 404
    assert b.delete(f"/api/cv/{cid}").status_code == 404
    assert b.post("/api/match", json={"job_id": jid, "cv_id": cid}).status_code == 404
    assert b.get(f"/api/recommendations?cv_id={cid}").status_code == 404
    assert b.patch(f"/api/applications/{app_id}", json={"status": "applied"}).status_code == 404
    assert b.delete(f"/api/applications/{app_id}").status_code == 404
    assert b.patch(f"/api/alerts/{alert_id}", json={"enabled": False}).status_code == 404
    assert b.delete(f"/api/alerts/{alert_id}").status_code == 404
    # and B's lists are empty, profile is separate
    assert b.get("/api/cv").get_json()["cvs"] == [] and b.get("/api/applications").get_json()["applications"] == []
    assert b.get("/api/alerts").get_json()["alerts"] == [] and b.get("/api/profile").get_json()["profile"] == {}
    dash = b.get("/api/applications/dashboard").get_json()
    assert dash["active"] == [] and dash["status_distribution"] == {}
    # A's data is intact
    assert a.get(f"/api/cv/{cid}").status_code == 200
    assert a.get("/api/applications").get_json()["applications"][0]["notes"] == "private note"


def test_private_data_never_in_public_endpoints(world, db_url):
    a, _ = world
    a.post("/api/applications", json={"job_title": "UniqueSecretTitleXYZ"})
    a.post("/api/cv", json={"text": SAMPLE_CV})
    anon = make_client(db_url)
    for path in ("/api/jobs", "/api/jobs?q=UniqueSecretTitleXYZ", "/api/insights/skills", "/api/health"):
        body = anon.get(path).get_data(as_text=True)
        assert "UniqueSecretTitleXYZ" not in body and "jane@example.com" not in body


# ---------------------------------------------------------------------------------------------- tracker
def test_tracker_crud_events_and_dashboard(world, db_url):
    a, _ = world
    jid = job_id(db_url, "Python Developer")
    r = a.post("/api/applications", json={"job_id": jid})            # job_title missing -> required
    assert r.status_code == 400
    r = a.post("/api/applications", json={"job_id": jid, "job_title": "Python Developer", "status": "preparing",
                                          "follow_up_on": (datetime.now() + timedelta(days=3)).date().isoformat()})
    app = r.get_json()["application"]
    assert app["employer"] == "Soft C" and app["listing_url"].startswith("https://acme")      # prefilled from the job
    assert a.patch(f"/api/applications/{app['id']}", json={"status": "interview",
                   "interview_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()}).status_code == 200
    assert a.patch(f"/api/applications/{app['id']}", json={"status": "bogus"}).status_code == 400
    d = a.get("/api/applications/dashboard").get_json()
    assert d["status_distribution"] == {"interview": 1} and len(d["active"]) == 1
    assert len(d["upcoming_interviews"]) == 1 and len(d["follow_up_reminders"]) == 1
    assert any("preparing -> interview" in e["detail"] for e in d["recent_activity"])
    assert a.delete(f"/api/applications/{app['id']}").status_code == 200


@pytest.mark.parametrize("body", [{"job_title": "x", "status": "nope"}, {"job_title": "x", "applied_on": "13/02/2026"},
                                  {"job_title": "x", "listing_url": "javascript:alert(1)"}, {"job_title": ""}])
def test_tracker_validation(world, body):
    a, _ = world
    assert a.post("/api/applications", json=body).status_code == 400


# ------------------------------------------------------------------------------- saved/dismiss/report
def test_save_dismiss_report(world, db_url):
    a, _ = world
    jid = job_id(db_url, "Finance Clerk")
    assert a.put(f"/api/jobs/{jid}/save").status_code == 200
    assert [j["title"] for j in a.get("/api/saved").get_json()["jobs"]] == ["Finance Clerk"]
    a.delete(f"/api/jobs/{jid}/save")
    assert a.get("/api/saved").get_json()["jobs"] == []
    assert a.post(f"/api/jobs/{jid}/report", json={"reason": "bogus"}).status_code == 400
    assert a.post(f"/api/jobs/{jid}/report", json={"reason": "wrong_details", "note": "salary wrong"}).status_code == 201
    with connect(db_url) as c:
        r = c.execute("SELECT needs_review, review_reasons FROM jobs WHERE id = %s", (jid,)).fetchone()
    assert r["needs_review"] and "user_reported" in r["review_reasons"]
    assert a.put("/api/jobs/999999/save").status_code == 404


# ---------------------------------------------------------------------------------- recommendations
def test_recommendations_are_explained_filtered_and_respect_dismissals(world, db_url):
    a, _ = world
    assert a.get("/api/recommendations").get_json()["recommendations"] == []        # nothing to go on yet
    a.put("/api/profile", json={"skills": ["photoshop", "illustrator", "graphic design"], "provinces": ["Gauteng"],
                                "work_modes": ["hybrid", "remote"]})
    recs = a.get("/api/recommendations").get_json()["recommendations"]
    titles = [r["job"]["title"] for r in recs]
    assert titles[0] == "Junior Graphic Designer" and "Finance Clerk" not in titles
    assert any("skills match" in x for x in recs[0]["reasons"]) and recs[0]["match_score"] > 0
    assert recs[0]["missing_or_unverified"] is not None
    a.post(f"/api/jobs/{recs[0]['job']['id']}/dismiss")
    assert "Junior Graphic Designer" not in [r["job"]["title"] for r in a.get("/api/recommendations").get_json()["recommendations"]]


def test_recommendation_not_driven_by_keyword_alone(world):
    a, _ = world
    a.put("/api/profile", json={"skills": ["welding"]})                                # skill outside our taxonomy
    assert a.get("/api/recommendations").get_json()["recommendations"] == []


def test_recommendations_skip_jobs_past_closing_date(world, db_url):
    a, _ = world
    with connect(db_url) as c:
        c.execute("UPDATE jobs SET closing_at = now() - interval '1 day' WHERE title = 'Python Developer'"); c.commit()
    a.put("/api/profile", json={"skills": ["python", "flask"]})
    assert "Python Developer" not in [r["job"]["title"] for r in a.get("/api/recommendations").get_json()["recommendations"]]


# ------------------------------------------------------------------------------------------- alerts
def test_alert_creation_validation_and_limits(world):
    a, _ = world
    assert a.post("/api/alerts", json={"filters": {}}).status_code == 400
    assert a.post("/api/alerts", json={"filters": {"keywords": ["x"]}, "frequency": "hourly"}).status_code == 400
    for _ in range(10):
        assert a.post("/api/alerts", json={"filters": {"keywords": ["python"]}}).status_code == 201
    assert a.post("/api/alerts", json={"filters": {"keywords": ["python"]}}).status_code == 400


def test_alerts_notify_once_and_never_repeat_unchanged_jobs(world, db_url):
    a, _ = world
    a.post("/api/alerts", json={"name": "Py", "filters": {"keywords": ["python"]}, "frequency": "instant"})
    with connect(db_url) as c:
        c.execute("UPDATE alerts SET created_at = now() - interval '1 day'"); c.commit()
    s1 = alerts_svc.run_alerts(db_url)
    assert s1["notifications"] == 1
    s2 = alerts_svc.run_alerts(db_url)                                      # nothing new
    assert s2["notifications"] == 0
    ingest.run_source(db_url, "src-a", force=True)                          # re-ingest unchanged jobs
    assert alerts_svc.run_alerts(db_url)["notifications"] == 0
    # a genuinely new matching vacancy notifies exactly once
    STATE["records"] = STATE["records"] + [rec("9", title="Senior Python Engineer", employer="Other", description="Python APIs")]
    ingest.run_source(db_url, "src-a", force=True)
    assert alerts_svc.run_alerts(db_url)["notifications"] == 1
    assert alerts_svc.run_alerts(db_url)["notifications"] == 0
    n = a.get("/api/notifications").get_json()
    assert n["unread"] == 2 and all(x["reasons"] for x in n["notifications"])
    assert a.post(f"/api/notifications/{n['notifications'][0]['id']}/read").status_code == 200
    assert a.get("/api/notifications").get_json()["unread"] == 1


def test_alert_frequency_respected(world, db_url):
    a, _ = world
    a.post("/api/alerts", json={"filters": {"keywords": ["python"]}, "frequency": "weekly"})
    with connect(db_url) as c:
        c.execute("UPDATE alerts SET created_at = now() - interval '2 days'"); c.commit()
    assert alerts_svc.run_alerts(db_url)["alerts_run"] == 1
    assert alerts_svc.run_alerts(db_url)["alerts_run"] == 0                 # not due again for a week
    assert alerts_svc.run_alerts(db_url, now=datetime.now(timezone.utc) + timedelta(days=7))["alerts_run"] == 1


def test_disabled_alert_does_not_run(world, db_url):
    a, _ = world
    aid = a.post("/api/alerts", json={"filters": {"keywords": ["python"]}, "frequency": "instant"}).get_json()["alert"]["id"]
    a.patch(f"/api/alerts/{aid}", json={"enabled": False})
    assert alerts_svc.run_alerts(db_url)["alerts_run"] == 0


class OkSender(alerts_svc.EmailSender):
    def __init__(self): self.sent = []
    def send(self, to, subject, body): self.sent.append((to, subject, body))


class FlakySender(alerts_svc.EmailSender):
    def send(self, to, subject, body): raise ConnectionError("smtp down")


def _email_alert(a, db_url):
    a.post("/api/alerts", json={"filters": {"keywords": ["python"]}, "frequency": "instant", "channel": "email"})
    with connect(db_url) as c:
        c.execute("UPDATE alerts SET created_at = now() - interval '1 day'"); c.commit()


def test_email_delivery_success_failure_and_unconfigured(world, db_url):
    a, _ = world
    _email_alert(a, db_url)
    stats = alerts_svc.run_alerts(db_url, sender=alerts_svc.NullSender())         # no provider configured
    assert stats["emails_queued"] == 1 and stats["outbox"]["not_configured"] == 1
    with connect(db_url) as c:
        assert c.execute("SELECT status FROM email_outbox").fetchone()["status"] == "not_configured"   # not faked as sent
    assert alerts_svc.process_outbox(db_url, FlakySender())["retry"] == 1
    assert alerts_svc.process_outbox(db_url, FlakySender())["retry"] == 1
    assert alerts_svc.process_outbox(db_url, FlakySender())["failed"] == 1          # gives up after 3 attempts
    with connect(db_url) as c:
        r = c.execute("SELECT status, attempts, error FROM email_outbox").fetchone()
    assert (r["status"], r["attempts"]) == ("failed", 3) and "smtp down" in r["error"]
    ok = OkSender()
    with connect(db_url) as c:
        c.execute("UPDATE email_outbox SET status = 'queued', attempts = 0"); c.commit()
    assert alerts_svc.process_outbox(db_url, ok)["sent"] == 1
    assert ok.sent[0][0] == "a@example.com" and "Python Developer" in ok.sent[0][2]
    assert alerts_svc.process_outbox(db_url, ok)["sent"] == 0                       # sent mail is not re-sent


# ----------------------------------------------------------------------------------------- insights
def test_skill_insights_are_aggregate_only(world, db_url):
    anon = make_client(db_url)
    j = anon.get("/api/insights/skills?q=python").get_json()
    assert j["jobs_analysed"] == 1 and {s["skill"] for s in j["skills"]} >= {"python", "flask", "postgresql"}
    j = anon.get("/api/insights/skills").get_json()
    assert j["jobs_analysed"] == 3 and all(set(s) == {"skill", "jobs", "share"} for s in j["skills"])
