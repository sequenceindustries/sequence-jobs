# Sequence Jobs - Production Deployment Guide

This guide walks you through deploying Sequence Jobs to Railway with a custom domain (e.g., `sequencejobs.co.za`).

**Time estimate**: 1-2 hours (mostly waiting for DNS propagation)  
**Difficulty**: Intermediate (infrastructure knowledge helpful)  
**Requirements**: GitHub account, Railway account, domain registrar access, Groq API key

## Quick Overview

1. **Setup** (15 min): GitHub repo, generate secrets
2. **Railway** (30 min): Create services, configure environment
3. **Database** (5 min): Run migrations, seed data
4. **Domain** (10 min): Add DNS records, configure SSL
5. **Test** (10 min): Verify everything works
6. **Monitor** (ongoing): Watch logs and health

## Detailed Steps

### 1. Prepare Your Repository

```bash
# Navigate to your project
cd /path/to/sequence-jobs

# Verify git status
git status

# Stage all files (they're already in .gitignore for sensitive data)
git add -A

# Create initial commit with proper attribution
git commit -m "Initial commit: Sequence Jobs ready for production deployment

- Backend: Flask API with PostgreSQL, job aggregation, AI integration
- Frontend: Next.js React app with job search and recommendations
- Docker: Containerized backend and frontend services
- Environment: Fully configurable for Railway deployment

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# Create main branch (if not already exists)
git branch -M main

# Verify commit was created
git log --oneline -3
```

**Output should show** your new commit at the top.

### 2. Push to GitHub

#### Create Repository on GitHub
1. Visit https://github.com/new
2. Fill in:
   - **Repository name**: sequence-jobs
   - **Description**: AI-powered job aggregator for South Africa
   - **Visibility**: Private (unless you want public source code)
   - **Initialize repo**: No (we have existing code)
3. Click "Create repository"
4. Note the repository URL: `https://github.com/YOUR_USERNAME/sequence-jobs.git`

#### Push Your Code
```bash
cd /path/to/sequence-jobs

# Add GitHub as remote
git remote add origin https://github.com/YOUR_USERNAME/sequence-jobs.git

# Push code to GitHub
git push -u origin main

# Verify on GitHub
# https://github.com/YOUR_USERNAME/sequence-jobs
```

**Output should show**: files pushed to GitHub.

### 3. Generate Secrets

Generate strong random values for sensitive configuration:

```bash
# PostgreSQL password (32 random hex characters)
echo "POSTGRES_PASSWORD:" $(openssl rand -hex 32)

# Flask SECRET_KEY (64 hex characters)
echo "SECRET_KEY:" $(python3 -c "import secrets; print(secrets.token_hex(32))")

# Save these values - you'll need them in Railway
```

### 4. Get API Keys

#### Groq API Key (for AI features)
1. Visit https://console.groq.com
2. Sign up (free tier available)
3. Click "API Keys" in sidebar
4. Create new API key
5. Copy the key (starts with `gsk_`)
6. Keep this secret - never commit to Git

### 5. Create Railway Project

1. Visit https://railway.app and log in (or sign up)
2. Click "Create New Project"
3. Choose "Empty Project" (we'll add services manually)
4. Name it: "Sequence Jobs Production"
5. Note the project URL: you'll need it later

### 6. Add PostgreSQL Database

In your Railway project:

1. Click "Add Service"
2. Select "Database"
3. Choose "PostgreSQL"
4. Click "Deploy"
5. Wait for database to start (2-3 minutes)
6. Click on the Postgres service
7. Go to "Variables" tab
8. Add environment variables:
   - **POSTGRES_USER**: sequence_jobs
   - **POSTGRES_PASSWORD**: (paste the strong password you generated)
   - **POSTGRES_DB**: sequence_jobs_prod
9. The DATABASE_URL should auto-generate - copy it (you'll need it soon)

### 7. Set GitHub Secrets

GitHub Secrets securely store sensitive values for deployment:

1. Go to your GitHub repository: https://github.com/YOUR_USERNAME/sequence-jobs
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret"
4. Add these secrets one by one:

| Secret Name | Value |
|---|---|
| RAILWAY_TOKEN | Get from `railway token` command (see below) |
| DATABASE_URL | From Postgres service in Railway |
| POSTGRES_PASSWORD | The strong password you generated |
| SECRET_KEY | The 64-char hex string you generated |
| GROQ_API_KEY | Your API key from Groq console |

**Get Railway Token**:
```bash
# Install Railway CLI (if not already installed)
npm install -g @railway/cli

# Login
railway login
# Opens browser to login

# Get token
railway token
# Outputs long token - copy and paste to GitHub Secret RAILWAY_TOKEN
```

### 8. Create Backend Service

In Railway:

1. Click "New Service"
2. Select "GitHub Repository"
3. Connect your GitHub account (if not already)
4. Select the repository: `sequence-jobs`
5. Click "Deploy"
6. Railway auto-detects Dockerfile and builds
7. Once built, click the service to configure:
   - Go to "Settings" tab
   - Set **Build Command**: `pip install -r requirements.txt`
   - Set **Start Command**: `gunicorn -b 0.0.0.0:$PORT -w 4 --timeout 120 app:create_app()`
   - Set **Port**: 8000
8. Go to "Variables" tab
9. Add environment variables:
   - **DATABASE_URL**: (paste from Postgres service)
   - **FLASK_ENV**: production
   - **PYTHONUNBUFFERED**: 1
   - **API_URL**: https://api.sequencejobs.co.za (update with your actual domain)
   - **CRAWLER_USER_AGENT**: SequenceJobsBot/0.1 (+contact: hello@sequencejobs.co.za)
   - **AI_PROVIDER**: groq
   - **AI_DAILY_BUDGET_USD**: 10
10. Go to "Secrets" tab
11. Add secrets:
    - **SECRET_KEY**: (paste your generated SECRET_KEY)
    - **GROQ_API_KEY**: (paste your Groq API key)
12. Wait for build to complete and service to start

### 9. Run Database Migrations

After backend builds and starts:

```bash
# Option A: Using Railway CLI
railway service select  # choose backend
railway run python manage.py migrate

# Option B: Using Railway Shell
# In Railway dashboard → backend service → Shell tab
# Paste: python manage.py migrate
# Press Enter

# Expected output:
# Operations to perform:
#   Apply all migrations: admin, jobs, users, ...
# Running migrations:
#   Applying migrations... OK
```

Verify migrations succeeded:
```bash
railway run python manage.py sources
# Should list: dev-fixture, dpsa-circular, etc.
```

### 10. Seed Initial Data (Optional)

Load synthetic development data for testing:

```bash
railway run python manage.py seed
# Loads DPSA and fixture sources

# Verify:
railway run python manage.py sources
# Should show source counts
```

### 11. Create Frontend Service

In Railway:

1. Click "New Service"
2. Select "GitHub Repository"
3. Select the same `sequence-jobs` repository
4. In service settings:
   - Set **Build Command**: `npm install && npm run build`
   - Set **Start Command**: `npm start`
   - Set **Port**: 3000
   - Set **Root Directory**: frontend
5. Go to "Variables" tab
6. Add environment variables:
   - **NODE_ENV**: production
   - **API_URL**: https://api.sequencejobs.co.za (or https://yourdomain.com/api if path-based)
   - **NEXT_PUBLIC_API_URL**: (same as API_URL)
7. Wait for build to complete

### 12. Configure Domain

#### Step A: Update Domain DNS Records

In your domain registrar (GoDaddy, Namecheap, Route53, etc.):

For domain: `sequencejobs.co.za`

Add these records:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | sequencejobs.co.za | [Railway IP from dashboard] | 3600 |
| CNAME | www | sequencejobs.co.za | 3600 |
| A | api | [Railway IP] | 3600 |

**Get Railway IP**: In Railway dashboard → Settings → Domains → copy the IP address Railroad shows

#### Step B: Add Domain to Railway Services

1. In Railway, go to project Settings → Domains
2. Click "Add Domain"
3. Enter: `sequencejobs.co.za`
4. Select service: **frontend**
5. Click "Save"
6. Add another domain:
   - Name: `api.sequencejobs.co.za`
   - Service: **backend**
   - Click "Save"
7. Wait for SSL certificate to issue (5-10 minutes)
   - Status should change from "Pending" to "Valid"

#### Step C: Verify DNS Propagation

```bash
# Check if domain resolves
nslookup sequencejobs.co.za
# Should show Railway's IP address

# May take 5 minutes to 24 hours for full propagation
# Useful tool: https://dnschecker.org
```

### 13. Test the Deployment

#### Test Frontend
```bash
# In browser or terminal
curl -I https://sequencejobs.co.za
# Should return: HTTP/1.1 200 OK

# Verify SSL certificate
# Browser should show: 🔒 Secure
```

#### Test API
```bash
curl https://api.sequencejobs.co.za/health
# Should return: {"status": "ok"}

curl https://api.sequencejobs.co.za/jobs
# Should return JSON array of jobs
```

#### Test in Browser
1. Visit https://sequencejobs.co.za
2. Page should load (not error)
3. Click "Jobs" to see job listing
4. Search for a job
5. Click a job to view details
6. Try "Register" to create account
7. Visit https://sequencejobs.co.za/admin
   - Should require login (expected)

### 14. Set Up Monitoring

#### View Logs
```bash
# Backend logs
railway logs backend -f

# Frontend logs
railway logs frontend -f

# Database logs (if needed)
railway logs postgres -f
```

#### Set Up Alerts (Optional but Recommended)
In Railway dashboard → Settings:
- Enable email notifications for:
  - Deployment failures
  - High error rates
  - Memory/CPU spikes
  - Service crashes

#### Monitor AI Usage
```bash
# Check daily AI usage and cost
railway run python manage.py ai-usage

# If approaching daily budget:
# - Review logs for expensive operations
# - Consider lowering AI_DAILY_BUDGET_USD
# - Or upgrade Groq plan
```

### 15. Configure Auto-Deploy (Optional)

To automatically deploy when you push to `main` branch:

#### Via GitHub Actions
Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Railway
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy
        run: npx @railway/cli up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

#### Via Railway Dashboard
1. Go to project Settings
2. Enable "Auto Deploy"
3. Select main branch
4. Click "Save"

Now every push to `main` automatically redeploys!

## Troubleshooting

### Domain not working
- Wait 5-30 minutes for DNS propagation
- Check DNS records in registrar (must match Railway IP)
- Verify domain in Railway Domains settings
- Clear browser cache: Ctrl+Shift+Del

### API returns 404 not found
- Verify `api.sequencejobs.co.za` domain is added to backend service
- Check API_URL environment variable in frontend
- Review backend logs: `railway logs backend -f`

### Frontend can't reach API
- Check API_URL in frontend environment variables
- Verify CORS is enabled in backend
- Check browser console for network errors
- Test API directly: `curl https://api.sequencejobs.co.za/jobs`

### Database migration failed
```bash
# View error
railway logs backend -f

# Common issues:
# 1. DATABASE_URL not set → add in backend Variables
# 2. Postgres not started → wait 2-3 minutes
# 3. Insufficient permissions → check POSTGRES_USER

# Retry migration
railway run python manage.py migrate
```

### Build failed
- Check service logs: Railway dashboard → Logs tab
- Verify Dockerfile exists: `frontend/Dockerfile`, `backend/Dockerfile`
- Ensure all files are committed: `git status`
- Review build errors and fix locally:
  ```bash
  docker build -f backend/Dockerfile backend/
  docker build -f frontend/Dockerfile frontend/
  ```

### High memory usage
- Check Railway dashboard → Metrics → Memory
- Review what's consuming memory:
  - Large database queries
  - Memory leaks in code
  - Cache not being cleared
- Restart service or upgrade plan

## Post-Deployment

### Day 1
- Monitor logs for errors
- Test all major features in browser
- Check performance metrics
- Verify backups are working

### Week 1
- Monitor daily usage and trends
- Review error logs
- Check AI usage vs budget
- Gather user feedback
- Plan any bug fixes

### Ongoing
- Monitor logs 2-3x per week
- Review performance weekly
- Update dependencies monthly
- Plan feature improvements
- Monitor SSL certificate expiry (auto-renewed)

## Next Steps

- See `deployment/deployment-checklist.md` for detailed pre-deployment checklist
- See `deployment/domain-setup.md` for advanced domain configuration
- See `deployment/environment-variables.md` for all configuration options
- See `deployment/github-setup.md` for GitHub repository best practices

## Getting Help

- **Railway documentation**: https://docs.railway.app
- **Railroad (Railway's AI)**: https://railroad.app
- **Groq API docs**: https://console.groq.com/docs
- **Next.js docs**: https://nextjs.org/docs
- **Flask docs**: https://flask.palletsprojects.com

## Rollback (If Something Goes Wrong)

If deployment fails catastrophically:

```bash
# Identify the issue
railway logs backend
railway logs frontend

# Rollback to previous commit
git revert HEAD
git push origin main

# Railway auto-redeploys (or manually in dashboard)

# If database corrupted, restore snapshot in Railway dashboard
# Contact Railway support for help
```

---

**Happy deploying!** 🚀

Once live, share your domain: `https://sequencejobs.co.za`
