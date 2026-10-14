from datetime import datetime
from decimal import Decimal

from app.connectors.dpsa_circular import parse_circular_text
from app.services.normalise import (
    detect_province, detect_work_mode, parse_closing, parse_salary,
)


def test_salary_monthly_range():
    assert parse_salary("R25 000 - R30 000 per month") == (Decimal(25000), Decimal(30000), "ZAR", "month")


def test_salary_annual_ignores_level_number():
    lo, hi, cur, per = parse_salary("R338 106 per annum (Level 07)")
    assert (lo, hi, cur, per) == (Decimal(338106), Decimal(338106), "ZAR", "year")


def test_salary_unparseable_stays_unknown():
    assert parse_salary("Market related") == (None, None, None, None)
    assert parse_salary(None) == (None, None, None, None)


def test_salary_without_period_keeps_period_unknown():
    assert parse_salary("R40 000")[3] is None


def test_closing_date_with_and_without_time():
    d = parse_closing("17 July 2026 at 16:00")
    assert (d.year, d.month, d.day, d.hour, d.minute) == (2026, 7, 17, 16, 0)
    assert parse_closing("31 July 2026").hour == 23
    assert parse_closing("sometime soon") is None
    assert parse_closing("31 Smarch 2026") is None


def test_province_only_when_unambiguous():
    assert detect_province("Zwelitsha, Eastern Cape") == "Eastern Cape"
    assert detect_province("Between Gauteng and Limpopo") is None
    assert detect_province("Johannesburg") is None          # city alone is not inferred


def test_work_mode_only_when_explicit():
    assert detect_work_mode("Fully remote role") == "remote"
    assert detect_work_mode("hybrid, 3 days in office") == "hybrid"
    assert detect_work_mode("Customer support agent") is None   # absence != on-site


CIRCULAR = """
PUBLIC SERVICE VACANCY CIRCULAR 99 OF 2026  (SYNTHETIC TEST TEXT)

ANNEXURE A: DEPARTMENT OF EXAMPLE HEALTH - EASTERN CAPE
APPLICATIONS: Direct to the HR Office, Private Bag 1, Exampleville.
CLOSING DATE : 17 July 2026 at 16:00

POST 99/001: Administration Clerk Supervisor
SALARY : R338 106 per annum (Level 07)
CENTRE : Organisational Development, Zwelitsha
REQUIREMENTS : Grade 12 or equivalent, at least four years' experience.
DUTIES : Facilitate planning and monitor annual operational plans.
ENQUIRIES : Ms A Example, (000) 000 0000

POST 99/002: Community Liaison Officer
SALARY : Market related
CENTRE : Exampleville
REQUIREMENTS : Matric.
DUTIES : Liaise with communities.
ENQUIRIES : Mr B Example

ANNEXURE B: DEPARTMENT OF EXAMPLE WORKS
APPLICATIONS: Email to hr@example.invalid

POST 99/003: Works Inspector
SALARY : R250 000 per annum
CENTRE : Head Office
REQUIREMENTS : N6 certificate.
DUTIES : Inspect sites.
"""


def test_circular_parser_extracts_posts_and_keeps_unknowns_unknown():
    res = parse_circular_text(CIRCULAR, "99/2026", "https://www.gov.za/x.pdf")
    by_id = {r.source_job_id: r for r in res.records}
    assert set(by_id) == {"99/2026/99/001", "99/2026/99/002", "99/2026/99/003"}
    a = by_id["99/2026/99/001"]
    assert a.title == "Administration Clerk Supervisor"
    assert a.salary_min == Decimal(338106) and a.salary_period == "year"
    assert a.province == "Eastern Cape"
    assert a.closing_at == datetime.fromisoformat("2026-07-17T16:00:00+02:00")
    assert a.application_url is None                      # never invented
    assert "Private Bag 1" in a.application_instructions
    b = by_id["99/2026/99/002"]
    assert b.salary_min is None and b.salary_raw == "Market related"
    c = by_id["99/2026/99/003"]
    assert c.closing_at is None and "closing_date_not_parsed" in c.extra_review_reasons
    assert c.extraction_confidence < a.extraction_confidence
    assert res.complete_snapshot is False


def test_circular_parser_empty_text_yields_nothing():
    res = parse_circular_text("no posts here", "1/2026", "https://www.gov.za/x.pdf")
    assert res.records == []
