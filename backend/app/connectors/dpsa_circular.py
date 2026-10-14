"""Connector: South African Public Service Vacancy Circular (DPSA), published weekly on gov.za.

Access method: official public notice, PDF, one file per weekly circular
(e.g. https://www.gov.za/sites/default/files/PUBLIC%20SERVICE%20VACANCY%20CIRCULAR%20%2023%20OF%202026_P.pdf).

Layout observed (circular 23 of 2026): front matter, an index of departments, then one annexure per
department/province. Each annexure carries the apply-to details and closing date once; each post lists
a post number/title, salary, centre, requirements, duties and enquiries.

STATUS (honest): the parser below is written to that observed layout and is covered by tests against
a *synthetic dev fixture*. It has NOT yet been run against a live circular from this build environment
(the build sandbox's network allowlist blocks gov.za), and gov.za's robots.txt / reuse terms have not been
verified. The source row is therefore seeded `enabled = false, terms_status = 'unverified'` and must be
verified by a human before production use.
"""
from __future__ import annotations

import io
import re
from typing import Optional

from .base import BaseConnector, FetchResult, JobRecord
from .registry import register
from ..services.normalise import (
    clean_text, detect_province, detect_work_mode, parse_closing, parse_salary,
)

POST_RE = re.compile(r"^\s*POST\s+(\d{1,3}/\d+)\s*[:\-–]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
ANNEXURE_RE = re.compile(r"^[ \t]*ANNEXURE\s+([A-Z]{1,2})\b[^\n]*", re.IGNORECASE | re.MULTILINE)
LABELS = ("SALARY", "CENTRE", "REQUIREMENTS", "DUTIES", "ENQUIRIES", "APPLICATIONS",
          "CLOSING DATE", "NOTE", "OTHER POSTS")


def _field(block: str, label: str) -> Optional[str]:
    """Text after 'LABEL :' up to the next known label or end of block."""
    others = "|".join(l for l in LABELS if l != label)
    m = re.search(
        rf"^\s*{label}\s*[:\-–]\s*(.*?)(?=^\s*(?:{others})\s*[:\-–]|\Z)",
        block, re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return clean_text(m.group(1)) if m else None


def _split_annexures(text: str):
    """Yield (annexure_heading_text, body). If no annexure markers, one pseudo-annexure."""
    marks = list(ANNEXURE_RE.finditer(text))
    if not marks:
        yield "", text
        return
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        heading = clean_text(m.group(0).split("\n")[0]) or ""
        yield heading, text[m.start():end]


def parse_circular_text(text: str, circular_ref: str, pdf_url: str) -> FetchResult:
    records: list[JobRecord] = []
    errors: list[tuple[str, str]] = []

    for heading, body in _split_annexures(text):
        posts = list(POST_RE.finditer(body))
        if not posts:
            continue
        # annexure-level apply details and closing date (appear before the first post)
        preamble = body[: posts[0].start()]
        apply_text = _field(preamble, "APPLICATIONS") or clean_text(
            re.search(r"(APPLICATIONS?\b.*?)(?=CLOSING DATE|\Z)", preamble, re.I | re.S).group(1)
        ) if re.search(r"APPLICATIONS?\b", preamble, re.I) else None
        closing_raw = _field(preamble, "CLOSING DATE")
        closing = parse_closing(closing_raw)

        for i, pm in enumerate(posts):
            end = posts[i + 1].start() if i + 1 < len(posts) else len(body)
            block = body[pm.end():end]
            post_no, title = pm.group(1), clean_text(pm.group(2))
            ref = f"{circular_ref}/{post_no}"
            try:
                salary_raw = _field(block, "SALARY")
                centre = _field(block, "CENTRE")
                reqs = _field(block, "REQUIREMENTS")
                duties = _field(block, "DUTIES")
                enquiries = _field(block, "ENQUIRIES")
                lo, hi, cur, period = parse_salary(salary_raw)

                # employer = the department named in the annexure heading, if we can read one
                employer = clean_text(re.sub(r"^ANNEXURE\s+[A-Z]{1,2}\s*[:\-–]?\s*", "", heading,
                                             flags=re.I)) or None

                confidence = 0.4
                confidence += 0.15 if salary_raw else 0
                confidence += 0.15 if centre else 0
                confidence += 0.15 if reqs else 0
                confidence += 0.15 if closing else 0
                reasons = []
                if not closing:
                    reasons.append("closing_date_not_parsed")
                if salary_raw and lo is None:
                    reasons.append("salary_not_parsed")
                if not employer:
                    reasons.append("employer_not_identified")

                records.append(JobRecord(
                    source_job_id=ref,
                    title=title,
                    source_url=pdf_url,
                    employer=employer,
                    description=duties,
                    requirements_text=reqs,
                    salary_min=lo, salary_max=hi, salary_currency=cur, salary_period=period,
                    salary_raw=salary_raw,
                    location_text=centre,
                    province=detect_province(centre, heading),
                    work_mode=detect_work_mode(duties, reqs, centre),
                    closing_at=closing,
                    application_instructions=apply_text,
                    # The circular directs applicants to the department; there is no per-post URL.
                    application_url=None,
                    reference_no=post_no,
                    extraction_confidence=round(min(confidence, 1.0), 2),
                    extra_review_reasons=reasons,
                ))
            except Exception as e:  # one bad post must not lose the rest of the circular
                errors.append((ref, f"parse error: {e}"))
    return FetchResult(records=records, complete_snapshot=False, parse_errors=errors)


def pdf_to_text(data: bytes) -> str:
    from pdfminer.high_level import extract_text   # lazy: only needed for live PDFs
    return extract_text(io.BytesIO(data))


@register
class DpsaCircularConnector(BaseConnector):
    """config: {"pdf_urls": [...], "circular_refs": {"<url>": "23/2026"}}

    complete_snapshot is False on purpose: a circular is an increment, not the whole current set.
    Jobs expire by closing date (see ingest.expire_by_closing_date), never by absence.
    """
    key = "dpsa_circular"

    def fetch(self) -> FetchResult:
        urls = self.config.get("pdf_urls", [])
        refs = self.config.get("circular_refs", {})
        all_records, all_errors = [], []
        for url in urls:
            ref = refs.get(url) or re.sub(r"\W+", "-", url.rsplit("/", 1)[-1])[:40]
            try:
                resp = self.http.get(url)
                text = pdf_to_text(resp.content)
            except Exception as e:
                all_errors.append((url, f"fetch/extract failed: {e}"))
                continue
            res = parse_circular_text(text, ref, url)
            all_records.extend(res.records)
            all_errors.extend(res.parse_errors)
        return FetchResult(all_records, complete_snapshot=False, parse_errors=all_errors)
