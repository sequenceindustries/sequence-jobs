# Sequence Jobs – AI-powered job aggregator (South Africa)

Sequence Industries (Pty) Ltd · MOTHER → Websites. Status: **foundation (Milestone 1 + part of 2)**. See `docs/`.

## Run locally
```bash
# 1. Backend (Python 3.13, PostgreSQL 16)
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://USER@HOST/sequence_jobs   # see backend/.env.example

# Optional: enable Groq (free tier: 25 requests/min)
# Sign up at https://console.groq.com and get your API key, then:
export AI_PROVIDER=groq
export GROQ_API_KEY=gsk_YOUR_API_KEY_HERE
export AI_DAILY_BUDGET_USD=10

cd backend
python manage.py migrate && python manage.py seed
python manage.py ingest dev-fixture --force                # loads SYNTHETIC dev data
python manage.py serve                                     # http://127.0.0.1:5000

# 2. Frontend (Node 22)
cd ../frontend && npm install
API_URL=http://127.0.0.1:5000 npm run dev                  # http://localhost:3000

# 3. Tests (need a scratch Postgres DB; they DROP the public schema of TEST_DATABASE_URL!)
cd ../backend && TEST_DATABASE_URL=postgresql://USER@HOST/sequence_jobs_test python -m pytest tests -q
```

## Layout
`backend/app/connectors` source connectors · `services` normalise/dedup/ingest/search · `ai` provider-independent gateway · `migrations` SQL · `frontend` Next.js · `docs` sources + decisions.

## Needs from you (nothing has been purchased or provisioned)
Groq API key (free tier available, 25 req/min; sign up at https://console.groq.com) · verification of gov.za terms + GCIS permission for DPSA · domain/GitHub repo/Railway project · email sender for alerts · ad provider account.

## Status (honest)
Implemented and covered by tests (196 backend tests; frontend typechecks and builds): ingestion framework with source gate, dedup, search, auth, CV upload/parsing, deterministic matching, recommendations, applications tracker, alerts + email outbox, AI gateway, AI workflows (CV improvement, cover letter, interview prep, assistant, export), **Groq provider integration** (ready to use with free or paid tier), admin API, SEO files.

NOT done / not possible without you: no real job source enabled (only synthetic dev data; DPSA is restricted pending GCIS permission); no email provider (alerts queue as `not_configured`); no deployment, repo, domain or paid service; JobPosting JSON-LD positive path is untested (no real data); no ads; no payments by design.

Frontend now includes login/register, an account area (recommendations, saved, tracker, alerts, CVs, profile), job-page save/track/match actions and a basic admin dashboard (`/admin`), served through a same-origin `/api` rewrite. Smoke-tested in a real browser (register, CV upload, profile, recommendations, match, track; admin denied for non-admins). AI-feature screens are not built yet because AI is not enabled.

Also added: interview practice and AI drafting UI on job pages (interview practice works without AI; AI buttons show "not available" until a provider is configured, verified in a browser), and a broken-link checker (`python manage.py check-links`, tested with fake HTTP only: sources must be enabled and verified-permitted, robots respected, flags a job for review only after two consecutive 404/410 results, never expires jobs by itself).

## AI & Groq

The project includes a provider-independent AI gateway (`backend/app/ai/provider.py`) that:
- Enforces a non-zero budget and token caps
- Logs all usage to `ai_usage_log` (task, model, tokens, latency, cost, status)
- Raises `AIUnavailable` when no provider is configured, budget is exhausted, or the provider fails
- Never fabricates output (keyword search falls back if AI is unavailable)

**Groq provider** (`backend/app/ai/providers/groq.py`): Mixtral 8x7B model via REST API.
- Free tier: 25 requests/minute (https://console.groq.com)
- Paid tier: $0.27 per 1M tokens (input + output)
- Configured via `AI_PROVIDER=groq`, `GROQ_API_KEY`, and `AI_DAILY_BUDGET_USD`
- Supports JSON mode for structured output
- Includes 7 unit tests covering success, errors, and budget enforcement

To use: sign up at https://console.groq.com, grab your API key, then set the env vars above and restart the backend.
