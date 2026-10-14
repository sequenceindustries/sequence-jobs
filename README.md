# Sequence Jobs – AI-powered job aggregator (South Africa)

Sequence Industries (Pty) Ltd · MOTHER → Websites. Status: **foundation (Milestone 1 + part of 2)**. See `docs/`.

## Run locally
```bash
# 1. Backend (Python 3.13, PostgreSQL 16)
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://USER@HOST/sequence_jobs   # see backend/.env.example
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
AI provider + API key + approved daily budget · verification of gov.za terms · domain/GitHub repo/Railway project · email sender for alerts · ad provider account.
