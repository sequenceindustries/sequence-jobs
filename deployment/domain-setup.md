# Custom Domain Setup Guide

This guide walks through setting up a custom domain (e.g., `sequencejobs.co.za`) with Railway for Sequence Jobs.

## Prerequisites

- Domain registered (e.g., with GoDaddy, Namecheap, Route53, etc.)
- Access to your domain registrar's DNS management
- Railway project with backend and frontend services deployed
- SSL/TLS certificate (Railway provides free certificates)

## Step 1: Decide on Domain Structure

Choose one of these patterns:

### Pattern A: Single Domain with Path-Based Routing (Recommended for MVP)
```
Frontend: https://sequencejobs.co.za
API:      https://sequencejobs.co.za/api
```
- Simpler DNS setup (single A record)
- Easier CORS configuration
- Shared SSL certificate
- Single domain cost

**Setup**: Frontend serves on root, backend routes `/api/*` to backend service

### Pattern B: Subdomains
```
Frontend: https://www.sequencejobs.co.za
API:      https://api.sequencejobs.co.za
```
- Cleaner API endpoints
- Better for future microservices
- Requires multiple DNS records
- Potential CORS complexity

### Pattern C: Separate Domains
```
Frontend: https://sequencejobs.co.za
API:      https://api.sequencejobs.co.za
```
- Maximum flexibility
- Most CORS configuration needed
- Highest DNS complexity

## Step 2: Add Domain to Railway

### Via Railway Dashboard
1. Navigate to your project in Railway
2. Go to Settings → Domains
3. Click "Add Domain"
4. Choose type:
   - Custom Domain: point to your own domain
   - Railway Domain: get a free *.railway.app subdomain (for testing)
5. Enter your domain name: `sequencejobs.co.za`
6. Click "Add"

Railroad displays:
- **Name Server**: target DNS records (e.g., `x.railway.internal`)
- **Status**: "Not configured" until DNS propagates

### Via Railway CLI
```bash
railway project select
railway domain add sequencejobs.co.za
railway domain add www.sequencejobs.co.za
railway domain add api.sequencejobs.co.za
```

## Step 3: Configure DNS Records

### For Pattern A (Path-Based Routing)

Add one A record pointing to Railway's IP:

| Type | Name                    | Value              | TTL   |
|------|-------------------------|--------------------|-------|
| A    | sequencejobs.co.za      | Railway IP (given) | 3600  |
| CNAME| www                     | sequencejobs.co.za | 3600  |

### For Pattern B (Subdomain Routing)

Add A records for each subdomain:

| Type  | Name                    | Value              | TTL   |
|-------|-------------------------|--------------------|-------|
| A     | sequencejobs.co.za      | Railway IP (given) | 3600  |
| CNAME | www                     | sequencejobs.co.za | 3600  |
| A     | api                     | Railway IP (given) | 3600  |

**Note**: Some registrars require CNAME instead of A records. Railroad will guide you.

### For Pattern C (Separate Domains)

If using separate domains, add A records for each:

| Type | Name                    | Value              | TTL   |
|------|-------------------------|--------------------|-------|
| A    | yourapidomain.co.za     | Railway IP (given) | 3600  |

## Step 4: Check DNS Propagation

```bash
# Check A record
nslookup sequencejobs.co.za
dig sequencejobs.co.za A

# Check CNAME record
nslookup www.sequencejobs.co.za
dig www.sequencejobs.co.za CNAME

# Check nameservers
dig sequencejobs.co.za NS
```

Expected output shows Railway's infrastructure. Propagation takes 5 minutes to 24 hours.

## Step 5: Update Railway Domain Routing

After DNS propagates, configure which service handles which domain:

### In Railway Dashboard
1. Go to your project → Frontend service
2. Settings → Domains
3. Add domain: `sequencejobs.co.za`
4. Go to Backend service → Settings → Domains
5. For path-based routing, add `/api/*` rewrite rule
   - Or use separate domain: `api.sequencejobs.co.za`

### In railway.json
```json
{
  "services": {
    "frontend": {
      "domains": [
        {
          "name": "sequencejobs.co.za",
          "path": "/"
        },
        {
          "name": "www.sequencejobs.co.za",
          "path": "/"
        }
      ]
    },
    "backend": {
      "domains": [
        {
          "name": "api.sequencejobs.co.za",
          "path": "/"
        }
      ]
    }
  }
}
```

## Step 6: SSL/TLS Certificate

Railway automatically provisions free SSL certificates via Let's Encrypt:

- **Status**: Check in Railroad dashboard → Domains section
- **Auto-renewal**: Certificates auto-renew 30 days before expiry
- **Validation**: Railway handles ACME validation automatically

### Verify HTTPS

```bash
# Check SSL certificate
openssl s_client -connect sequencejobs.co.za:443 -servername sequencejobs.co.za

# Quick test
curl -I https://sequencejobs.co.za
# Should show: HTTP/1.1 200 OK
```

## Step 7: Configure Application

### Backend (flask)

Update app configuration to recognize your domain:

```python
# backend/app/__init__.py
app.config['ALLOWED_HOSTS'] = [
    'sequencejobs.co.za',
    'www.sequencejobs.co.za',
    'api.sequencejobs.co.za'
]

# CORS configuration
CORS(app, origins=[
    'https://sequencejobs.co.za',
    'https://www.sequencejobs.co.za'
])
```

Set environment variable:
```bash
API_URL=https://api.sequencejobs.co.za
# OR for path-based routing:
API_URL=https://sequencejobs.co.za/api
```

### Frontend (Next.js)

Update Next.js to use correct API URL:

```typescript
// frontend/.env.production
NEXT_PUBLIC_API_URL=https://api.sequencejobs.co.za
# OR for path-based routing:
NEXT_PUBLIC_API_URL=https://sequencejobs.co.za/api
```

Update API client:

```typescript
// frontend/lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.sequencejobs.co.za';

export async function fetchApi(endpoint: string, options?: RequestInit) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });
  return response.json();
}
```

## Step 8: Test Everything

```bash
# Test frontend
curl -I https://sequencejobs.co.za
curl -I https://www.sequencejobs.co.za

# Test API
curl -I https://api.sequencejobs.co.za/health
curl https://api.sequencejobs.co.za/jobs

# Test from frontend (browser console)
# Should successfully fetch from API
fetch('https://api.sequencejobs.co.za/jobs')
  .then(r => r.json())
  .then(data => console.log('Jobs:', data))

# Check SSL
openssl s_client -connect sequencejobs.co.za:443 -servername sequencejobs.co.za
# Should show: Verify return code: 0 (ok)
```

## Step 9: Security Headers

Add security headers to prevent vulnerabilities:

### In Backend (Flask)

```python
# backend/app/__init__.py
@app.after_request
def set_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response
```

### In Frontend (Next.js)

```typescript
// next.config.ts
export default {
  headers: async () => [
    {
      source: '/:path*',
      headers: [
        {
          key: 'Strict-Transport-Security',
          value: 'max-age=31536000; includeSubDomains'
        },
        {
          key: 'X-Content-Type-Options',
          value: 'nosniff'
        }
      ]
    }
  ]
}
```

## Step 10: DNS Monitoring

Monitor DNS health:

```bash
# Check all records
dig sequencejobs.co.za ANY

# Monitor propagation progress
# https://mxtoolbox.com/domain/sequencejobs.co.za

# Check nameserver delegation
dig @8.8.8.8 sequencejobs.co.za

# Long-term monitoring
# Set up alerts in your registrar dashboard
```

## Troubleshooting

### Domain not resolving
- Wait 24 hours for DNS propagation
- Clear local DNS cache: `sudo systemctl restart systemd-resolved`
- Check DNS records are correct in registrar
- Verify A record points to Railway IP

### SSL certificate not issuing
- Check domain is resolving to Railway IP
- Wait 5+ minutes for ACME validation
- Verify no firewalls blocking validation traffic
- Contact Railway support if persists

### Mixed content warnings
- Ensure all frontend requests use HTTPS
- Update all hardcoded HTTP URLs to HTTPS
- Check backend API_URL is HTTPS

### CORS errors
- Verify CORS headers in backend match frontend domain
- Check allowed origins in app config
- Use browser DevTools Network tab to see headers

### API endpoint not responding
- Check backend service is deployed and running
- Verify API_URL environment variable is set
- Check backend logs: `railway logs backend`
- Test API directly: `curl https://api.sequencejobs.co.za/health`

## Post-Launch

1. **Monitor SSL certificates** - Railway auto-renews, but verify expiry dates
2. **Track domain health** - Set up monitoring for uptime
3. **Update documentation** - Point team to new domain
4. **Update external links** - Blog, social media, etc.
5. **Set up email forwarding** - Optional: configure mail forwarding for domain

## Additional Resources

- [Railway Domains Documentation](https://docs.railway.app/guides/domains)
- [Let's Encrypt SSL](https://letsencrypt.org)
- [MXToolBox DNS Check](https://mxtoolbox.com)
- [SSL Labs Test](https://www.ssllabs.com/ssltest)
