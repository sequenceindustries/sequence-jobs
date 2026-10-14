"""Deterministic normalisation helpers. Nothing here guesses: if a value cannot be parsed it is None."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")

PROVINCES = {
    "eastern cape": "Eastern Cape",
    "free state": "Free State",
    "gauteng": "Gauteng",
    "kwazulu-natal": "KwaZulu-Natal",
    "kwazulu natal": "KwaZulu-Natal",
    "limpopo": "Limpopo",
    "mpumalanga": "Mpumalanga",
    "northern cape": "Northern Cape",
    "north west": "North West",
    "north-west": "North West",
    "western cape": "Western Cape",
}

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s).strip()
    return s or None


def detect_province(*texts: Optional[str]) -> Optional[str]:
    """Return a province only when one (and only one) is explicitly named."""
    found = set()
    for t in texts:
        if not t:
            continue
        low = t.lower()
        for key, name in PROVINCES.items():
            if re.search(rf"\b{re.escape(key)}\b", low):
                found.add(name)
    return found.pop() if len(found) == 1 else None


_SALARY_NUM = r"R?\s?(\d{1,3}(?:[  ,]\d{3})+|\d+)(?:\.\d{2})?"


def parse_salary(raw: Optional[str]):
    """Parse ZAR salary text like 'R338 106 per annum (Level 07)' or 'R25 000 - R30 000 per month'.

    Returns (min, max, currency, period) or (None, None, None, None) when unparseable.
    Only the stated figures are used; allowances/benefits text is ignored, not summed.
    """
    if not raw:
        return None, None, None, None
    low = raw.lower()
    nums = []
    for m in re.finditer(_SALARY_NUM, raw):
        digits = re.sub(r"[  ,]", "", m.group(1))
        try:
            nums.append(Decimal(digits))
        except InvalidOperation:
            continue
    # ignore tiny numbers that are levels/grades rather than money (e.g. 'Level 07')
    nums = [n for n in nums if n >= 1000]
    if not nums:
        return None, None, None, None
    if re.search(r"per\s+(annum|year)|p\.?a\.?|annual", low):
        period = "year"
    elif re.search(r"per\s+month|p\.?m\.?\b|monthly", low):
        period = "month"
    elif re.search(r"per\s+hour|hourly", low):
        period = "hour"
    else:
        period = None
    lo, hi = min(nums[:2]), max(nums[:2])
    return lo, hi, "ZAR", period


def parse_closing(raw: Optional[str]) -> Optional[datetime]:
    """Parse '17 July 2026 at 16:00' / 'Friday, 31 July 2026' (end of day if no time). SAST."""
    if not raw:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s*(?:at|@|,)?\s*(\d{1,2})[:h](\d{2}))?", raw)
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    day, year = int(m.group(1)), int(m.group(3))
    hour, minute = (int(m.group(4)), int(m.group(5))) if m.group(4) else (23, 59)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=SAST)
    except ValueError:
        return None


def detect_work_mode(*texts: Optional[str]) -> Optional[str]:
    """Only explicit statements count. Absence of the word 'remote' is NOT on-site."""
    blob = " ".join(t.lower() for t in texts if t)
    if re.search(r"\bhybrid\b", blob):
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|work from home|remote position|remote role|remote)\b", blob):
        return "remote"
    if re.search(r"\bon-?site\b", blob):
        return "on_site"
    return None


_HASH_FIELDS = (
    "title", "employer", "description", "requirements_text", "qualifications_text",
    "experience_text", "employment_type", "salary_min", "salary_max", "salary_period",
    "location_text", "city", "province", "work_mode", "published_at", "closing_at",
    "application_instructions", "application_url", "source_url", "reference_no",
)


def content_hash(rec) -> str:
    data = {f: getattr(rec, f) for f in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def changed_fields(old: dict, rec) -> list[str]:
    out = []
    for f in _HASH_FIELDS:
        a, b = old.get(f), getattr(rec, f)
        if isinstance(a, Decimal) or isinstance(b, Decimal):
            a = None if a is None else Decimal(str(a))
            b = None if b is None else Decimal(str(b))
        if a != b:
            out.append(f)
    return out


def norm_key(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
