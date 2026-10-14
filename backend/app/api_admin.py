"""Admin API. Every route requires role=admin (401/403 otherwise) and every write is recorded in audit_log.
Enabling a source is refused unless its terms_status is 'verified_permitted' (the legal gate cannot be bypassed here)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .auth import admin_required, current_user, db_url
from .db import connect
from .services import ingest
from .services.accounts import audit

bp = Blueprint("admin", __name__)


@bp.get("/stats")
@admin_required
def stats():
    with connect(db_url()) as c:
        by_status = c.execute("SELECT status, count(*) n FROM jobs GROUP BY status ORDER BY status").fetchall()
        one = lambda q: c.execute(q).fetchone()["n"]
        per_source = c.execute(
            "SELECT s.slug, s.enabled, s.terms_status, s.is_dev_data, s.health, "
            "count(j.id) FILTER (WHERE j.status='active') active_jobs, count(j.id) total_jobs "
            "FROM sources s LEFT JOIN jobs j ON j.source_id = s.id GROUP BY s.id ORDER BY s.slug").fetchall()
        return jsonify(
            jobs_by_status=by_status,
            new_last_24h=one("SELECT count(*) n FROM jobs WHERE first_seen_at > now() - interval '24 hours'"),
            duplicates=one("SELECT count(*) n FROM jobs WHERE canonical_job_id IS NOT NULL"),
            needs_review=one("SELECT count(*) n FROM jobs WHERE needs_review"),
            users=one("SELECT count(*) n FROM users"), per_source=per_source)


@bp.get("/sources")
@admin_required
def sources():
    with connect(db_url()) as c:
        rows = c.execute("SELECT id, slug, name, connector, access_method, terms_status, terms_notes, republication, enabled, "
                         "is_dev_data, health, consecutive_failures, last_success_at, last_run_at, min_interval_secs "
                         "FROM sources ORDER BY slug").fetchall()
    return jsonify(sources=rows)


@bp.patch("/sources/<slug>")
@admin_required
def patch_source(slug: str):
    body = request.get_json(silent=True) or {}
    with connect(db_url()) as c:
        s = c.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
        if not s:
            return jsonify(error="not_found"), 404
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                return jsonify(error="invalid"), 400
            if body["enabled"] and s["terms_status"] != "verified_permitted":
                audit(db_url(), current_user()["id"], "admin.source.enable_refused", slug, {"terms_status": s["terms_status"]})
                return jsonify(error="terms_not_verified",
                               message=f"Source terms are '{s['terms_status']}'. Only 'verified_permitted' sources can be enabled."), 409
            c.execute("UPDATE sources SET enabled = %s WHERE id = %s", (body["enabled"], s["id"]))
        if "min_interval_secs" in body:
            v = body["min_interval_secs"]
            if not isinstance(v, int) or isinstance(v, bool) or not 300 <= v <= 604800:
                return jsonify(error="invalid", message="min_interval_secs must be 300..604800"), 400
            c.execute("UPDATE sources SET min_interval_secs = %s WHERE id = %s", (v, s["id"]))
        c.commit()
    audit(db_url(), current_user()["id"], "admin.source.update", slug,
          {k: body[k] for k in ("enabled", "min_interval_secs") if k in body})
    return jsonify(ok=True)


@bp.post("/sources/<slug>/run")
@admin_required
def run_source(slug: str):
    with connect(db_url()) as c:
        if not c.execute("SELECT 1 FROM sources WHERE slug = %s", (slug,)).fetchone():
            return jsonify(error="not_found"), 404
    res = ingest.run_source(db_url(), slug, force=True)      # force skips the interval only; the legal gate still applies
    audit(db_url(), current_user()["id"], "admin.source.run", slug, {"status": res.get("status")})
    return jsonify(res)


@bp.get("/runs")
@admin_required
def runs():
    with connect(db_url()) as c:
        rows = c.execute("SELECT r.*, s.slug FROM ingestion_runs r JOIN sources s ON s.id = r.source_id "
                         "ORDER BY r.id DESC LIMIT 50").fetchall()
        errs = c.execute("SELECT e.*, s.slug FROM ingestion_errors e JOIN ingestion_runs r ON r.id = e.run_id "
                         "JOIN sources s ON s.id = r.source_id ORDER BY e.id DESC LIMIT 50").fetchall()
    return jsonify(runs=rows, errors=errs)


@bp.get("/ai-usage")
@admin_required
def ai_usage():
    with connect(db_url()) as c:
        rows = c.execute(
            "SELECT task, status, count(*) calls, coalesce(sum(input_tokens),0) input_tokens, "
            "coalesce(sum(output_tokens),0) output_tokens, round(avg(latency_ms)) avg_latency_ms, "
            "sum(est_cost_usd) est_cost_usd FROM ai_usage_log WHERE at > now() - interval '30 days' "
            "GROUP BY task, status ORDER BY task, status").fetchall()
    return jsonify(last_30_days=rows, note="est_cost_usd is null when the provider's price is unknown; it is never guessed.")


@bp.get("/data-quality")
@admin_required
def data_quality():
    checks = {
        "missing_employer": "employer IS NULL",
        "missing_location": "location_text IS NULL AND province IS NULL",
        "missing_closing_date": "closing_at IS NULL",
        "suspicious_salary": "(salary_min IS NOT NULL AND (salary_min <= 0 OR (salary_max IS NOT NULL AND salary_max < salary_min)))",
        "conflicting_dates": "(published_at IS NOT NULL AND closing_at IS NOT NULL AND closing_at::date < published_at)",
        "stale_unverified_14d": "last_verified_at < now() - interval '14 days'",
        "low_extraction_confidence": "extraction_confidence IS NOT NULL AND extraction_confidence < 0.5",
        "flagged_needs_review": "needs_review",
    }
    out = {}
    with connect(db_url()) as c:
        for name, cond in checks.items():           # conditions are constants above, never user input
            r = c.execute(f"SELECT count(*) n FROM jobs WHERE status='active' AND {cond}").fetchone()["n"]
            ex = c.execute(f"SELECT id, title, source_id FROM jobs WHERE status='active' AND {cond} ORDER BY id LIMIT 10").fetchall()
            out[name] = {"count": r, "examples": ex}
    return jsonify(checks=out)


@bp.get("/audit")
@admin_required
def audit_view():
    with connect(db_url()) as c:
        rows = c.execute("SELECT a.id, a.at, a.actor_id, a.action, a.target, a.detail FROM audit_log a "
                         "ORDER BY a.id DESC LIMIT 200").fetchall()
    return jsonify(entries=rows)
