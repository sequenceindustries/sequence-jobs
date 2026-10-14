#!/usr/bin/env python
"""CLI: python manage.py migrate | seed | ingest [slug|--all] [--force] | sources | serve"""
import argparse
import json
import sys
from pathlib import Path

from app.config import Config
from app.db import connect, migrate
from app.services import ingest

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "dev_jobs.json"

# Source registry rows. Terms are NEVER marked verified here unless a human did so.
SEED_SOURCES = [
    dict(slug="dpsa-circular", name="Public Service Vacancy Circular (DPSA via gov.za)",
         website="https://www.gov.za", connector="dpsa_circular", access_method="public_notice_pdf",
         terms_status="restricted", republication="link_only", enabled=False, is_dev_data=False,
         min_interval_secs=21600,
         terms_notes="Official weekly PDF. Verified 14 Oct 2026: robots.txt does not disallow /sites/default/files/, BUT gov.za terms allow copying/distribution only for non-commercial purposes; commercial use needs prior written permission from GCIS (electronic@gcis.gov.za) and the notice '(c) GCIS2018: ALL RIGHTS RESERVED'. Linking is welcomed; framing is prohibited. Do not enable until written permission is on file.",
         config={"pdf_urls": [], "circular_refs": {}}),
    dict(slug="dev-fixture", name="DEV FIXTURE (synthetic data)", website=None, connector="fixture",
         access_method="local_file", terms_status="verified_permitted", republication="full",
         enabled=True, is_dev_data=True, min_interval_secs=0,
         terms_notes="Synthetic development data authored for tests. Not real vacancies.",
         config={"path": str(FIXTURE), "complete_snapshot": True,
                 "field_map": {"source_job_id": "id", "title": "title", "employer": "employer",
                               "description": "description", "requirements_text": "requirements",
                               "location_text": "location", "city": "city", "salary_raw": "salary",
                               "employment_type": "employment_type", "published_at": "published",
                               "closing_at": "closing", "application_url": "apply_url",
                               "reference_no": "ref"}}),
]


def seed(url: str):
    from psycopg.types.json import Jsonb
    with connect(url) as conn:
        for s in SEED_SOURCES:
            cols = [k for k in s if k != "config"]
            conn.execute(
                f"INSERT INTO sources ({','.join(cols)}, config) VALUES ({','.join(['%s'] * len(cols))}, %s) "
                f"ON CONFLICT (slug) DO NOTHING",
                [s[c] for c in cols] + [Jsonb(s["config"])])
        conn.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["migrate", "seed", "ingest", "sources", "serve"])
    p.add_argument("slug", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    url = Config.DATABASE_URL

    if a.cmd == "migrate":
        print("applied:", migrate(url) or "nothing to do")
    elif a.cmd == "seed":
        seed(url); print("seeded sources")
    elif a.cmd == "sources":
        with connect(url) as conn:
            for r in conn.execute("SELECT slug, enabled, terms_status, health, last_success_at FROM sources ORDER BY slug"):
                print(r)
    elif a.cmd == "ingest":
        kw = dict(user_agent=Config.USER_AGENT, timeout=Config.HTTP_TIMEOUT_SECS, retries=Config.HTTP_MAX_RETRIES)
        res = ingest.run_all(url, max_workers=Config.MAX_CONCURRENT_SOURCES, **kw) if a.all \
            else [ingest.run_source(url, a.slug, force=a.force, **kw)]
        print(json.dumps(res, indent=2, default=str))
    elif a.cmd == "serve":
        from app import create_app
        create_app().run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    sys.exit(main())
