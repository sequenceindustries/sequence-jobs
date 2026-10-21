# GitHub Repository Setup for Deployment

This guide prepares your Sequence Jobs repository for deployment automation with Railway.

## Step 1: Create GitHub Repository

### Option A: New Repository (Recommended)
```bash
# Create a new private repository on GitHub
# Visit: https://github.com/new

# Repository Name: sequence-jobs (or your preference)
# Description: AI-powered job aggregator for South Africa
# Visibility: Private (unless you want public source)
# Initialize with: None (we'll push existing code)
```

### Option B: Existing Repository
If you already have a repo, ensure:
- Main branch is `main` (not `master`)
- `.gitignore` excludes `.env`, `node_modules`, `.venv`, `.next`

## Step 2: Push Code to GitHub

```bash
cd /path/to/sequence-jobs

# Initialize git (if not already done)
git init

# Add remote
git remote add origin https://github.com/YOUR_USERNAME/sequence-jobs.git

# Verify structure before pushing
git status

# Stage everything except ignored files
git add -A

# Verify what's staged
git diff --cached --name-only | head -20

# Create initial commit
git commit -m "Initial commit: Sequence Jobs backend and frontend

- Backend: Flask API with PostgreSQL, AI integration, job aggregation
- Frontend: Next.js with React, job search and recommendations
- Infrastructure: Docker support, environment configuration
- AI: Groq provider integration for job recommendations

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# Push to GitHub
git branch -M main
git push -u origin main
```

## Step 3: Repository Structure Verification

Ensure your repository has this structure:

```
sequence-jobs/
├── .github/
│   └── workflows/
│       └── deploy.yml          # Automated deployment (optional)
├── backend/
│   ├── Dockerfile              # ✅ Created
│   ├── requirements.txt         # ✅ Exists
│   ├── manage.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── api_admin.py
│   │   ├── api_ai.py
│   │   ├── api_user.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/
│   │   ├── services/
│   │   ├── connectors/
│   │   └── ai/
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── Dockerfile              # ✅ Created
│   ├── package.json
│   ├── next.config.ts
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── public/
├── deployment/                 # ✅ Created
│   ├── deploy.md              # ✅ Created
│   ├── domain-setup.md        # ✅ Created
│   ├── environment-variables.md # ✅ Created
│   └── deployment-checklist.md # ✅ Created
├── .railway/
│   └── config.json            # ✅ Created
├── railway.toml               # ✅ Created
├── .gitignore
├── README.md
└── docs/
    └── sources.md
```

## Step 4: Update .gitignore

Ensure `.gitignore` prevents committing sensitive files:

```bash
cat > /path/to/sequence-jobs/.gitignore << 'EOF'
# Environment variables
.env
.env.local
.env.*.local
.env.production

# Virtual environments
.venv/
venv/
env/

# Node modules
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Next.js
.next/
out/
dist/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Testing
.coverage
.pytest_cache/
coverage/

# Secrets
secrets/
*.key
*.pem
.ssh/

# Build artifacts
*.tar.gz
*.zip
EOF
```

## Step 5: Create GitHub Secrets for Railway

GitHub Secrets protect sensitive values used during deployment:

```bash
# Via GitHub web UI:
# 1. Go to Settings → Secrets and variables → Actions
# 2. Click "New repository secret"
# 3. Add each secret:

RAILWAY_TOKEN=<your-railway-api-token>
GROQ_API_KEY=<your-groq-api-key>
POSTGRES_PASSWORD=<strong-random-password>
SECRET_KEY=<python-secrets-hex-32>
```

### Get Railway API Token
```bash
# Via Railway CLI
railway login
railway token

# Copy the token and add to GitHub Secrets as RAILWAY_TOKEN
```

### Generate Passwords
```bash
# PostgreSQL password
openssl rand -hex 32

# Flask SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Step 6: Create Deployment Workflow (Optional)

Create GitHub Actions workflow to auto-deploy on push:

```yaml
# .github/workflows/deploy.yml
name: Deploy to Railway

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Railway
        run: |
          npm install -g @railway/cli
          railway up \
            --service backend \
            --service frontend
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          SECRET_KEY: ${{ secrets.SECRET_KEY }}
```

## Step 7: Connect GitHub to Railway

### Via Railway Dashboard
1. Go to your Railway project
2. Settings → Integrations
3. Connect GitHub account
4. Select `sequence-jobs` repository
5. Configure auto-deploy:
   - Trigger: "Push to main"
   - Services: backend, frontend
   - Auto-redeploy: enabled

### Benefits
- Automatic deployments on every push to `main`
- Preview deployments for pull requests (optional)
- Deployment status visible in GitHub

## Step 8: Branch Strategy

Set up a safe deployment strategy:

### Main Branch (Production)
```bash
# Protect main branch
# GitHub Settings → Branches → Branch protection rules

Rule name: main
✅ Require a pull request before merging
✅ Require status checks to pass before merging
✅ Require branches to be up to date before merging
✅ Require code reviews (at least 1)
✅ Dismiss stale pull requests
```

### Development Branch
```bash
# For ongoing development
git checkout -b develop
git push -u origin develop

# Create feature branches from develop
git checkout -b feature/new-feature
# ... work on feature ...
git push -u origin feature/new-feature

# Create pull request: feature/new-feature → develop
# After review and tests pass: merge to develop
# After testing on staging: create PR develop → main
```

## Step 9: Commit Hygiene

Ensure clean commit history for deployments:

### Before Committing
```bash
# Check what will be staged
git status

# Review changes
git diff

# Stage selectively
git add backend/app/api.py
git add frontend/components/JobCard.tsx

# Never use git add -A in production code
```

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

Closes #<issue-number>

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`

Examples:
```bash
git commit -m "feat(jobs): add job matching algorithm

- Implement semantic similarity matching
- Add unit tests for match scoring
- Update API response format

Closes #42

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

git commit -m "fix(api): handle missing job descriptions

- Return empty string instead of null
- Update frontend null checks
- Add validation test

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

## Step 10: Deployment Verification

After pushing to GitHub:

```bash
# Check deploy status
git log --oneline -5

# View on GitHub
# https://github.com/YOUR_USERNAME/sequence-jobs/commits/main

# Check Railway deployment
# https://railway.app/project/YOUR_PROJECT_ID

# Check workflow runs (if using GitHub Actions)
# https://github.com/YOUR_USERNAME/sequence-jobs/actions
```

## Security Checklist

- [ ] Repository is Private (or access restricted)
- [ ] Secrets are in GitHub Secrets (not .env files)
- [ ] .gitignore includes .env, node_modules, .venv
- [ ] Main branch requires PR reviews
- [ ] Railway token is stored as GitHub Secret
- [ ] Database password is strong (32+ chars)
- [ ] No API keys in code or commit history
- [ ] .env.example doesn't contain real values
- [ ] SSH keys are not in repository
- [ ] Sensitive docs are not committed

## Accessing Repository Later

```bash
# Clone for the first time
git clone https://github.com/YOUR_USERNAME/sequence-jobs.git
cd sequence-jobs

# Pull latest changes
git pull origin main

# Check status
git status

# View recent commits
git log --oneline -10
```

## Next Steps

1. ✅ Push code to GitHub
2. ✅ Add GitHub Secrets for deployment
3. ✅ Connect GitHub to Railway
4. ✅ Test auto-deploy workflow
5. → See `deploy.md` for deployment instructions
