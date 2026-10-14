"""Connector architecture.

A connector turns one legitimate source into a stream of `JobRecord`s.
It never writes to the database; the ingestion service does that, so a broken connector
can only affect its own source.
"""
from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Iterator, Optional
from urllib.parse import urlparse

import requests


@dataclass
class JobRecord:
    """Normalised job as produced by a connector. None means 'unknown' - never a guess."""
    source_job_id: str
    title: str
    source_url: str
    employer: Optional[str] = None
    description: Optional[str] = None
    requirements_text: Optional[str] = None
    qualifications_text: Optional[str] = None
    experience_text: Optional[str] = None
    employment_type: Optional[str] = None
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    salary_raw: Optional[str] = None
    location_text: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    work_mode: Optional[str] = None
    published_at: Optional[date] = None
    closing_at: Optional[datetime] = None
    application_instructions: Optional[str] = None
    application_url: Optional[str] = None
    reference_no: Optional[str] = None
    extraction_confidence: Optional[float] = None
    extra_review_reasons: list[str] = field(default_factory=list)


@dataclass
class FetchResult:
    records: list[JobRecord]
    # True only if the source returned its *complete* current set. Expiry of unseen jobs is
    # only allowed after a complete snapshot, so a partial/failed fetch can never expire jobs.
    complete_snapshot: bool
    parse_errors: list[tuple[str, str]] = field(default_factory=list)  # (item_ref, message)


class ConnectorError(Exception):
    pass


class RobotsDisallowed(ConnectorError):
    pass


class HttpClient:
    """requests wrapper: timeouts, bounded retries with backoff, robots.txt respect, polite UA.

    It deliberately has no CAPTCHA/auth-bypass features.
    """

    def __init__(self, user_agent: str, timeout: int = 20, max_retries: int = 3,
                 respect_robots: bool = True, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.respect_robots = respect_robots
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{base}/robots.txt", timeout=self.timeout)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                elif resp.status_code in (401, 403):
                    rp.disallow_all = True      # access control on robots.txt: treat as closed
                else:
                    rp.parse([])                # 404 etc: no restrictions published
            except requests.RequestException:
                rp.disallow_all = True          # cannot verify -> do not crawl
            self._robots[base] = rp
        return rp.can_fetch(self.user_agent, url)

    def get(self, url: str, **kw) -> requests.Response:
        if not self._allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        last: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, timeout=self.timeout, **kw)
                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = resp.headers.get("Retry-After")
                    delay = min(float(retry_after), 60) if retry_after and retry_after.isdigit() \
                        else 2 ** attempt
                    last = ConnectorError(f"HTTP {resp.status_code} from {url}")
                    time.sleep(delay)
                    continue
                if resp.status_code in (401, 403):
                    # Never try to work around access controls.
                    raise ConnectorError(f"Access refused (HTTP {resp.status_code}) for {url}")
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                time.sleep(2 ** attempt)
        raise ConnectorError(f"Giving up on {url} after {self.max_retries} attempts: {last}")


class BaseConnector:
    """Subclass and implement `fetch`. `key` is stored in sources.connector."""
    key: str = ""

    def __init__(self, source_config: dict, http: Optional[HttpClient] = None):
        self.config = source_config or {}
        self.http = http

    def fetch(self) -> FetchResult:  # pragma: no cover - interface
        raise NotImplementedError
