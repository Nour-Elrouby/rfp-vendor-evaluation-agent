# Production Deployment

ProcureLens can be deployed as a secured single-tenant MVP. A commercial
multi-tenant service still requires an identity provider, tenant-isolated
storage, centralized observability, backups, and an external security review.

## Required production configuration

Set these environment variables in the hosting platform, not in Git:

```dotenv
APP_ENV=production
API_AUTH_TOKEN=generate-at-least-32-random-characters
ALLOWED_HOSTS=procurelens.example.com
GROQ_API_KEY=your-current-groq-key
GROQ_MODEL=llama-3.3-70b-versatile
AUDIT_LOG_FILE=/app/data/audit_log.jsonl
```

Optional operating limits:

```dotenv
ENABLE_DOCS=false
MAX_UPLOAD_BYTES=15728640
MAX_REQUEST_BYTES=16728640
MAX_CRITERIA_CHARS=20000
MAX_EXTRACTED_CHARS=1000000
MAX_CHAT_RFP_CHARS=200000
MAX_QUESTION_CHARS=2000
MAX_RANK_VENDORS=500
MAX_AUDIT_PAGE_SIZE=200
RATE_LIMIT_PER_MINUTE=60
MAX_CONCURRENT_EVALUATIONS=2
LOG_LEVEL=INFO
```

Generate a token with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Container

```bash
docker build -t procurelens .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v procurelens-data:/app/data \
  procurelens
```

Terminate TLS at a managed load balancer or reverse proxy. Keep one application
worker per container because each worker loads a separate embedding model.
Scale by adding containers after moving rate limiting and audit storage to
shared services.

## Operational requirements

- Persist and back up `/app/data`.
- Restrict access to audit records; they include criteria and evidence excerpts.
- Rotate `API_AUTH_TOKEN` and `GROQ_API_KEY`.
- Monitor `/health/live` and `/health/ready`.
- Set request limits again at the load balancer.
- Run dependency and container vulnerability scans in CI.
- Establish retention/deletion rules for procurement data.
- Complete legal review, accessibility testing, penetration testing, and
  scoring validation before selling the service.
