"""Multi-signal cross-source deduplication.

Rules (see docs/DECISIONS.md):
* Within one source, identity is (source_id, source_job_id) - handled by upsert, not here.
* Across sources a listing is linked to an earlier one ONLY if the employer matches AND at least
  two further independent signals agree. Similar titles alone never link anything.
* Linking never deletes: the later row gets canonical_job_id + dup_relation, history is preserved.
* Relations: same_vacancy_other_source | repost | duplicate. Similar-but-distinct => no link.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .normalise import norm_key


def _tokens(s: Optional[str]) -> set[str]:
    return set(norm_key(s).split())


def jaccard(a: Optional[str], b: Optional[str]) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _shingles(s: Optional[str], n: int = 4) -> set[tuple[str, ...]]:
    words = norm_key(s).split()
    return {tuple(words[i:i + n]) for i in range(max(len(words) - n + 1, 0))}


def description_similarity(a: Optional[str], b: Optional[str]) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _norm_url(u: Optional[str]) -> str:
    if not u:
        return ""
    u = re.sub(r"^https?://(www\.)?", "", u.strip().lower())
    return re.sub(r"[?#].*$", "", u).rstrip("/")


def classify_pair(new: dict, old: dict) -> Optional[dict]:
    """Compare a new job dict with an existing one. Return None (distinct) or
    {"relation": ..., "signals": [...]}."""
    # Employer is mandatory. Unknown employer on either side => never auto-link.
    if not new.get("employer") or not old.get("employer"):
        return None
    if norm_key(new["employer"]) != norm_key(old["employer"]):
        return None

    signals = []
    if _norm_url(new.get("application_url")) and \
            _norm_url(new.get("application_url")) == _norm_url(old.get("application_url")):
        signals.append("application_url")
    title_sim = jaccard(new.get("title"), old.get("title"))
    if title_sim >= 0.85:
        signals.append("title")
    desc_sim = description_similarity(new.get("description"), old.get("description"))
    if desc_sim >= 0.6:
        signals.append("description")
    same_loc = bool(new.get("city") and norm_key(new["city"]) == norm_key(old.get("city"))) or \
        bool(new.get("province") and new["province"] == old.get("province")
             and norm_key(new.get("location_text")) == norm_key(old.get("location_text")))
    if same_loc:
        signals.append("location")
    if new.get("reference_no") and new.get("reference_no") == old.get("reference_no"):
        signals.append("reference_no")

    # Need >= 2 signals besides employer, and a title/url/reference anchor so we never link on
    # location+description coincidence alone.
    anchor = {"title", "application_url", "reference_no"} & set(signals)
    if len(signals) < 2 or not anchor:
        return None

    pa, pb = new.get("published_at"), old.get("published_at")
    gap = abs((pa - pb).days) if isinstance(pa, date) and isinstance(pb, date) else None
    old_ended = old.get("status") in ("expired", "closed", "removed")

    if gap is not None and gap > 30 or old_ended:
        relation = "repost"          # same role advertised again after the first ended / long gap
    elif new.get("source_id") == old.get("source_id"):
        relation = "duplicate"
    else:
        relation = "same_vacancy_other_source"
    return {"relation": relation, "signals": signals}


def find_canonical(conn, rec_dict: dict) -> Optional[dict]:
    """Search candidate rows (same normalised employer) and return the best link, if any."""
    emp = rec_dict.get("employer")
    if not emp:
        return None
    rows = conn.execute(
        "SELECT * FROM jobs WHERE canonical_job_id IS NULL "
        "AND NOT (source_id = %s AND source_job_id = %s) "
        "AND trim(lower(regexp_replace(employer, '[^a-zA-Z0-9]+', ' ', 'g'))) = %s",
        (rec_dict["source_id"], rec_dict["source_job_id"], norm_key(emp)),
    ).fetchall()
    best = None
    for row in rows:
        res = classify_pair(rec_dict, row)
        if res and (best is None or len(res["signals"]) > len(best["signals"])):
            best = {**res, "canonical_job_id": row["id"]}
    return best
