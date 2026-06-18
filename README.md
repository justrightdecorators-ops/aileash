# AILeash

AILeash is a lightweight Python HTTP service providing real-time AI governance and child-safety decisioning (ALLOW / CHALLENGE / BLOCK) with a tamper-evident SHA-256 audit chain. It is implemented as a small threaded HTTP server (server.py) and stores persistent data in a local SQLite database by default.

This repository contains the full platform for evaluation and small deployments. For production readiness see the "Production & Enterprise" section.

## Features

- Real-time decisioning API: /api/govern (POST)
- Health and status: /api/health
- Audit chain verification: /api/verify-chain
- Signup, contact, and simple web pages for marketing and scanner UI
- Per-key and global rate limits, basic load tracking and graceful throttling

## Quick start (development)

Requirements:

- Python 3.10+ (recommended)
- git

Run locally:

1. Clone the repo

   git clone https://github.com/justrightdecorators-ops/aileash.git
   cd aileash

2. (Optional) Create a virtualenv

   python -m venv .venv
   source .venv/bin/activate

3. Start the server (defaults to port 8080):

   python -u server.py

4. Check health:

   curl http://localhost:8080/api/health

5. Test governance endpoint:

   curl -s -X POST http://localhost:8080/api/govern \
     -H "Content-Type: application/json" \
     -d '{"user_id":"u1","action":"test","amount":0,"country":"UK","device_id":"d1","anomaly":0,"device_risk":0}'

## Docker (recommended for consistent environments)

A simple Dockerfile is included (or can be added on request). Typical steps:

  docker build -t aileash:latest .
  docker run -p 8080:8080 -e PORT=8080 --env-file .env aileash:latest

## Environment variables

The server reads these environment variables (defaults shown in parentheses):

- PORT (8080) — TCP port the server listens on
- HOST (https://sebbi.pro) — canonical host used in emails/links
- STRIPE_SECRET ("") — Stripe API secret (required for billing/checkout)
- BREVO_API_KEY ("") — Brevo/Sendinblue API key for outgoing emails

Production deployments should set STRIPE_SECRET and BREVO_API_KEY only in secret stores or CI/CD environment variables (do not commit secrets).

## Persistence

By default the server uses a local SQLite file named `aileash.db`. For single-instance testing this is fine. For production use, replace SQLite with a managed Postgres instance (see "Production & Enterprise" below).

## Endpoints (important)

- GET /api/health — service health and rps
- POST /api/govern — main decision endpoint (JSON body, required fields listed below)
- POST /signup or /api/keys — create API key
- POST /contact — contact form
- GET /api/verify-chain — verify tamper-evident audit chain integrity

Required fields for /api/govern:

- user_id, action, amount, country, device_id, anomaly, device_risk

Responses are JSON and include a decision (ALLOW / CHALLENGE / BLOCK) plus an audit_hash.

## Security & operational notes

See SECURITY.md for responsible disclosure, secrets handling, and hardening recommendations. Key points:

- Do not store secrets in repository files or environment files committed to VCS.
- Use HTTPS/TLS in front of the server in production (reverse proxy, load balancer).
- Replace SQLite with Postgres for multi-instance deployments.
- Run the app under a process manager (systemd, or container with an orchestrator) or with Gunicorn when refactored to a WSGI app.

## Production & Enterprise (recommended)

For enterprise use I recommend:

- Refactor server into a WSGI app (Flask) and serve with Gunicorn using gthread or gthread+workers.
- Use a managed Postgres database and set DATABASE_URL environment variable.
- Add CI to build, lint, run unit tests, and build a container image.
- Add monitoring (Prometheus metrics), structured JSON logging, and alerting.
- Add automatic backups for the DB and secure secret rotation.

I can implement the above (Dockerfile, Gunicorn/Werkzeug wrapper, Postgres migration, CI) — tell me which items to prioritize.

## License

This repository includes a LICENCE file. Check the license before commercial use.

## Contact

For questions, or to report issues: justin@monopcontent.com
