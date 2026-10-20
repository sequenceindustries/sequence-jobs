"""Broken-link checker for listing source URLs.

Polite and conservative: only sources that are enabled AND verified_permitted AND not dev data are checked, robots.txt is
respected, one request per job (no retries), a delay between requests, and a job is only flagged after TWO runs in a row see
404/410. Flagging sets needs_review for a human; it never expires or deletes a job by itself. Network errors, 5xx, 401/403
and robots blocks change nothing (we cannot tell the page is gone).
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from ..connectors.base import HttpClient
from ..db import connect

ONCE, BROKEN = "link_gone_once", "link_broken"


def classify(http: HttpClient, url: str) -> str:
    """ok | gone | unknown | blocked"""
    if not http._allowed(url):
        return "blocked"
    try:
        resp = http.session.get(url, timeout=http.timeout, allow_redirects=True)
    except requests.RequestException:
        return "unknown"
    if resp.status_code in (404, 410):
        return "gone"
    if 200 <= resp.status_code < 400:
        return "ok"
    return "unknown"


def check_links(db_url: str, http: Optional[HttpClient] = None, limit: int = 50, delay: float = 1.0,
                user_agent: str = "SequenceJobsBot/0.1") -> dict:
    http = http or HttpClient(user_agent, max_retries=1)
    stats = {"checked": 0, "ok": 0, "gone_first": 0, "flagged": 0, "unknown": 0, "blocked": 0}
    with connect(db_url) as conn:
        rows = conn.execute(
            "SELECT j.id, j.source_url, j.review_reasons FROM jobs j JOIN sources s ON s.id = j.source_id "
            "WHERE j.status = 'active' AND s.enabled AND s.terms_status = 'verified_permitted' AND NOT s.is_dev_data "
            "AND NOT j.is_dev_data ORDER BY j.last_verified_at LIMIT %s", (limit,)).fetchall()
        for i, j in enumerate(rows):
            if i and delay:
                time.sleep(delay)
            result = classify(http, j["source_url"])
            stats["checked"] += 1
            reasons = [r for r in j["review_reasons"] if r not in (ONCE, BROKEN)]
            if result == "ok":
                conn.execute("UPDATE jobs SET last_verified_at = now(), review_reasons = %s, "
                             "needs_review = (cardinality(%s::text[]) > 0) WHERE id = %s", (reasons, reasons, j["id"]))
                stats["ok"] += 1
            elif result == "gone":
                if ONCE in j["review_reasons"] or BROKEN in j["review_reasons"]:
                    new = reasons + [BROKEN]
                    conn.execute("UPDATE jobs SET review_reasons = %s, needs_review = true WHERE id = %s", (new, j["id"]))
                    stats["flagged"] += 1
                else:
                    conn.execute("UPDATE jobs SET review_reasons = %s WHERE id = %s", (reasons + [ONCE], j["id"]))
                    stats["gone_first"] += 1
            else:
                stats["blocked" if result == "blocked" else "unknown"] += 1
        conn.commit()
    return stats
