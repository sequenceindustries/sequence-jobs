# Architecture decisions

1. **Modular monolith.** One Flask app (API + services) plus a CLI (`manage.py`) that workers/cron call. A queue (Redis) is deferred until AI jobs/alerts need async processing; `redis-server` exists locally but nothing depends on it yet.
2. **Raw SQL via psycopg3, forward-only `.sql` migrations.** Small surface, full control of `tsvector`/generated columns, no ORM needed yet.
3. **Unknown stays NULL.** Parsers return None rather than guess (salary period, work mode, province, closing date). Absence of "remote" is not "on-site". Search treats unknown as non-matching for filters and tells the user which fields are unavailable.
4. **Provenance on every row:** source, source job id, source URL, first/last seen, last verified, content hash, extraction confidence; `job_versions` keeps change history.
5. **Source health isolation.** Each source runs in its own try/savepoint; one source or record failing never stops others. Jobs expire by absence **only after a complete snapshot**, otherwise by closing date. An outage can never mass-expire jobs.
6. **Source gate.** `terms_status` + `enabled` per source. `prohibited` is never fetched; new sources default to disabled/unverified. HTTP client respects robots.txt (unverifiable robots ⇒ do not crawl), refuses on 401/403 without working around them, bounded retries/timeouts.
7. **Dedup is conservative.** Link only when employer matches **and** ≥2 more signals incl. a title/URL/reference anchor. Never delete; later row gets `canonical_job_id` + relation (`same_vacancy_other_source` / `repost` / `duplicate`). Title similarity alone never links.
8. **AI behind a gateway.** All AI goes through `AIGateway`: needs provider + key, a non-zero daily budget, token caps; logs usage; validates structured output; **never fabricates a fallback**. Natural-language search only produces whitelisted filters that run as SQL over real rows, so the model cannot invent vacancies. Keyword search has no AI dependency.
9. **Dev data is labelled.** Sources flagged `is_dev_data` produce jobs shown with a "DEV DATA" tag, `noindex` detail pages, and are hidden entirely when `APP_ENV=production`.
10. **Frontend:** Next.js App Router, server-rendered, no client JS needed for search; API URL is server-side only.
