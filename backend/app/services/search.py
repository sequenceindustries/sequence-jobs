"""Keyword/filter search over real job rows using PostgreSQL full-text search.

This path has no AI dependency and keeps working when the AI provider is down.
Unknown values are never treated as matches for a filter (e.g. a job with no stated salary does not
satisfy a salary filter), and results say which fields matched and which are unavailable.
"""
from __future__ import annotations

from typing import Any, Optional

PUBLIC_FIELDS = (
    "j.id, j.title, j.employer, j.location_text, j.city, j.province, j.work_mode, j.employment_type, "
    "j.salary_min, j.salary_max, j.salary_currency, j.salary_period, j.salary_raw, j.published_at, "
    "j.closing_at, j.source_url, j.application_url, j.last_verified_at, j.status, j.is_dev_data, "
    "s.name AS source_name, s.slug AS source_slug"
)

# Filters we cannot honour yet because the data model has no reliable structured value for them.
# They are reported back instead of silently ignored.
NOT_YET_APPLICABLE = ("experience_level", "max_years_experience")


def search_jobs(conn, q: Optional[str] = None, filters: Optional[dict[str, Any]] = None,
                page: int = 1, per_page: int = 20, include_dev: bool = True) -> dict:
    filters = dict(filters or {})
    page, per_page = max(1, page), min(max(1, per_page), 50)
    where = ["j.status = 'active'", "j.canonical_job_id IS NULL"]
    params: list[Any] = []

    if not include_dev:
        where.append("j.is_dev_data = false")

    terms = " ".join(filter(None, [q or "", " ".join(filters.get("keywords") or [])])).strip()
    rank = "0"
    if terms:
        where.append("j.search_tsv @@ websearch_to_tsquery('english', %s)")
        params.append(terms)
        rank = "ts_rank_cd(j.search_tsv, websearch_to_tsquery('english', %s))"
    if filters.get("province"):
        where.append("j.province = %s"); params.append(filters["province"])
    if filters.get("city"):
        where.append("(lower(j.city) = lower(%s) OR j.location_text ILIKE %s)")
        params += [filters["city"], f"%{filters['city']}%"]
    if filters.get("work_mode"):
        where.append("j.work_mode = %s"); params.append(filters["work_mode"])
    if filters.get("employment_type"):
        where.append("j.employment_type ILIKE %s"); params.append(filters["employment_type"].replace("_", " "))
    if filters.get("posted_within_days"):
        where.append("j.published_at >= current_date - %s::int"); params.append(filters["posted_within_days"])
    if filters.get("salary_min") and filters.get("salary_period"):
        # only rows that STATE a salary in the same period can match; unknown never matches
        where.append("j.salary_period = %s AND coalesce(j.salary_max, j.salary_min) >= %s")
        params += [filters["salary_period"], filters["salary_min"]]

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT count(*) AS n FROM jobs j WHERE {where_sql}", params
    ).fetchone()["n"]

    order = "rank DESC, " if terms else ""
    select_params = [terms] if terms else []      # placeholder inside the rank expression
    rows = conn.execute(
        f"SELECT {PUBLIC_FIELDS}, {rank} AS rank FROM jobs j JOIN sources s ON s.id = j.source_id "
        f"WHERE {where_sql} ORDER BY {order} j.published_at DESC NULLS LAST, j.id DESC "
        f"LIMIT %s OFFSET %s",
        select_params + params + [per_page, (page - 1) * per_page],
    ).fetchall()

    results = []
    for r in rows:
        matched = []
        if terms: matched.append("keywords matched title/employer/location/description")
        if filters.get("province"): matched.append(f"province = {r['province']}")
        if filters.get("work_mode"): matched.append(f"work mode = {r['work_mode']}")
        if filters.get("salary_min"): matched.append(f"stated salary meets {filters['salary_min']:.0f} per {filters['salary_period']}")
        unavailable = [f for f, v in (("salary", r["salary_min"]), ("closing_date", r["closing_at"]),
                                      ("employer", r["employer"]), ("work_mode", r["work_mode"])) if v is None]
        r.pop("rank", None)
        results.append({**r, "match_reasons": matched, "unavailable_fields": unavailable})

    return {
        "total": total, "page": page, "per_page": per_page, "results": results,
        "unapplied_filters": [f for f in NOT_YET_APPLICABLE if f in filters],
    }
