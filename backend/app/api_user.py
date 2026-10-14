"""Authenticated, per-user API. Every query is scoped by user_id; other users' resources look like 404."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from psycopg.types.json import Jsonb

from .auth import current_user, db_url, limited, login_required
from .db import connect
from .services import alerts as alerts_svc
from .services import cv as cv_svc
from .services.matching import match_job
from .services.profile import ProfileError, validate_profile
from .services.recommend import recommend
from .services.search import PUBLIC_FIELDS, search_jobs

bp = Blueprint("user", __name__)

STATUSES = ("interested", "preparing", "applied", "interview", "assessment", "offer", "rejected", "withdrawn", "closed")


def _uid() -> int:
    return current_user()["id"]


def _include_dev() -> bool:
    return not current_app.config["CFG"].is_production()


def _json() -> dict:
    return request.get_json(silent=True) or {}


# ------------------------------------------------------------------------------------------- profile
@bp.get("/profile")
@login_required
def get_profile():
    with connect(db_url()) as c:
        row = c.execute("SELECT data, updated_at FROM profiles WHERE user_id = %s", (_uid(),)).fetchone()
    return jsonify(profile=row["data"] if row else {}, updated_at=row["updated_at"] if row else None)


@bp.put("/profile")
@login_required
def put_profile():
    try:
        data = validate_profile(_json())
    except ProfileError as e:
        return jsonify(error=e.code, message=e.message, fields=e.fields), 400
    with connect(db_url()) as c:
        c.execute("INSERT INTO profiles (user_id, data) VALUES (%s,%s) ON CONFLICT (user_id) "
                  "DO UPDATE SET data = EXCLUDED.data, updated_at = now()", (_uid(), Jsonb(data)))
        c.commit()
    return jsonify(profile=data)


@bp.delete("/profile")
@login_required
def delete_profile():
    with connect(db_url()) as c:
        c.execute("DELETE FROM profiles WHERE user_id = %s", (_uid(),))
        c.commit()
    return jsonify(ok=True)


def _profile(c) -> dict:
    row = c.execute("SELECT data FROM profiles WHERE user_id = %s", (_uid(),)).fetchone()
    return row["data"] if row else {}


# ------------------------------------------------------------------------------------------------- CVs
@bp.post("/cv")
@login_required
@limited("cv-upload", 20, 3600, by_user=True)
def upload_cv():
    cfg = current_app.config["CFG"]
    try:
        if "file" in request.files:
            f = request.files["file"]
            text, ext = cv_svc.extract_text(f.filename or "", f.read(cfg.CV_MAX_BYTES + 1), cfg.CV_MAX_BYTES)
        else:
            text = _json().get("text", "")
            if not isinstance(text, str) or len(text.strip()) < 40:
                raise cv_svc.CVError("no_text", "Provide a file, or CV text of at least a few lines.")
            text, ext = cv_svc._clean(text), "txt"
    except cv_svc.CVError as e:
        return jsonify(error=e.code, message=e.message), 400
    parsed = cv_svc.parse_cv(text)
    label = (request.form.get("label") or _json().get("label") or "")[:80] or None
    with connect(db_url()) as c:
        n = c.execute("SELECT count(*) n FROM cvs WHERE user_id = %s", (_uid(),)).fetchone()["n"]
        if n >= 5:
            return jsonify(error="cv_limit", message="You can keep up to 5 CVs. Delete one first."), 400
        row = c.execute(
            "INSERT INTO cvs (user_id, label, source_ext, text_content, parsed, expires_at) "
            "VALUES (%s,%s,%s,%s,%s, now() + make_interval(days => %s)) RETURNING id, expires_at",
            (_uid(), label, ext, text, Jsonb(parsed), cfg.CV_RETENTION_DAYS)).fetchone()
        c.commit()
    return jsonify(id=row["id"], parsed=parsed, expires_at=row["expires_at"],
                   retention_note=f"The uploaded file itself is not kept. Extracted text is deleted after "
                                  f"{cfg.CV_RETENTION_DAYS} days or when you delete it."), 201


@bp.get("/cv")
@login_required
def list_cvs():
    with connect(db_url()) as c:
        rows = c.execute("SELECT id, label, source_ext, created_at, expires_at FROM cvs WHERE user_id = %s ORDER BY id DESC", (_uid(),)).fetchall()
    return jsonify(cvs=rows)


def _own_cv(c, cv_id: int):
    return c.execute("SELECT * FROM cvs WHERE id = %s AND user_id = %s AND expires_at > now()", (cv_id, _uid())).fetchone()


@bp.get("/cv/<int:cv_id>")
@login_required
def get_cv(cv_id: int):
    with connect(db_url()) as c:
        cv = _own_cv(c, cv_id)
    if not cv:
        return jsonify(error="not_found"), 404
    return jsonify(id=cv["id"], label=cv["label"], text=cv["text_content"], parsed=cv["parsed"], expires_at=cv["expires_at"])


@bp.delete("/cv/<int:cv_id>")
@login_required
def delete_cv(cv_id: int):
    with connect(db_url()) as c:
        n = c.execute("DELETE FROM cvs WHERE id = %s AND user_id = %s", (cv_id, _uid())).rowcount
        c.commit()
    return (jsonify(ok=True), 200) if n else (jsonify(error="not_found"), 404)


# ----------------------------------------------------------------------------------------- matching
def _job_for_match(c, job_id: int):
    return c.execute(
        f"SELECT {PUBLIC_FIELDS}, j.extracted_skills, j.min_experience_years, j.required_education, j.description, "
        "j.requirements_text FROM jobs j JOIN sources s ON s.id = j.source_id "
        "WHERE j.id = %s AND j.canonical_job_id IS NULL" + ("" if _include_dev() else " AND j.is_dev_data = false"),
        (job_id,)).fetchone()


@bp.post("/match")
@login_required
@limited("match", 120, 3600, by_user=True)
def match():
    body = _json()
    try:
        job_id, cv_id = int(body.get("job_id")), body.get("cv_id")
    except (TypeError, ValueError):
        return jsonify(error="invalid", message="job_id is required."), 400
    with connect(db_url()) as c:
        job = _job_for_match(c, job_id)
        if not job:
            return jsonify(error="job_not_found"), 404
        cv = _own_cv(c, int(cv_id)) if cv_id is not None else None
        if cv_id is not None and not cv:
            return jsonify(error="cv_not_found"), 404
        profile = _profile(c)
    result = match_job(job, cv["text_content"] if cv else None, cv["parsed"] if cv else None, profile)
    result["job_id"] = job_id
    return jsonify(result)


# ------------------------------------------------------------------------- saved / dismissed / report
@bp.put("/jobs/<int:job_id>/save")
@login_required
def save_job(job_id: int):
    return _interact(job_id, "saved")


@bp.post("/jobs/<int:job_id>/dismiss")
@login_required
def dismiss_job(job_id: int):
    return _interact(job_id, "dismissed")


def _interact(job_id: int, state: str):
    with connect(db_url()) as c:
        if not c.execute("SELECT 1 FROM jobs WHERE id = %s", (job_id,)).fetchone():
            return jsonify(error="not_found"), 404
        c.execute("INSERT INTO job_interactions (user_id, job_id, state) VALUES (%s,%s,%s) "
                  "ON CONFLICT (user_id, job_id) DO UPDATE SET state = EXCLUDED.state, at = now()", (_uid(), job_id, state))
        c.commit()
    return jsonify(ok=True, state=state)


@bp.delete("/jobs/<int:job_id>/save")
@login_required
def unsave_job(job_id: int):
    with connect(db_url()) as c:
        c.execute("DELETE FROM job_interactions WHERE user_id = %s AND job_id = %s", (_uid(), job_id))
        c.commit()
    return jsonify(ok=True)


@bp.get("/saved")
@login_required
def saved_jobs():
    with connect(db_url()) as c:
        rows = c.execute(f"SELECT {PUBLIC_FIELDS}, i.at AS saved_at FROM job_interactions i JOIN jobs j ON j.id = i.job_id "
                         "JOIN sources s ON s.id = j.source_id WHERE i.user_id = %s AND i.state = 'saved' ORDER BY i.at DESC",
                         (_uid(),)).fetchall()
    return jsonify(jobs=rows)


@bp.post("/jobs/<int:job_id>/report")
@login_required
@limited("report", 30, 3600, by_user=True)
def report_job(job_id: int):
    body = _json()
    reason = body.get("reason")
    if reason not in ("incorrect_match", "wrong_details", "expired", "scam_or_fake", "duplicate", "other"):
        return jsonify(error="invalid_reason"), 400
    with connect(db_url()) as c:
        if not c.execute("SELECT 1 FROM jobs WHERE id = %s", (job_id,)).fetchone():
            return jsonify(error="not_found"), 404
        c.execute("INSERT INTO job_reports (user_id, job_id, reason, note) VALUES (%s,%s,%s,%s)",
                  (_uid(), job_id, reason, (body.get("note") or "")[:500] or None))
        if reason in ("wrong_details", "expired", "scam_or_fake", "duplicate"):
            c.execute("UPDATE jobs SET needs_review = true, review_reasons = array_append("
                      "array_remove(review_reasons, 'user_reported'), 'user_reported') WHERE id = %s", (job_id,))
        c.commit()
    return jsonify(ok=True), 201


# ----------------------------------------------------------------------------------- recommendations
@bp.get("/recommendations")
@login_required
def recommendations():
    cv_id = request.args.get("cv_id", type=int)
    with connect(db_url()) as c:
        profile = _profile(c)
        cv = _own_cv(c, cv_id) if cv_id else None
        if cv_id and not cv:
            return jsonify(error="cv_not_found"), 404
        recs = recommend(c, _uid(), profile, cv["text_content"] if cv else None, cv["parsed"] if cv else None,
                         _include_dev(), limit=min(request.args.get("limit", 20, type=int), 50))
    if not profile and not cv:
        return jsonify(recommendations=[], message="Add a profile or CV to get recommendations.")
    return jsonify(recommendations=recs)


# --------------------------------------------------------------------------------- application tracker
APP_FIELDS = ("job_id", "employer", "job_title", "listing_url", "status", "applied_on", "interview_at", "follow_up_on", "notes")


def _clean_app(body: dict, partial: bool) -> dict:
    out = {}
    if "job_title" in body or not partial:
        t = (body.get("job_title") or "").strip()
        if not t or len(t) > 200:
            raise ValueError("job_title is required (max 200 characters).")
        out["job_title"] = t
    if "employer" in body:
        out["employer"] = (body["employer"] or "")[:200] or None
    if "listing_url" in body:
        u = body["listing_url"]
        if u and not str(u).startswith(("http://", "https://")):
            raise ValueError("listing_url must start with http:// or https://")
        out["listing_url"] = (u or None)
    if "status" in body:
        if body["status"] not in STATUSES:
            raise ValueError("status must be one of: " + ", ".join(STATUSES))
        out["status"] = body["status"]
    for f in ("applied_on", "follow_up_on"):
        if f in body:
            try:
                out[f] = date.fromisoformat(body[f]) if body[f] else None
            except (TypeError, ValueError):
                raise ValueError(f"{f} must be YYYY-MM-DD")
    if "interview_at" in body:
        try:
            out["interview_at"] = datetime.fromisoformat(body["interview_at"]) if body["interview_at"] else None
        except (TypeError, ValueError):
            raise ValueError("interview_at must be an ISO date-time")
    if "notes" in body:
        out["notes"] = (body["notes"] or "")[:4000] or None
    if "job_id" in body:
        out["job_id"] = body["job_id"]
    return out


@bp.post("/applications")
@login_required
def create_application():
    body = _json()
    try:
        d = _clean_app(body, partial=False)
    except ValueError as e:
        return jsonify(error="invalid", message=str(e)), 400
    with connect(db_url()) as c:
        if d.get("job_id") is not None:
            j = c.execute("SELECT id, title, employer, source_url FROM jobs WHERE id = %s", (d["job_id"],)).fetchone()
            if not j:
                return jsonify(error="job_not_found"), 404
            d.setdefault("employer", j["employer"]); d.setdefault("listing_url", j["source_url"])
        cols = list(d)
        row = c.execute(f"INSERT INTO applications (user_id, {','.join(cols)}) VALUES (%s,{','.join(['%s']*len(cols))}) RETURNING *",
                        [_uid()] + [d[k] for k in cols]).fetchone()
        c.execute("INSERT INTO application_events (application_id, user_id, kind, detail) VALUES (%s,%s,'created',%s)",
                  (row["id"], _uid(), row["status"]))
        c.commit()
    return jsonify(application=row), 201


@bp.get("/applications")
@login_required
def list_applications():
    with connect(db_url()) as c:
        rows = c.execute("SELECT * FROM applications WHERE user_id = %s ORDER BY updated_at DESC", (_uid(),)).fetchall()
    return jsonify(applications=rows)


@bp.patch("/applications/<int:app_id>")
@login_required
def update_application(app_id: int):
    try:
        d = _clean_app(_json(), partial=True)
    except ValueError as e:
        return jsonify(error="invalid", message=str(e)), 400
    d.pop("job_id", None)
    if not d:
        return jsonify(error="invalid", message="Nothing to update."), 400
    with connect(db_url()) as c:
        old = c.execute("SELECT status FROM applications WHERE id = %s AND user_id = %s", (app_id, _uid())).fetchone()
        if not old:
            return jsonify(error="not_found"), 404
        sets = ", ".join(f"{k} = %s" for k in d)
        row = c.execute(f"UPDATE applications SET {sets}, updated_at = now() WHERE id = %s AND user_id = %s RETURNING *",
                        [d[k] for k in d] + [app_id, _uid()]).fetchone()
        if "status" in d and d["status"] != old["status"]:
            c.execute("INSERT INTO application_events (application_id, user_id, kind, detail) VALUES (%s,%s,'status',%s)",
                      (app_id, _uid(), f"{old['status']} -> {d['status']}"))
        c.commit()
    return jsonify(application=row)


@bp.delete("/applications/<int:app_id>")
@login_required
def delete_application(app_id: int):
    with connect(db_url()) as c:
        n = c.execute("DELETE FROM applications WHERE id = %s AND user_id = %s", (app_id, _uid())).rowcount
        c.commit()
    return (jsonify(ok=True), 200) if n else (jsonify(error="not_found"), 404)


@bp.get("/applications/dashboard")
@login_required
def tracker_dashboard():
    now = datetime.now(timezone.utc)
    with connect(db_url()) as c:
        dist = c.execute("SELECT status, count(*) n FROM applications WHERE user_id = %s GROUP BY status", (_uid(),)).fetchall()
        active = c.execute("SELECT * FROM applications WHERE user_id = %s AND status IN ('interested','preparing','applied','interview','assessment') "
                           "ORDER BY updated_at DESC", (_uid(),)).fetchall()
        interviews = c.execute("SELECT id, job_title, employer, interview_at FROM applications WHERE user_id = %s AND interview_at >= %s "
                               "ORDER BY interview_at LIMIT 10", (_uid(), now)).fetchall()
        followups = c.execute("SELECT id, job_title, employer, follow_up_on FROM applications WHERE user_id = %s AND follow_up_on IS NOT NULL "
                              "AND follow_up_on <= current_date + 7 AND status NOT IN ('rejected','withdrawn','closed','offer') "
                              "ORDER BY follow_up_on LIMIT 20", (_uid(),)).fetchall()
        recent = c.execute("SELECT e.at, e.kind, e.detail, a.job_title FROM application_events e JOIN applications a ON a.id = e.application_id "
                           "WHERE e.user_id = %s ORDER BY e.at DESC LIMIT 10", (_uid(),)).fetchall()
    return jsonify(status_distribution={r["status"]: r["n"] for r in dist}, active=active,
                   upcoming_interviews=interviews, follow_up_reminders=followups, recent_activity=recent)


# ------------------------------------------------------------------------------------ alerts / notifications
@bp.post("/alerts")
@login_required
def create_alert():
    body = _json()
    try:
        f = alerts_svc.validate_alert_filters(body.get("filters") or {})
    except ValueError as e:
        return jsonify(error="invalid", message=str(e)), 400
    name = (body.get("name") or "").strip()[:80] or "My alert"
    freq, ch = body.get("frequency", "daily"), body.get("channel", "in_app")
    if freq not in alerts_svc.FREQ or ch not in ("in_app", "email"):
        return jsonify(error="invalid", message="frequency: instant|daily|weekly; channel: in_app|email"), 400
    with connect(db_url()) as c:
        if c.execute("SELECT count(*) n FROM alerts WHERE user_id = %s", (_uid(),)).fetchone()["n"] >= 10:
            return jsonify(error="alert_limit", message="You can have up to 10 alerts."), 400
        row = c.execute("INSERT INTO alerts (user_id, name, filters, frequency, channel) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                        (_uid(), name, Jsonb(f), freq, ch)).fetchone()
        c.commit()
    return jsonify(alert=row), 201


@bp.get("/alerts")
@login_required
def list_alerts():
    with connect(db_url()) as c:
        rows = c.execute("SELECT * FROM alerts WHERE user_id = %s ORDER BY id", (_uid(),)).fetchall()
    return jsonify(alerts=rows)


@bp.patch("/alerts/<int:alert_id>")
@login_required
def update_alert(alert_id: int):
    body, sets, vals = _json(), [], []
    if "enabled" in body:
        sets.append("enabled = %s"); vals.append(bool(body["enabled"]))
    if body.get("frequency") in alerts_svc.FREQ:
        sets.append("frequency = %s"); vals.append(body["frequency"])
    if body.get("channel") in ("in_app", "email"):
        sets.append("channel = %s"); vals.append(body["channel"])
    if not sets:
        return jsonify(error="invalid", message="Nothing to update."), 400
    with connect(db_url()) as c:
        row = c.execute(f"UPDATE alerts SET {', '.join(sets)} WHERE id = %s AND user_id = %s RETURNING *", vals + [alert_id, _uid()]).fetchone()
        c.commit()
    return (jsonify(alert=row), 200) if row else (jsonify(error="not_found"), 404)


@bp.delete("/alerts/<int:alert_id>")
@login_required
def delete_alert(alert_id: int):
    with connect(db_url()) as c:
        n = c.execute("DELETE FROM alerts WHERE id = %s AND user_id = %s", (alert_id, _uid())).rowcount
        c.commit()
    return (jsonify(ok=True), 200) if n else (jsonify(error="not_found"), 404)


@bp.get("/notifications")
@login_required
def notifications():
    with connect(db_url()) as c:
        rows = c.execute(f"SELECT n.id, n.created_at, n.read_at, n.reasons, a.name AS alert_name, j.id AS job_id, j.title, j.employer, j.status "
                         "FROM notifications n JOIN alerts a ON a.id = n.alert_id JOIN jobs j ON j.id = n.job_id "
                         "WHERE n.user_id = %s ORDER BY n.created_at DESC LIMIT 100", (_uid(),)).fetchall()
    return jsonify(notifications=rows, unread=sum(1 for r in rows if r["read_at"] is None))


@bp.post("/notifications/<int:nid>/read")
@login_required
def read_notification(nid: int):
    with connect(db_url()) as c:
        n = c.execute("UPDATE notifications SET read_at = now() WHERE id = %s AND user_id = %s", (nid, _uid())).rowcount
        c.commit()
    return (jsonify(ok=True), 200) if n else (jsonify(error="not_found"), 404)


# ------------------------------------------------------------------------------------- career insights
@bp.get("/insights/skills")
def skill_insights():
    """Public, aggregate-only: which skills appear most often in active jobs matching a keyword/province."""
    q, province = request.args.get("q"), request.args.get("province")
    where, params = ["j.status = 'active'", "j.canonical_job_id IS NULL"], []
    if not _include_dev():
        where.append("j.is_dev_data = false")
    if q:
        where.append("j.search_tsv @@ websearch_to_tsquery('english', %s)"); params.append(q[:100])
    if province:
        where.append("j.province = %s"); params.append(province[:40])
    with connect(db_url()) as c:
        total = c.execute(f"SELECT count(*) n FROM jobs j WHERE {' AND '.join(where)}", params).fetchone()["n"]
        rows = c.execute(f"SELECT skill, count(*) n FROM jobs j, unnest(j.extracted_skills) AS skill "
                         f"WHERE {' AND '.join(where)} GROUP BY skill ORDER BY n DESC, skill LIMIT 20", params).fetchall()
    return jsonify(jobs_analysed=total, skills=[{"skill": r["skill"], "jobs": r["n"],
                                                 "share": round(r["n"] / total, 2) if total else None} for r in rows],
                   note="Counts come from active listings in our database; skills are extracted by keyword and may be incomplete.")
