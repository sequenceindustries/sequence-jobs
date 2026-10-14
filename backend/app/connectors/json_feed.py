"""Generic connector for an authorised JSON vacancy feed (employer or partner feed).

Use only for feeds whose terms permit our intended use. config:
{
  "url": "https://.../jobs.json",
  "items_path": "jobs",                 # key holding the list ('' if the root is a list)
  "page_param": "page", "max_pages": 20, # optional pagination
  "complete_snapshot": true,             # feed lists ALL currently open vacancies
  "field_map": {"source_job_id": "id", "title": "title", "employer": "company", ...}
}
Unmapped fields stay None (unknown).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .base import BaseConnector, FetchResult, JobRecord
from .registry import register
from ..services.normalise import (
    clean_text, detect_province, detect_work_mode, parse_closing, parse_salary,
)

TEXT_FIELDS = ("title", "employer", "description", "requirements_text", "qualifications_text",
               "experience_text", "employment_type", "salary_raw", "location_text", "city",
               "application_instructions", "application_url", "reference_no", "source_url")


def _dig(obj: Any, path: str):
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def map_item(item: dict, fmap: dict, default_url: str) -> JobRecord:
    g = lambda name: _dig(item, fmap[name]) if name in fmap else None
    sid = g("source_job_id")
    if sid in (None, ""):
        raise ValueError("missing source_job_id")
    vals = {f: clean_text(str(g(f))) if g(f) not in (None, "") else None for f in TEXT_FIELDS}
    if not vals["title"]:
        raise ValueError("missing title")
    lo, hi, cur, period = parse_salary(vals["salary_raw"])
    published = None
    if g("published_at"):
        try:
            published = date.fromisoformat(str(g("published_at"))[:10])
        except ValueError:
            published = None
    closing = None
    if g("closing_at"):
        raw = str(g("closing_at"))
        try:
            closing = datetime.fromisoformat(raw)
        except ValueError:
            closing = parse_closing(raw)
    return JobRecord(
        source_job_id=str(sid), title=vals["title"],
        source_url=vals["source_url"] or default_url,
        employer=vals["employer"], description=vals["description"],
        requirements_text=vals["requirements_text"], qualifications_text=vals["qualifications_text"],
        experience_text=vals["experience_text"], employment_type=vals["employment_type"],
        salary_min=lo, salary_max=hi, salary_currency=cur, salary_period=period,
        salary_raw=vals["salary_raw"], location_text=vals["location_text"], city=vals["city"],
        province=detect_province(vals["location_text"], vals["city"]),
        work_mode=detect_work_mode(vals["location_text"], vals["description"]),
        published_at=published, closing_at=closing,
        application_instructions=vals["application_instructions"],
        application_url=vals["application_url"], reference_no=vals["reference_no"],
        extraction_confidence=0.9,
    )


@register
class JsonFeedConnector(BaseConnector):
    key = "json_feed"

    def fetch(self) -> FetchResult:
        url = self.config["url"]
        fmap = self.config["field_map"]
        items_path = self.config.get("items_path", "")
        page_param = self.config.get("page_param")
        max_pages = int(self.config.get("max_pages", 1))
        records, errors = [], []
        pages_ok = True
        for page in range(1, (max_pages if page_param else 1) + 1):
            params = {page_param: page} if page_param else None
            try:
                data = self.http.get(url, params=params).json()
            except Exception as e:
                errors.append((f"page {page}", f"fetch failed: {e}"))
                pages_ok = False
                break
            items = _dig(data, items_path) if items_path else data
            if not items:
                break
            for it in items:
                try:
                    records.append(map_item(it, fmap, url))
                except Exception as e:
                    errors.append((str(_dig(it, fmap.get("source_job_id", "")) or "?"), f"map error: {e}"))
        complete = bool(self.config.get("complete_snapshot")) and pages_ok and not errors
        return FetchResult(records, complete_snapshot=complete, parse_errors=errors)
