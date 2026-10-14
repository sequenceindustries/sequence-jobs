-- Accounts, profiles, CVs, tracker, alerts, admin audit, derived job fields.

-- ---- derived job fields (deterministic extraction, not AI) ------------------------------
ALTER TABLE jobs ADD COLUMN extracted_skills text[] NOT NULL DEFAULT '{}';
ALTER TABLE jobs ADD COLUMN min_experience_years smallint;       -- NULL = not stated
ALTER TABLE jobs ADD COLUMN seniority text CHECK (seniority IN ('entry','junior','mid','senior'));
ALTER TABLE jobs ADD COLUMN required_education text
    CHECK (required_education IN ('matric','certificate','diploma','degree','honours','masters'));
CREATE INDEX jobs_skills_idx ON jobs USING gin (extracted_skills);

-- ---- users -------------------------------------------------------------------------------
CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         text NOT NULL,
    password_hash text NOT NULL,
    role          text NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);
CREATE UNIQUE INDEX users_email_idx ON users (lower(email));

CREATE TABLE rate_limits (
    key          text NOT NULL,
    window_start timestamptz NOT NULL,
    hits         integer NOT NULL DEFAULT 0,
    PRIMARY KEY (key, window_start)
);

CREATE TABLE audit_log (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    actor_id  bigint REFERENCES users(id) ON DELETE SET NULL,
    action    text NOT NULL,
    target    text,
    detail    jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_log_at_idx ON audit_log (at DESC);

-- ---- profile: whitelisted fields only (no protected characteristics) ---------------------
CREATE TABLE profiles (
    user_id    bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data       jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---- CVs: raw upload is never stored; extracted text expires --------------------------
CREATE TABLE cvs (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label       text,
    source_ext  text NOT NULL,
    text_content text NOT NULL,
    parsed      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX cvs_user_idx ON cvs (user_id);
CREATE INDEX cvs_expiry_idx ON cvs (expires_at);

-- ---- saved / dismissed / reported jobs --------------------------------------------------
CREATE TABLE job_interactions (
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id  bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    state   text NOT NULL CHECK (state IN ('saved','dismissed')),
    at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);
CREATE TABLE job_reports (
    id      bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id  bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    reason  text NOT NULL,
    note    text,
    at      timestamptz NOT NULL DEFAULT now()
);

-- ---- application tracker (private) ------------------------------------------------------
CREATE TABLE applications (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id        bigint REFERENCES jobs(id) ON DELETE SET NULL,
    employer      text,
    job_title     text NOT NULL,
    listing_url   text,
    status        text NOT NULL DEFAULT 'interested' CHECK (status IN
        ('interested','preparing','applied','interview','assessment','offer','rejected','withdrawn','closed')),
    applied_on    date,
    interview_at  timestamptz,
    follow_up_on  date,
    notes         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX applications_user_idx ON applications (user_id, updated_at DESC);

CREATE TABLE application_events (
    id             bigserial PRIMARY KEY,
    application_id bigint NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    user_id        bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    at             timestamptz NOT NULL DEFAULT now(),
    kind           text NOT NULL,
    detail         text
);

-- ---- alerts, notifications, email outbox -----------------------------------------------
CREATE TABLE alerts (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    filters     jsonb NOT NULL,
    frequency   text NOT NULL DEFAULT 'daily' CHECK (frequency IN ('instant','daily','weekly')),
    channel     text NOT NULL DEFAULT 'in_app' CHECK (channel IN ('in_app','email')),
    enabled     boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_run_at timestamptz
);
CREATE TABLE notifications (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id   bigint NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    job_id     bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    reasons    text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at    timestamptz,
    UNIQUE (alert_id, job_id)                     -- a vacancy is never notified twice per alert
);
CREATE TABLE email_outbox (
    id        bigserial PRIMARY KEY,
    user_id   bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject   text NOT NULL,
    body      text NOT NULL,
    status    text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed','not_configured')),
    attempts  integer NOT NULL DEFAULT 0,
    error     text,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at   timestamptz
);
