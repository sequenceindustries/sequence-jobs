"""AI feature 1: natural-language job search.

The model only *translates* a request into filters. Those filters are validated against a strict
whitelist here, then executed by ordinary SQL against real job rows - the model never produces,
sees, or ranks vacancies, so it cannot invent one.
"""
from __future__ import annotations

import re
from typing import Any

from ..services.normalise import PROVINCES
from .provider import AIGateway

WORK_MODES = {"remote", "hybrid", "on_site"}
EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "internship", "temporary", "graduate"}
EXPERIENCE_LEVELS = {"entry", "junior", "mid", "senior"}
PERIODS = {"month", "year", "hour"}
SYSTEM = (
    "Translate a South African job-search request into JSON filters. Output ONLY JSON with keys: "
    "keywords (list of strings), skills (list of skill names, optional), province (one of the nine SA provinces or null), city (string or null), "
    "work_mode (remote|hybrid|on_site|null), employment_type (full_time|part_time|contract|internship|"
    "temporary|graduate|null), experience_level (entry|junior|mid|senior|null), max_years_experience "
    "(integer or null), salary_min (number or null), salary_period (month|year|hour|null), "
    "posted_within_days (integer or null). Use null for anything the user did not say. Never invent values."
)


def validate_filters(raw: dict[str, Any]) -> dict[str, Any]:
    """Whitelist + coerce. Anything invalid is dropped (becomes 'not filtered'), never trusted."""
    out: dict[str, Any] = {}
    kws = raw.get("keywords")
    if isinstance(kws, list):
        clean = [re.sub(r"[^\w\s\-+#.]", "", str(k)).strip()[:40] for k in kws][:8]
        out["keywords"] = [k for k in clean if k]
    sk = raw.get("skills")
    if isinstance(sk, list):
        from ..services.skills import TAXONOMY
        out["skills"] = [x.lower() for x in sk if isinstance(x, str) and x.lower() in TAXONOMY][:10]
        if not out["skills"]:
            del out["skills"]
    prov = raw.get("province")
    if isinstance(prov, str) and prov.lower() in PROVINCES:
        out["province"] = PROVINCES[prov.lower()]
    city = raw.get("city")
    if isinstance(city, str) and re.fullmatch(r"[A-Za-z .\-']{2,40}", city):
        out["city"] = city.strip()
    if raw.get("work_mode") in WORK_MODES:
        out["work_mode"] = raw["work_mode"]
    if raw.get("employment_type") in EMPLOYMENT_TYPES:
        out["employment_type"] = raw["employment_type"]
    if raw.get("experience_level") in EXPERIENCE_LEVELS:
        out["experience_level"] = raw["experience_level"]
    for k, lo, hi in (("max_years_experience", 0, 40), ("posted_within_days", 1, 365)):
        v = raw.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
            out[k] = v
    sm = raw.get("salary_min")
    if isinstance(sm, (int, float)) and not isinstance(sm, bool) and 0 < sm < 10_000_000:
        out["salary_min"] = float(sm)
        out["salary_period"] = raw.get("salary_period") if raw.get("salary_period") in PERIODS else None
        if out["salary_period"] is None:
            del out["salary_min"], out["salary_period"]   # a salary without a period is ambiguous
    return out


def natural_language_to_filters(gateway: AIGateway, query: str) -> dict[str, Any]:
    """Raises AIUnavailable / AIOutputInvalid; callers fall back to plain keyword search."""
    query = query.strip()[:300]
    data = gateway.run_json("search_filters", SYSTEM, query, required_keys=("keywords",))
    return validate_filters(data)
