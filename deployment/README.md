# Sequence Jobs Deployment Documentation

This folder contains all documentation and configuration files needed to deploy Sequence Jobs to Railway with a custom domain.

## Quick Start

**New to deployment?** Start here:
1. Read the top-level `DEPLOY.md` (15-minute overview)
2. Follow the step-by-step instructions
3. Use `deployment-checklist.md` to track progress

**Already familiar?** Jump to:
- `environment-variables.md` - All configuration options
- `domain-setup.md` - Advanced domain setup
- `github-setup.md` - Repository and CI/CD setup

## File Guide

### `DEPLOY.md` (Top-level, in root)
**Main deployment guide** with step-by-step instructions.

- Quick overview of the deployment process
- Detailed steps for GitHub, Railway, database, domain setup
- Testing and troubleshooting
- Post-deployment monitoring

**When to use**: First-time deployments, quick reference

### `deployment-checklist.md`
**Pre-deployment verification** to catch issues early.

Sections:
- Pre-deployment (1-2 weeks before): code quality, infrastructure, security
- Deployment day (execute carefully): step-by-step checklist
- Post-deployment (week 1+): monitoring and validation
- Rollback plan: what to do if something breaks

**When to use**: Before deploying, to ensure nothing is missed

### `environment-variables.md`
**Complete reference** for all configuration options.

Sections:
- Backend variables (database, Flask, AI, crawler)
- Frontend variables (API URL, environment)
- Database variables (PostgreSQL)
- Security best practices
- Troubleshooting guide

**When to use**: Setting up environment, debugging configuration issues

### `domain-setup.md`
**Advanced domain configuration** guide.

Sections:
- Domain structure patterns (subdomain vs path-based vs separate)
- DNS record setup
- SSL/TLS certificate configuration
- Application configuration
- Security headers
- Troubleshooting

**When to use**: Custom domain setup, SSL issues, DNS debugging

### `github-setup.md`
**GitHub repository preparation** for deployment.

Sections:
- Creating and pushing repository
- Structure verification
- Adding GitHub Secrets
- GitHub Actions workflow (optional)
- Branch strategy and commit hygiene
- Security checklist

**When to use**: Setting up GitHub, configuring CI/CD, security review

## Configuration Files (Root Directory)

### `railway.toml`
Railway service definition (legacy format).

**Note**: Updated configuration should be in `.railway/config.json` (see below).

### `.railway/config.json`
Modern Railway configuration with all services.

Defines:
- PostgreSQL database service
- Backend service with environment variables
- Frontend service with environment variables
- Domain routing
- Health checks
- Auto-scaling options

**When to use**: Infrastructure-as-code, Railway CLI, project documentation

### `backend/Dockerfile`
Backend (Flask) containerization.

- Python 3.13-slim base image
- Required system dependencies
- Gunicorn WSGI server
- Health check endpoint
- Non-root user for security

**When to use**: Docker builds, local testing, understanding backend deployment

### `frontend/Dockerfile`
Frontend (Next.js) containerization.

- Multi-stage build (builder + runtime)
- Node 22-alpine for small image
- Production optimizations
- Health check endpoint
- Non-root user for security

**When to use**: Docker builds, local testing, understanding frontend deployment

## Deployment Sequence

### Before Day 1 (1-2 weeks)
1. Code quality checks (tests, linting, build)
2. Infrastructure decisions (domain, Railway plan, Groq API)
3. Security review (secrets, HTTPS, CORS, headers)
4. Documentation (README update, deployment guides)

### Day 1 Morning (Deployment)
1. **GitHub** (10 min): Push code to repository
2. **Railway** (30 min): Create project, add services, configure environment
3. **Database** (5 min): Run migrations, seed data
4. **Domain** (15 min): Add DNS records, configure SSL
5. **Test** (10 min): Verify everything works

### Day 1 Afternoon (Monitoring)
1. Watch logs for errors
2. Test features manually
3. Verify metrics and performance
4. Notify stakeholders

### Weeks 1+ (Ongoing)
1. Monitor logs and errors
2. Review performance metrics
3. Update code as needed
4. Plan improvements

## Common Tasks

### "I need to deploy the backend"
→ See `DEPLOY.md` steps 1-11

### "Domain won't resolve"
→ See `domain-setup.md` Troubleshooting section

### "How do I set environment variables?"
→ See `environment-variables.md`

### "API returns 404 on deployed version"
→ See `DEPLOY.md` Troubleshooting section

### "Want to automate deployments?"
→ See `github-setup.md` Step 6

### "Need to understand the deployment?"
→ Read `deployment-checklist.md` for full overview

## Key Concepts

### Services
- **Backend**: Flask API server (port 8000)
- **Frontend**: Next.js web app (port 3000)
- **Database**: PostgreSQL 16 (port 5432)

### Domains (Example)
- `sequencejobs.co.za` → Frontend (port 3000)
- `api.sequencejobs.co.za` → Backend (port 8000)
- `www.sequencejobs.co.za` → Frontend (redirect)

### Environments
- **Development**: Local with .env files
- **Production**: Railway with secrets/variables
- **Staging**: Optional separate Railway project

### Secrets vs Variables
- **Secrets**: Passwords, API keys, tokens (not shown in logs)
- **Variables**: Configuration, URLs, settings (visible but not sensitive)

## Security Checklist

Before going live:
- [ ] All secrets in Railway (not in code)
- [ ] Database password is strong (32+ random chars)
- [ ] Groq API key is restricted (IP allowlist if possible)
- [ ] HTTPS enforced everywhere (no HTTP)
- [ ] CORS configured to your domain only
- [ ] Security headers enabled (HSTS, CSP, etc.)
- [ ] SSH keys not in repository
- [ ] API endpoints authenticated where needed
- [ ] Rate limiting enabled for public endpoints
- [ ] Monitoring and alerts configured

## Performance Considerations

### Database
- PostgreSQL 16 on Railway (managed)
- Automatic backups enabled
- Monitor query performance
- Index frequently-searched columns

### Frontend
- Next.js optimizes bundle size
- Image optimization enabled
- API caching for repeated requests
- CDN for static assets

### Backend
- Gunicorn with 4 workers
- Connection pooling to database
- Request timeouts (120s)
- AI budget limits prevent runaway costs

## Maintenance Tasks

### Weekly
- [ ] Review error logs
- [ ] Check performance metrics
- [ ] Monitor AI usage vs budget

### Monthly
- [ ] Update dependencies
- [ ] Review security logs
- [ ] Test backup restoration
- [ ] Update documentation

### Quarterly
- [ ] Review and optimize database indexes
- [ ] Audit user permissions
- [ ] Plan major version upgrades
- [ ] Review and update security policies

## Getting Help

### Documentation
- [Railway Docs](https://docs.railway.app)
- [Next.js Docs](https://nextjs.org/docs)
- [Flask Docs](https://flask.palletsprojects.com)
- [PostgreSQL Docs](https://www.postgresql.org/docs)

### Support
- Railway support: https://railway.app/support
- Groq support: https://console.groq.com (in-app chat)
- GitHub issues: Use for code-specific questions

### Debugging Tools
- Railway logs: `railway logs <service> -f`
- Railway shell: `railway run <command>`
- Browser DevTools: Network tab for API errors
- Database client: `psql` for direct queries

## Troubleshooting Workflow

1. **Identify the problem**
   - Frontend down? Check `railway logs frontend`
   - API failing? Check `railway logs backend`
   - Database issue? Check `railway logs postgres`

2. **Find documentation**
   - Search this folder for your issue
   - Check `DEPLOY.md` Troubleshooting section
   - Review error messages in logs

3. **Fix locally if possible**
   - Reproduce issue locally
   - Fix code and test
   - Push to GitHub (triggers redeploy)

4. **If urgent**
   - Rollback to previous version (git revert)
   - Or pause services in Railway dashboard
   - Investigate root cause

## Next Steps

1. Read `DEPLOY.md` in the root directory
2. Use `deployment-checklist.md` to plan deployment
3. Follow step-by-step instructions
4. Come back to these docs as reference

Good luck! 🚀

---

**Questions?** Check the relevant guide file above or reach out to Railway support.
