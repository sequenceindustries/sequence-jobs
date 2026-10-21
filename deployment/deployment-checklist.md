# Deployment Checklist

Complete this checklist before deploying Sequence Jobs to production on Railway.

## Pre-Deployment (1-2 weeks before)

### Code Quality
- [ ] All tests pass locally
  ```bash
  cd backend && TEST_DATABASE_URL=postgresql://... python -m pytest tests -q
  ```
- [ ] Frontend builds without errors
  ```bash
  cd frontend && npm run build
  ```
- [ ] No TypeScript errors
  ```bash
  cd frontend && npm run typecheck
  ```
- [ ] Linting passes (if configured)
  ```bash
  cd frontend && npm run lint 2>/dev/null || echo "No linter configured"
  ```

### Infrastructure Preparation
- [ ] GitHub repository created and code pushed
- [ ] GitHub Secrets configured (see github-setup.md)
- [ ] Railway account created and project set up
- [ ] Domain registered (e.g., sequencejobs.co.za)
- [ ] Domain registrar access credentials available
- [ ] PostgreSQL database plan selected in Railway

### Environment Configuration
- [ ] Groq API key obtained (https://console.groq.com)
- [ ] Groq API quota verified (25 req/min free, or paid plan)
- [ ] Database password generated
  ```bash
  openssl rand -hex 32
  ```
- [ ] Flask SECRET_KEY generated
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] All environment variables documented (see environment-variables.md)

### Security Review
- [ ] .gitignore includes .env files
- [ ] No secrets in git history
  ```bash
  git log --all --source --remotes --oneline | grep -i "secret\|password\|key"
  ```
- [ ] ALLOWED_HOSTS configured for your domain
- [ ] CORS origins set to your domain
- [ ] HTTPS required everywhere (no HTTP)
- [ ] Security headers enabled (HSTS, CSP, etc.)

### Documentation
- [ ] README.md updated with production URL
- [ ] deployment/ folder created with all guides
- [ ] Environment variables documented
- [ ] Domain setup steps written
- [ ] Rollback procedure documented

## Deployment Day (Day 0)

### 6-12 Hours Before
- [ ] Schedule maintenance window
- [ ] Notify stakeholders of upcoming deployment
- [ ] Back up current database (if upgrading existing system)
- [ ] Prepare rollback plan
- [ ] Create new branch for deployment: `git checkout -b deploy/v1-production`

### 2-4 Hours Before
- [ ] Final code review
- [ ] Pull latest from main branch
- [ ] Verify all tests pass again
- [ ] Check Railway service status: https://status.railway.app

### 1 Hour Before
- [ ] Have Railway dashboard open
- [ ] Have GitHub dashboard open
- [ ] Have domain registrar DNS management open
- [ ] Have terminal ready with all commands prepared

## Deployment Execution (Day 0 - Morning)

### Step 1: GitHub Repository
- [ ] Code is on main branch
  ```bash
  git branch -v
  ```
- [ ] All changes committed
  ```bash
  git status
  ```
- [ ] Recent commit visible on GitHub
  ```bash
  git log -1 --oneline
  ```

### Step 2: Railway Project Setup
- [ ] Log into Railway: https://railway.app/dashboard
- [ ] Create new project: "Sequence Jobs Production"
- [ ] Note project ID

### Step 3: Database Service
- [ ] Add Postgres 16 service
- [ ] Configure variables:
  - [ ] POSTGRES_USER = sequence_jobs
  - [ ] POSTGRES_PASSWORD = (strong random 32 chars)
  - [ ] POSTGRES_DB = sequence_jobs_prod
- [ ] Note DATABASE_URL from service details
- [ ] Wait for Postgres to start (2-3 minutes)
- [ ] Test connection (optional):
  ```bash
  psql "$DATABASE_URL"
  \dt  # list tables (should be empty)
  \q
  ```

### Step 4: Backend Service
- [ ] Create new service from GitHub repository
- [ ] Select backend/ directory as root
- [ ] Set environment variables:
  - [ ] DATABASE_URL (from Postgres service)
  - [ ] FLASK_ENV = production
  - [ ] PYTHONUNBUFFERED = 1
  - [ ] API_URL = https://api.yourdomain.com (or https://yourdomain.com/api)
  - [ ] CRAWLER_USER_AGENT = SequenceJobsBot/0.1 (+contact: hello@...)
  - [ ] AI_PROVIDER = groq
  - [ ] AI_DAILY_BUDGET_USD = 10
- [ ] Set secrets:
  - [ ] SECRET_KEY (generated earlier)
  - [ ] GROQ_API_KEY (from Groq console)
- [ ] Set port: 8000
- [ ] Enable auto-deploy from main branch
- [ ] Watch logs for build completion
  ```bash
  # In Railway dashboard: Logs tab
  # Should see: "gunicorn: Listening at..."
  ```

### Step 5: Run Database Migrations
After backend builds successfully:
```bash
# Option A: Via Railway CLI
railway run python manage.py migrate

# Option B: Via Railway Dashboard Shell
# Services → backend → Shell tab
# $ python manage.py migrate

# Option C: Direct SSH
ssh user@railway.app
cd /app
python manage.py migrate
```

Expected output:
```
Operations to perform:
  Apply all migrations: auth, jobs, users, ...
Running migrations:
  Applying migrations ... OK
```

- [ ] Migrations completed without errors
- [ ] Verify tables created:
  ```bash
  psql "$DATABASE_URL" -c "\dt"
  ```

### Step 6: Seed Initial Data (Optional)
```bash
# Via Railway shell (same as migrations above)
python manage.py seed

# Verify data:
python manage.py sources
```

- [ ] Sources seeded successfully
- [ ] Backend health check passes:
  ```bash
  curl https://api.yourdomain.com/health
  # or
  curl http://localhost:8000/health  (if testing locally)
  ```

### Step 7: Frontend Service
- [ ] Create new service from GitHub repository
- [ ] Select frontend/ directory as root
- [ ] Set environment variables:
  - [ ] NODE_ENV = production
  - [ ] API_URL = https://api.yourdomain.com (or https://yourdomain.com/api)
  - [ ] NEXT_PUBLIC_API_URL (same as API_URL if publicly accessible)
- [ ] Set port: 3000
- [ ] Enable auto-deploy from main branch
- [ ] Watch logs for build completion
  ```bash
  # In Railway dashboard: Logs tab
  # Should see: "ready - started server on..."
  ```
- [ ] Frontend health check passes:
  ```bash
  curl https://yourdomain.com/
  # Should return HTML (Next.js page)
  ```

### Step 8: Domain Configuration

#### Step 8a: Add Domain to Railway
- [ ] Go to Railway project → Settings → Domains
- [ ] Click "Add Domain"
- [ ] Enter domain: sequencejobs.co.za
- [ ] Select frontend service to handle root domain
- [ ] Note DNS instructions from Railroad

#### Step 8b: Update DNS Records
In your domain registrar (GoDaddy, Namecheap, Route53, etc.):

- [ ] Add A record:
  - Name: sequencejobs.co.za
  - Type: A
  - Value: (Railway IP address)
  - TTL: 3600

- [ ] Add CNAME record:
  - Name: www
  - Type: CNAME
  - Value: sequencejobs.co.za
  - TTL: 3600

- [ ] For subdomains (if using separate API domain):
  - [ ] Add A record:
    - Name: api
    - Type: A
    - Value: (same Railway IP)
    - TTL: 3600

#### Step 8c: Verify DNS Propagation
```bash
# Check DNS propagation
nslookup sequencejobs.co.za
dig sequencejobs.co.za A

# Should resolve within 5-30 minutes
# Full propagation may take up to 24 hours
```

- [ ] A record resolves to Railway IP
- [ ] CNAME record resolves correctly
- [ ] DNS propagation check shows green

#### Step 8d: SSL Certificate Issuance
- [ ] In Railway dashboard, check domain status
- [ ] Wait for "Valid SSL Certificate" message (5-10 minutes)
- [ ] Verify SSL certificate:
  ```bash
  openssl s_client -connect sequencejobs.co.za:443 -servername sequencejobs.co.za
  # Should show: Verify return code: 0 (ok)
  ```

### Step 9: Backend Routing (if using path-based API)

If API is at `yourdomain.com/api`:
- [ ] Configure frontend to route `/api/*` to backend service
- [ ] Test routing:
  ```bash
  curl https://yourdomain.com/api/jobs
  # Should return job data, not 404
  ```

If using separate domain:
- [ ] Ensure backend service has domain: api.sequencejobs.co.za
- [ ] Test API endpoint:
  ```bash
  curl https://api.sequencejobs.co.za/jobs
  ```

## Post-Deployment (Day 1-7)

### Immediate (Day 0, end of day)
- [ ] All services show as "Running" in Railway
- [ ] No errors in logs (railway logs backend, railway logs frontend)
- [ ] Frontend loads: https://yourdomain.com
- [ ] API responds: https://api.yourdomain.com/jobs
- [ ] SSL certificate is valid (green in browser)
- [ ] Notify stakeholders deployment complete

### Day 1-2: Smoke Testing
- [ ] Manual testing in production:
  - [ ] Visit homepage: https://yourdomain.com
  - [ ] Load jobs page: https://yourdomain.com/jobs
  - [ ] Search for a job
  - [ ] Register a new account
  - [ ] Upload a CV
  - [ ] Save a job
  - [ ] Get recommendations
  - [ ] Visit admin dashboard: https://yourdomain.com/admin (as admin user)
  
- [ ] Monitor logs for errors:
  ```bash
  railway logs backend -f  # Follow logs
  railway logs frontend -f
  ```

- [ ] Check database:
  ```bash
  railway run python manage.py sources
  # Should list all sources and counts
  ```

### Day 3-7: Extended Monitoring
- [ ] Monitor CPU and memory usage in Railway
- [ ] Monitor error logs and exceptions
- [ ] Check AI usage against budget:
  ```bash
  railway run python manage.py ai-usage
  ```
- [ ] Monitor database query performance
- [ ] Set up alerts in Railway for:
  - [ ] High error rate (>1%)
  - [ ] High response time (>1s)
  - [ ] Memory usage >90%
  - [ ] Disk usage >80%

### Week 1+: Ongoing
- [ ] Monitor Railway dashboard daily
- [ ] Review logs 2-3 times per week
- [ ] Check SSL certificate expiry (auto-renewed by Let's Encrypt)
- [ ] Monitor AI usage and costs
- [ ] Gather user feedback
- [ ] Plan first maintenance window

## Rollback Plan (If Something Goes Wrong)

### Quick Rollback
If deployment is catastrophic (won't start, database issues, etc.):

1. **Identify issue**
   ```bash
   railway logs backend
   railway logs frontend
   # Look for error messages in last 10 lines
   ```

2. **Rollback deployment**
   - Option A: Revert to previous commit
     ```bash
     git revert HEAD
     git push origin main
     # Railway auto-deploys updated code
     ```
   
   - Option B: Pause services in Railway
     - Go to each service → Settings → Pause
     - Creates manual intervention forcing review before restart

3. **Restart services**
   - Go to service → Logs tab
   - Look for "Restarting" message
   - Wait for healthy status

4. **Verify recovery**
   ```bash
   curl https://yourdomain.com
   curl https://api.yourdomain.com/health
   ```

### Database Rollback
If data got corrupted during migration:

```bash
# Stop backend service (Railway dashboard)
# Then restore from snapshot (if available)
railway backup restore <backup-id>

# Or restore from manual backup (if you made one before deployment)
# Contact Railway support for older snapshots
```

## Post-Rollback
- [ ] Investigate root cause
- [ ] Write incident report
- [ ] Plan fix
- [ ] Test fix locally
- [ ] Schedule new deployment
- [ ] Brief team on what went wrong

## Sign-Off

- [ ] Deployment completed successfully
- [ ] All checks passed
- [ ] Stakeholders notified
- [ ] Team briefed on production URL
- [ ] Monitoring set up
- [ ] Rollback plan documented
- [ ] Post-deployment review scheduled

**Deployed by**: ________________
**Date**: ________________
**Time**: ________________
**Duration**: ________________ minutes
**Issues encountered**: None / [describe]
**Notes**: [any additional observations]
