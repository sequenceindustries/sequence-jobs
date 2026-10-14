"""Public REST API (read-only). No admin or personal-data endpoints exist yet."""
from flask import Blueprint, current_app, jsonify, request

from .ai.provider import AIOutputInvalid, AIUnavailable
from .ai.search_filters import natural_language_to_filters
from .db import connect
from .services.normalise import PROVINCES
from .services.search import PUBLIC_FIELDS, search_jobs

bp = Blueprint("api", __name__)


def _include_dev() -> bool:
    return not current_app.config["CFG"].is_production()


def _filters_from_args(args) -> dict:
    f: dict = {}
    for k in ("province", "city", "work_mode", "employment_type", "salary_period"):
        if args.get(k):
            f[k] = args[k][:60]
    for k, cast in (("salary_min", float), ("posted_within_days", int)):
        if args.get(k):
            try:
                f[k] = cast(args[k])
            except ValueError:
                pass
    from .ai.search_filters import validate_filters
    return validate_filters({**f, "keywords": []})


@bp.get("/health")
def health():
    try:
        with connect(current_app.config["DB_URL"]) as conn:
            conn.execute("SELECT 1")
        db = "ok"
    except Exception:
        db = "down"
    return jsonify(status="ok" if db == "ok" else "degraded", database=db,
                   environment=current_app.config["CFG"].ENV,
                   ai_configured=current_app.config["AI"].provider.name != "none")


@bp.get("/jobs")
def list_jobs():
    page = request.args.get("page", 1, type=int)
    with connect(current_app.config["DB_URL"]) as conn:
        out = search_jobs(conn, q=request.args.get("q"), filters=_filters_from_args(request.args),
                          page=page, per_page=request.args.get("per_page", 20, type=int),
                          include_dev=_include_dev())
    out["data_notice"] = ("Development data: synthetic, not real vacancies."
                          if any(r["is_dev_data"] for r in out["results"]) else None)
    return jsonify(out)


@bp.get("/jobs/<int:job_id>")
def job_detail(job_id: int):
    with connect(current_app.config["DB_URL"]) as conn:
        row = conn.execute(
            f"SELECT {PUBLIC_FIELDS}, j.description, j.requirements_text, j.qualifications_text, "
            "j.experience_text, j.application_instructions, j.reference_no, j.extraction_confidence, "
            "j.canonical_job_id FROM jobs j JOIN sources s ON s.id = j.source_id WHERE j.id = %s",
            (job_id,)).fetchone()
        if row is None or (row["is_dev_data"] and not _include_dev()):
            return jsonify(error="not_found"), 404
        if row["canonical_job_id"]:
            return jsonify(error="merged", canonical_job_id=row["canonical_job_id"]), 301
    row["disclaimer"] = ("Listed for information. The employer named is the advertiser; "
                         "Sequence Industries is not the employer. Apply via the original source.")
    return jsonify(row)


@bp.post("/search/natural")
def natural_search():
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify(error="query_required"), 400
    try:
        filters = natural_language_to_filters(current_app.config["AI"], query)
    except (AIUnavailable, AIOutputInvalid) as e:
        # No fabricated fallback: tell the client AI search is off and keyword search is available.
        return jsonify(error="ai_unavailable", message="AI search is currently unavailable. "
                       "Use keyword search instead.", detail=str(e)), 503
    with connect(current_app.config["DB_URL"]) as conn:
        out = search_jobs(conn, filters=filters, include_dev=_include_dev())
    out["interpreted_filters"] = filters
    return jsonify(out)


@bp.get("/meta/provinces")
def provinces():
    return jsonify(sorted(set(PROVINCES.values())))
