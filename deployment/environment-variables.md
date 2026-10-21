# Environment Variables Configuration

This document describes all environment variables required for Sequence Jobs production deployment on Railway.

## Backend Variables

### Database
- **DATABASE_URL** - PostgreSQL connection string
  - Format: `postgresql://username:password@host:port/database`
  - Set automatically by Railway when you link the Postgres service
  - Example: `postgresql://sequence_jobs:password@postgres.railway.internal:5432/sequence_jobs_prod`

### Flask Configuration
- **FLASK_ENV** - Application environment
  - Value: `production`
  - Controls debug mode and error handling

- **PYTHONUNBUFFERED** - Python output buffering
  - Value: `1`
  - Ensures logs are flushed immediately for Railway logging

- **SECRET_KEY** - Flask session secret
  - Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"`
  - Keep secure and unique per environment
  - Length: 64 characters recommended

### API Configuration
- **API_URL** - Backend API public URL
  - Value: `https://api.yourdomain.com` or `https://yourdomain.com/api`
  - Used by frontend to make requests
  - Must be HTTPS in production

- **CRAWLER_USER_AGENT** - HTTP User-Agent header
  - Default: `SequenceJobsBot/0.1 (+contact: hello@sequencejobs.co.za)`
  - Update contact email as needed

### AI Provider Configuration
- **AI_PROVIDER** - AI service provider
  - Options: `groq`, `none` (disabled)
  - Default: `none` (AI disabled until configured)

- **GROQ_API_KEY** - Groq API authentication key
  - Get from: https://console.groq.com
  - Format: `gsk_...` (long alphanumeric string)
  - Store as secret (not plain text)

- **AI_DAILY_BUDGET_USD** - Daily AI token budget
  - Value: `10` (or your preferred limit)
  - Units: USD per day
  - Set to `0` to disable AI entirely

## Frontend Variables

### Environment
- **NODE_ENV** - Node.js environment
  - Value: `production`
  - Enables Next.js production optimizations

- **API_URL** - Backend API endpoint
  - Value: `https://api.yourdomain.com` or `https://yourdomain.com/api`
  - Frontend uses this to call backend endpoints
  - Must match backend's API_URL

## Database Variables

### PostgreSQL (Railway Postgres Service)
- **POSTGRES_USER** - Database owner username
  - Default: `sequence_jobs`
  - Used for connection pooling and migrations

- **POSTGRES_PASSWORD** - Database password
  - Generate: `openssl rand -hex 32`
  - Store as secret
  - Railway auto-generates if not provided

- **POSTGRES_DB** - Database name
  - Default: `sequence_jobs_prod`
  - Must be unique per environment

## Setting Variables in Railway

### Via Railway Dashboard
1. Go to your project → Service → Variables tab
2. Add each variable:
   - Name: variable name (e.g., `DATABASE_URL`)
   - Value: variable value
   - Check "Secret" if sensitive (passwords, API keys)
3. Click "Add Variable"
4. Redeploy service

### Via Railway CLI
```bash
railway variables set KEY=VALUE
railway variables set SECRET_KEY=your-secret-value --secret
railway redeploy
```

### Via railway.json
```json
{
  "services": {
    "backend": {
      "variables": {
        "FLASK_ENV": "production",
        "PYTHONUNBUFFERED": "1"
      },
      "secrets": {
        "SECRET_KEY": "set-in-dashboard",
        "GROQ_API_KEY": "set-in-dashboard"
      }
    }
  }
}
```

## Security Best Practices

1. **Never commit secrets** to Git
   - Use Railway secrets for sensitive values
   - Keep .env files in .gitignore

2. **Rotate API keys regularly**
   - Update GROQ_API_KEY every 90 days
   - Generate new SECRET_KEY before each deployment

3. **Use strong passwords**
   - Database password: `openssl rand -hex 32`
   - SECRET_KEY: `python3 -c "import secrets; print(secrets.token_hex(32))"`

4. **Limit scope**
   - Groq API key: restrict to your IP range in Groq console
   - Database: use password authentication, not trust

5. **Monitor access**
   - Review Railway activity logs regularly
   - Set up alerts for failed deployments
   - Monitor database query logs

## Verification Checklist

Before deploying:
- [ ] All required environment variables are set
- [ ] Secrets are marked as "Secret" in Railway
- [ ] DATABASE_URL points to production Postgres service
- [ ] API_URL matches your custom domain
- [ ] GROQ_API_KEY is valid and has sufficient quota
- [ ] AI_DAILY_BUDGET_USD is appropriate for your use
- [ ] No sensitive values are in plain text in code
- [ ] Environment files (.env, .env.local) are in .gitignore

## Troubleshooting

### Backend can't connect to database
- Check DATABASE_URL is set correctly
- Verify Postgres service is running (Railway dashboard)
- Check database credentials in Postgres Variables
- Look at backend logs: `railway logs backend`

### Frontend can't reach API
- Check API_URL is set to correct backend domain
- Verify backend is deployed and healthy
- Check CORS headers in backend (app/__init__.py)
- Look at browser console for network errors

### AI features not working
- Verify AI_PROVIDER is set to `groq` (not `none`)
- Check GROQ_API_KEY is valid and has quota
- Check AI_DAILY_BUDGET_USD is > 0
- Monitor AI usage: backend logs show all AI calls

### Deployment fails
- Check logs in Railway dashboard
- Verify all secrets are set (not empty)
- Ensure DATABASE_URL is set before deploying backend
- Check Dockerfile syntax
