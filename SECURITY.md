# SECURITY.md

This repository takes security and responsible disclosure seriously. This SECURITY.md document describes how to report vulnerabilities, what we will do in response, and security best practices for deploying AILeash in production.

## Reporting security issues

If you believe you have found a security vulnerability in AILeash, please report it privately to the project maintainers.

Preferred contact:

- Email: security@monopcontent.com (primary)
- If email is unavailable: justin@monopcontent.com

When reporting a vulnerability, please include:

- A concise description of the problem and impact
- Reproduction steps, PoC, or a minimal reproducible example
- Affected versions and environment details (OS, Python version, configuration)
- Any suggested mitigation or remediation if known

Do not publish the issue publicly until we have had a reasonable time to respond and, where applicable, provide a fix.

## Response policy

- Acknowledgement: within 48 hours of receiving a report.
- Initial triage: within 5 business days.
- Patch / remediation: timeline depends on severity; high-severity fixes will be prioritised and coordinated with the reporter.
- Coordination: We will coordinate disclosure timing with the reporter for CVE assignment where applicable.

## Supported versions

- This repository's main branch is considered the active line for reporting. If you are using a tagged/released version, please specify the tag.

## Severity and CVE

If a report qualifies as a security vulnerability, we will: investigate, assign a severity, and — where appropriate — create a CVE and public advisory after a coordinated disclosure window.

## Security best practices for deployments

These recommendations help harden deployments of AILeash in production environments.

1. Secrets management
   - Never store STRIPE_SECRET, BREVO_API_KEY or any production credentials in git or in files checked into VCS.
   - Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, Railway/Railway Envs, Heroku config vars) and provide credentials via environment variables at runtime.
   - Rotate API keys on a schedule and whenever a developer leaves or credentials are suspected to be compromised.

2. Use TLS / HTTPS
   - Deploy behind a TLS-terminating reverse proxy (NGINX, Traefik, load balancer) or use a platform-managed TLS certificate.
   - Redirect HTTP to HTTPS and use HSTS where appropriate.

3. Database
   - For production, use a managed Postgres (or equivalent) rather than SQLite.
   - Ensure the DB user has only the privileges it needs (least privilege).
   - Enable automated backups and test restores periodically.

4. Process & application server
   - Run under a process manager or container orchestrator (systemd, Docker + orchestrator, or Gunicorn for WSGI apps).
   - Use multiple worker processes/threads for availability and resilience.

5. Logging, monitoring & alerting
   - Emit structured logs to stdout/stderr and aggregate them with a logging system (LogDNA, Papertrail, ELK, CloudWatch).
   - Instrument basic operational metrics: request rate, error rate, latency, DB connection health, and disk/DB size.
   - Add alerts for high error rate, high RPS, or DB failures.

6. Rate limiting & abuse
   - The app includes per-key and global rate-limiting; ensure these values are appropriate for your deployment and adjust as needed.
   - Implement request logging and automated throttling thresholds to protect availability.

7. Dependency & vulnerability scanning
   - Regularly run dependency vulnerability scans (e.g., `pip-audit`, `safety`, GitHub Dependabot) and apply updates.
   - Pin direct dependencies and use automated tooling to update safely.

8. Input validation & sanitisation
   - Validate all incoming JSON and guard against unexpected types and sizes.
   - Limit request body size (the server already reads Content-Length; ensure your proxy enforces size limits too).

9. Rate-limit sensitive endpoints
   - Endpoints like /signup and /create-checkout are potential abuse vectors; ensure they are monitored and rate-limited.

10. Email & third-party integrations
   - Outgoing email (BREVO_API_KEY) and Stripe calls should be made only over HTTPS.
   - Treat third-party API errors as untrusted input and handle failures gracefully.

## Known limitations

- SQLite persistence is not suitable for multi-instance, horizontally scaled deployments.
- The current server is a threaded HTTPServer — suitable for modest loads but not a production multi-process setup. Consider a WSGI refactor + Gunicorn for production.

## Recommended tests and checks before deployment

- Run unit and integration tests (I can help add these).
- Run `pip-audit` or `safety` on your environment and fix any high/critical findings.
- Perform a basic penetration test on deployed staging instance (authentication, rate-limiting, input validation checks).

## Disclosure & acknowledgement

If you report a vulnerability and wish to be acknowledged publicly, we will list your name (or handle) in the repository's SECURITY.md or a public advisory unless you request anonymity.

---

If you'd like, I can also:
- Add Dependabot configuration to this repository to automatically scan/raise PRs for vulnerable dependencies.
- Add a simple GitHub Actions workflow to run `pip-audit` on pushes and create PRs for fixes.
- Add a CONTRIBUTING.md with secure development practices.

Contact: security@monopcontent.com
