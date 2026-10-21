# Email Provider Setup for Sequence Jobs

This guide walks you through setting up job alert emails for Sequence Jobs. The system supports three free email providers optimized for different needs.

## Quick Start

Choose your provider, create an account, get your API key, and set three environment variables. No emails are sent until a provider is configured.

## Recommended: Resend (Best for South Africa)

**Why Resend?**
- 100 emails/day free tier (perfect for ~3,300 alerts/month)
- Modern, developer-friendly API
- Excellent documentation and support
- No credit card required for free tier
- Fast email delivery

**Setup:**

1. Sign up at https://resend.com (no credit card needed for free tier)
2. Go to **API Keys** (https://resend.com/api-keys)
3. Create a new API key and copy it
4. Verify your sender email domain:
   - In the Resend dashboard, go to **Domains**
   - Add your domain (e.g., `noreply.example.com`)
   - Follow the DNS verification steps
   - Or use Resend's test domain for development

5. Set environment variables:
   ```bash
   export EMAIL_PROVIDER=resend
   export EMAIL_API_KEY=re_xxxxxxxxxxxxx
   export EMAIL_FROM_ADDRESS=noreply@example.com  # Must match verified domain
   ```

6. Test the setup:
   ```bash
   cd backend
   python manage.py test-email your-email@example.com
   ```

## Alternative: SendGrid

**Why SendGrid?**
- 100 emails/day free tier
- Excellent reputation and delivery
- Established, reliable infrastructure
- Detailed email analytics

**Setup:**

1. Sign up at https://sendgrid.com (no credit card required)
2. Go to **Settings → API Keys** (https://app.sendgrid.com/settings/api_keys)
3. Create a new API key with "Mail Send" permission
4. Verify your sender email address:
   - Go to **Settings → Sender Authentication**
   - Add your sender email
   - Confirm verification email
   - Or add a domain for higher sending limits

5. Set environment variables:
   ```bash
   export EMAIL_PROVIDER=sendgrid
   export EMAIL_API_KEY=SG.xxxxxxxxxxxxx
   export EMAIL_FROM_ADDRESS=noreply@example.com  # Must be verified
   ```

6. Test the setup:
   ```bash
   cd backend
   python manage.py test-email your-email@example.com
   ```

## Alternative: Mailgun

**Why Mailgun?**
- 5,000 emails/month free tier (most generous)
- ~166 emails/day average
- Powerful API with detailed logging
- Great if you expect high alert volume

**Setup:**

1. Sign up at https://mailgun.com (no credit card required)
2. Go to **API** (https://app.mailgun.com/app/account/security/api_keys)
3. Copy your API key
4. Create a new domain:
   - Go to **Domains**
   - Add a new domain (e.g., `mail.example.com`)
   - Set up DNS records (MX and CNAME)
   - Wait for verification (usually 5-10 minutes)
   - Or use the sandbox domain for testing (limits to authorized recipients only)

5. Set environment variables:
   ```bash
   export EMAIL_PROVIDER=mailgun
   export EMAIL_API_KEY=key-xxxxxxxxxxxxx
   export EMAIL_FROM_ADDRESS=noreply@mail.example.com
   export EMAIL_MAILGUN_DOMAIN=mail.example.com
   ```

6. Test the setup:
   ```bash
   cd backend
   python manage.py test-email your-email@example.com
   ```

## Using South African Domain

If you have a `.co.za` domain:

1. For **Resend**: Add your `.co.za` domain in the Resend dashboard and verify via DNS
2. For **SendGrid**: Same process via the Sender Authentication page
3. For **Mailgun**: Create a domain entry with your `.co.za` domain and complete DNS setup

All providers support international domains. DNS verification typically takes 5-15 minutes.

## Development: Testing Without Real Emails

To test the alert system without sending real emails:

```bash
# Just run alerts without processing the outbox
cd backend
python manage.py run-alerts
# Emails will be queued as "not_configured"
```

To inspect the email queue:

```python
from app.db import connect
from app.config import Config

with connect(Config.DATABASE_URL) as conn:
    rows = conn.execute(
        "SELECT id, status, subject, attempts, error FROM email_outbox "
        "ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        print(f"[{r['status']}] {r['subject']} (attempt {r['attempts']})")
        if r['error']:
            print(f"  Error: {r['error']}")
```

## Integration with Alert System

The email system integrates seamlessly with the alert runner:

```bash
# Run alerts AND send queued emails
cd backend
EMAIL_PROVIDER=resend \
EMAIL_API_KEY=re_xxxxx \
EMAIL_FROM_ADDRESS=noreply@example.com \
python manage.py run-alerts
```

This will:
1. Find users with alerts due to run
2. Search for new matching jobs
3. Create notifications (no duplicates per alert+job)
4. Queue emails for new matches
5. Immediately send queued emails

Each email attempt is logged with:
- Timestamp
- Provider response
- Delivery status (sent/failed/retry)
- Error details if any

## Configuration Details

All email configuration via environment variables:

| Variable | Required | Example | Notes |
|----------|----------|---------|-------|
| `EMAIL_PROVIDER` | Yes | `resend` | `none` to disable |
| `EMAIL_API_KEY` | If not "none" | `re_xxxxx` | Keep secret! |
| `EMAIL_FROM_ADDRESS` | If not "none" | `noreply@example.com` | Must be verified with provider |
| `EMAIL_MAILGUN_DOMAIN` | If Mailgun | `mg.example.com` | Mailgun domain only |

## Troubleshooting

### Test Email Fails with "Invalid API key"
- Check your API key is correctly copied (no spaces, full key)
- Verify the provider hasn't revoked the key
- Ensure key has the right permissions (Mail Send for SendGrid, Emails for Resend)

### "Sender email not verified"
- For Resend: Verify domain in dashboard or use Resend's test domain
- For SendGrid: Verify sender email in "Sender Authentication"
- For Mailgun: Use sandbox domain or verify your domain via DNS

### Emails stuck in "queued" status
- Check `EMAIL_PROVIDER` is set correctly
- Run `python manage.py test-email test@example.com` to verify setup
- Check database for error messages: `SELECT error FROM email_outbox WHERE status='failed' LIMIT 5`

### High email bounce/spam rates
- Ensure your sender domain/email is legitimate
- For SendGrid/Resend: Set up DKIM/SPF via domain verification
- For Mailgun: Configure CNAME records for domain
- Include clear unsubscribe info (alert management in user account)

## Production Checklist

Before deploying to production:

- [ ] Created account with chosen provider (no credit card required for free tier)
- [ ] Generated API key with appropriate permissions
- [ ] Verified sender email/domain
- [ ] Tested with `python manage.py test-email your-test-email@example.com`
- [ ] Added environment variables to production `.env` or secrets manager
- [ ] Set `APP_ENV=production` and other production config
- [ ] Confirmed alert runner is scheduled (cron/task scheduler)
- [ ] Monitored email delivery for first week

## Email Limits and Monitoring

Monitor your usage in the provider dashboard:

- **Resend**: https://resend.com/dashboards/overview (shows daily totals)
- **SendGrid**: https://app.sendgrid.com/email_activity (shows all emails sent)
- **Mailgun**: https://app.mailgun.com/app/logs (detailed delivery logs)

### Free Tier Limits
- **Resend**: 100 emails/day = ~3,000/month (perfect for 100 daily active alerts)
- **SendGrid**: 100 emails/day = ~3,000/month
- **Mailgun**: 5,000 emails/month = ~166/day (most headroom)

If you exceed limits, upgrade to paid tier or add a second domain.

## Code Integration

The email system is provider-agnostic. To send an email in code:

```python
from app.services.email import get_email_sender

# Get configured sender (raises if not configured)
sender = get_email_sender()

# Send email
sender.send(
    to="user@example.com",
    subject="Your alert matches",
    body="Check out these jobs matching your alert..."
)
```

Error handling:

```python
from app.services.email import get_email_sender, NotConfigured, EmailError

try:
    sender = get_email_sender()
    sender.send(to, subject, body)
except NotConfigured:
    print("Email provider not configured")
except EmailError as e:
    print(f"Failed to send: {e}")
```

## Architecture

Email provider adapters implement a common interface (`EmailSender`):

- `ResendSender` - Resend.com API
- `SendGridSender` - SendGrid API
- `MailgunSender` - Mailgun API
- `NullSender` - No-op (default when not configured)

Each adapter:
- Handles API authentication (headers, basic auth)
- Formats payloads for the provider's API
- Catches and translates errors
- Runs in ~200-500ms (actual network latency)

Tests in `backend/tests/test_email_providers.py` cover:
- Success cases for each provider
- Network and API errors
- Configuration validation
- Factory function (get_email_sender)

## Support

For issues with:
- **Resend**: https://resend.com/support
- **SendGrid**: https://support.sendgrid.com
- **Mailgun**: https://help.mailgun.com

For issues with Sequence Jobs email integration, check the logs and verify your configuration with `python manage.py test-email`.
