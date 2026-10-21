# Using Groq with Sequence Jobs

## Quick Start

1. **Sign up for Groq** (free tier available):
   - Go to https://console.groq.com
   - Create an account
   - Generate an API key in your settings

2. **Set environment variables**:
   ```bash
   export AI_PROVIDER=groq
   export GROQ_API_KEY=gsk_YOUR_KEY_HERE
   export AI_DAILY_BUDGET_USD=10  # adjust as needed
   ```

3. **Start the backend**:
   ```bash
   cd backend
   python manage.py serve
   ```

4. **Test it works**:
   - Upload a CV at http://localhost:3000/account
   - Browse to a job page
   - Click "Generate cover letter" or "Suggest CV improvements"
   - You should see AI-generated content (or an error if quota is exceeded)

## Groq Limits & Pricing

**Free tier**: 25 requests per minute
- Good for development and testing
- No credit card required
- Limited to small models (Mixtral, Llama)

**Paid tier**: $0.27 per 1 million tokens (input + output)
- No rate limits (subject to fair use)
- Upgrade in the Groq console

## Budget Controls

The `AI_DAILY_BUDGET_USD` setting enforces a soft limit:
- Set it to $10 for testing (covers ~37,000 tokens at Groq prices)
- Set it to $0 to disable paid AI calls (free tier only)
- The gateway logs all usage to `ai_usage_log` table and checks budget before each request

## Troubleshooting

**"AI is not configured"** → Check `GROQ_API_KEY` is set and non-empty.

**"provider error: 429"** → Free tier rate limit hit (25 req/min). Wait 60 seconds or upgrade to paid.

**"provider error: 401"** → Invalid API key. Regenerate it in the Groq console.

**"AI daily budget is zero or exhausted"** → Reduce budget or wait until tomorrow (budget resets daily at UTC midnight).

Check logs: `SELECT * FROM ai_usage_log WHERE at >= now() - interval '1 hour' ORDER BY at DESC;`

## Architecture

The provider is pluggable. If you want to switch to OpenAI, Claude, or another LLM, implement `AIProvider` in a new file under `backend/app/ai/providers/` and update `backend/app/__init__.py` to instantiate it.

See `backend/app/ai/provider.py` for the interface.
