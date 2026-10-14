"""Ingestion service: runs one source through fetch -> validate -> upsert -> expire -> log.

Isolation guarantees:
* run_source never raises for source/connector problems; failures are recorded on the run and source.
* every record is stored inside its own savepoint, so one bad record cannot lose the rest.
* jobs are expired by absence only after a *complete* snapshot, and by closing date otherwise.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from psycopg.types.json import Jsonb

from ..connectors.base import HttpClient, JobRecord
from ..connectors.registry import get_connector_class
from ..db import connect
from . import dedup
from .normalise import changed_fields, content_hash

log = logging.getLogger("ingest")

JOB_COLS = [
    "title", "employer", "description", "requirements_text", "qualifications_text",
    "experience_text", "employment_type", "salary_min", "salary_max", "salary_currency",
    "salary_period", "salary_raw", "location_text", "city", "province", "work_mode",
    "published_at", "closing_at", "application_instructions", "application_url", "source_url",
    "reference_no", "extraction_confidence",
]


def review_reasons(rec: JobRecord) -> list[str]:
    reasons = list(rec.extra_review_reasons)
    if rec.extraction_confidence is not None and rec.extraction_confidence < 0.6:
        reasons.append("low_extraction_confidence")
    if rec.salary_min is not None:
        lo, hi, per = rec.salary_min, rec.salary_max or rec.salary_min, rec.salary_period
        if (per == "month" and (hi < Decimal(1000) or hi > Decimal(500_000))) or \
           (per == "year" and (hi < Decimal(12_000) or hi > Decimal(6_000_000))) or \
           (per == "hour" and (hi < Decimal(5) or hi > Decimal(5_000))):
            reasons.append("suspicious_salary")
        if rec.salary_max is not None and rec.salary_max < rec.salary_min:
            reasons.append("salary_range_inverted")
        if per is None:
            reasons.append("salary_period_unknown")
    if rec.closing_at and rec.published_at and rec.closing_at.date() < rec.published_at:
        reasons.append("closing_before_published")
    if not rec.employer:
        reasons.append("employer_unknown")
    return sorted(set(reasons))


def _validate(rec: JobRecord) -> None:
    if not rec.source_job_id or not rec.title or not rec.title.strip():
        raise ValueError("record needs source_job_id and title")
    if not rec.source_url or not rec.source_url.startswith(("http://", "https://", "file://")):
        raise ValueError("record needs a source_url")


def _row_dict(rec: JobRecord, source_id: int) -> dict:
    d = {c: getattr(rec, c) for c in JOB_COLS}
    d.update(source_id=source_id, source_job_id=rec.source_job_id)
    return d


def _store(conn, source: dict, rec: JobRecord, run_started: datetime) -> str:
    """Insert/update one record. Returns 'created' | 'updated' | 'unchanged'."""
    _validate(rec)
    chash = content_hash(rec)
    reasons = review_reasons(rec)
    now = datetime.now(timezone.utc)
    existing = conn.execute(
        "SELECT * FROM jobs WHERE source_id = %s AND source_job_id = %s",
        (source["id"], rec.source_job_id),
    ).fetchone()

    if existing is None:
        link = dedup.find_canonical(conn, _row_dict(rec, source["id"]))
        cols = JOB_COLS + ["source_id", "source_job_id", "content_hash", "is_dev_data",
                           "needs_review", "review_reasons", "canonical_job_id", "dup_relation"]
        vals = [getattr(rec, c) for c in JOB_COLS] + [
            source["id"], rec.source_job_id, chash, source["is_dev_data"], bool(reasons), reasons,
            link["canonical_job_id"] if link else None, link["relation"] if link else None,
        ]
        row = conn.execute(
            f"INSERT INTO jobs ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
            vals,
        ).fetchone()
        conn.execute(
            "INSERT INTO job_versions (job_id, content_hash, changed_fields, snapshot) VALUES (%s,%s,%s,%s)",
            (row["id"], chash, ["__created__"], Jsonb(json.loads(json.dumps(_row_dict(rec, source["id"]), default=str)))),
        )
        return "created"

    # Seen again: always refresh liveness
    reactivate = existing["status"] in ("expired", "closed", "removed")
    if existing["content_hash"] == chash:
        conn.execute(
            "UPDATE jobs SET last_seen_at = %s, last_verified_at = %s, "
            "status = CASE WHEN %s THEN 'active' ELSE status END WHERE id = %s",
            (now, now, reactivate, existing["id"]),
        )
        return "unchanged"

    fields = changed_fields(existing, rec)
    sets = ", ".join(f"{c} = %s" for c in JOB_COLS)
    conn.execute(
        f"UPDATE jobs SET {sets}, content_hash = %s, last_seen_at = %s, last_verified_at = %s, "
        "status = 'active', needs_review = %s, review_reasons = %s, "
        "ai_analysis_status = CASE WHEN ai_analysis_status = 'complete' THEN 'pending' ELSE ai_analysis_status END "
        "WHERE id = %s",
        [getattr(rec, c) for c in JOB_COLS] + [chash, now, now, bool(reasons), reasons, existing["id"]],
    )
    conn.execute(
        "INSERT INTO job_versions (job_id, content_hash, changed_fields, snapshot) VALUES (%s,%s,%s,%s)",
        (existing["id"], chash, fields, Jsonb(json.loads(json.dumps(_row_dict(rec, source["id"]), default=str)))),
    )
    return "updated"


def expire_by_closing_date(conn, source_id: Optional[int] = None) -> int:
    q = "UPDATE jobs SET status = 'expired' WHERE status = 'active' AND closing_at IS NOT NULL AND closing_at < now()"
    params: tuple = ()
    if source_id is not None:
        q += " AND source_id = %s"
        params = (source_id,)
    return conn.execute(q, params).rowcount


def run_source(db_url: str, source_slug: str, http: Optional[HttpClient] = None, force: bool = False,
               user_agent: str = "SequenceJobsBot/0.1", timeout: int = 20, retries: int = 3) -> dict:
    """Run one source. Returns the run summary dict. Never raises for source-level failures."""
    with connect(db_url) as conn:
        source = conn.execute("SELECT * FROM sources WHERE slug = %s", (source_slug,)).fetchone()
        if source is None:
            raise KeyError(f"unknown source '{source_slug}'")

        # Legal gate: not bypassed by force. 'restricted' = permission/licence needed before use.
        if source["terms_status"] in ("prohibited", "restricted"):
            return {"source": source_slug, "status": "skipped",
                    "reason": f"terms {source['terms_status']}: collection not permitted"}
        if not source["enabled"] and not force:
            return {"source": source_slug, "status": "skipped", "reason": "source disabled"}
        if source["last_run_at"] and not force:
            age = (datetime.now(timezone.utc) - source["last_run_at"]).total_seconds()
            if age < source["min_interval_secs"]:
                return {"source": source_slug, "status": "skipped", "reason": "min_interval not elapsed"}

        run = conn.execute(
            "INSERT INTO ingestion_runs (source_id) VALUES (%s) RETURNING id, started_at", (source["id"],)
        ).fetchone()
        conn.execute("UPDATE sources SET last_run_at = %s WHERE id = %s", (run["started_at"], source["id"]))
        conn.commit()

        counts = dict(fetched=0, created=0, updated=0, unchanged=0, expired=0, flagged=0, errors=0)
        status, summary = "success", None
        try:
            cls = get_connector_class(source["connector"])
            client = http or HttpClient(user_agent, timeout, retries)
            result = cls(source["config"], client).fetch()
        except Exception as e:                      # connector crashed: isolate, record, move on
            log.exception("connector failed for %s", source_slug)
            conn.execute("INSERT INTO ingestion_errors (run_id, stage, message) VALUES (%s,'fetch',%s)",
                         (run["id"], str(e)[:2000]))
            _finish(conn, run["id"], source, "failed", counts | {"errors": 1}, str(e)[:500])
            conn.commit()
            return {"source": source_slug, "status": "failed", "error": str(e), **counts, "errors": 1}

        for ref, msg in result.parse_errors:
            conn.execute("INSERT INTO ingestion_errors (run_id, stage, item_ref, message) VALUES (%s,'parse',%s,%s)",
                         (run["id"], ref, msg[:2000]))
            counts["errors"] += 1
        counts["fetched"] = len(result.records)

        for rec in result.records:
            try:
                with conn.transaction():            # savepoint per record
                    outcome = _store(conn, source, rec, run["started_at"])
                counts[outcome] += 1
                if outcome != "unchanged" and review_reasons(rec):
                    counts["flagged"] += 1
            except Exception as e:
                counts["errors"] += 1
                conn.execute("INSERT INTO ingestion_errors (run_id, stage, item_ref, message) VALUES (%s,'store',%s,%s)",
                             (run["id"], rec.source_job_id, str(e)[:2000]))

        # Expiry
        if result.complete_snapshot:
            counts["expired"] += conn.execute(
                "UPDATE jobs SET status = 'expired' WHERE source_id = %s AND status = 'active' "
                "AND last_seen_at < %s", (source["id"], run["started_at"])).rowcount
        counts["expired"] += expire_by_closing_date(conn, source["id"])

        if counts["errors"] and counts["fetched"] == counts["errors"]:
            status = "failed"
        elif counts["errors"]:
            status = "partial"
        _finish(conn, run["id"], source, status, counts, None)
        conn.commit()
        return {"source": source_slug, "status": status, "run_id": run["id"], **counts}


def _finish(conn, run_id: int, source: dict, status: str, counts: dict, summary: Optional[str]) -> None:
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = now(), status = %s, fetched = %s, created = %s, "
        "updated = %s, unchanged = %s, expired = %s, flagged = %s, errors = %s, error_summary = %s WHERE id = %s",
        (status, counts["fetched"], counts["created"], counts["updated"], counts["unchanged"],
         counts["expired"], counts["flagged"], counts["errors"], summary, run_id),
    )
    if status == "failed":
        failures = source["consecutive_failures"] + 1
        health = "failing" if failures >= 3 else "degraded"
        conn.execute("UPDATE sources SET consecutive_failures = %s, health = %s WHERE id = %s",
                     (failures, health, source["id"]))
    else:
        health = "healthy" if status == "success" else "degraded"
        conn.execute(
            "UPDATE sources SET consecutive_failures = 0, health = %s, last_success_at = now() WHERE id = %s",
            (health, source["id"]))


def run_all(db_url: str, **kw) -> list[dict]:
    """Run every enabled source independently, a bounded number at a time."""
    from concurrent.futures import ThreadPoolExecutor
    with connect(db_url) as conn:
        slugs = [r["slug"] for r in conn.execute("SELECT slug FROM sources WHERE enabled ORDER BY slug")]
    workers = max(1, int(kw.pop("max_workers", 3)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_source, db_url, s, **kw) for s in slugs]
        out = []
        for s, f in zip(slugs, futures):
            try:
                out.append(f.result())
            except Exception as e:                   # even an unexpected crash is contained per source
                out.append({"source": s, "status": "failed", "error": str(e)})
        return out
