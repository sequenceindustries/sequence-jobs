"""Job alerts: find newly seen matching vacancies, notify once per (alert, job), queue email digests.

* No duplicate notifications: UNIQUE (alert_id, job_id) in the database, so even concurrent runs cannot double-send.
* Email goes through an outbox with attempt counts and failure reasons; without a configured sender nothing is
  sent and rows are marked 'not_configured' (never silently dropped, never faked as sent).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from ..db import connect
from .email import EmailSender, NotConfigured
from .search import search_jobs

FREQ = {"instant": timedelta(0), "daily": timedelta(hours=23), "weekly": timedelta(days=6, hours=23)}
MAX_PER_RUN = 200
MAX_EMAIL_ATTEMPTS = 3


def validate_alert_filters(raw: dict) -> dict:
    from ..ai.search_filters import validate_filters
    f = validate_filters(raw or {})
    if not (f.get("keywords") or f.get("skills") or f.get("province") or f.get("city") or f.get("work_mode")
            or f.get("employment_type") or f.get("experience_level") or f.get("salary_min")):
        raise ValueError("An alert needs at least one criterion (keywords, location, skills, etc.).")
    return f


def run_alerts(db_url: str, sender: Optional[EmailSender] = None, include_dev: bool = True,
               now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = {"alerts_run": 0, "notifications": 0, "emails_queued": 0}
    with connect(db_url) as conn:
        alerts = conn.execute("SELECT * FROM alerts WHERE enabled").fetchall()
        for a in alerts:
            if a["last_run_at"] and now - a["last_run_at"] < FREQ[a["frequency"]]:
                continue
            since = a["last_run_at"] or a["created_at"]
            f = dict(a["filters"])
            q = " ".join(f.get("keywords", []))
            found, page = [], 1
            while len(found) < MAX_PER_RUN:
                res = search_jobs(conn, q=None, filters=f, page=page, per_page=50, include_dev=include_dev, since=since)
                found += res["results"]
                if page * 50 >= res["total"]:
                    break
                page += 1
            new = 0
            lines = []
            for j in found[:MAX_PER_RUN]:
                ins = conn.execute(
                    "INSERT INTO notifications (user_id, alert_id, job_id, reasons) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (alert_id, job_id) DO NOTHING RETURNING id",
                    (a["user_id"], a["id"], j["id"], j["match_reasons"])).fetchone()
                if ins:
                    new += 1
                    lines.append(f"- {j['title']}" + (f" at {j['employer']}" if j["employer"] else "") +
                                 (f" ({j['location_text']})" if j["location_text"] else "") +
                                 f"\n  Why: {'; '.join(j['match_reasons']) or 'matches your alert'}")
            if new and a["channel"] == "email":
                conn.execute("INSERT INTO email_outbox (user_id, subject, body) VALUES (%s,%s,%s)",
                             (a["user_id"], f"{new} new job(s) for your alert '{a['name']}'",
                              "New vacancies matching your alert:\n\n" + "\n".join(lines) +
                              "\n\nOpen the site for full details and the original application links.\n"
                              "You can change or delete this alert in your account."))
                stats["emails_queued"] += 1
            conn.execute("UPDATE alerts SET last_run_at = %s WHERE id = %s", (now, a["id"]))
            stats["alerts_run"] += 1
            stats["notifications"] += new
        conn.commit()
    if sender is not None:
        stats["outbox"] = process_outbox(db_url, sender)
    return stats


def process_outbox(db_url: str, sender: EmailSender) -> dict:
    out = {"sent": 0, "failed": 0, "not_configured": 0, "retry": 0}
    with connect(db_url) as conn:
        rows = conn.execute(
            "SELECT o.*, u.email FROM email_outbox o JOIN users u ON u.id = o.user_id "
            "WHERE o.status IN ('queued','not_configured') ORDER BY o.id LIMIT 200").fetchall()
        for r in rows:
            try:
                sender.send(r["email"], r["subject"], r["body"])
                conn.execute("UPDATE email_outbox SET status='sent', sent_at=now(), attempts=attempts+1, error=NULL WHERE id=%s", (r["id"],))
                out["sent"] += 1
            except NotConfigured as e:
                conn.execute("UPDATE email_outbox SET status='not_configured', error=%s WHERE id=%s", (str(e)[:300], r["id"]))
                out["not_configured"] += 1
            except Exception as e:
                attempts = r["attempts"] + 1
                status = "failed" if attempts >= MAX_EMAIL_ATTEMPTS else "queued"
                conn.execute("UPDATE email_outbox SET status=%s, attempts=%s, error=%s WHERE id=%s",
                             (status, attempts, str(e)[:300], r["id"]))
                out["failed" if status == "failed" else "retry"] += 1
        conn.commit()
    return out
