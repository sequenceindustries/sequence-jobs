-- Sequence Industries AI Job Aggregator: initial schema (PostgreSQL 16)
-- Principles: unknown stays NULL; source facts are separated from AI interpretations;
-- every job keeps provenance (source, source id, source URL, verification time).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- sources
CREATE TABLE sources (
    id                  serial PRIMARY KEY,
    slug                text NOT NULL UNIQUE,
    name                text NOT NULL,
    website             text,
    connector           text NOT NULL,               -- connector class key
    access_method       text NOT NULL,               -- official_api | rss | partner_feed | public_notice_pdf | ...
    terms_status        text NOT NULL DEFAULT 'unverified'
                        CHECK (terms_status IN ('unverified','verified_permitted','restricted','prohibited')),
    terms_notes         text,
    republication       text NOT NULL DEFAULT 'link_only'
                        CHECK (republication IN ('full','summary','link_only')),
    enabled             boolean NOT NULL DEFAULT false,
    is_dev_data         boolean NOT NULL DEFAULT false,
    min_interval_secs   integer NOT NULL DEFAULT 3600,
    config              jsonb NOT NULL DEFAULT '{}',
    health              text NOT NULL DEFAULT 'unknown'
                        CHECK (health IN ('unknown','healthy','degraded','failing')),
    consecutive_failures integer NOT NULL DEFAULT 0,
    last_success_at     timestamptz,
    last_run_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------- jobs
CREATE TABLE jobs (
    id                  bigserial PRIMARY KEY,
    source_id           integer NOT NULL REFERENCES sources(id),
    source_job_id       text NOT NULL,                -- id in the original source
    canonical_job_id    bigint REFERENCES jobs(id),   -- set when this row is a cross-source duplicate
    dup_relation        text CHECK (dup_relation IN ('same_vacancy_other_source','duplicate','repost')),

    -- original facts (NULL = unknown; never invented)
    title               text NOT NULL,
    employer            text,
    description         text,
    requirements_text   text,
    qualifications_text text,
    experience_text     text,
    employment_type     text,
    salary_min          numeric(12,2),
    salary_max          numeric(12,2),
    salary_currency     text,
    salary_period       text CHECK (salary_period IN ('hour','month','year')),
    salary_raw          text,
    location_text       text,
    city                text,
    province            text,
    work_mode           text CHECK (work_mode IN ('on_site','hybrid','remote')),
    published_at        date,
    closing_at          timestamptz,
    application_instructions text,
    application_url     text,
    source_url          text NOT NULL,
    reference_no        text,

    -- lifecycle
    status              text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','expired','closed','removed')),
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    last_verified_at    timestamptz NOT NULL DEFAULT now(),
    content_hash        text NOT NULL,
    is_dev_data         boolean NOT NULL DEFAULT false,
    needs_review        boolean NOT NULL DEFAULT false,
    review_reasons      text[] NOT NULL DEFAULT '{}',

    -- deterministic extraction (not AI): confidence 0..1 for parsed fields
    extraction_confidence numeric(3,2),

    -- AI-derived layer, always kept separate from the original facts above
    ai_analysis_status  text NOT NULL DEFAULT 'not_requested'
                        CHECK (ai_analysis_status IN ('not_requested','pending','complete','failed','skipped')),

    search_tsv          tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title,'')), 'A') ||
        setweight(to_tsvector('english', coalesce(employer,'')), 'B') ||
        setweight(to_tsvector('english', coalesce(location_text,'') || ' ' || coalesce(province,'')), 'B') ||
        setweight(to_tsvector('english', coalesce(description,'') || ' ' || coalesce(requirements_text,'')), 'C')
    ) STORED,

    UNIQUE (source_id, source_job_id)
);
CREATE INDEX jobs_search_idx   ON jobs USING gin (search_tsv);
CREATE INDEX jobs_status_idx   ON jobs (status, published_at DESC);
CREATE INDEX jobs_province_idx ON jobs (province) WHERE status = 'active';
CREATE INDEX jobs_closing_idx  ON jobs (closing_at) WHERE status = 'active';
CREATE INDEX jobs_canonical_idx ON jobs (canonical_job_id);

-- change history: one row per detected change to a stored job
CREATE TABLE job_versions (
    id          bigserial PRIMARY KEY,
    job_id      bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    seen_at     timestamptz NOT NULL DEFAULT now(),
    content_hash text NOT NULL,
    changed_fields text[] NOT NULL DEFAULT '{}',
    snapshot    jsonb NOT NULL
);
CREATE INDEX job_versions_job_idx ON job_versions (job_id, seen_at DESC);

-- ----------------------------------------------------- AI layer (job side)
-- AI interpretations of a job. Keyed by content_hash so unchanged listings are never re-analysed.
CREATE TABLE job_ai_analyses (
    id              bigserial PRIMARY KEY,
    job_id          bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    content_hash    text NOT NULL,
    task            text NOT NULL,                   -- e.g. extract_requirements, classify
    provider        text NOT NULL,
    model           text NOT NULL,
    output          jsonb NOT NULL,
    input_tokens    integer,
    output_tokens   integer,
    est_cost_usd    numeric(10,6),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, content_hash, task)
);

CREATE TABLE ai_usage_log (
    id              bigserial PRIMARY KEY,
    at              timestamptz NOT NULL DEFAULT now(),
    task            text NOT NULL,
    provider        text NOT NULL,
    model           text,
    status          text NOT NULL CHECK (status IN ('ok','error','blocked_budget','unavailable')),
    input_tokens    integer,
    output_tokens   integer,
    latency_ms      integer,
    est_cost_usd    numeric(10,6),
    error           text
);
CREATE INDEX ai_usage_at_idx ON ai_usage_log (at);

-- --------------------------------------------------------- ingestion logs
CREATE TABLE ingestion_runs (
    id              bigserial PRIMARY KEY,
    source_id       integer NOT NULL REFERENCES sources(id),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','success','partial','failed')),
    fetched         integer NOT NULL DEFAULT 0,
    created         integer NOT NULL DEFAULT 0,
    updated         integer NOT NULL DEFAULT 0,
    unchanged       integer NOT NULL DEFAULT 0,
    expired         integer NOT NULL DEFAULT 0,
    flagged         integer NOT NULL DEFAULT 0,
    errors          integer NOT NULL DEFAULT 0,
    error_summary   text
);
CREATE INDEX ingestion_runs_src_idx ON ingestion_runs (source_id, started_at DESC);

CREATE TABLE ingestion_errors (
    id          bigserial PRIMARY KEY,
    run_id      bigint NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    at          timestamptz NOT NULL DEFAULT now(),
    stage       text NOT NULL,                       -- fetch | parse | normalise | store
    item_ref    text,
    message     text NOT NULL
);
