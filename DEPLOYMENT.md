# AILeash Deployment Guide

## Local Development

```bash
python3 main.py
```

Server starts on http://localhost:8080

## Docker

```bash
# Build
docker build -t aileash:3.0.0 .

# Run
docker run -p 8080:8080 \
  -v $(pwd)/aileash.db:/app/aileash.db \
  -e STRIPE_SECRET="sk_live_..." \
  aileash:3.0.0
```

## Railway

1. Install Railway CLI: `npm i -g @railway/cli`
2. Login: `railway login`
3. Link project: `railway link` (select repo)
4. Set variables in Railway dashboard:
   ```
   PORT=8080
   STRIPE_SECRET=sk_live_...
   STRIPE_PRICE_ID=price_...
   ```
5. Deploy: `railway up`

## Render

1. Create new Web Service
2. Connect GitHub repo
3. Set build command: `pip install -r requirements.txt` (no-op, but required)
4. Set start command: `python3 main.py`
5. Set environment:
   ```
   PORT=10000
   STRIPE_SECRET=sk_live_...
   STRIPE_PRICE_ID=price_...
   ```
6. Deploy

## Fly.io

```bash
# Install flyctl
curl https://fly.io/install.sh | sh

# Login
flyctl auth login

# Create app
flyctl launch

# Set secrets
flyctl secrets set STRIPE_SECRET=sk_live_...
flyctl secrets set STRIPE_PRICE_ID=price_...

# Deploy
flyctl deploy
```

## AWS Lambda (with Docker)

```dockerfile
FROM public.ecr.aws/lambda/python:3.11

COPY main.py ${LAMBDA_TASK_ROOT}
COPY landing.html ${LAMBDA_TASK_ROOT}

CMD ["main.handler"]
```

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `PORT` | 8080 | HTTP server port |
| `STRIPE_SECRET` | (empty) | Stripe API key for usage tracking |
| `STRIPE_PRICE_ID` | (empty) | Stripe price ID for metering |

## Production Checklist

- [ ] Set `STRIPE_SECRET` and `STRIPE_PRICE_ID`
- [ ] Enable HTTPS (reverse proxy or platform default)
- [ ] Restrict CORS in `send()` function
- [ ] Set up database backups (aileash.db)
- [ ] Monitor `/health` endpoint
- [ ] Enable request logging (remove `log_message` passthrough)
- [ ] Set up alerting on chain verification failures
- [ ] Use persistent volume for database
- [ ] Enable rate limiting on API endpoints
- [ ] Document regulatory compliance in your systems

## Database Persistence

The SQLite database (`aileash.db`) is created on first run. For cloud deployments:

**Railway/Render/Fly:** Mount volume at `/app/aileash.db`

**Lambda:** Use RDS + custom connector (see examples)

## Monitoring

```bash
# Check chain health
curl https://your-deployment.com/api/verify

# Check server status
curl https://your-deployment.com/health

# Monitor logs
railway logs  # Railway
flyctl logs   # Fly.io
```

## Scaling Notes

- SQLite supports ~100 concurrent connections
- For >10k decisions/second, migrate to PostgreSQL
- Thread pool handled by Python's HTTPServer (single-threaded by default)
- For high throughput, use nginx + gunicorn + multiple workers
